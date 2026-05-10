# Substrate Pivot -- Decisions Matrix and Cascade Analysis

> The detailed companion to `docs/artifacts/substrate_master_plan.md`. Where the master sequences phases and indexes companions, this artifact is the operator-grade decisions matrix: every cut and every add named with its target file paths, the cascade fan-out across the codebase, the substrate-vs-surface heuristic stated as a tested principle, mobile-first considerations, and per-phase Definition of Done.
> Status: PLAN | Author: conductor | Created: 2026-05-10
> Companions: `docs/artifacts/substrate_master_plan.md`, `docs/artifacts/circle_removal.md`, `docs/artifacts/dynamic_domain.md`, `docs/artifacts/walkthroughs_and_briefings.md`, `docs/artifacts/memory_atlas.md`, `docs/artifacts/full_ambient_intelligence_roadmap.md`, `docs/artifacts/federated_memory.md`, `docs/artifacts/voice_edge_pod.md`, `agents.md`.

---

## 1. Purpose

The master plan ([substrate_master_plan.md](docs/artifacts/substrate_master_plan.md)) tells implementing agents WHAT to ship and IN WHICH ORDER. This artifact tells them WHERE the code lives, WHY each decision was locked, and HOW to validate the cascade before deletion. Read the master first; come here when you need to grep, delete, or wire a specific piece.

---

## 2. The substrate-vs-surface heuristic (tested principle)

The pivot rests on one heuristic that every change in the program must pass:

> For every proposed change, ask: does this make the substrate think better, or does it give the operator another surface to manage? Cut surfaces. Build substrate.

This is enshrined as `agents.md` rule 22. It is not advisory. Implementing agents apply it as a gate:

- **Surface signals**: a new widget that asks the operator to categorise, drag, sort, tag, configure, or "fill in the blanks." A new settings panel. A new "manage X" route. A new wizard step.
- **Substrate signals**: a new MemorySource plugin. A new crew that reasons over existing memory. A new spine summariser pass. A new contradiction or decision detector. A new "why?" hook. A new derivation that shrinks the operator's hand-authored config.

When in doubt, the heuristic resolves toward "build the substrate." Surface affordances are added only when the substrate cannot yet do the work and the operator-managed UI is provably temporary.

---

## 3. Cuts -- with target paths

Every cut below is locked. Re-introducing any of these without an explicit, recorded operator approval in `docs/artifacts/substrate_master_plan.md` violates `agents.md` rule 22.

