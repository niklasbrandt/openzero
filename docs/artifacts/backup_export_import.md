# Backup Export / Import -- schema_version 3

## Overview

openZero provides a full-content backup system that serialises all operator data into a single encrypted archive. The archive is produced by the backend on demand, downloaded by the operator, and can be restored to any openZero instance.

Schema version: **3**
Encryption: pynacl `SecretBox` (XSalsa20-Poly1305) with Argon2id key derivation
Archive format: ZIP containing `manifest.json` + section JSON files, encrypted as a single opaque blob

---

## Sections table

| Section             | Pydantic model          | Source                                    | Notes                                                   |
| ------------------- | ----------------------- | ----------------------------------------- | ------------------------------------------------------- |
| `planka`            | `PlankaExportV3`        | Planka REST API                           | Projects -> boards -> lists -> cards -> tasks hierarchy |
| `calendar`          | `CalendarBundle`        | CalDAV, Google Calendar, local DB         | Three sub-bundles: caldav / google / local              |
| `memory`            | `list[MemoryPointNode]` | Qdrant `personal_memory` collection       | id + text + payload per point                           |
| `atlas`             | `AtlasCurationExport`   | Postgres atlas_nodes / atlas_edges tables | Nodes, edges, spines, decisions, contradictions         |
| `preferences`       | `PreferencesExport`     | Postgres user_preferences table           | Opt-in only (`include_preferences` query flag)          |
| `custom_tasks`      | `list[CustomTaskExport]`| Postgres custom_tasks table               | Cron/interval job definitions                           |
| `tracking_sessions` | `list[TrackingSessionExport]` | Postgres tracking_sessions table    | `is_active` forced `False` on import                   |
| `email_rules`       | `list[EmailRuleExport]` | Postgres email_triage_rules table         | Pattern-based triage rules                              |
| `walkthroughs`      | `list[WalkthroughExport]` | Postgres walkthroughs + stops tables    | Atlas node refs resolved by label on import             |
| `share_contracts`   | `list[ShareContractExport]` | Postgres share_contracts table        | `status` forced `inactive` on import                   |
| `redis`             | `RedisExport`           | Redis key-value store                     | Privacy override + ambient authorship keys only         |
| `files`             | `FilesExport`           | agent/ + personal/ directories            | Text files only; path allowlist enforced                |

---

## Conflict strategy table

Each import section applies the `conflict` query parameter independently.

| Section           | `skip`                                       | `merge`                                                 | `replace`                                               |
| ----------------- | -------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------- |
| planka            | Skip board if a board with same name exists  | Append new lists/cards; skip existing cards by name     | Delete all boards in project, then insert from backup   |
| calendar          | Skip event if uid already exists in DB       | Insert if uid absent; update dtstart/dtend if present   | Delete all local events, reinsert from backup           |
| memory            | Skip point if id already exists in Qdrant    | Upsert: overwrite payload if id matches                 | Requires `X-Confirm-Destructive: yes`; wipes collection |
| atlas             | Skip node if label+type collision detected   | Insert new nodes; skip collisions                       | Requires `X-Confirm-Destructive: yes`; truncates tables |
| preferences       | Skip all (disabled unless opt-in flag set)   | Upsert each key individually                            | Truncate preferences table, reinsert all rows           |
| custom_tasks      | Skip task if name already exists             | Insert new tasks; skip name collisions                  | Delete all custom tasks, reinsert from backup           |
| tracking_sessions | Insert new sessions (no uid collision check) | Same as skip                                            | Same as skip (sessions are append-only)                 |
| email_rules       | Skip rule if sender_pattern already exists   | Insert new rules; skip pattern collisions               | Delete all rules, reinsert from backup                  |
| walkthroughs      | Skip if title already exists                 | Insert new walkthroughs; skip title collisions          | Delete all walkthroughs, reinsert                       |
| share_contracts   | Insert with `status=inactive` always         | Same as skip                                            | Same as skip (contracts start inactive on every import) |
| redis             | Set key only if it does not already exist    | Overwrite key unconditionally                           | Overwrite key unconditionally                           |
| files             | Skip file if it already exists on disk       | Overwrite if content differs                            | Overwrite unconditionally                               |

`replace` mode for destructive sections (`memory`, `atlas`) requires the `X-Confirm-Destructive: yes` request header to prevent accidental data loss.

---

## Hard exclusion list

The following data categories are never included in a backup bundle, regardless of operator request.

| Excluded category                     | Rationale                                                                        |
| ------------------------------------- | -------------------------------------------------------------------------------- |
| `.env` and all secret files           | Credentials must never be embedded in a portable archive                         |
| `tokens/` directory                   | OAuth refresh tokens are instance-specific and invalidate on restore             |
| Chat history (all channels)           | Conversations may contain third-party PII; excluded to limit blast radius       |
| LLM response caches                   | Transient; regenerated on next inference call                                    |
| Docker volumes / database binaries    | Binary state is non-portable and unsuitable for JSON serialisation               |
| Planka media attachments              | Binary blobs excluded from schema v3; reserved for schema v4                    |
| Qdrant collection indices             | Re-built automatically from `memory` section payload on import                  |
| `__pycache__`, `.venv`, `node_modules`| Build artefacts; excluded by path allowlist                                     |
| Any file outside `agent/` + `personal/` path prefix | Files export is restricted to these two directories by the path allowlist |

---

## Pollution guards

The service applies multiple pollution guards before writing any field to the bundle.

