# Substrate Pivot -- Master Plan

> Single source of truth for openZero's reframing from a tools-dashboard into a thinking substrate. Implementing agents load this artifact first to execute the entire pivot cohesively. The detailed decisions matrix and cascade analysis live in `docs/artifacts/substrate_pivot.md`.
> Status: P0-P4, MA0-MA2, D, C, W, DC, DD, Y, H, Z COMPLETE | Author: conductor | Created: 2026-05-10 | Updated: 2026-05-11
> Companions: `docs/artifacts/substrate_pivot.md`, `docs/artifacts/memory_atlas.md`, `docs/artifacts/circle_removal.md`, `docs/artifacts/dynamic_domain.md`, `docs/artifacts/walkthroughs_and_briefings.md`, `docs/artifacts/full_ambient_intelligence_roadmap.md`, `docs/artifacts/federated_memory.md`, `docs/artifacts/voice_edge_pod.md`, `docs/artifacts/ambient_capture_routing.md`, `docs/artifacts/ambient_intelligence.md`, `docs/artifacts/multimodal_vision.md`, `docs/artifacts/DESIGN.md`, `agents.md`, `README.md`.

---

## 1. The Essence

openZero stops being a surface that humans arrange work on (the Miro / Jira / Trello pattern -- cards, boards, arrows that humans move around while the intelligence stays in the humans). openZero becomes the **substrate that sits underneath the work**: it builds and maintains context on its own, reasons about that context, and lets the operator walk and recompose it. Boards, tickets, calendar entries, emails, voice notes, photos -- all of these become inputs to a memory that thinks. They are no longer the place where thinking has to live. The operator may run several **purpose-shaped instances** of the substrate (`life-Z`, `work-Z`, `partner-Z`, `fishing-Z`), each with its own ontology, its own topic spines, and its own visual language, all running on hardware the operator owns.

**One-sentence essence:** openZero is a sovereign, self-hosted AI companion that grows a purpose-shaped memory around whatever you point it at -- a life, a team, a project, a craft -- and thinks alongside you there, with every byte staying under your control.

**What does it solve.** Knowledge workers, founders, makers, parents, and craftspeople accumulate context faster than any single tool can hold it. Calendars forget. Notes apps fragment. Boards reset every quarter. Conversations vanish. The work of remembering, connecting, and reconciling all of this falls back on the human, and the human runs out of bandwidth. Off-the-shelf AI assistants can chat, but they own the substrate -- your memory lives on someone else's servers, your ontology is whatever they shipped this quarter, and the moment you push real life through them you become the product.

openZero solves both halves of that. It removes the substrate problem by growing one for you, locally, automatically, and continuously: every signal you let in (calendar, mail, chats, photos, voice, sensor feed) is parsed, related, weighted, and woven into a navigable memory that an Atlas surfaces and a chat conversation walks through. And it removes the sovereignty problem by running entirely on hardware you own, with model weights you choose, behind a Tailscale perimeter, with optional federation that ships reasoning slices instead of raw data. You point an instance at a domain; the substrate grows there; you stop carrying the reconciliation work in your head.

---

## 2. Substrate vs Surface principle

The operating heuristic for every decision in this pivot:

> For every feature, ask: does this make the substrate think better, or does it give the operator another surface to manage? Cut surfaces. Build thinkers.

A "surface" is a UI element that asks the human to arrange, classify, drag, tag, schedule, or otherwise do the cognitive work the substrate should be doing. A "thinker" is a service, crew, or surface that increases the substrate's autonomous understanding of the operator's world. When in doubt, prefer the option that increases autonomous understanding over the option that adds operator-managed UI. This principle is enshrined as `agents.md` rule 22.

---

## 3. Locked decisions matrix

These decisions are **non-negotiable**. Implementing agents MUST NOT re-open them. If an implementing agent believes a locked decision is wrong, it surfaces the concern in its summary and proceeds with the locked decision unless the operator explicitly reverses it.

