# Memory Atlas

> The substrate's navigable surface over its own memory. The Atlas is the home screen (Phase Z, desktop and responsive mobile in the same codebase). Operators walk and recompose memory through nine lenses (with List as the accessibility fallback). MemorySource plugins ingest signals; spines summarise continuously; the diff ribbon and the universal "why?" hook are cross-cutting Atlas surfaces. This artifact is the substrate's blueprint.
> Status: MA3 IN PROGRESS | Author: conductor | Created: 2026-05-10 | Updated: 2026-05-10
> Companions: `docs/artifacts/substrate_master_plan.md`, `docs/artifacts/dynamic_domain.md`, `docs/artifacts/walkthroughs_and_briefings.md`, `docs/artifacts/circle_removal.md`, `docs/artifacts/federated_memory.md`, `docs/artifacts/voice_edge_pod.md`, `docs/artifacts/full_ambient_intelligence_roadmap.md`, `docs/artifacts/DESIGN.md`.

---

## 1. Objective

Make memory walkable. Today the substrate has Qdrant points, Postgres rows, and channel-bound chat history; none of it is presentable as a coherent surface the operator can navigate. The Memory Atlas is that surface. It does not become the place where thinking lives -- the substrate still does the thinking -- but it is where the operator confirms, refines, recomposes, and walks the substrate's reasoning.

The Atlas is the home screen of every openZero instance (Phase Z). The same codebase serves desktop and mobile via responsive build (no separate mobile app). ChatPrompt sits as the persistent bottom edge of every Atlas view (per master artifact A4): the operator's primary input is conversation, not a widget grid.

---

## 2. Design principles

- **Substrate first.** Every Atlas affordance must satisfy `agents.md` rule 22. If a surface asks the operator to do work the substrate could do (categorise, sort, prioritise, tag), it does not ship.
- **One memory, many lenses.** The data model is one graph. Lenses are projections. No lens duplicates state.
- **Justifiable on demand.** Every node, spine paragraph, and diff ribbon entry exposes the universal "why?" hook (Phase Y) that returns `source_refs` and `confidence`.
- **Conversation-first.** ChatPrompt is the bottom edge of every screen. Atlas affordances complement conversation; they do not replace it.
- **Sovereign.** No external CDN, no external font, no external tile server. Bundle stays inside the dashboard's Lighthouse budget (`src/dashboard/lighthouse-prod.json`).
- **Accessible by default.** The List lens is the WCAG 2.1 AA fallback for every other lens; if a lens cannot be made accessible, the List lens replaces it on screen readers and reduced-motion contexts.
- **Per-instance ontology.** The Atlas reads `agent/domain.derived.yaml` (per `docs/artifacts/dynamic_domain.md`) for spines, node types, and visual language. There is no static `ATLAS_TEMPLATE` config -- the previous design's `ATLAS_TEMPLATE` is replaced by `ATLAS_TEMPLATE_HINT` (bootstrap-only).

---

## 3. Instance templates

Per master artifact section 1, the operator may run multiple purpose-shaped instances (`life-Z`, `work-Z`, `partner-Z`, `fishing-Z`). Each instance:

