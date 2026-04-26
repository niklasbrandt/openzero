# Federated Memory With Selective Sharing

> Architectural plan for multi-instance openZero memory federation over Tailscale.
> Status: DRAFT | Author: conductor | Created: 2026-04-26
> Foundation for: Z-to-Z protocol (#9), digital twin (#11), predictive orchestration (#10).

---

## 1. Problem Statement

openZero today assumes one Z per operator. In reality a person has multiple operational contexts (work, family, side-business, household) that should not share the same Qdrant collection, Planka instance, or personal context files. But they should not be fully isolated either:

- Work-Z needs to know "blocked Tuesday evening" without knowing why (family dinner).
- Family-Z needs the household shopping list without seeing the business pipeline.
- A partner instance may want shared calendar availability and shared boards (groceries, holidays) but nothing else.

Today the only path is manual copy. The objective is to make selective sharing a first-class primitive.

---

## 2. Design Principles

1. Sovereignty by default. No data leaves an instance unless an explicit, scoped share contract authorises it.
2. Pull, not push. Peers request scoped views; the source instance evaluates the contract and returns a redacted slice. No background replication of raw memories.
3. Scopes, not collections. Sharing is governed by tag and scope predicates, not by exposing whole stores.
4. Auditable. Every cross-instance read is logged on both sides with the contract id that authorised it.
5. Revocable instantly. Revoking a contract immediately invalidates derived caches on the consumer side.
6. Mesh-trust. Authentication piggybacks on Tailscale identity (peer node key + Tailnet ACLs). No new PKI.
7. Additive only. Single-instance openZero is unchanged; the federation layer is opt-in behind a feature flag.

---

## 3. Architecture Overview

```
        Instance A (work-Z)                        Instance B (personal-Z)
   +-----------------------------+            +-----------------------------+
   | FastAPI                     |            | FastAPI                     |
   |  /api/federation/*          |<---mTLS--->|  /api/federation/*          |
   |                             | Tailscale  |                             |
   | ShareContract Registry      |            | ShareContract Registry      |
   | ScopeEvaluator              |            | ScopeEvaluator              |
   | FederatedMemoryClient       |            | FederatedMemoryClient       |
   | FederatedAvailabilityClient |            | FederatedAvailabilityClient |
   | Audit Log                   |            | Audit Log                   |
   +-------------+---------------+            +-------------+---------------+
                 |                                          |
           Local Qdrant                                Local Qdrant
           Local Planka                                Local Planka
           Local Postgres                              Local Postgres
```

No central server. Each instance is both producer (responds to scoped reads) and consumer (queries other instances when a memory search yields no local hit and a relevant contract exists).

---

## 4. Core Concepts

### 4.1 Scope

A scope is a stable string namespace attached to memory points, Planka boards, and calendar events.

```
scope = "work" | "family" | "household" | "partner" | "<custom>"
```

Existing memory points and boards get `scope="default"` on migration -- shareable with no peer (fully private). Operators tag explicitly to opt in to sharing.

### 4.2 ShareContract

The only thing that authorises a cross-instance read. Stored in Postgres on both producer and consumer sides.

```python
@dataclass
class ShareContract:
	id: str                          # uuid
	producer_node: str               # tailscale node name of the source
	consumer_node: str               # tailscale node name of the requester
	resource: Literal[
		"memory", "calendar_availability",
		"planka_board", "personal_fact",
	]
	scope_predicate: ScopePredicate
	redactions: list[str]            # field paths to strip before sending
	read_only: bool = True           # v1: writes never federated
	expires_at: datetime | None
	created_at: datetime
	revoked_at: datetime | None
	signature: str                   # producer-side HMAC over contract body
```

`ScopePredicate` is structured, never raw SQL or free-text:

```python
@dataclass
class ScopePredicate:
	scopes_in: list[str]
	tags_any: list[str] = []
	tags_none: list[str] = []
	max_results_per_query: int = 20
	max_age_days: int | None = None
```

Contracts are pairwise. Defining a contract is an explicit operator action, not LLM-driven.

### 4.3 Redactions

Each resource type has a fixed redaction allowlist. For example, `calendar_availability` always strips: `title`, `attendees`, `location`, `description`, `notes`, `attachments`. Only opaque busy/free intervals plus scope tag remain. Redactions are enforced server-side; consumers never see the unredacted form.

### 4.4 Federation Identity

- The producer accepts requests only from Tailnet-internal IPs in the CGNAT range.
- The producer cross-checks the requester's Tailscale node name against the contract's `consumer_node`.
- Contract requests carry a producer-issued bearer token. Loss of the token invalidates only that contract.

No new public CA or key rotation pipeline. The trust root is the Tailnet itself.

---

## 5. New API Surface

All routes under `/api/federation/`, all require Tailscale-internal source plus bearer token, all rate-limited per peer.

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/contracts` | List contracts where this node is producer or consumer |
| `POST` | `/contracts` | Create a new contract (operator only, dashboard) |
| `DELETE` | `/contracts/{id}` | Revoke (immediate) |
| `POST` | `/memory/search` | Federated memory query under a contract id |
| `POST` | `/calendar/availability` | Free/busy slots under a contract id |
| `POST` | `/planka/board` | Read scoped board snapshot (read-only) |
| `GET` | `/audit` | Cross-instance access log for this node |

`POST /memory/search` request body:

```json
{
	"contract_id": "uuid",
	"query": "shopping list for Saturday",
	"top_k": 5
}
```

Producer sequence:

1. Load the contract; verify active, not expired, belongs to the requesting peer.
2. Run the Qdrant search with a hard pre-filter matching `scope_predicate`.
3. Cap results at `max_results_per_query`.
4. Strip redacted fields.
5. Log the read with contract id, query hash (SHA-256), and result count bucket.
6. Return surviving points.

The query string is logged as a hash, never plaintext. Result counts are bucketed (`0`, `1-5`, `6-20`) to avoid exact-match probing.

---

## 6. Data Model Changes

### 6.1 Qdrant payload extension

Add to every memory point:

```
scope: str          # default "default"
share_tags: list[str]
```

Existing points get defaults via a one-shot migration (`scripts/migrate_qdrant_scopes.py`). No vector recomputation.

### 6.2 Planka

Add a `scope` custom property per board (Planka v6 supports board metadata). Boards default to `scope="default"`. Federation only reads boards whose scope matches the contract.

### 6.3 Postgres

Two new tables:

```
share_contracts(
	id uuid pk, producer_node text, consumer_node text,
	resource text, scope_predicate jsonb, redactions jsonb,
	read_only bool, expires_at timestamptz,
	created_at timestamptz, revoked_at timestamptz,
	bearer_token_hash text, signature text
)

federation_audit(
	id bigserial pk, ts timestamptz default now(),
	direction text check (direction in ('inbound','outbound')),
	contract_id uuid, peer_node text, resource text,
	query_hash text, result_count int, status text, latency_ms int
)
```

Both tables are created by an Alembic migration gated behind `FEDERATION_ENABLED=true`.

### 6.4 Personal context

Add a `scope:` frontmatter key to fragments inside `personal/*.md`. The personal-context loader honours scope when injecting into prompts. Fragments without scope are treated as `default`.

---

## 7. Backend Module Layout

```
src/backend/app/services/federation/
	__init__.py            # init_federation(), feature flag gate
	contracts.py           # ShareContract CRUD + signing
	predicates.py          # ScopePredicate evaluation
	identity.py            # Tailscale peer resolution + token verification
	redaction.py           # per-resource redaction allowlists
	audit.py               # federation_audit read/write
	client.py              # FederatedMemoryClient, FederatedAvailabilityClient
	server.py              # request handlers backing /api/federation/*

src/backend/app/api/
	federation.py          # FastAPI router

tests/
	test_federation_security.py
	test_federation_predicates.py
	test_federation_redaction.py
```

Federation never imports from any crew or LLM module. It is a pure data-plane layer.

---

## 8. Consumer-Side Integration

### 8.1 Memory search

`memory.semantic_search(query)` becomes scope-aware:

1. Run the local Qdrant search as today.
2. If `FEDERATION_ENABLED` and active inbound contracts plausibly match the query (cheap keyword/tag heuristic), fan out parallel `/memory/search` calls.
3. Merge results, tagging each remote point with `origin_node` and `contract_id`.
4. Re-rank by cosine distance; ties broken by local > remote.
5. Cap total federated points (`FEDERATION_MAX_REMOTE_POINTS`, default 5).

The LLM prompt template gains a clearly attributed line per remote group:

```
[Shared from work-z under contract <id>] ...
```

Attribution is non-negotiable.

### 8.2 Calendar availability

`/calendar/availability` queries fan out the same way. Remote results merge as opaque busy blocks with the producer node as the title (`"work busy"`, `"partner busy"`).

### 8.3 Crew context

Crews never call federation directly. They consume already-merged context via memory and calendar services. Crew code is unchanged.

---

## 9. Trust, Security, and Failure Modes

### 9.1 Threat model

- Compromised peer: contract is per-peer, revocable in one click; bearer token rotation regenerates the secret without changing the contract id.
- Malicious producer: remote text passes through untrusted-content sentinels; action tags stripped via `_MUTATING_TAG_RE`; remote points clearly attributed in prompt.
- Replay: every request includes a monotonic nonce; producer rejects repeats within token lifetime.
- Scope leakage via predicate confusion: predicate is a fixed DTO, evaluated server-side; consumers cannot inject custom predicates.
- Audit side channel: queries logged as hashes; result counts bucketed.

### 9.2 Failure modes

- Producer offline: 1.5 s timeout; consumer continues local-only and logs degraded read.
- Contract revoked mid-query: producer returns `410 Gone`; consumer drops result and clears cache.
- Token mismatch: `403 Forbidden` plus audit entry; no leakage.
- Tailscale link down: requests never start; consumer falls through to local-only.

### 9.3 Operator overrides

Two new `SENSITIVE_ACTIONS`, HITL-gated:

- `SHARE_SCOPE` -- create or update a contract (dashboard-only in v1; no LLM-initiated contracts).
- `REVOKE_SHARE` -- revoke a contract by id.

`MERGE_INSTANCE`, `EXPORT_ALL`, `WIPE_REMOTE` are explicitly not added. Federation is read-only in v1.

---

## 10. Dashboard

A new `FederationManager.ts` Shadow DOM component (matches existing conventions: `${ACCESSIBILITY_STYLES}`, `tr()`, HSLA tokens, no hardcoded English).

Sections:

1. This node's identity -- Tailscale node name, scopes in use, point counts per scope.
2. Outbound contracts (this node as producer) -- peer, resource, predicate summary, last access, revoke button.
3. Inbound contracts (this node as consumer) -- producer, resource, last successful read, manual refresh.
4. Create contract -- guided form: peer (from Tailscale device list), resource, scopes, tag filters, expiry.
5. Audit feed -- last 100 federation reads with status colour coding (`status-dot` class).

Contract creation is two-step confirm; the second step shows a plain-language summary of what the contract will permit.

All strings via `this.tr()` with new keys added to `_EN` and `_DE` first.

---

## 11. Configuration

`src/backend/app/config.py` additions:

```python
FEDERATION_ENABLED: bool = False
FEDERATION_NODE_NAME: str = ""                 # this instance's stable identifier
FEDERATION_MAX_REMOTE_POINTS: int = 5
FEDERATION_QUERY_TIMEOUT_MS: int = 1500
FEDERATION_AUDIT_RETENTION_DAYS: int = 90
```

Mirror in `.env.example` and `config.example.yaml`. `BUILD.md` gains a phase: "Federation -- linking multiple openZero instances", covering Tailscale ACL setup, generating `FEDERATION_NODE_NAME`, and the dashboard contract-creation walk-through.

---

## 12. Phased Implementation

### Phase F0 -- Foundations (single instance, no traffic)

DoD: schema migrations land on producer side; nothing federates yet.

- Alembic migration for `share_contracts` and `federation_audit`.
- Qdrant payload migration (scope + share_tags) with default values.
- Planka board scope custom property + migration helper.
- Personal-context frontmatter parser learns `scope:`.
- Config flags + `.env.example` + `BUILD.md` section.
- Unit tests for scope tagging round-trip.

### Phase F1 -- Producer-only

DoD: a node can serve scoped memory reads to itself via loopback; security tests pass.

- `services/federation/contracts.py`, `predicates.py`, `redaction.py`, `audit.py`.
- `/api/federation/contracts` CRUD (operator-authenticated only).
- `/api/federation/memory/search` with scope-pre-filtered Qdrant query.
- `tests/test_federation_security.py`: unauthorised peer, expired contract, revoked contract, predicate bypass attempt, tag-deny enforcement, redaction completeness.
- Loopback test: federation API matches direct Qdrant query restricted to the same scope.

### Phase F2 -- Consumer + two-node mesh

DoD: two instances on the same Tailnet exchange scoped memory and merge it into prompts; revocation propagates within one query.

- `client.py` with `FederatedMemoryClient` (connection pool, timeout, circuit breaker per peer).
- Memory service integration: scope-aware merge plus remote attribution.
- Calendar availability federation.
- `FederationManager.ts` component (outbound + inbound tables, create form, revoke flow).
- i18n keys in `_EN`, `_DE`, propagated via the i18n gate.
- Channel parity check for prompt attribution on Telegram, WhatsApp, dashboard SSE.
- Two-instance docker-compose fixture; revocation, audit, and revocation tests pass on both nodes.

### Phase F3 -- Planka board sharing + crew interplay

DoD: a household-scope Planka board is readable from a second instance; crews like `nutrition` recognise federated shopping items without modification.

- `/api/federation/planka/board` snapshot (read-only, redacts comments and attachments).
- Consumer-side board mirror cache (5-minute TTL, invalidated by revocation).
- Crew memory layer reads federated boards transparently when scope is shared.
- `ProjectTree.ts` shared-board badge.

### Phase F4 -- Operator polish + observability

DoD: an operator running 3+ instances can manage all share relationships from the dashboard and spot anomalies fast.

- Federation audit panel with filtering (peer, resource, status, time range).
- Per-peer metrics: P50/P95 latency, error rate, last successful read.
- Dry-run mode for contracts: shows what the predicate would expose without activating.
- Per-rule alert on inbound query rate spikes from a peer.

### Phase F5 -- Future hooks (deferred)

Out of v1 scope, captured to avoid box-out:

- Bidirectional writes (`PROPOSE_TASK` from peer node, HITL on producer).
- Encrypted at rest with per-contract keys.
- Multi-hop federation (A -> B -> C). v1 forbids re-federation; remote points carry "do not re-share".
- Z-to-Z conversational protocol (#9) -- thin layer on top of federation primitives.

---

## 13. Test Strategy

| Layer | Test |
|---|---|
| Predicate eval | Forbidden tags never appear; `max_results_per_query` always honoured |
| Redaction | Schema test asserting every redacted field is absent in the response |
| Auth | Reject non-Tailnet IPs, mismatched node names, revoked or expired contracts |
| Injection | Federated points stripped of action tags and wrapped in untrusted sentinels; new "federated memory poisoning" attack class extends the 268-test injection suite |
| Channel parity | Telegram, WhatsApp, dashboard all show remote attribution prefix; verified by `tests/test_live_regression.py` |
| i18n | All new strings present in `_EN` and `_DE`; `pytest tests/test_i18n_coverage.py -v` green |
| Two-node E2E | Compose fixture with `node-a` and `node-b`; revocation, expiry, offline producer scenarios |
| Audit completeness | Every successful and failed read produces matching audit rows on both sides |

---

## 14. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Operator misconfigures a contract and leaks sensitive scope | Two-step confirm with plain-language summary, default deny, dry-run mode in F4, audit alerting |
| Federated content poisons the consumer's LLM | Untrusted sentinels, action-tag stripping, attribution in prompt, capped at `FEDERATION_MAX_REMOTE_POINTS` |
| Network partitions degrade UX | 1.5 s timeout, circuit breaker per peer, silent fall-through to local-only |
| Audit log grows unbounded | `FEDERATION_AUDIT_RETENTION_DAYS` (default 90), nightly prune, hashed queries keep rows small |
| Scope tagging burden on operator | Migration defaults to `default` (private); ambient-capture lane proposes scope tags during conversation, HITL-confirmed |
| Two-instance test infra is heavy | Compose fixture is opt-in; CI runs it only on changes under `services/federation/` or `api/federation.py` |
| Schema drift between producer and consumer | Contracts include `schema_version`; producer responds `426 Upgrade Required` on mismatch; surfaced in dashboard |

---

## 15. Definition of Done (Program-Level)

- A single operator can run `work-Z`, `personal-Z`, and `family-Z` on three Tailscale-connected hosts.
- `personal-Z` answering "am I free Saturday afternoon?" correctly merges `work-Z`'s busy blocks without ever seeing meeting titles.
- `family-Z` adding "buy sourdough" routes into the household-shared shopping list visible from `personal-Z`.
- Revoking the household contract from the dashboard immediately stops cross-visibility on the next query.
- Every cross-instance read appears in both nodes' audit feeds with matching contract id and timestamps within 1 second.
- The 268-test injection suite plus its new "federated memory poisoning" extension passes.
- `BUILD.md` includes a working two-node walkthrough; a fresh operator can stand up a second instance and create the first contract in under 30 minutes.

---

## 16. Why This Unlocks The Rest Of The Roadmap

- #9 Z-to-Z protocol -- two operators' instances negotiate a meeting time using only `calendar/availability` and a tiny `propose_meeting` endpoint behind a contract. No new trust model.
- #11 Digital twin threshold -- a personal scope can be exported and imported into a sandbox instance for "what would I do" simulations, with the audit trail proving nothing leaked back.
- #10 Predictive life orchestration -- cross-scope correlations (work meeting density vs household stress) become possible without merging stores.