| ID | Subject | Target paths | Replacement | Phase |
|----|---------|--------------|-------------|-------|
| C1 | Person / Circle subsystem | [src/backend/app/models/db.py](src/backend/app/models/db.py) (`class Person`); [src/backend/app/api/dashboard.py](src/backend/app/api/dashboard.py) (`/api/dashboard/people`, `Inner Circle` blocks); [src/backend/app/services/timezone.py](src/backend/app/services/timezone.py); [src/backend/app/services/agent_actions.py](src/backend/app/services/agent_actions.py); [src/backend/app/services/llm.py](src/backend/app/services/llm.py); [src/backend/app/services/crew_memory.py](src/backend/app/services/crew_memory.py); [src/backend/app/services/ambient/delivery.py](src/backend/app/services/ambient/delivery.py); [src/backend/app/services/translations.py](src/backend/app/services/translations.py) and every populated [src/backend/app/services/i18n](src/backend/app/services/i18n) dict; [src/backend/app/tasks/morning.py](src/backend/app/tasks/morning.py); [src/backend/app/tasks/scheduler.py](src/backend/app/tasks/scheduler.py); [src/dashboard/components/CircleManager.ts](src/dashboard/components/CircleManager.ts); [src/dashboard/components/UserCard.ts](src/dashboard/components/UserCard.ts) (identity row); [src/dashboard/index.html](src/dashboard/index.html); [src/dashboard/src/main.ts](src/dashboard/src/main.ts); [src/dashboard/vite.config.ts](src/dashboard/vite.config.ts) | Substrate-derived people nodes (calendar / mail / chat MemorySources auto-grow person nodes in the Atlas). Identity row migrates to a small `operator_identity` record sourced from `agent/domain.derived.yaml` plus minimal startup-DDL fields. See [docs/artifacts/circle_removal.md](docs/artifacts/circle_removal.md). | P4 |
| C2 | Rule-engine automation | [src/backend/app/services/automation.py](src/backend/app/services/automation.py); import sites in [src/backend/app/tasks/morning.py](src/backend/app/tasks/morning.py); any APScheduler registration referencing it. | New `signal_interpreter` crew in [agent/crews.yaml](agent/crews.yaml). The crew reasons over signals (no keyword list, no `<Name>:` prefix matching, no hardcoded board name) and proposes Planka cards via HITL. | P3 |
| C3 | ShoppingList standalone widget | Any standalone `ShoppingList.ts` Web Component (currently absorbed at backend in [src/backend/app/services/shopping_list.py](src/backend/app/services/shopping_list.py) and the ambient-capture plugin [src/backend/app/services/ambient_capture/plugins/shopping_list.py](src/backend/app/services/ambient_capture/plugins/shopping_list.py)). | Structured `items` field on the nutrition crew briefing slot, rendered inline in the nutrition crew briefing. The standalone surface disappears from the dashboard. The ambient-capture plugin remains as an ingestion path. | P1 |
| C4 | Multi-step onboarding wizard | [src/dashboard/components/WelcomeOnboarding.ts](src/dashboard/components/WelcomeOnboarding.ts); the lazy import in [src/dashboard/src/main.ts](src/dashboard/src/main.ts); the chunk entry in [src/dashboard/vite.config.ts](src/dashboard/vite.config.ts). | Single screen: template hint (`ATLAS_TEMPLATE_HINT`) + one-line "what is this instance for?" + connect-one-source CTA. | P2 |
| C5 | Translations beyond `en` + `de` | Stub language dicts: [src/backend/app/services/i18n/ar.py](src/backend/app/services/i18n/ar.py), [es.py](src/backend/app/services/i18n/es.py), [fr.py](src/backend/app/services/i18n/fr.py), [hi.py](src/backend/app/services/i18n/hi.py), [ja.py](src/backend/app/services/i18n/ja.py), [ko.py](src/backend/app/services/i18n/ko.py), [pt.py](src/backend/app/services/i18n/pt.py), [ru.py](src/backend/app/services/i18n/ru.py), [zh.py](src/backend/app/services/i18n/zh.py); the language selector entries in [src/dashboard/components/UserCard.ts](src/dashboard/components/UserCard.ts); the `_TRANSLATIONS` map in [src/backend/app/services/translations.py](src/backend/app/services/translations.py). | Two languages only: `en`, `de`. Stub languages return when their dicts are populated to parity, not before. | P1 |
| C6 | Email always-on | [src/dashboard/components/EmailRules.ts](src/dashboard/components/EmailRules.ts); any nav link / settings panel / API surface for email when `EMAIL_ENABLED` is unset. Existing dist artefact [src/dashboard/dist/dashboard-assets/lazy-components-CPyScf1t.js](src/dashboard/dist/dashboard-assets/lazy-components-CPyScf1t.js) is regenerated, not hand-edited. | `EMAIL_ENABLED=1` opt-in. When unset: no UI, no nav, no settings, no API surface. The substrate forgets email exists. **Not discoverable when off.** | P1 |
| C7 | Calendar manager CRUD ambitions | Any CRUD-grade endpoints under `src/backend/app/api/` for calendar manager features beyond read + HITL create. Calendar widget in the dashboard stays visible (read-only-ish viewer + HITL event creation). | Calendar becomes a `MemorySource` plugin (read-only ingestion) with a single HITL "create event" path the operator can confirm. Drop the manager-grade ambitions. | P5 |
| C8 | "Family" board hardcode | Any code-level reference that hardcodes a board name, list, or category as `Family` (or any operator-shaped category). | Board names come from operator config or substrate inference. There is no product-shaped board. Operator did not see a `Family` board, so the cleanup is "delete the prefix/keyword logic" rather than a migration. | P4 |

---

## 4. Keeps -- with rationale