| Guard                        | Implementation                               | Applies to                          |
| ---------------------------- | -------------------------------------------- | ----------------------------------- |
| Control character strip      | `_CTRL_RE` regex strips `0x00-0x1f` range   | All string fields via Pydantic validators |
| Max field length enforcement | Pydantic `Field(max_length=...)` constants  | All text fields (name, desc, rrule, etc.) |
| Far-future date rejection    | `dtstart > 100 years` raises `ValueError`   | `EventNode.dtstart`                 |
| High-entropy secret scanner  | Trufflehog-style `_SECRET_PATTERNS` regex   | Planka card descriptions            |
| Card/event volume cap        | `MAX_CARDS = 50000`, `MAX_EVENTS = 10000`   | Per-board card count, calendar fetch |
| Path traversal guard         | `FileEntry.path` must match allowlist prefix | `files` section                     |
| Atlas orphaned edge check    | Edge source/target ids must exist in node id set | `atlas` section on import      |

---

## Routes table

All routes are authenticated via the `require_auth` dependency (bearer token).

| Method | Path                              | Description                                              |
| ------ | --------------------------------- | -------------------------------------------------------- |
| GET    | `/api/dashboard/backup/preview`   | Paginated preview of one section without encryption      |
| GET    | `/api/dashboard/backup/export`    | Build and stream full encrypted backup archive           |
| POST   | `/api/dashboard/backup/import`    | Upload, decrypt, and restore a backup archive            |
| GET    | `/api/dashboard/backup/strength`  | Check passphrase entropy score via zxcvbn                |

### Export query parameters

| Parameter             | Type    | Default | Description                                      |
| --------------------- | ------- | ------- | ------------------------------------------------ |
| `passphrase`          | string  | --      | Required. Min 12 characters. Used for encryption |
| `include_preferences` | boolean | `true`  | Include the preferences section                  |

### Import query parameters

| Parameter             | Type    | Default | Description                                           |
| --------------------- | ------- | ------- | ----------------------------------------------------- |
| `passphrase`          | string  | --      | Required. Must match the passphrase used at export    |
| `dry_run`             | boolean | `false` | Simulate import without writing to any data store     |
| `conflict`            | string  | `skip`  | Conflict resolution mode: `skip`, `merge`, `replace`  |
| `include_preferences` | boolean | `false` | Restore the preferences section                       |

Destructive conflict modes also require the request header `X-Confirm-Destructive: yes`.

### Export response headers

| Header                    | Example value                   |
| ------------------------- | ------------------------------- |
| `X-Backup-Schema-Version` | `3`                             |
| `X-Backup-Instance`       | `openzero42`                    |
| `X-Backup-Sections`       | `planka,calendar,memory,atlas`  |
| `Content-Disposition`     | `attachment; filename="..."`    |

---

## Encryption design

### Key derivation

```
key = Argon2id(
	password = passphrase.encode("utf-8"),
	salt     = random 16-byte salt (nacl.pwhash.argon2id.SALTBYTES),
	opslimit = OPSLIMIT_INTERACTIVE,
	memlimit = MEMLIMIT_INTERACTIVE,
	dklen    = 32,
)
```

### Encryption

```
ciphertext = nacl.secret.SecretBox(key).encrypt(plaintext)
blob       = salt || ciphertext
```

`SecretBox` uses XSalsa20-Poly1305, providing authenticated encryption. The 16-byte Poly1305 MAC detects any tampering. A wrong passphrase results in a `nacl.exceptions.CryptoError` (400 returned to caller -- no internal detail exposed).

### Wire format

```
[ 16 bytes Argon2id salt ][ N bytes nacl SecretBox ciphertext ]
```

The ciphertext includes the nonce prepended by pynacl. Total overhead vs plaintext: 16 (salt) + 24 (nonce) + 16 (MAC) = 56 bytes.

---

## Manifest structure

Every backup contains a `manifest.json` section with the following fields.

```json
{
	"schema_version": 3,
	"created_at": "2026-05-11T12:00:00+00:00",
	"instance_slug": "openzero42",
	"source_commit": "abc1234",
	"sections": ["planka", "calendar", "memory", "atlas", "files"],
	"sha256": {
		"planka": "e3b0c44298fc...",
		"calendar": "6b86b273ff34..."
	},
	"exclusion_log": [
		"planka/MyProject/Sprint 3/APIKey card: description excluded (possible secret)"
	]
}
```

`sha256` maps each section name to the SHA-256 hex digest of its raw JSON bytes before encryption. This allows per-section integrity verification without decrypting the full bundle.

`exclusion_log` lists every item silently dropped by a pollution guard, so the operator can audit what was not backed up.

---

## Backup filename format

```
oz-backup-{instance_slug}-{YYYYMMDD-HHMMSS}Z.enc
```

Example: `oz-backup-openzero42-20260511-120000Z.enc`

---

## Future extension path

Schema v4 is reserved for binary attachment support (Planka card attachments, voice transcripts, document uploads). The planned approach:

- Each attachment stored as a separate ZIP entry: `attachments/{hash}/{filename}`
- `FileEntry` model extended with `content_type` and `sha256` fields
- `manifest.sha256` entries added per attachment for integrity checks
- Import deduplicates by content hash before writing to the Planka media volume

No changes to the v3 schema are required to accommodate this extension; v4 simply adds the `attachments/` namespace to the ZIP and bumps `schema_version`.

Older instances receiving a v4 bundle will reject it with a `409 Conflict` response and an `old_schema` flag in the import report, prompting the operator to upgrade.
