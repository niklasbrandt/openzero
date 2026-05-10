# Phase P4 -- Person / Circle Removal Deep-Dive

> Deletion plan for the entire Person / Circle / inner_circle subsystem. No feature flag, no sunset window, no export-before-delete. The substrate forgets the concept exists. Briefings and personal context shift to a substrate-derived "people surface naturally from memory" pattern.
> Status: PLAN | Author: conductor | Created: 2026-05-10
> Companions: `docs/artifacts/substrate_master_plan.md`, `docs/artifacts/memory_atlas.md`, `docs/artifacts/dynamic_domain.md`.

---

## 1. Why this exists

The Person / Circle subsystem is a classic **surface**: it asks the operator to maintain a structured social graph (inner / outer circles, identity row, birthdays, relationships) so that briefings and prompts can refer to "Markus has a birthday in 3 days." This is exactly the operator-managed-UI failure mode `agents.md` rule 22 (substrate vs surface) is designed to prevent.

Replacement pattern: people surface **naturally from memory**. When a calendar event mentions Markus, when an email thread surfaces a recurring sender, when a chat references a partner, the Atlas grows a node for that person automatically. Birthdays and relationships are captured if the operator volunteers them in conversation or if a `MemorySource` (e.g. calendar, contacts) supplies them. The operator does not maintain a structured list.

Briefing language shifts from "Markus has a birthday in 3 days" (which requires an operator-maintained Person row) to "a birthday event for Markus surfaced in your calendar; it's been 2 years since you last mentioned him in a chat" (which requires only memory and source_refs). See `docs/artifacts/walkthroughs_and_briefings.md` for the full briefing render contract.

---

## 2. Strategy

- **Rip, don't deprecate.** No `EMAIL_ENABLED`-style opt-out. No "circles_disabled" flag. The code, models, routes, components, and translation keys are deleted in a single phase.
- **No export.** Operator-confirmed: there is no migration of existing Person rows to a new representation. Any latent value lives in memory ingestion (calendar events, mail, chat history) which is unaffected.
- **Identity row migration.** The current `Person` row with `circle_type == "identity"` (read by `services/timezone.py` and `UserCard.ts`) is replaced by a substrate-owned `operator_identity` record sourced from `agent/domain.derived.yaml` (Phase DD) plus a minimal startup-DDL `operator_identity` table for fields that domain inference cannot derive (timezone preference, display name override). See `docs/artifacts/dynamic_domain.md` section 4.
- **DB cleanup.** Drop tables `persons`, `inner_circle_*` (any auxiliary join tables) on phase landing via the same `Base.metadata.create_all` startup pattern in `src/backend/app/main.py` plus a one-shot `DROP TABLE IF EXISTS` block in `main.py`'s startup DDL (no Alembic, per repo convention).
- **No regression bypass.** `tests/test_security_prompt_injection.py` people/circles adversarial test (line 445 area) is rewritten as a memory-injection test once memory ingestion of names is the new attack surface.

---

## 3. File-by-file deletion list

This list is best-effort enumeration based on workspace scan. Implementing agent confirms exhaustively at execution time using `tests/test_remnant_audit.py` (Phase P4 entry).

### 3.1 Backend models

- `src/backend/app/models/db.py`: delete `class Person`. Drop the table and any related indexes via startup DDL in `src/backend/app/main.py`.

### 3.2 Backend services

- `src/backend/app/services/timezone.py`: remove `Person` import; rewrite `circle_type == "identity"` lookup to read from new `operator_identity` source.
- `src/backend/app/services/memory.py`: audit and remove any circle-scoped retrieval branches.
- `src/backend/app/services/personal_context.py`: NOT deleted (sibling subsystem). Audit only for any `Person` references.
- `src/backend/app/services/agent_actions.py`: remove `Person`-bound action vocabulary entries (e.g. `ADD_PERSON`) from the allowlist.
- `src/backend/app/services/llm.py`: remove any system-prompt fragment that enumerates circle members; replace with substrate-derived people node references from the Atlas.
- `src/backend/app/services/crew_memory.py`: remove circle-scoped memory retrieval branches; replace with topic / spine retrieval.
- `src/backend/app/services/ambient/delivery.py`: remove circle-scoped delivery routing; replace with substrate routing per the unified pending-action queue.
- `src/backend/app/services/translations.py`: **cascade-finding (audit 2026-05-10)** -- this legacy `_TRANSLATIONS` map exists in parallel to `services/i18n/*.py`. Both surfaces hold `circle*` and `inner_circle*` keys; both must be cleaned in this phase. Operator should also confirm whether `translations.py` is to be deleted in P1 or kept in parallel.

### 3.3 Backend API

- `src/backend/app/api/dashboard.py`:
	- Remove `Person` from the `from app.models.db import ...` line.
	- Delete the `/api/dashboard/people` route family (GET / POST / DELETE).
	- Delete the `inner_circle` briefing-context block (around line 398-400, 1166-1171, 1248).
	- Delete the regression cleanup of `TEST_%` people (around line 741-743).
	- Delete the `Inner Circle (People):` system-prompt fragment (around line 463).
	- Delete the `circles` onboarding step entry (around line 1267).
	- Delete the duplicate-identity guardrail comment (around line 1775).

### 3.4 Backend tasks