| ID | Subject | Why kept | Reshape under pivot |
|----|---------|----------|---------------------|
| K1 | Briefings (morning / weekly / monthly / quarterly / yearly) | Anti-forgetting. Briefings entice the operator to keep up with projects instead of losing them while living life. | Re-rendered as walk-throughs per [docs/artifacts/walkthroughs_and_briefings.md](docs/artifacts/walkthroughs_and_briefings.md). Cadence preserved. Pushed to Telegram + WhatsApp + dashboard + voice-edge per `agents.md` rule 21. |
| K2 | `ZProtocols` widget | Surfaces "here's what I'm capable of" / discovery surface for substrate capabilities -- it advertises substrate, it does not ask the operator to manage anything. | No structural change. |
| K3 | `HardwareMonitor`, `DiagnosticsWidget`, `SystemBenchmark` | Operator MUST be able to see substrate health on their own hardware. | No structural change; kept where they are. |

---

## 5. Adds -- with target paths and dependent companion artifacts

| ID | Subject | Target paths (new or extended) | Dependent companion | Phase |
|----|---------|--------------------------------|---------------------|-------|
| A1 | MemoryAtlas as home screen, desktop + mobile responsive | [src/dashboard/components/MemoryAtlas.ts](src/dashboard/components/MemoryAtlas.ts) (new); [src/dashboard/index.html](src/dashboard/index.html) (root route); [src/dashboard/vite.config.ts](src/dashboard/vite.config.ts); new `src/backend/app/api/atlas.py`. | [docs/artifacts/memory_atlas.md](docs/artifacts/memory_atlas.md) | MA1 -> Z |
| A2 | Diff ribbon -- "what changed since you last looked" persistent across every dashboard route | New Web Component `src/dashboard/components/DiffRibbon.ts`; new `atlas_diffs` table via startup DDL in [src/backend/app/main.py](src/backend/app/main.py); new `services/atlas/diff_engine.py`. Mobile-collapsible to one line. | [docs/artifacts/memory_atlas.md](docs/artifacts/memory_atlas.md) | D |
| A3 | Contradiction detector crew | New crew entry in [agent/crews.yaml](agent/crews.yaml) (mirror in [agent.example/crews.yaml](agent.example/crews.yaml)); new `atlas_contradictions` table; cosine-threshold + stance/sentiment divergence logic in `services/atlas/contradiction_crew.py`. Surfaces in diff ribbon and as Atlas badge. | [docs/artifacts/memory_atlas.md](docs/artifacts/memory_atlas.md) | C |
| A4 | Conversation as primary input -- ChatPrompt persistent at bottom edge | Refactor existing `ChatPrompt.ts` into a persistent layout slot in [src/dashboard/index.html](src/dashboard/index.html); applies on desktop AND mobile. | [docs/artifacts/memory_atlas.md](docs/artifacts/memory_atlas.md) | MA1 |
| A5 | Walk-throughs tied INTO briefings | New `services/walkthroughs.py`, `services/walkthrough_renderer.py`; new `walkthroughs` and `walkthrough_stops` tables; rewire [src/backend/app/tasks/morning.py](src/backend/app/tasks/morning.py), [weekly.py](src/backend/app/tasks/weekly.py), [monthly.py](src/backend/app/tasks/monthly.py), [quarterly.py](src/backend/app/tasks/quarterly.py), [yearly.py](src/backend/app/tasks/yearly.py); add `/walk` to [src/backend/app/api/telegram_bot.py](src/backend/app/api/telegram_bot.py) and [src/backend/app/api/whatsapp.py](src/backend/app/api/whatsapp.py); new `WalkthroughViewer.ts`. **Briefings keep cadence**, are pushed to all messengers per rule 21. | [docs/artifacts/walkthroughs_and_briefings.md](docs/artifacts/walkthroughs_and_briefings.md) | W |
| A6 | Decision capture as universal verb | Global `Cmd/Ctrl+Shift+D` handler in [src/dashboard/src/main.ts](src/dashboard/src/main.ts); mic affordance in `ChatPrompt.ts`; new `decisions` node type with `revisit_when` predicate; new `atlas_decisions` table. Substrate later surfaces "decision X was made because Y; Y appears no longer to hold." | [docs/artifacts/memory_atlas.md](docs/artifacts/memory_atlas.md) | DC |
| A7 | Steel-manning + echo-finder (promoted MA6 -> MA2) | Recompose operations in `services/atlas/recompose.py`; UI surfaces in `MemoryAtlas.ts` lens menu. | [docs/artifacts/memory_atlas.md](docs/artifacts/memory_atlas.md) | MA2 |
| A8 | Agent-to-agent context handoff (company seed) | New endpoint `POST /api/federation/handoff` in `src/backend/app/api/federation.py`; reasoning-slice contract documented in [docs/artifacts/federated_memory.md](docs/artifacts/federated_memory.md). Receiver gets a read-only attributed bundle in their Atlas. | [docs/artifacts/federated_memory.md](docs/artifacts/federated_memory.md), [docs/artifacts/memory_atlas.md](docs/artifacts/memory_atlas.md) | H |
| A9 | Universal "why?" query | `?` keystroke handler on every Atlas node, spine paragraph, and diff ribbon entry; new `justifier` crew in [agent/crews.yaml](agent/crews.yaml); new `atlas_why_traces` table. | [docs/artifacts/memory_atlas.md](docs/artifacts/memory_atlas.md) | Y |
| A10 | Dynamic domain definition | New `domain_inference` crew in [agent/crews.yaml](agent/crews.yaml); writes `agent/domain.derived.yaml` (gitignored, never hand-authored); new `domain_inference_runs` and `domain_signals` tables; new "what this instance is becoming" panel in `MemoryAtlas.ts`. Replaces `ATLAS_TEMPLATE` with `ATLAS_TEMPLATE_HINT` (bootstrap-only). | [docs/artifacts/dynamic_domain.md](docs/artifacts/dynamic_domain.md) | DD |