### 3.1 Cuts

| ID | Subject | Action | Phase |
|----|---------|--------|-------|
| C1 | `CircleManager.ts`, `Person` model, all `inner_circle_*` tables, `/api/circle/*`, all circle-scoped logic across calendar / gmail / briefings / personal_context / crews / tasks | Delete entirely. No feature flag. No sunset window. No export-before-delete. | P4 |
| C2 | `src/backend/app/services/automation.py` (rule engine) | Delete entirely. Replaced by `signal_interpreter` crew (HITL). | P3 |
| C3 | `ShoppingList.ts` standalone widget | Absorb into nutrition crew output as a structured `items` field. Widget removed. | P1 |
| C4 | `WelcomeOnboarding.ts` multi-step wizard | Collapse to a one-screen entry: template hint + "what is this instance for?" + connect-one-source CTA. | P2 |
| C5 | Translation matrix beyond `en` + `de` | Trim `_TRANSLATIONS` and the `UserCard` selector to `en` + `de` only. Remove all stub language dicts. | P1 |
| C6 | `EmailRules.ts` and discoverable email affordance | Email becomes opt-in via `EMAIL_ENABLED`. When off: no UI, no settings panel, no nav link, no API surface. The substrate forgets email exists. | P1 |
| C7 | Calendar **Manager** CRUD ambitions | Downgrade to read-only viewer in the UI. KEEP the operator-initiated HITL "create event" path. Calendar primarily becomes a `MemorySource` plugin. | P5 |
| C8 | "Family" board hardcode | Remove any code-level references that hardcode a "Family" board, list, or category. Operator-shaped, not product-shaped. | P4 |

### 3.2 Keeps

| ID | Subject | Rationale |
|----|---------|-----------|
| K1 | Briefings (morning / weekly / monthly / quarterly / yearly) | Entice operators to keep up with projects instead of forgetting them while living life. Content reshaped per Phase W: every briefing is backed by an Atlas walk-through with deep-links to specific nodes/spines. Ships to ALL channels per `agents.md` rule 21. |
| K2 | `ZProtocols.ts` | Surfaces "here's what I'm capable of" / possible use cases. Acts as a discovery surface for substrate capabilities, not an operator-managed list. |
| K3 | `HardwareMonitor.ts`, `DiagnosticsWidget.ts`, `SystemBenchmark.ts` | Operator MUST be able to see substrate health on their own hardware. Kept in current location. |

### 3.3 Adds

| ID | Subject | Phase |
|----|---------|-------|
| A1 | MemoryAtlas as home screen, desktop + mobile-optimised, same codebase responsive build, no separate mobile app. | MA1 -> Z |
| A2 | Diff ribbon -- "what changed since you last looked" persistent across every dashboard route. | D |
| A3 | Contradiction detector crew -- raises a contradiction node when new high-weight memory contradicts a high-weight prior. | C |
| A4 | Conversation as primary input -- ChatPrompt is the bottom edge of every screen, not a widget. | MA1 |
| A5 | Walk-throughs -- ADDITIONAL to briefings AND tied into them. Briefings render as walk-throughs. Ad-hoc walk-throughs launchable from any Atlas node. | W |
| A6 | Decision capture as universal verb -- `Cmd/Ctrl+Shift+D` global, mic affordance, new `decisions` node type with `revisit_when` predicate; substrate later surfaces "decision X was made because Y; Y appears no longer to hold." | DC |
| A7 | Steel-manning + echo-finder -- promoted from MA6 to MA2. | MA2 |
| A8 | Agent-to-agent context handoff for company use -- federation extension shipping reasoning slices, not raw data. | H |
| A9 | Universal "why?" query -- `?` keystroke on every Atlas node, spine paragraph, and diff entry returns substrate's justification (source_refs trace + confidence). | Y |
| A10 | Dynamic domain definition -- `domain_inference` crew writes `agent/domain.derived.yaml` (gitignored, substrate-authored, never hand-authored). Replaces `ATLAS_TEMPLATE` config with `ATLAS_TEMPLATE_HINT` (bootstrap-only). Atlas surfaces a "what this instance is becoming" panel for operator confirmation. | DD |