- `src/backend/app/tasks/morning.py`: delete `inner_circle_tasks`, `get_person_briefing_data` references; replace briefing assembly with the memory-derived pattern from `docs/artifacts/walkthroughs_and_briefings.md`.
- `src/backend/app/tasks/scheduler.py`: **cascade-finding (audit 2026-05-10)** -- audit any APScheduler registration that imports or schedules a person/circle helper, and remove the registration alongside the helper.

### 3.5 Backend i18n (per `agents.md` rule 19)

Remove every key matching the patterns below from **every populated dict** under `src/backend/app/services/i18n/`. After Phase P1's i18n trim (C5), only `en.py` and `de.py` survive; this phase deletes the corresponding keys from those two files.

Forbidden i18n keys (exact match, post-deletion):

- `circles`, `circles_empty`, `nav_circles`, `social_circles`
- `inner_circle`, `inner_circle_desc`, `inner_circle_full`, `outer_circle_full`
- `step_inner_circle`, `add_to_circle`, `update_person`
- `aria_add_inner`, `aria_add_person`, `aria_delete_person`, `aria_edit_person`
- `confirm_delete_person`, `confirm_remove`, `edit_person`
- `error_adding_person`, `error_deleting_person`
- `no_people`

Run `pytest tests/test_i18n_coverage.py -v` after deletion to confirm parity.

### 3.6 Frontend dashboard

- `src/dashboard/components/CircleManager.ts`: full file deletion.
- `src/dashboard/components/WelcomeOnboarding.ts`: also deleted under C4 in Phase P2; if P2 ran first, this is already gone. If not, remove the `step_inner_circle` step entry first.
- `src/dashboard/components/UserCard.ts`: remove the `circle_type=identity` fetch (line 120) and the `circle_type: 'identity'` POST body (line 170); rewire to the new `operator_identity` endpoint introduced in Phase DD.
- `src/dashboard/index.html`:
	- Remove the `<a href="#section-circles" ...>` nav links (lines 112, 168).
	- Remove the `<span data-tr="nav_circles">` labels (lines 114, 170).
	- Remove the `<section ... id="section-circles" ...>` block (line 246).
- `src/dashboard/src/main.ts`: remove the `import('../components/CircleManager')` lazy-load registration (line 16).
- `src/dashboard/vite.config.ts`: remove `'CircleManager'` from the manual chunk array (line 43).

### 3.7 Tests

- `tests/test_security_prompt_injection.py`: rewrite the people/circles adversarial test (around line 445) as a memory-injection test once names enter via `MemorySource` ingestion. Do not simply delete -- the attack class still applies.
- Any pytest fixture seeding `Person` rows: delete.

### 3.8 Docs

- `README.md`: remove the `ADD_PERSON` row from the action vocabulary table (line 356).
- `BUILD.md`: audit for any setup step referencing circles or people; delete.

### 3.9 Reports / generated artifacts

- `src/dashboard/lighthouse-report*`: not hand-edited. Regenerated on next Lighthouse run.

---

## 4. Post-deletion remnant-audit symbol list

Append to `tests/test_remnant_audit.py` under `PHASE_FORBIDDEN["P4_circle_rip"]` (the master artifact section 6.2 shows the format):

- `filenames`: `["CircleManager.ts"]`
- `imports`: `["from app.models.db import.*Person", "import.*CircleManager"]`
- `identifiers`: `["class Person", "CircleManager", "circle_type", "circle_manager", "inner_circle", "outer_circle", "social_circles", "get_person_briefing_data", "section-circles"]`
- `i18n_keys`: full list from section 3.5 above
- `api_routes`: `["/api/dashboard/people", "/api/circle"]`

The `personal_context` service must not match any of these patterns -- audit confirms it stays clean.

---

## 5. Briefing / personal_context behaviour change

**Before (operator-managed surface):**

> Markus has a birthday in 3 days. Add a reminder?

**After (substrate-derived):**

> A birthday event for Markus surfaced in your calendar; it's been 2 years since you last mentioned him in a chat. Atlas node: oz://atlas/node/<id>.

The briefing assembly path in `src/backend/app/tasks/morning.py` (and weekly/monthly/quarterly/yearly counterparts) stops querying `Person` and starts querying:

- **Calendar `MemorySource`** for upcoming events involving named individuals.
- **Atlas spine summariser** for "last mentioned" recency on each name node.
- **Memory** (Qdrant) for source_refs justifying the mention.

Every briefing line gets a `oz://atlas/node/<id>` deep-link per `docs/artifacts/walkthroughs_and_briefings.md`.

`personal_context.py` is unaffected -- it reads `/personal/*.md` files which are operator-authored prose, not structured Person rows.

---

## 6. Definition of Done (Phase P4)

- All files listed in section 3 are deleted or modified as specified.
- `pytest tests/test_remnant_audit.py::test_phase_p4_circle_rip -v` is green.
- `pytest tests/test_i18n_coverage.py -v` is green (all six tests).
- `pytest tests/test_security_prompt_injection.py -v` is green with the rewritten memory-injection test.
- `tsc`, `ruff check`, `mypy` are clean.
- Dashboard loads without `CircleManager` registration errors; no nav link to `#section-circles`; no console fetch to `/api/dashboard/people`.
- Morning briefing renders the new substrate-derived pattern on Telegram, WhatsApp, dashboard, and voice-edge (channel parity rule 21).
- `BUILD.md` and `README.md` updated per section 3.8.
- `docs/artifacts/circle_removal.md` updated to mark Phase P4 complete; deviations recorded.
