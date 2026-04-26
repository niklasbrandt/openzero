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
   |  /api/federation/*          |<- bearer ->|  /api/federation/*          |
   |                             |  over      |                             |
   |                             | Tailscale  |                             |
   | ShareContract Registry      | (CGNAT pin)| ShareContract Registry      |
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

No central server. Each instance is both producer (responds to scoped reads) and consumer (queries other instances when a memory search yields no local hit and a relevant contract exists). Trust uses **bearer tokens over Tailscale** -- no separate mTLS / PKI layer (Tailscale already provides node identity + WireGuard transport). Producer-side middleware additionally pins the source IP to the Tailscale CGNAT range `100.64.0.0/10`.

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

- The producer accepts requests only from Tailnet-internal IPs in the CGNAT range `100.64.0.0/10`, enforced by a shared FastAPI dependency in `app/api/_deps.py` (also reused by voice-edge).
- The producer cross-checks the requester's **Tailscale node-key** (immutable identity) against the contract's `consumer_node`. Friendly node names alone are renameable and not used for trust.
- Contract requests carry a producer-issued bearer token plus a request-level `nonce` and `issued_at` (Redis idempotency window, 60 s skew tolerance). Loss of the token invalidates only that contract.
- Bearer tokens are encrypted at rest with a per-instance KEK (`FEDERATION_KEK`); rotation cadence default 90 days; tokens are bound to the peer's node-key fingerprint so an exfiltrated token off-Tailnet is useless.

Trust root is the Tailnet plus per-contract bearer. **No separate mTLS / public CA**.

---

## 5. New API Surface

All routes under `/api/federation/`, all require Tailscale-internal source plus bearer token, all rate-limited per peer. Contract-CRUD endpoints additionally require **dashboard operator auth** (`DASHBOARD_TOKEN`), never federation bearer -- a Tailnet-internal compromised peer must not be able to create or revoke contracts on a peer's behalf.

| Method | Route | Purpose | Auth |
|---|---|---|---|
| `GET` | `/contracts` | List contracts where this node is producer or consumer | dashboard |
| `POST` | `/contracts` | Create a new contract (operator only, dashboard) | dashboard |
| `DELETE` | `/contracts/{id}` | Revoke (immediate) | dashboard |
| `POST` | `/memory/search` | Federated memory query under a contract id | federation bearer |
| `POST` | `/calendar/availability` | Free/busy slots under a contract id | federation bearer |
| `POST` | `/planka/board` | Read scoped board snapshot (read-only) | federation bearer |
| `GET` | `/audit` | Cross-instance access log for this node | dashboard |

`POST /memory/search` request body:

```json
{
	"contract_id": "uuid",
	"query": "shopping list for Saturday",
	"top_k": 5,
	"nonce": "<monotonic-per-contract>",
	"issued_at": "2026-04-26T07:14:33Z"
}
```

Producer sequence:

1. Verify Tailnet-internal source IP and bearer token (constant-time compare against encrypted-at-rest hash).
2. Reject if `nonce` already seen for this contract within token lifetime, or if `issued_at` skew > 60 s.
3. Load the contract; verify active, not expired, belongs to the requesting peer (by node-key, not friendly name).
4. Run the Qdrant search with a hard pre-filter matching `scope_predicate` (`tags_any` first, `tags_none` deny-list applied **after**).
5. Cap results at `max_results_per_query`.
6. Re-check contract validity at result-emit time (not just at request-receive) so revocation during a long-running query is honoured.
7. Strip redacted fields per the resource's redaction allowlist.
8. Log the read with contract id, **HMAC-SHA-256 of the query** (per-instance audit pepper), and result count bucket. Plain SHA-256 is rainbow-tableable for short queries; HMAC defeats this.
9. Return surviving points.

Result counts are bucketed (`0`, `1-5`, `6-20`) in the audit log only -- the consumer receives the actual list. This is documented as a producer-side audit-privacy measure, not a wire-level cap.

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

Planka v6's public API does **not** expose arbitrary board metadata; openZero already drops to direct Postgres for board moves (see `services/planka.py`). Federation therefore stores scope in a side table:

```
board_scopes(
	board_id text primary key,
	scope text not null default 'default',
	share_tags jsonb not null default '[]'::jsonb,
	updated_at timestamptz not null default now()
)
```

Federation only reads boards whose `board_scopes.scope` matches the contract. Operators never edit `board_scopes` directly; the dashboard FederationManager component owns CRUD.

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

Both tables are created via the repo's existing startup-DDL pattern (`Base.metadata.create_all` plus raw `ALTER TABLE` in `main.py`'s startup hook), gated behind `FEDERATION_ENABLED=true`. **Alembic is not used in this codebase.**

### 6.4 Personal context

Add a `scope:` frontmatter key to fragments inside `personal/*.md`. The personal-context loader honours scope when injecting into prompts. Fragments without scope are treated as `default`. Frontmatter is parsed with `yaml.safe_load`, duplicate keys rejected, and per-fragment frontmatter size capped (default 4 KB) -- frontmatter is a YAML-injection sink if any fragment contains operator-pasted untrusted content.

---

## 7. Backend Module Layout

```
src/backend/app/services/federation/
	__init__.py            # init_federation(), feature flag gate
	contracts.py           # ShareContract CRUD + signing
	predicates.py          # ScopePredicate evaluation
	identity.py            # Tailscale peer resolution + token verification
	redaction.py           # per-resource redaction allowlists
	access_log.py          # federation_audit read/write (renamed from audit.py to avoid collision with services/self_audit.py)
	peer_client.py         # FederatedMemoryClient, FederatedAvailabilityClient
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

`memory.semantic_search()` returns a string today; the merge layer must operate on `memory.semantic_search_raw()` (`list[dict]`) and emit a recombined string at the prompt-assembly site. The federation hop becomes:

1. Run the local Qdrant search as today.
2. If `FEDERATION_ENABLED` and active inbound contracts plausibly match the query (cheap keyword/tag heuristic, plus an explicit `@scope` mention), fan out parallel `/memory/search` calls. Side-channel risk acknowledged in §9.1.
3. Use `asyncio.wait(..., return_when=FIRST_COMPLETED)` with an early-return at 400 ms if local + best peer have answered; ceiling 800 ms p99, hard timeout 1500 ms.
4. Per-peer circuit breaker state in Redis (`fed:cb:<peer>`) so all uvicorn workers share it.
5. Merge results, tagging each remote point with `origin_node` and `contract_id`.
6. Re-rank by cosine distance only -- attribution metadata is preserved, but local does **not** automatically outrank remote (that bias defeats federation's purpose).
7. Cap total federated points (`FEDERATION_MAX_REMOTE_POINTS`, default 5).

Remote points enter the prompt wrapped in untrusted-content sentinels:

```
<<<FEDERATED node="work-z" contract="<id>">>>
[Shared from work-z under contract <id>] ...
<<<END_FEDERATED>>>
```

The LLM is instructed to treat federated text as **third-party hearsay**, never as Z's own memory. Sentinel-wrap, `_MUTATING_TAG_RE` strip, control-char strip, and `_sanitize_for_log` are applied uniformly to **all four resource types** (memory, calendar block titles, board snapshots, personal_fact text) inside `peer_client.py`, not at each call site. Attribution is non-negotiable.

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

Two new `SENSITIVE_ACTIONS` are added to the `SENSITIVE_ACTIONS` set in `services/agent_actions.py` and surfaced through the unified pending-action dashboard view:

- `SHARE_SCOPE` -- create or update a contract. **Dashboard-only in v1**; never confirmable via voice or any other channel; the LLM cannot initiate.
- `REVOKE_SHARE` -- revoke a contract by id. Dashboard-only in v1.

`MERGE_INSTANCE`, `EXPORT_ALL`, `WIPE_REMOTE` are explicitly not added. Federation is read-only in v1.

---

## 10. Dashboard

A new `FederationManager.ts` Shadow DOM component (matches existing conventions: `${ACCESSIBILITY_STYLES}`, `tr()`, HSLA tokens, no hardcoded English).

Sections:

1. This node's identity -- Tailscale node name plus node-key fingerprint, scopes in use, point counts per scope.
2. Outbound contracts (this node as producer) -- peer, resource, predicate summary, last access, revoke button.
3. Inbound contracts (this node as consumer) -- producer, resource, last successful read, manual refresh.
4. Create contract -- guided form: peer (from Tailscale device list), resource, scopes, tag filters, expiry. Native `<label for>`, `aria-describedby` for the predicate explainer, error-summary pattern with `aria-invalid`. Predicate-summary plain-language strings use `tr()` for every static fragment **and** every interpolated value -- never concatenated English glue.
5. Audit feed -- last 100 federation reads, rendered with `role="log"` + `aria-live="polite"`. Status colour pairs with text/icon (forced-colors safety, agents.md rule 12 colour independence). Uses `${SCROLLBAR_STYLES}` and `${SECTION_HEADER_STYLES}` (`.h-icon`, `.status-dot`, `.empty-state` per design-system rule 18).

Contract creation and revocation are two-step confirms following the canonical `AgentsWidget` `*-step1` / `*-confirm` pattern (red HSLA border `hsla(0, 80%, 65%, 0.3)`); the second step shows a plain-language summary of what the contract will permit.

Mandatory boilerplate: `${ACCESSIBILITY_STYLES}`, `${BUTTON_STYLES}`, `${SECTION_HEADER_STYLES}`, `${SCROLLBAR_STYLES}`, `tr()` (loaded in `connectedCallback`), local `.sr-only`, `:focus-visible`, `@media (prefers-reduced-motion: reduce)`, `@media (forced-colors: active)`, HSLA `var(--token, fallback)`, `rem` spacing.

All user-visible strings (visible text, `aria-label`, `placeholder`, `title`) go through `this.tr('key', 'English fallback')` with new keys added at minimum to `src/backend/app/services/i18n/en.py` and `de.py`. `pytest tests/test_i18n_coverage.py -v` is a Phase F2 DoD line.

---

## 11. Configuration

`src/backend/app/config.py` additions:

```python
FEDERATION_ENABLED: bool = False
FEDERATION_NODE_NAME: str = ""                 # this instance's friendly name
FEDERATION_NODE_KEY_FINGERPRINT: str = ""      # immutable Tailscale node-key fp; populated at startup
FEDERATION_KEK: str = ""                       # per-instance KEK for at-rest token encryption
FEDERATION_MAX_REMOTE_POINTS: int = 5
FEDERATION_QUERY_TIMEOUT_MS: int = 1500        # hard ceiling; early-return at 400 ms
FEDERATION_AUDIT_RETENTION_DAYS: int = 90
FEDERATION_AUDIT_PEPPER: str = ""              # per-instance HMAC pepper for query-hash logging
FEDERATION_TOKEN_ROTATION_DAYS: int = 90
```

Mirror in `.env.example` and `config.example.yaml`. `BUILD.md` gains a phase: "Federation -- linking multiple openZero instances", covering Tailscale ACL JSON sample, generating `FEDERATION_NODE_NAME` and `FEDERATION_KEK`, the dashboard contract-creation walk-through, and the bearer-token rotation procedure.

---

## 12. Phased Implementation

### Phase F0 -- Foundations (single instance, no traffic)

DoD: schema migrations land on producer side; nothing federates yet. Phase A of the unified ambient roadmap (`full_ambient_intelligence_roadmap.md`) -- shared sanitiser module + unified pending queue + `SENSITIVE_ACTIONS` extension surface -- is a prerequisite.

- Startup-DDL migration for `share_contracts`, `federation_audit`, and `board_scopes` (no Alembic).
- Qdrant payload migration (scope + share_tags) with default values; idempotent dry-run flag.
- Personal-context frontmatter parser learns `scope:` (uses `safe_load`, rejects duplicate keys, caps frontmatter size).
- Config flags + `.env.example` + `config.example.yaml` + `BUILD.md` section.
- Add `SHARE_SCOPE` and `REVOKE_SHARE` to `SENSITIVE_ACTIONS` in `services/agent_actions.py` (parser regex, allowlist, dashboard pending UI).
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

- `peer_client.py` with `FederatedMemoryClient` (connection pool, timeout, **shared Redis-backed circuit breaker** per peer).
- Memory service integration via `memory.semantic_search_raw()`: scope-aware merge plus remote attribution sentinels.
- Calendar availability federation.
- `FederationManager.ts` component (outbound + inbound tables, create form, revoke flow, audit feed). Mandatory boilerplate per §10.
- i18n keys in `services/i18n/en.py` and `de.py`; `pytest tests/test_i18n_coverage.py -v` green.
- Channel parity check for prompt attribution on Telegram, WhatsApp, dashboard SSE, and voice-edge (rule 21).
- Two-instance docker-compose fixture (overlay file `docker-compose.federation.yml`, two networks bridged via Tailscale stub or skipped under a CI path-filter); revocation, audit, and offline-producer tests pass on both nodes.

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

---

## Appendix R -- Review Revisions (2026-04-26)

Multi-specialist review (security, backend, infra, qa, ui-builder, perf, ai-engineer, researcher) folded into the body above. Tracked open items:

### Cross-cutting prerequisites

- **i18n location.** Keys live in `src/backend/app/services/i18n/{code}.py`, not in `services/translations.py` (aggregator only). agents.md rule 19 pointer must be corrected in the same PR.
- **Alembic does not exist.** Use `Base.metadata.create_all` + raw startup DDL in `main.py`. All references corrected in body.
- **Tailnet-source-IP middleware** is a shared dependency in `app/api/_deps.py`, also reused by voice-edge.
- **Shared sanitiser module** at `services/security/sanitisers.py` (Phase A of unified ambient roadmap, prerequisite for F0).

### Security tightenings (folded above; tracked here)

- mTLS contradiction resolved: bearer + Tailscale CGNAT pin only.
- Bearer at-rest encryption with per-instance KEK; 90-day rotation; bound to peer node-key fingerprint.
- HMAC-SHA-256 query hashing in audit log (per-instance pepper); plain SHA-256 was rainbow-tableable.
- Replay nonce + `issued_at` skew (60 s) in every request body; per-(contract, nonce) idempotency window in Redis.
- Contract CRUD requires `DASHBOARD_TOKEN`, never federation bearer (closes A01 broken-access-control gap).
- Side-channel of fan-out trigger heuristic: documented as accepted risk; mitigated by requiring local Qdrant top-1 score < 0.55 OR explicit `@scope` mention before federating.
- Contract bound to **node-key**, not friendly node-name (renameable).
- Producer re-checks contract validity at result-emit time, not just at request-receive (revocation during long-running query honoured).
- `ScopePredicate` precedence: `tags_any` first, `tags_none` deny-list applied **after**.
- `share_contracts.scope_predicate jsonb` pydantic-validated on every read; reject contract on schema mismatch.
- All four resource types (memory, calendar, board, personal_fact) pass through sentinel-wrap + `_MUTATING_TAG_RE` strip + control-char strip uniformly inside `peer_client.py`, not at each call site.
- Personal-context YAML frontmatter uses `safe_load`, rejects duplicate keys, caps fragment size (4 KB default).

### Backend feasibility

- Planka v6 has no API for arbitrary board metadata. Scope encoded in side table `board_scopes(board_id, scope, share_tags)`, not Planka-internal custom property.
- `memory.semantic_search` returns a string today; merge layer operates on `memory.semantic_search_raw` (`list[dict]`).
- `bus.ingest` signature does not accept `lang`/`conversation_id`. Coordinated as a cross-artifact PR.
- `services/federation/audit.py` renamed to `access_log.py` to avoid grep collision with `services/self_audit.py`.
- `services/federation/client.py` renamed to `peer_client.py` (matches existing `*_client` convention).
- F0 and F1 may collapse into a single shippable slice (producer-only requires minimal wiring beyond schema).

### Performance

- Fan-out latency: `asyncio.wait(FIRST_COMPLETED)` early-return at 400 ms; ceiling 800 ms p99; hard timeout 1500 ms only as last resort.
- Per-peer circuit breaker state in Redis (`fed:cb:<peer>`) so all uvicorn workers share it.
- Cache "no remote hit" decisions per query-hash for 60 s.
- `FEDERATION_MAX_REMOTE_POINTS=5` is per-query; future per-resource caps for calendar/board fan-out.
- Audit table: batched insert via async queue (drain every 500 ms), monthly-partitioned for fast prune (`DROP PARTITION` instead of `DELETE`).
- Bearer-token verification uses an LRU cache (1024) to avoid Postgres roundtrip per request.
- Qdrant `scope` and `share_tags` payload **keyword index** required (not just the field) -- otherwise every federated query is a full collection scan.
- Consumer cache invalidation: piggyback revocation token version on every successful response (`ETag: contract_id:rev`).

### QA

- `tests/test_security_prompt_injection.py` extension named "federated memory poisoning" with explicit count delta (target +20 cases). Reference suite by file/name, not the volatile total.
- New test fixtures: nonce-replay, schema-version downgrade (`426`), bearer-token rotation mid-query, contract revocation race, HMAC tampering, multi-hop guard ("do not re-share").
- Bearer plaintext never appears in audit, logs, or `share_contracts` row dumps -- explicit test.
- Predicate fuzz test in `test_federation_predicates.py` (json injection, oversized lists, unicode tag names).
- Two-instance compose fixture is opt-in via CI path-filter on `services/federation/` or `api/federation.py`. Tailscale stub provided to avoid auth-key secrets in CI.
- F2 channel parity check explicitly enumerates Telegram, WhatsApp, dashboard, **voice-edge**.
- "Under 30 minutes" operator setup is documentation acceptance, not a CI gate.
- Audit timestamp delta "within 1 second" needs NTP-stable fixtures.
- `FEDERATION_MAX_REMOTE_POINTS` cap enforcement at the merge layer is an explicit consumer-side test.

### Dashboard / a11y / i18n

- Two-step confirm follows the canonical `AgentsWidget` `*-step1` / `*-confirm` red HSLA-border pattern (folded into §10).
- Audit feed is `role="log"` + `aria-live="polite"`; status pairs with text/icon (forced-colors safety).
- Predicate-summary plain-language strings: every static fragment AND every interpolated value via `tr()`. No concatenated English glue.
- Native `<label for>`, `aria-describedby`, error-summary pattern, `aria-invalid` on contract form.
- `${SCROLLBAR_STYLES}` and `${SECTION_HEADER_STYLES}` for the audit feed.
- "11 languages" claim replaced with "`_EN` and `_DE` parity is the CI gate; other populated dicts under `services/i18n/` get parity by `TestKeyCompleteness`".

### AI / persona / crew

- New `agent-rules.md` section: **Federated Attribution** -- federated facts are third-party hearsay; consumer-Z must cite the source node by friendly name, must not fold into first-person, must defer to local data on conflict.
- New `agent-rules.md` section: **Cross-Node Voice Lock** -- persona/voice is per-node; consumer-Z never adopts producer-Z's crew persona for a federated point.
- Federated points carry the producer's `persona_hash` (added to `crews.yaml` schema in unified ambient roadmap); consumer warns on mismatch.
- F3 hard clamp: ambient capture cannot write to a federated board (consumer side is read-only in v1).
- Federated calendar busy labels (`work busy`, `partner busy`) use `tr()` keys, not hardcoded English.
- Sentinel-wrap applies to all federated text: memory, calendar block titles, board snapshot fields, personal_fact fragments.

### Cross-artifact consistency

- `SHARE_SCOPE` / `REVOKE_SHARE` ownership: this artifact wires them into `SENSITIVE_ACTIONS`. Voice-edge §9.2 must remove `SHARE_SCOPE` from spoken HITL list (federation §9.3 is dashboard-only in v1).
- F2 channel parity now includes voice-edge.
- `MERGE_INSTANCE` / `EXPORT_ALL` / `WIPE_REMOTE` decision ledger captured in agents.md or `docs/artifacts/self_audit.md` follow-up to prevent reintroduction.
- Profile labels (`micro` / `standard` / `performance` vs `Tier A/B/C`) reconciled via the `HARDWARE_PROFILE` enum prerequisite owned by the unified ambient roadmap.
- Audit retention `FEDERATION_AUDIT_RETENTION_DAYS` defaults are profile-aware (`micro` Pi 5 needs a smaller default than `performance`).