---

## 6. Cascade analysis

The riskiest deletions reach across many files. Implementing agents must grep before they delete. The full Phase P4 enumeration lives in [docs/artifacts/circle_removal.md](docs/artifacts/circle_removal.md); this section captures the cross-phase fan-out the master indexes only at summary level.

### 6.1 Person / Circle (C1) -- complete touchpoint list

A workspace grep on 2026-05-10 revealed touchpoints beyond the original deletion plan. The implementing agent in P4 confirms with a fresh grep before deleting and updates [docs/artifacts/circle_removal.md](docs/artifacts/circle_removal.md) to reflect any drift.

**Backend models**

- [src/backend/app/models/db.py](src/backend/app/models/db.py) -- `class Person` and any `inner_circle_*` join tables.

**Backend services**

- [src/backend/app/services/timezone.py](src/backend/app/services/timezone.py) -- `Person.circle_type == "identity"` lookup. Migrate to `operator_identity`.
- [src/backend/app/services/agent_actions.py](src/backend/app/services/agent_actions.py) -- references to `Person` action vocabulary (`ADD_PERSON` etc.). Remove from allowlist.
- [src/backend/app/services/llm.py](src/backend/app/services/llm.py) -- any system-prompt fragment enumerating circle members. Replace with substrate-derived people nodes from the Atlas.
- [src/backend/app/services/crew_memory.py](src/backend/app/services/crew_memory.py) -- circle-scoped memory retrieval branches. Replace with topic / spine retrieval.
- [src/backend/app/services/ambient/delivery.py](src/backend/app/services/ambient/delivery.py) -- circle-scoped delivery routing. Replace with substrate routing per the unified pending-action queue.
- [src/backend/app/services/translations.py](src/backend/app/services/translations.py) -- legacy `_TRANSLATIONS` map and any `circle*` keys. **Cascade-finding:** this file is parallel to `services/i18n/*.py`; both must be cleaned in P1 (translation trim) AND P4 (circle key removal).
- [src/backend/app/services/memory.py](src/backend/app/services/memory.py) -- audit only; remove any circle-scoped retrieval if present.
- [src/backend/app/services/personal_context.py](src/backend/app/services/personal_context.py) -- audit only; the file itself is NOT deleted (reads `/personal/*.md` operator prose).

**Backend API**

- [src/backend/app/api/dashboard.py](src/backend/app/api/dashboard.py) -- `/api/dashboard/people` route family, `Inner Circle` system-prompt fragment, briefing-context block, regression cleanup of `TEST_%` people, `circles` onboarding step entry.