---

## 4. Phase index with cross-references

Phases run in the order shown. Each phase has a one-line summary, the artifact(s) that govern it, and prerequisite phases. A phase closes only when every governance gate in section 8 is green.

| Phase | Summary | Artifact(s) | Prereq | Status |
|-------|---------|-------------|--------|--------|
| P0 | This artifact set lands; remnant audit harness `tests/test_remnant_audit.py` lands with empty forbidden-symbol lists per phase; README essence paragraph applied. | this artifact, all five new artifacts | -- | COMPLETE 2026-05-10 |
| P1 | Email opt-in (`EMAIL_ENABLED`); `ShoppingList.ts` absorbed; i18n trim to `en` + `de`. | this artifact (C3, C5, C6) | P0 | COMPLETE 2026-05-10 |
| P2 | Kill multi-step wizard; collapse to one-screen entry. | this artifact (C4) | P0 | COMPLETE 2026-05-10 |
| P3 | Delete `services/automation.py`; introduce `signal_interpreter` crew (HITL) in `agent/crews.yaml`. | this artifact (C2), `docs/artifacts/full_ambient_intelligence_roadmap.md` | P0 | COMPLETE 2026-05-10 |
| P4 | RIP Person / Circle / inner_circle / CircleManager. No flag. No export. | `docs/artifacts/circle_removal.md` | P0 | COMPLETE 2026-05-10 |
| P5 | Calendar Manager downgrade to read-only viewer; keep HITL "create event"; turn calendar into a `MemorySource`. | this artifact (C7), `docs/artifacts/memory_atlas.md` | MA0 | PENDING -- prereq MA0 |
| MA0 | Atlas foundations: data model, MemorySource plugin contract scaffolding, no UI yet. | `docs/artifacts/memory_atlas.md` | P0..P4 | COMPLETE 2026-05-10 |
| MA1 | Atlas v1: graph lens, list lens (a11y fallback), spine reader; ChatPrompt persistent at bottom edge. | `docs/artifacts/memory_atlas.md` | MA0 | COMPLETE 2026-05-10 |
| MA2 | Recompose operations + steel-manning + echo-finder (promoted). | `docs/artifacts/memory_atlas.md` | MA1 | COMPLETE 2026-05-10 |
| MA3 | Lenses beyond graph (timeline, heatmap, focus, etc. per memory_atlas.md). | `docs/artifacts/memory_atlas.md` | MA2 | IN PROGRESS |
| D | Diff ribbon -- persistent "what changed since you last looked" surface. | `docs/artifacts/memory_atlas.md` (cross-cutting) | MA1 | COMPLETE 2026-05-11 |
| C | Contradiction detector crew + contradiction node type. | `docs/artifacts/memory_atlas.md`, `agent/crews.yaml` | MA1 | COMPLETE 2026-05-11 |
| W | Walk-throughs into briefings; channel-parity delivery. | `docs/artifacts/walkthroughs_and_briefings.md` | MA1 | COMPLETE 2026-05-11 |
| DC | Decision capture verb (`Cmd/Ctrl+Shift+D`, mic), `decisions` node type, `revisit_when` predicate. | `docs/artifacts/memory_atlas.md` | MA1 | COMPLETE 2026-05-11 |
| DD | Dynamic domain definition: `domain_inference` crew, `agent/domain.derived.yaml`, "what this instance is becoming" panel; replaces `ATLAS_TEMPLATE` with `ATLAS_TEMPLATE_HINT`. | `docs/artifacts/dynamic_domain.md` | MA1 | COMPLETE 2026-05-11 |
| Y | Universal "why?" query: `?` keystroke surfaces source_refs trace + confidence on every Atlas node, spine paragraph, diff entry. | `docs/artifacts/memory_atlas.md` (cross-cutting) | MA1, D | COMPLETE 2026-05-11 |
| H | Agent-to-agent context handoff (federation extension shipping reasoning slices). | `docs/artifacts/federated_memory.md`, `docs/artifacts/memory_atlas.md` | MA2 | COMPLETE 2026-05-11 |
| Z | Atlas-as-home: home route = Atlas; responsive mobile build (List lens default on small viewports; Graph lens collapses to touch-friendly cluster view; ChatPrompt persistent at bottom edge). | `docs/artifacts/memory_atlas.md` | MA1..MA3, D, Y | COMPLETE 2026-05-11 |