- Has its own Postgres schema, Qdrant collection namespace, `agent/` tree, and `personal/` tree.
- Has its own `agent/domain.derived.yaml` -- the substrate-authored ontology for this instance.
- Has its own visual language (`visual_language.palette_seed` from the derived definition; the dashboard's theme picker honours it).
- Receives only one bootstrap input: `ATLAS_TEMPLATE_HINT` (e.g. `team`, `family`, `marriage`, `craft`). After the first inference run the hint becomes irrelevant; the substrate self-defines.

Cross-instance reasoning (e.g. "I want my work-Z to know that life-Z said I'm taking next week off") is mediated by federation per `docs/artifacts/federated_memory.md`, extended with agent-to-agent context handoff in Phase H. Federation ships **reasoning slices** -- substrate-summarised statements with `source_refs` and `confidence` -- not raw memory points.

---

## 4. Backend architecture

```
+--------------------+     +-------------------+     +---------------------+
| MemorySource[N]    |---->| Ingestion bus     |---->| Memory store        |
| (calendar, mail,   |     | (existing message |     | - Qdrant (semantic) |
|  chat, voice,      |     |  bus + new        |     | - Postgres (graph,  |
|  vision, file...)  |     |  source adapters) |     |    spines, decisions)|
+--------------------+     +-------------------+     +----------+----------+
                                                                |
                                  +-----------------------------+
                                  |
                                  v
                       +---------------------+
                       | Atlas services      |
                       | - spine summariser  |
                       | - contradiction crew|
                       | - decision capture  |
                       | - domain inference  |
                       | - diff engine       |
                       | - "why?" service    |
                       +---------+-----------+
                                 |
                                 v
                       +---------------------+      +----------------+
                       | /api/atlas/*        |<---->| MemoryAtlas    |
                       | (FastAPI)           |      | dashboard      |
                       +---------------------+      | component      |
                                                    +----------------+
```

- **MemorySource plugins** ingest signals into the unified ingestion bus (extends today's bus from `services/ambient_capture/`). Calendar (per Phase P5), mail (when `EMAIL_ENABLED=1`), chat (existing channels), voice (via voice-edge), vision (existing `services/vision.py` per `docs/artifacts/multimodal_vision.md`), files (`/personal`), and any future source plug into the same contract.
- **Memory store** is dual: Qdrant for semantic retrieval (existing), Postgres for the navigable graph, spines, decisions, contradictions, walk-throughs, domain inference cache. New tables created via startup DDL in `src/backend/app/main.py` (no Alembic).
- **Atlas services** are the substrate's thinkers -- spine summariser (continuous), contradiction crew (Phase C), decision capture (Phase DC), domain inference (Phase DD), diff engine (Phase D), "why?" service (Phase Y).
- **/api/atlas/* routes** expose the navigable surface to the MemoryAtlas dashboard component and to the channel renderers.

---

## 5. Data model

Postgres tables (created via startup DDL):

- `atlas_nodes(id pk, type, label, payload jsonb, confidence float, created_at, updated_at, last_mentioned_at)`
- `atlas_edges(id pk, source_node_id fk, target_node_id fk, kind, weight float, payload jsonb, created_at)`
- `atlas_spines(id pk, label, confidence float, payload jsonb, derived bool, locked bool, updated_at)` -- `derived` flags substrate-authored vs operator-confirmed.
- `atlas_spine_members(spine_id fk, node_id fk, weight float, primary key (spine_id, node_id))`
- `atlas_spine_summaries(spine_id fk, generated_at, summary_text, source_refs jsonb)`
- `atlas_decisions(id pk, node_id fk, made_at, rationale, revisit_when text, status enum('open','revisit_due','resolved'), payload jsonb)` -- per Phase DC.
- `atlas_contradictions(id pk, primary_node_id fk, opposing_node_id fk, detected_at, status enum('open','dismissed','resolved'), payload jsonb)` -- per Phase C.
- `atlas_diffs(id pk, node_id fk nullable, spine_id fk nullable, kind, since, until, summary, payload jsonb)` -- per Phase D.
- `atlas_why_traces(id pk, subject_kind, subject_id, generated_at, source_refs jsonb, confidence float)` -- cached "why?" traces per Phase Y.
- `domain_inference_runs`, `domain_signals` -- per `docs/artifacts/dynamic_domain.md`.
- `walkthroughs`, `walkthrough_stops` -- per `docs/artifacts/walkthroughs_and_briefings.md`.

Qdrant collections (existing semantic memory) gain a `node_id` payload field linking points back to their `atlas_node` row. Existing memory points are linked lazily on first read.

Node `type` values are seeded by `agent/domain.derived.yaml.node_types` plus a small set of substrate primitives: `memory`, `decision`, `contradiction`, `source`, `instance`. Operator-derived types (e.g. `project`, `person`) come from the derived definition.

---

## 6. MemorySource plugin contract

A single Python `Protocol` lives in `src/backend/app/services/atlas/sources.py`:

```python
class MemorySource(Protocol):
	source_id: str

	async def discover(self) -> AsyncIterator["RawSignal"]:
		"""Yield new raw signals since the last cursor."""

	async def normalise(self, raw: "RawSignal") -> "AtlasIngest":
		"""Convert a raw signal into one or more atlas_nodes + edges."""

	async def cursor(self) -> str: ...
	async def advance_cursor(self, to: str) -> None: ...
```

Existing services become MemorySource plugins:

- `services/calendar.py` -> `CalendarSource` (read-only by Phase P5; HITL "create event" path stays).
- `services/gmail.py` -> `GmailSource` (only registered when `EMAIL_ENABLED=1`, per master C6).
- `services/vision.py` -> `VisionSource` (image -> structured node).
- `services/personal_context.py` -> `PersonalFolderSource` (files in `/personal`).
- Channel handlers (`telegram_bot.py`, `whatsapp.py`, dashboard chat) -> `ConversationSource`.
- Voice-edge -> `VoiceSource` (per `docs/artifacts/voice_edge_pod.md`).

Plugins MUST sanitise via the shared `services/security/sanitisers.py` (per `docs/artifacts/full_ambient_intelligence_roadmap.md` Phase A) before yielding signals. Any plugin that produces text for ingestion is treated as untrusted-content origin per the existing security posture.

---

## 7. MemoryAtlas dashboard component

Single Web Component `src/dashboard/components/MemoryAtlas.ts`. Shadow DOM, `${ACCESSIBILITY_STYLES}`, `this.tr()` for every user-visible string, HSLA `var(--token, fallback)` colours, `rem` for spacing, full design-token chains per `docs/artifacts/DESIGN.md` and `agents.md` rule 18.

### 7.1 Lenses

Nine lenses plus the List accessibility fallback:

| ID | Lens | Best for | Notes |
|----|------|----------|-------|
| 1 | **Graph** | Topology, relationships | Default on desktop. Implementing agent picks layout library at MA1 (master artifact section 9). |
| 2 | **List** | Linear scan, accessibility | a11y fallback for every other lens. Default on small viewports per Phase Z. |
| 3 | **Timeline** | Temporal sequencing | Per-spine and global. |
| 4 | **Heatmap** | Density, recency | Calendar-grid style; intensity = confidence x recency. |
| 5 | **Focus** | Single-node deep dive | Node + first-degree neighbours + source_refs panel. |
| 6 | **Spines** | Topic-paragraph reader | Spine summariser output, paragraph-by-paragraph; each paragraph has its own "why?". |
| 7 | **Decisions** | Open/revisit-due/resolved kanban-style view | Phase DC. |
| 8 | **Contradictions** | Unresolved/dismissed list | Phase C. |
| 9 | **Diffs** | Change feed | Powers the persistent diff ribbon (Phase D). |

Lens switching preserves selection and filter state. Each lens is a sub-Web-Component lazy-loaded via the existing Vite chunk split pattern (`src/dashboard/vite.config.ts`).

### 7.2 Cross-cutting Atlas surfaces

These cut across every lens and every node:

- **Diff ribbon** (Phase D): persistent strip across the top of every dashboard route (Atlas home and elsewhere). Surfaces "what changed since you last looked." Each entry has `oz://atlas/...` deep-link, "why?" hook, dismiss action.
- **Universal "why?" hook** (Phase Y): `?` keystroke on any focused Atlas node, spine paragraph, or diff entry returns the substrate's justification (cached `atlas_why_traces` row: source_refs + confidence + a short prose explanation).
- **ChatPrompt persistent bottom edge** (master A4): conversation as primary input; the operator can ask "tell me more about Markus" without leaving the lens.
- **"What this instance is becoming" panel** (per `docs/artifacts/dynamic_domain.md`): right rail on desktop, drawer on mobile.
- **Decision capture verb** (Phase DC): `Cmd/Ctrl+Shift+D` global keystroke; mic affordance; opens a minimal capture overlay; persists a `decisions` node with `revisit_when` predicate.

### 7.3 Mobile responsive (Phase Z)

Same codebase. Same component. Breakpoint-driven adjustments only:

- Default lens on `< 768px` viewport: List.
- Graph lens collapses to a touch-friendly cluster view (nodes grouped by spine, swipe between spines).
- Diff ribbon collapses to a single icon with badge; expanded view is a full-screen drawer.
- "What this instance is becoming" panel is a bottom drawer instead of a right rail.
- ChatPrompt remains persistent at the bottom edge; the keyboard inset is handled by the existing viewport-fit pattern.
- All min 44x44 px touch targets retained per `agents.md` rule 12.

---

## 8. Recompose operations

Operator-driven, substrate-validated. Every recompose action MUST satisfy the substrate-vs-surface heuristic: it's an operator confirming substrate-proposed changes, not arranging cards. Two-step confirm pattern (`AgentsWidget *-step1 / *-confirm`) for any destructive recompose.

- **Merge nodes** -- substrate proposes when two nodes have high semantic similarity and overlapping `source_refs`; operator confirms.
- **Split node** -- substrate proposes when a single node accumulates evidence pointing to two clearly-separable referents; operator confirms.
- **Promote/demote spine** -- operator can lock or rename a spine via the "what this instance is becoming" panel (per `docs/artifacts/dynamic_domain.md`).
- **Steel-man** (Phase MA2, **promoted from MA6**): operator selects a node or spine; substrate generates the strongest counter-argument from existing memory; result becomes a `contradiction` candidate (resolvable into a confirmed `contradiction` node or dismissed).
- **Echo-finder** (Phase MA2, **promoted from MA6**): operator selects a memory point; substrate finds semantically near-duplicate prior memory and surfaces the chain; operator can merge, mark superseded, or accept as a recurring theme.
- **Re-tag with current domain** -- when `agent/domain.derived.yaml` updates with new node types, operator can confirm a substrate-proposed re-tag of historical nodes.

All recompose operations write `atlas_diffs` rows so the diff ribbon (Phase D) reflects them and the next walk-through can include them.

---

## 9. Continuous spine summariser

A background service `services/atlas/spine_summariser.py`:

- Runs in the lowest-priority lane (alongside `domain_inference`, never preempts foreground LLM tier).
- Re-summarises a spine when its member set changes by `>= 5%` since the last summary or when `>= 24h` have passed.
- Reads `agent/domain.derived.yaml` to know which spines exist.
- Produces an `atlas_spine_summaries` row: `summary_text` (paragraph-grade prose) + `source_refs` (every paragraph's evidence).
- Each paragraph is the unit of "why?" justification (Phase Y) -- the operator can press `?` on any paragraph in the Spines lens.

---

## 10. Federation -- cross-instance spines

Per `docs/artifacts/federated_memory.md`, extended in Phase H:

- Federation publishes a **spine slice**: `{spine_id, summary_text, source_refs (redacted), confidence, instance_id}`.
- Receiving instance can opt-in per spine; published spines appear as a special `external_spine` lens entry, visually distinguished from local spines.
- No raw memory points cross instance boundaries. Reasoning slices only.
- Channel parity (rule 21) applies: a federation event surfaces in the diff ribbon, the next walk-through, and any active channel.

---

## 11. Configuration

- **`ATLAS_TEMPLATE_HINT`** -- bootstrap-only string; see `docs/artifacts/dynamic_domain.md`. Replaces the obsolete `ATLAS_TEMPLATE` design.
- **`ATLAS_HOME=1`** (Phase Z) -- when set, `/` route renders the Atlas instead of the legacy widget grid. Default in fresh installs after Phase Z lands.
- **`ATLAS_DIFF_RIBBON=1`** (Phase D) -- toggles the persistent diff ribbon. Default on after Phase D lands.
- **`ATLAS_WHY_HOTKEY`** -- override the `?` keystroke if the operator has conflicts. Default `?`.
- All env vars added to `.env.example` and `BUILD.md` per `agents.md` rule 10.

---

## 12. Phased implementation MA0..MA6 (with cross-cutting D, C, W, DC, DD, Y, H, Z)

Phase IDs match `docs/artifacts/substrate_master_plan.md` section 4.

- **MA0** -- Atlas foundations. Postgres tables created. `MemorySource` Protocol scaffolded. No UI.
- **MA1** -- Atlas v1: Graph + List + Spines lenses; ChatPrompt persistent at bottom edge; basic node `Focus` lens. `/api/atlas/*` shipping.
- **MA2** -- Recompose operations + steel-manning + echo-finder (**promoted to MA2** per master A7).
- **MA3** -- Lenses beyond the core three: Timeline, Heatmap, Focus polish, Decisions, Contradictions, Diffs.
- **MA4** -- (Reserved for federation-cross-spine UX prep; unlocks H.)
- **MA5** -- (Reserved for performance / large-graph optimisation.)
- **MA6** -- (Reserved for any remaining advanced lenses; **steel-manning + echo-finder no longer wait here -- they ship at MA2.**)
- Cross-cutting phases run on top of MA1+: **D** (diff ribbon), **C** (contradiction crew), **W** (walk-throughs into briefings), **DC** (decision capture), **DD** (dynamic domain definition), **Y** (universal why?), **H** (agent-to-agent handoff). **Z** (Atlas-as-home + responsive mobile) lands after MA1..MA3, D, and Y are stable.

---

## 13. Test strategy

- **Backend unit:** `tests/test_atlas_nodes.py`, `tests/test_atlas_spines.py`, `tests/test_atlas_diffs.py`, `tests/test_atlas_why.py`, `tests/test_memory_source_contract.py`.
- **Backend integration:** `tests/test_atlas_e2e.py` -- ingest synthetic signals through `MemorySource`, assert nodes/edges/spines materialise, summariser produces stable output across two runs.
- **Frontend:** `src/dashboard/tests/MemoryAtlas.spec.ts` (existing Vitest pattern), Playwright e2e for graph<->list lens switching with state preservation.
- **Accessibility:** `MemoryAtlas` and every lens passes axe-core in the dashboard test harness (`docs/artifacts/accessibility_ci_tests.md`). List lens is the assured fallback.
- **Channel parity:** federation events, diff entries, walk-throughs reach all configured channels (rule 21).
- **i18n:** every new string in `_EN` and `_DE`. `pytest tests/test_i18n_coverage.py -v` green.
- **Remnant audit:** `tests/test_remnant_audit.py` Phase MA0+ entries forbid the obsolete `ATLAS_TEMPLATE` symbol (replaced by `ATLAS_TEMPLATE_HINT`) and any post-deletion references from cuts C1..C8.
- **Security:** new `tests/test_atlas_security.py` -- no untrusted MemorySource content escapes sanitisation; "why?" trace cannot leak source content from a federation slice marked redacted; recompose two-step confirm cannot be bypassed.

---

## 14. Risks

- **Graph layout performance at scale.** Mitigated by mandatory List lens fallback and stratified rendering above `> 2000` nodes.
- **Spine churn.** Mitigated by `operator_overrides` locking in the derived definition; locked spines stop re-summarising structurally.
- **Operator overwhelm by the diff ribbon.** Mitigated by per-instance noise budget (configurable, default 5 entries visible, rest collapsed under "more").
- **Federation leak risk.** Mitigated by reasoning-slice-only contract; raw memory points never cross. New `tests/test_atlas_security.py` enforces.
- **Mobile graph UX.** Mitigated by List-default and cluster-view collapse; Phase Z DoD requires axe-clean and 44x44 targets on every Atlas affordance.
- **LLM hallucination in spine summaries / "why?" traces.** Mitigated by `source_refs` mandatory on every paragraph; Phase Y exposes the trace so the operator can verify; aligns with `docs/artifacts/anti_hallucination_master_plan.md`.

---

## 15. Definition of Done (Atlas-as-substrate, end-state)

- Operator opens any instance; the home route is the Atlas (Phase Z, `ATLAS_HOME=1`).
- All nine lenses + List fallback render. List lens is screen-reader-clean.
- Diff ribbon (Phase D) shows what changed since last visit on every route.
- Universal "why?" (Phase Y) returns `source_refs` + `confidence` on every node, spine paragraph, and diff entry.
- Contradiction crew (Phase C) raises contradiction nodes; they appear in the Contradictions lens and in the next walk-through.
- Decision capture (Phase DC) `Cmd/Ctrl+Shift+D` and mic affordance create `decisions` nodes with `revisit_when` predicates; the substrate later raises "decision X was made because Y; Y appears no longer to hold."
- Spine summariser produces stable, justifiable spine paragraphs.
- `agent/domain.derived.yaml` is the only source of ontology; `ATLAS_TEMPLATE` references gone; `ATLAS_TEMPLATE_HINT` documented.
- Federation publishes spine slices (Phase H); receiving instance opt-in per spine works.
- Mobile responsive build of the same codebase passes Lighthouse budget and axe-core.
- Channel parity (rule 21) holds for every Atlas-originating event (briefings, walk-throughs, contradictions, decisions, diffs).
- `pytest tests/test_remnant_audit.py -v`, `pytest tests/test_i18n_coverage.py -v`, `pytest tests/test_static_analysis.py -v`, `tsc`, `ruff check`, `mypy` -- all green.

---

## 16. How this composes with the roadmap

- `docs/artifacts/full_ambient_intelligence_roadmap.md` provides the ambient ingestion + state-diff foundations the Atlas consumes. The unified pending-action queue is reused by recompose operations and decision-capture confirmations.
- `docs/artifacts/federated_memory.md` provides the cross-instance transport the Atlas's spine slices ride on.
- `docs/artifacts/voice_edge_pod.md` provides the voice MemorySource and the voice rendering for walk-throughs and "why?" responses.
- `docs/artifacts/multimodal_vision.md` provides the vision MemorySource (images become structured nodes).
- `docs/artifacts/anti_hallucination_master_plan.md` provides the discipline the spine summariser and "why?" service must follow (every claim has source_refs).
- `docs/artifacts/DESIGN.md` provides the visual language the Atlas honours (HSLA token chains, rem spacing, accessibility primitives).
- `docs/artifacts/walkthroughs_and_briefings.md` provides the rendering contract for ordered tours through the Atlas.
- `docs/artifacts/dynamic_domain.md` provides the per-instance ontology the Atlas reads.
- `docs/artifacts/circle_removal.md` removes the surface (Person/Circle) the Atlas replaces with substrate-derived people nodes.
- `docs/artifacts/substrate_master_plan.md` is the parent. This artifact realises sections A1..A10 of that master.