**Backend tasks**

- [src/backend/app/tasks/morning.py](src/backend/app/tasks/morning.py) -- `inner_circle_tasks`, `get_person_briefing_data`. Replace per [docs/artifacts/walkthroughs_and_briefings.md](docs/artifacts/walkthroughs_and_briefings.md).
- [src/backend/app/tasks/scheduler.py](src/backend/app/tasks/scheduler.py) -- **Cascade-finding:** any APScheduler registration referencing person/circle helpers. Audit and remove.

**Backend i18n**

- Every populated dict under [src/backend/app/services/i18n/](src/backend/app/services/i18n/) -- after P1 only `en.py` and `de.py` survive; this phase deletes `circles*`, `inner_circle*`, `outer_circle*`, `social_circles`, `step_inner_circle`, `add_to_circle`, `update_person`, `aria_add_inner`, `aria_add_person`, `aria_delete_person`, `aria_edit_person`, `confirm_delete_person`, `edit_person`, `error_adding_person`, `error_deleting_person`, `no_people`, `nav_circles`.

**Frontend dashboard**

- [src/dashboard/components/CircleManager.ts](src/dashboard/components/CircleManager.ts) -- full file deletion.
- [src/dashboard/components/WelcomeOnboarding.ts](src/dashboard/components/WelcomeOnboarding.ts) -- already deleted in C4 / Phase P2; if P2 ran first, this is already gone.
- [src/dashboard/components/UserCard.ts](src/dashboard/components/UserCard.ts) -- remove `circle_type=identity` fetch and POST body; migrate to `operator_identity` per [docs/artifacts/dynamic_domain.md](docs/artifacts/dynamic_domain.md).
- [src/dashboard/index.html](src/dashboard/index.html) -- nav links and `<section id="section-circles">` block.
- [src/dashboard/src/main.ts](src/dashboard/src/main.ts) -- lazy import of `CircleManager`.
- [src/dashboard/vite.config.ts](src/dashboard/vite.config.ts) -- chunk entry for `CircleManager`.

**Tests**

- [tests/test_security_prompt_injection.py](tests/test_security_prompt_injection.py) -- people / circles adversarial test rewritten as a memory-injection test (the attack class still applies once names enter via MemorySource ingestion).
- Any pytest fixture seeding `Person` rows -- delete.

**Docs**

- [README.md](README.md) -- `ADD_PERSON` row in the action vocabulary table.
- [BUILD.md](BUILD.md) -- audit for any setup step referencing circles.

### 6.2 `automation.py` (C2) -- touchpoints

- [src/backend/app/services/automation.py](src/backend/app/services/automation.py) -- delete.
- [src/backend/app/tasks/morning.py](src/backend/app/tasks/morning.py) -- import sites; remove and replace with `signal_interpreter` crew dispatch.
- [agent/crews.yaml](agent/crews.yaml) and [agent.example/crews.yaml](agent.example/crews.yaml) -- add the `signal_interpreter` crew entry per [docs/artifacts/full_ambient_intelligence_roadmap.md](docs/artifacts/full_ambient_intelligence_roadmap.md).
- No `Family` board hardcode was found in the workspace at audit time; the `signal_interpreter` crew design must not introduce one.

### 6.3 ShoppingList (C3) -- touchpoints

- [src/backend/app/services/shopping_list.py](src/backend/app/services/shopping_list.py) -- backend service; remains as an ingestion target for the nutrition crew.
- [src/backend/app/services/ambient_capture/plugins/shopping_list.py](src/backend/app/services/ambient_capture/plugins/shopping_list.py) -- ambient capture plugin; remains.
- Any standalone `ShoppingList.ts` Web Component -- delete (none currently registered in [src/dashboard/src/main.ts](src/dashboard/src/main.ts) under that name; audit before deletion).
- The nutrition crew briefing slot in `WalkthroughStop.payload` gains a structured `items` field; rendered inline by `WalkthroughViewer.ts`.

### 6.4 EmailRules (C6) -- touchpoints