Phases P1..P5 may be parallelised after P0 if the implementing agent confirms no shared file conflicts. MA / D / C / W / DC / DD / Y / H / Z are sequenced per the prereq column.

---

## 5. Cascade analysis -- what touches what

The riskiest deletions in this pivot are C1 (Person / Circle) and C2 (`automation.py`). Both reach into many files. The full enumeration for C1 is in `docs/artifacts/circle_removal.md`. The summary blast radius:

- **Backend models:** `src/backend/app/models/db.py` (`class Person`, `inner_circle*` columns and tables).
- **Backend services:** `src/backend/app/services/timezone.py` (reads `Person.circle_type == "identity"`), `src/backend/app/services/personal_context.py` (sibling subsystem -- reviewed, not deleted), `src/backend/app/services/memory.py` (review for circle-scoped retrieval), `src/backend/app/services/automation.py` (independently deleted in C2).
- **Backend API routes:** `src/backend/app/api/dashboard.py` lines around `select(Person)`, `/api/dashboard/people`, briefing context assembly referring to `Inner Circle`, regression cleanup paths (`TEST_%` people).
- **Backend tasks:** `src/backend/app/tasks/morning.py` (`inner_circle_tasks`, `get_person_briefing_data`).
- **Backend i18n:** every key matching `circle*`, `inner_circle*`, `outer_circle*`, `social_circles`, `confirm_delete_person`, `aria_add_inner`, `aria_add_person`, `edit_person`, `error_adding_person`, `error_deleting_person`, `step_inner_circle`, `add_to_circle`, `update_person`, `no_people` in every `src/backend/app/services/i18n/*.py` -- removed from `_EN` and `_DE` per Rule 19; the other language dicts disappear entirely under C5.
- **Frontend dashboard:** `src/dashboard/components/CircleManager.ts` (full deletion), `src/dashboard/components/WelcomeOnboarding.ts` (also deleted under C4), `src/dashboard/components/UserCard.ts` (lines using `circle_type=identity` -- migrate to a non-circle identity record per `docs/artifacts/dynamic_domain.md`), `src/dashboard/index.html` (`#section-circles`, `nav_circles`), `src/dashboard/src/main.ts` (lazy import line for `CircleManager`), `src/dashboard/vite.config.ts` (chunk list).
- **Tests:** `tests/test_security_prompt_injection.py` (people/circles adversarial test), any fixture seeding `Person` rows.
- **Docs:** `README.md` ADD_PERSON line, `BUILD.md` if any setup step references circles.
- **Reports:** `src/dashboard/lighthouse-report*` references to `/api/dashboard/people` URLs -- regenerated, not hand-edited.

The `personal_context` service is **not** deleted -- it reads files from `/personal` and is orthogonal to Person/Circle.

For C2 (`automation.py`):

- Direct file deletion of `src/backend/app/services/automation.py`.
- Remove all import sites (grep for `from app.services.automation`).
- Remove any APScheduler registrations referring to automation rules.
- Add `signal_interpreter` crew entry to `agent/crews.yaml` per `docs/artifacts/full_ambient_intelligence_roadmap.md` and the `agent.example/crews.yaml` parity file (rule 4).