- [src/dashboard/components/EmailRules.ts](src/dashboard/components/EmailRules.ts) -- delete unless `EMAIL_ENABLED=1`.
- [src/dashboard/src/main.ts](src/dashboard/src/main.ts) -- lazy import; gate behind a build-time check or runtime feature flag that is FALSE by default.
- [src/dashboard/vite.config.ts](src/dashboard/vite.config.ts) -- chunk entry; remove from default build.
- [src/dashboard/dist/dashboard-assets/lazy-components-CPyScf1t.js](src/dashboard/dist/dashboard-assets/lazy-components-CPyScf1t.js) -- regenerated by build, not hand-edited.
- The opt-in MUST NOT be discoverable when off: no settings panel, no nav link, no API surface.

### 6.5 WelcomeOnboarding (C4) -- touchpoints

- [src/dashboard/components/WelcomeOnboarding.ts](src/dashboard/components/WelcomeOnboarding.ts) -- collapse to one screen (template hint + "what is this instance for?" + connect-one-source CTA). Multi-step wizard removed.
- [src/dashboard/src/main.ts](src/dashboard/src/main.ts) -- lazy import remains, points at the collapsed component.
- [src/dashboard/vite.config.ts](src/dashboard/vite.config.ts) -- chunk entry remains.

### 6.6 Calendar manager (C7) -- touchpoints

- Workspace grep on 2026-05-10 found no `/api/calendar/*` CRUD routes in [src/backend/app/api/](src/backend/app/api/). The cleanup is therefore confined to the dashboard widget downgrade and the `MemorySource` wiring per [docs/artifacts/memory_atlas.md](docs/artifacts/memory_atlas.md) section 6.

### 6.7 Surprising findings flagged for operator decision

- **Two parallel translation surfaces.** [src/backend/app/services/translations.py](src/backend/app/services/translations.py) coexists with [src/backend/app/services/i18n/](src/backend/app/services/i18n/) per-language modules. The repo convention enshrined in `agents.md` rule 19 references `_EN`, `_DE`, and the i18n test gate, but the actual file layout is split. Implementing agents in P1 must clean BOTH and then either delete `translations.py` or document why it remains. Operator may want to confirm which is canonical before P1 lands.
- **`ShoppingList` has no standalone Web Component currently registered.** The "absorb into nutrition crew" cut (C3) therefore reduces to (a) confirming no widget exists in the dashboard nav, (b) wiring the nutrition crew briefing slot to render the structured `items`. No deletion of a `ShoppingList.ts` file is required at audit time -- but the implementing agent confirms with a fresh grep.
- **No calendar manager CRUD endpoints found.** C7's "downgrade" is therefore primarily a dashboard widget reshape, not a backend API removal. The `MemorySource` wiring is the larger work item.
- **`scheduler.py` references circle helpers.** Originally not enumerated in [docs/artifacts/circle_removal.md](docs/artifacts/circle_removal.md); now added to the cascade list above. Implementing agent updates that artifact when P4 lands.

---

## 7. Phase plan with per-phase Definition of Done

The canonical phase index is in [docs/artifacts/substrate_master_plan.md](docs/artifacts/substrate_master_plan.md) section 4. This section restates each phase with its operator-observable Definition of Done.

| Phase | Definition of Done |
|-------|--------------------|
| P0 | This artifact set is committed. `tests/test_remnant_audit.py` lands with empty forbidden-symbol lists per phase. README essence paragraph applied. `agents.md` rule 22 lands. `BUILD.md` records the new env vars introduced by the pivot (none yet at P0). All quality gates green. |
| P1 | `EMAIL_ENABLED` documented and respected (off by default; no UI when off). ShoppingList absorbed into nutrition crew briefing slot. i18n trimmed to `en` + `de`. `pytest tests/test_i18n_coverage.py -v` green with the trimmed dict set. Remnant audit P1 entry populated. |
| P2 | One-screen onboarding ships. Multi-step wizard removed. axe-clean. i18n keys for old wizard steps removed from `_EN`/`_DE`. Remnant audit P2 entry populated. |
| P3 | `automation.py` deleted. `signal_interpreter` crew added to `crews.yaml` (and example mirror). HITL Planka card creation works end-to-end on Telegram + WhatsApp + dashboard + voice-edge (channel parity rule 21). Remnant audit P3 entry populated. |
| P4 | Person / Circle subsystem fully removed per [docs/artifacts/circle_removal.md](docs/artifacts/circle_removal.md). `pytest tests/test_remnant_audit.py::test_phase_p4_circle_rip -v` green. Briefings render the substrate-derived pattern across all four channels. `BUILD.md` and `README.md` updated. |
| P5 | Calendar widget downgraded to read-only-ish viewer with HITL "create event." Calendar `MemorySource` plugin online and ingesting. Remnant audit P5 entry populated. |
| MA0..MA3 | Per [docs/artifacts/memory_atlas.md](docs/artifacts/memory_atlas.md) section 12. |
| D | Diff ribbon ships across every dashboard route, mobile-collapsible to a single line. axe-clean. |
| C | Contradiction crew detects + raises contradiction nodes; surfaces in diff ribbon and Atlas badge. |
| W | Briefings render as walk-throughs on all four channels (rule 21). Ad-hoc walk-throughs launchable from any Atlas node. |
| DC | `Cmd/Ctrl+Shift+D` global keystroke + mic affordance create `decisions` nodes. `revisit_when` predicate evaluation triggers walk-through inclusion. |
| H | `POST /api/federation/handoff` ships reasoning slices; receiver instance shows read-only attributed Atlas bundles. No raw memory points cross instance boundaries (security test enforces). |
| Y | `?` keystroke / button on every Atlas node, spine paragraph, and diff ribbon entry returns `source_refs` + `confidence` + short prose. |
| DD | `domain_inference` crew online, lowest-priority lane, writes `agent/domain.derived.yaml` (gitignored). `ATLAS_TEMPLATE` references gone; `ATLAS_TEMPLATE_HINT` documented in `BUILD.md` and `.env.example`. "What this instance is becoming" panel renders with confirm/override two-step flow. |
| Z | Atlas is the home route on `/`. Same codebase serves desktop and mobile via responsive build. List lens default on small viewports. ChatPrompt persistent at bottom edge on every screen. Lighthouse budget honoured. axe-clean across breakpoints. |

---

## 8. Mobile-first considerations

The pivot ships one codebase that serves desktop and mobile via responsive build. There is no separate mobile app. Implementing agents in Phase Z (and in any earlier phase that adds a UI surface) follow these constraints:

- **Default lens on `< 768px`**: List lens. Graph lens collapses to a touch-friendly cluster view (nodes grouped by spine, swipe between spines).
- **Diff ribbon mobile**: collapses to a single icon with badge; expanded view is a full-screen drawer. Persistent across every route.
- **"What this instance is becoming" panel mobile**: bottom drawer instead of right rail.
- **ChatPrompt mobile**: persistent bottom edge; viewport-fit and safe-area inset handled by the existing pattern.
- **Touch targets**: minimum 44x44 px per `agents.md` rule 12. No hover-only affordances.
- **Reduced motion**: every component includes `@media (prefers-reduced-motion: reduce)` per `agents.md` rule 12.
- **Forced colors**: every component includes `@media (forced-colors: active)` per `agents.md` rule 12.
- **Bundle**: stays inside [src/dashboard/lighthouse-prod.json](src/dashboard/lighthouse-prod.json) budget. Lazy-load every Atlas lens via the existing Vite chunk-split pattern in [src/dashboard/vite.config.ts](src/dashboard/vite.config.ts).
- **Zero external dependencies**: no CDN, no external font, no external tile server. Sovereign-by-default.

---

## 9. i18n hygiene reminder

Per `agents.md` rule 19, every user-facing string introduced by this pivot -- including ARIA labels, placeholders, titles, and visible text -- MUST go through `this.tr('key', 'English fallback')`. Keys land in [src/backend/app/services/i18n/en.py](src/backend/app/services/i18n/en.py) and [src/backend/app/services/i18n/de.py](src/backend/app/services/i18n/de.py) at minimum. The legacy [src/backend/app/services/translations.py](src/backend/app/services/translations.py) surface is cleaned in P1; until then, BOTH paths must stay in parity. After every i18n change, run `pytest tests/test_i18n_coverage.py -v` locally before committing.