---

## 6. Remnant audit harness

A new test file `tests/test_remnant_audit.py` lands in P0 with **empty** forbidden-symbol lists per phase. Each subsequent phase appends its own forbidden-symbol entries before the phase closes. The test fails CI if any forbidden symbol reappears in tracked source.

### 6.1 Design

- Static analysis only (no dynamic imports), per `agents.md` rule 20.
- One `pytest` test per phase, e.g. `test_phase_p4_circle_remnants`, parameterised over symbol categories.
- Scans tracked text files under `src/`, `tests/`, `docs/`, `agent/`, `personal/`, `infrastructure/`, `scripts/`, plus root-level `.md` and `.yaml`. Excludes: `.git/`, `node_modules/`, `dist/`, `pw-browsers/`, `playwright-report/`, `lighthouse-report*`, `__pycache__/`, `.venv/`, generated JSON reports.
- For each forbidden symbol, scans with a non-overlapping regex (per `agents.md` rule 19's anti-backtracking guidance).
- On match, fails with `phase`, `symbol`, `category`, `path`, `line`, and `excerpt`.

### 6.2 File format

A single Python module `tests/test_remnant_audit.py`. Forbidden symbols live as Python literals at the top of the module, grouped by phase:

```python
PHASE_FORBIDDEN: dict[str, dict[str, list[str]]] = {
	"P1_email_optin": {
		"filenames": ["EmailRules.ts"],
		"imports": ["from app.services.email_rules"],
		"identifiers": ["EmailRulesWidget"],
		"i18n_keys": ["email_rule", "email_rules"],
		"api_routes": ["/api/email/rules"],
	},
	"P3_automation_kill": {
		"filenames": ["automation.py"],
		"imports": ["from app.services.automation"],
		"identifiers": ["AutomationRule", "evaluate_rules"],
		"i18n_keys": [],
		"api_routes": ["/api/automation"],
	},
	"P4_circle_rip": {
		"filenames": ["CircleManager.ts"],
		"imports": ["from app.models.db import.*Person"],
		"identifiers": [
			"class Person", "CircleManager", "circle_type",
			"inner_circle", "outer_circle", "social_circles",
			"get_person_briefing_data",
		],
		"i18n_keys": [
			"circles", "circles_empty", "inner_circle", "inner_circle_desc",
			"inner_circle_full", "outer_circle_full", "social_circles",
			"step_inner_circle", "add_to_circle", "update_person",
			"aria_add_inner", "aria_add_person", "aria_delete_person",
			"aria_edit_person", "confirm_delete_person", "edit_person",
			"error_adding_person", "error_deleting_person", "no_people",
			"nav_circles",
		],
		"api_routes": ["/api/dashboard/people", "/api/circle"],
	},
	# Subsequent phases append their own entries here.
}
```

### 6.3 Symbol categories

- `filenames` -- bare filename or basename. The audit fails if any file with this name exists (after the phase's deletion step).
- `imports` -- a regex matched against any `import` or `from ... import ...` line.
- `identifiers` -- a regex matched against any code line. Useful for class names, attribute names, function names, table column names, attribute accesses.
- `i18n_keys` -- exact key string. Matched against `_EN`, `_DE`, and any other populated dict in `src/backend/app/services/i18n/*.py`. Also matched against `this.tr('<key>', ...)` call sites in `src/dashboard/components/**/*.ts`.
- `api_routes` -- exact path prefix. Matched against route decorator strings in `src/backend/app/api/*.py` and against `fetch('<route>...')` call sites in `src/dashboard/**/*.ts`.

### 6.4 Failure mode

Standard pytest assertion failure. CI gate. Implementing agents add forbidden symbols to the relevant phase entry **as part of the same commit that deletes the corresponding code**, so re-introduction is caught immediately.

---

## 7. Channel parity reminder

Per `agents.md` rule 21, every fix to message handling, briefing rendering, walk-through delivery, contradiction surfacing, decision-capture acknowledgement, or "why?" responses MUST land on Telegram, WhatsApp, dashboard, and voice-edge simultaneously. Briefings ship to **all** messengers (operator-confirmed), not only Telegram.

For walk-throughs specifically, the deep-link format `oz://atlas/node/{id}` is rendered:

- **Telegram / WhatsApp:** as a tappable link to a dashboard URL the operator's instance already serves (e.g. `https://<host>/atlas?node=<id>`).
- **Dashboard:** as in-page navigation that focuses the node.
- **Voice-edge:** spoken with a "say `open node` to navigate" affordance.

See `docs/artifacts/walkthroughs_and_briefings.md` for the full per-channel render contract.

---

## 8. Governance gates

Before closing any phase, all of the following must be green and committed:

1. `pytest tests/test_remnant_audit.py -v` (per section 6).
2. `pytest tests/test_i18n_coverage.py -v` (per `agents.md` rule 19).
3. `pytest tests/test_static_analysis.py -v`.
4. `tsc` (dashboard), `ruff check`, `mypy` (backend), all clean.
5. `BUILD.md` audit (per `agents.md` rule 10): any new env var, secret, manual setup step, or service config landed by the phase is reflected.
6. `.example` parity (per `agents.md` rule 4): any structural change to `agent/crews.yaml`, `config.yaml`, `.env`, or `personal/*` has been mirrored into `agent.example/`, `config.example.yaml`, `.env.example`, or `personal.example/`.
7. Artifact update (per `agents.md` rule 13): the phase's governing artifact is updated to mark the phase complete and to record any deviations.

---

## 8b. P0-P4 completion record (2026-05-10)

All governance gates were green at close of P4:

- `test_remnant_audit.py` -- 4/4 PASSED (P1, P2, P3, P4 phases all clean).
- `test_i18n_coverage.py` -- 6/6 PASSED.
- `test_static_analysis.py` -- 12/12 PASSED (4 pre-existing stack-trace-exposure hits fixed in `planka.py` and `intent_router.py`).
- `tsc --noEmit` -- PASSED.
- `BUILD.md` -- audited; no new env vars or manual steps introduced beyond `EMAIL_ENABLED` (already documented in `config.example.yaml`).
- `.example` parity -- `agent.example/crews.yaml` updated with `signal_interpreter` crew.
- Commit: `a7dd84f feat: substrate pivot P0-P4 -- circle/automation removal, i18n trim, email opt-in, instance entry`.

Deviations from plan:
- `WelcomeOnboarding.ts` was renamed to `InstanceEntry.ts` (new custom element `<instance-entry>`) rather than rewritten in-place, because `WelcomeOnboarding.ts` was itself in the P2 forbidden-filename list. This is consistent with the master plan intent.
- `UserCard.ts` identity endpoint migrated to `/api/dashboard/identity` (not `/api/dashboard/people/identity`) so the P4 remnant guard for `/api/dashboard/people` would not fire on the identity route.
- `shopping_list.py` service retained (still has callers in nutrition crew); `circle_type` identity lookup replaced with `Preference` table read.
- Stack-trace-exposure violations in `planka.py` and `intent_router.py` were pre-existing (not introduced by P4) but were fixed in the same commit to keep the static analysis gate green.

Next phase: MA0 (Atlas foundations -- data model, MemorySource plugin contract scaffolding). Prereqs P0..P4 are now all met. Read `docs/artifacts/memory_atlas.md` before starting MA0.

---

## 9. Open questions LEFT for implementing agent

These decisions are deliberately deferred. Implementing agents resolve them in the moment, defaulting to existing repo conventions (`docs/artifacts/DESIGN.md`, `agents.md` rule 18, `agents.md` rule 19) where ambiguous.

- **Postgres table names for new domain inference cache.** Default: `domain_inference_runs`, `domain_signals`. Reuse the `Base.metadata.create_all` + raw startup DDL pattern in `src/backend/app/main.py`; no Alembic.
- **Exact GSAP easing for diff ribbon entrance.** Default: `expo.out` per `agents.md` rule 18 (entrance).
- **HSLA token chain for `--diff-ribbon-*`.** Default: derive from `--accent-*` chain; full `-h`, `-s`, `-l`, `-rgb`, composite per `.github/copilot-instructions.md`.
- **Atlas graph layout library.** Implementing agent picks at MA1 (e.g. `cytoscape`, `d3-force`, custom WebGL). Constraints: zero external network calls, bundle size acceptable to Lighthouse budget in `src/dashboard/lighthouse-prod.json`, accessible List lens fallback ALWAYS available for screen readers.
- **Voice-edge walk-through prosody.** Implementing agent decides at W; defer to `docs/artifacts/voice_edge_pod.md` if it specifies.
- **Confidence threshold for `domain_inference` to auto-publish a derived definition without operator confirmation.** Default: never auto-publish; always show the "what this instance is becoming" panel and require operator confirmation. See `docs/artifacts/dynamic_domain.md`.
- **Exact keystroke binding on macOS vs Linux for decision capture.** Default: `Cmd+Shift+D` on macOS, `Ctrl+Shift+D` on Linux/Windows. Mic affordance always available regardless of platform.
- **Two-step confirm pattern for decision capture and contradiction acknowledgement.** Default: follow the `AgentsWidget *-step1 / *-confirm` pattern referenced in this brief and existing in the dashboard.

---

## 10. Definition of Done (program-level)

The pivot is complete when an operator can:

- Run multiple purpose-shaped instances of openZero (`life-Z`, `work-Z`, `partner-Z`, `fishing-Z`, etc.), each with its own ontology and visual language, on hardware they own.
- Open any instance and find an Atlas as the home screen, both desktop and responsive mobile, in the same codebase.
- Justify any node, spine paragraph, or diff ribbon entry on demand by pressing `?` (Phase Y).
- See contradictions surfaced automatically when new high-weight memory contradicts a high-weight prior (Phase C).
- Receive briefings (morning / weekly / monthly / quarterly / yearly) that double as walk-throughs, on every channel they have configured (Phase W, channel parity rule 21).
- See "what this instance is becoming" without ever hand-authoring an ontology (Phase DD).
- Watch the diff ribbon update across every route to show what changed since they last looked (Phase D).
- Confirm: no surface widget remains in the dashboard that does not earn its keep against the substrate-vs-surface test (`agents.md` rule 22).

---

## 11. README essence update

Apply this paragraph replacement during P0. Find the existing essence prose under `README.md` "What it does" and replace it with the following two paragraphs (no badge changes, no other section changes):

> openZero is a **thinking substrate**, not a tools dashboard. You point an instance at a domain -- a life, a team, a project, a craft -- and the substrate grows a purpose-shaped memory there: it ingests calendar, mail, chats, photos, voice, and any source you give it; it relates and weighs what it learns; it surfaces contradictions, decisions, and changes; and it lets you walk and recompose that memory through a Memory Atlas. The substrate sits underneath the work. Surfaces like Miro, Jira, and Trello put cards on a wall and ask you to do the thinking. openZero builds and maintains the context itself, and you think alongside it.
>
> Every byte stays under your control. The runtime is self-hosted, the model weights are yours to choose (local llama.cpp or any OpenAI-compatible endpoint), the memory backend is open-source (Qdrant), the perimeter is Tailscale, and federation between your own instances ships reasoning slices, not raw data. You can run as many purpose-shaped instances as your hardware supports -- `life-Z`, `work-Z`, `partner-Z`, `fishing-Z` -- each with its own ontology and visual language.