Stub languages (`ar`, `es`, `fr`, `hi`, `ja`, `ko`, `pt`, `ru`, `zh`) are removed entirely in P1 along with the `UserCard.ts` selector entries. They return when their dicts are populated to parity, not before.

---

## 10. Channel parity reminder

Per `agents.md` rule 21, every fix to message handling, briefing rendering, walk-through delivery, contradiction surfacing, decision-capture acknowledgement, or "why?" responses MUST land on Telegram, WhatsApp, dashboard, and voice-edge simultaneously. The three foundational channels:

- **Telegram** -- [src/backend/app/api/telegram_bot.py](src/backend/app/api/telegram_bot.py)
- **WhatsApp** -- [src/backend/app/api/whatsapp.py](src/backend/app/api/whatsapp.py)
- **Dashboard** -- [src/backend/app/api/dashboard.py](src/backend/app/api/dashboard.py)

Voice-edge is the fourth, per [docs/artifacts/voice_edge_pod.md](docs/artifacts/voice_edge_pod.md). Briefings (K1) ship to ALL of them on schedule -- not Telegram-only. The `/walk` command in Phase W lands on Telegram and WhatsApp in the same commit.

---

## 11. No-Alembic schema discipline

Per repo convention (and `agents.md` general project layout), all new tables introduced by this pivot follow the startup-DDL pattern: `Base.metadata.create_all` in [src/backend/app/main.py](src/backend/app/main.py) plus raw `ALTER TABLE` / `DROP TABLE IF EXISTS` blocks in the same startup hook. No Alembic migrations. Implementing agents add the DDL in the same commit that introduces the SQLAlchemy model.

New tables (cumulative across the pivot): `atlas_nodes`, `atlas_edges`, `atlas_spines`, `atlas_spine_members`, `atlas_spine_summaries`, `atlas_decisions`, `atlas_contradictions`, `atlas_diffs`, `atlas_why_traces`, `domain_inference_runs`, `domain_signals`, `walkthroughs`, `walkthrough_stops`, `operator_identity`. Tables to drop: `persons`, `inner_circle_*` (any auxiliary join tables).

---

## 12. Definition of Done (pivot-level)

Per [docs/artifacts/substrate_master_plan.md](docs/artifacts/substrate_master_plan.md) section 10. Restated here for the deep-dive reader's convenience: the operator can run multiple purpose-shaped instances, the Atlas is the home screen on desktop and mobile, "why?" works everywhere, contradictions surface automatically, decisions persist with `revisit_when`, briefings ship as walk-throughs on every channel, the substrate authors its own ontology (no hand-authored `ATLAS_TEMPLATE`), the diff ribbon shows what changed, federation ships reasoning slices, and no surface widget remains that does not earn its keep against `agents.md` rule 22.

---

## 13. How this composes with the rest of the artifact set

- [docs/artifacts/substrate_master_plan.md](docs/artifacts/substrate_master_plan.md) -- the orchestration / phase sequence / governance gates. Read first.
- [docs/artifacts/circle_removal.md](docs/artifacts/circle_removal.md) -- the deep-dive on Phase P4. The cascade in section 6.1 above is its summary; the artifact is the operator-grade enumeration.
- [docs/artifacts/dynamic_domain.md](docs/artifacts/dynamic_domain.md) -- Phase DD detail; how `ATLAS_TEMPLATE_HINT` bootstraps and how the substrate self-defines after.
- [docs/artifacts/walkthroughs_and_briefings.md](docs/artifacts/walkthroughs_and_briefings.md) -- Phase W detail; the briefing-as-walk-through redesign with channel parity rendering contracts.
- [docs/artifacts/memory_atlas.md](docs/artifacts/memory_atlas.md) -- the substrate's blueprint; lenses, recompose ops, MemorySource contract, mobile responsive design.
- [docs/artifacts/full_ambient_intelligence_roadmap.md](docs/artifacts/full_ambient_intelligence_roadmap.md) -- the ambient ingestion / state-diff foundations the Atlas consumes.
- [docs/artifacts/federated_memory.md](docs/artifacts/federated_memory.md) -- the cross-instance transport for Phase H.
- [docs/artifacts/voice_edge_pod.md](docs/artifacts/voice_edge_pod.md) -- voice MemorySource and walk-through prosody.
