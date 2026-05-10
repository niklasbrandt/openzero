# Dynamic Domain Definition

> Replaces the static `ATLAS_TEMPLATE` config with a substrate-authored `agent/domain.derived.yaml` file. The `domain_inference` crew runs continuously in the lowest-priority lane, infers what the instance is becoming from accumulated memory, and surfaces a confirmation panel in the Atlas. Operator confirms or overrides; never hand-authors.
> Status: PLAN | Author: conductor | Created: 2026-05-10
> Companions: `docs/artifacts/substrate_master_plan.md`, `docs/artifacts/memory_atlas.md`, `agent/crews.yaml`, `agents.md`.

---

## 1. Why this exists

A purpose-shaped instance (`life-Z`, `work-Z`, `partner-Z`, `fishing-Z`) needs an ontology -- a sense of what the topic spines are, what node types matter, what the visual language should be. The previous design proposed a hand-authored `ATLAS_TEMPLATE` config. That is a **surface**: it makes the operator pre-declare what the instance will be, before the substrate has any memory to ground that declaration in.

The substrate-vs-surface heuristic (`agents.md` rule 22) demands the inverse. The operator gives a one-line **hint** at bootstrap (`ATLAS_TEMPLATE_HINT`), and the substrate **derives** the actual ontology from accumulated memory. The Atlas surfaces "what this instance is becoming" so the operator can confirm, refine, or override -- but never originate.

---

## 2. The `domain_inference` crew

### 2.1 Lane and cadence

- **Lane:** lowest priority, equivalent to a background maintenance crew. Never preempts foreground LLM tier.
- **Cadence:** opportunistic. Runs whenever the substrate detects a meaningful inflection in memory volume or topic distribution. Concretely: triggered when `>= 50` new high-confidence memory points have landed since the last run, or weekly, whichever comes first.
- **Hardware tier:** fast tier (3B). Domain inference is a clustering/labelling task, not a deep reasoning task.

### 2.2 Inputs

- The full corpus of memory points in Qdrant for this instance (sampled if `> 5000` points -- see section 6).
- The current `agent/domain.derived.yaml` (if it exists), used as a stability prior.
- The bootstrap `ATLAS_TEMPLATE_HINT` (if set), used only on the very first run when no derived definition yet exists.
- The set of active `MemorySource` plugins and their declared topic vocabularies.

### 2.3 Outputs

A new `agent/domain.derived.yaml` file (gitignored, never hand-authored) with the following shape:

```yaml
schema_version: 1
generated_at: 2026-05-10T14:23:00Z
inference_run_id: 2026-05-10-1423
confidence: 0.71

# Operator-confirmed fields persist across runs unless explicitly overridden.
identity:
	name: "work-Z"
	purpose: "Run a 6-person research team in Berlin."
	hint: "team"

# Substrate-derived ontology.
spines:
	- id: people-team
		label: "Team"
		confidence: 0.88
		evidence_count: 142
	- id: projects-active
		label: "Active projects"
		confidence: 0.79
		evidence_count: 96
	- id: decisions
		label: "Decisions"
		confidence: 0.66
		evidence_count: 31

node_types:
	- id: person
		label: "Person"
		confidence: 0.91
	- id: project
		label: "Project"
		confidence: 0.82
	- id: decision
		label: "Decision"
		confidence: 0.74

visual_language:
	palette_seed: "team-warm"   # operator-overridable; consumed by Atlas theme picker
	default_lens: "graph"
	mobile_default_lens: "list"

# Confirmed-by-operator fields. Substrate never overwrites these.
operator_overrides:
	identity:
		purpose_locked: false
	spines:
		- id: people-team
			locked: true
```

### 2.4 Storage and gitignore

- File path: `agent/domain.derived.yaml` (mirrors the location of `agent/crews.yaml` so per-instance vaults keep all substrate-authored config in one tree).
- Add `agent/domain.derived.yaml` to `.gitignore` (the implementing agent does this in Phase DD).
- The `agent.example/` mirror does NOT include a `domain.derived.yaml` (per `agents.md` rule 4, the `.example` tree mirrors structural config -- this file is substrate-authored, so its absence is the correct example).

### 2.5 Postgres-side cache

A small `domain_inference_runs` table records each run for auditability and the diff ribbon (Phase D):

- `run_id` (primary key)
- `started_at`, `completed_at`
- `confidence`
- `delta_summary` (JSON: which spines added, removed, renamed)
- `derived_yaml_snapshot` (text)

A companion `domain_signals` table stores per-spine evidence sampling for the Atlas "why?" hook (Phase Y):

- `run_id` (FK)
- `spine_id`
- `signal_kind` (enum: memory_point, source_ref, cluster_centroid)
- `payload` (JSON)

Both tables follow the repo's `Base.metadata.create_all` + raw startup DDL pattern in `src/backend/app/main.py`. No Alembic.

---

## 3. `ATLAS_TEMPLATE_HINT` -- bootstrap-only env var

Replaces the previous `ATLAS_TEMPLATE` (which would have prescribed the ontology). The new env var:

- Lives in `.env` and `.env.example`. Add to `BUILD.md` Phase 1 with a one-line explanation per `agents.md` rule 10.
- Accepts a free-text hint of arbitrary length. Examples: `team`, `family`, `solo-founder`, `fly-fishing-craft`, `marriage-with-Anna`.
- Is read **only** during the first `domain_inference` run when no `agent/domain.derived.yaml` exists.
- After the first derived definition lands, `ATLAS_TEMPLATE_HINT` becomes irrelevant. Changing it later does NOT re-bootstrap; the operator instead uses the "what this instance is becoming" panel to override.
- Default if unset: `general` (substrate proceeds with no hint and infers entirely from memory).

---

## 4. Atlas "what this instance is becoming" panel

A new panel inside the Atlas component (defined in `docs/artifacts/memory_atlas.md` MA1+). UX contract:

- Lives as a collapsible right-rail card on desktop, full-width drawer on mobile (responsive same-codebase per Phase Z).
- Renders the current `agent/domain.derived.yaml` as readable prose (not raw YAML), e.g. "This instance is becoming a **team** -- spines: Team (high confidence), Active projects (medium), Decisions (medium). Last inferred 14 minutes ago. Confidence: 71%."
- Shows the latest `delta_summary` from `domain_inference_runs` -- "since last run: added spine `Decisions`, renamed `People` -> `Team`."
- For each spine and node type, a small `?` button invokes the universal "why?" hook (Phase Y), revealing the evidence sample from `domain_signals`.
- Two operator actions per row, following the `AgentsWidget *-step1 / *-confirm` two-step confirm pattern (per `agents.md` rule 18 and the user brief):
	- **Confirm** -- locks the field in `operator_overrides`. Substrate stops re-inferring it.
	- **Override** -- opens an inline rename / re-purpose input. Locked on submit.
- A single "Re-run inference now" button (low-priority, advisory only -- the crew may decline if the lane is busy).

All strings go through `this.tr('key', 'English fallback')` and land in `_EN` and `_DE` only (post-Phase P1 trim). Accessibility: `${ACCESSIBILITY_STYLES}`, `aria-live="polite"` on the delta summary, `aria-expanded` on the collapsible card, min 44x44 px touch targets, focus-visible ring per `docs/artifacts/DESIGN.md`.

---

## 5. How spine summariser and Atlas lenses consume the derived definition

- The **continuous spine summariser** (memory_atlas.md) reads `domain.derived.yaml` to know which spines to summarise. New spines that appear in a fresh inference run are automatically picked up on the next summariser cycle.
- The **Atlas lenses** (graph, list, timeline, heatmap, focus, etc.) read `node_types` and `visual_language.palette_seed` to colour-encode and group nodes. The graph lens uses `default_lens` to decide whether to open in graph or list mode on first render per platform.
- The **MemorySource plugins** read `spines` to bias their tagging suggestions when ingesting new content (e.g. the calendar source learns that `team` is a spine and tags accordingly).
- The **briefings / walk-throughs** (`docs/artifacts/walkthroughs_and_briefings.md`) order their walk-through stops by spine confidence, so the highest-confidence spines are visited first.

None of these consumers fall back to a static `ATLAS_TEMPLATE`. If `domain.derived.yaml` does not yet exist (very first boot, before the first inference run), consumers default to a built-in `general` ontology shipped in code (no node types beyond `memory`, no spines beyond `recent`).

---

## 6. Confidence model

- Spine confidence: ratio of memory points clustered into the spine over total memory points in the inference window, weighted by source quality (calendar > chat > inferred).
- Node-type confidence: stability of the type label across the last `N=3` inference runs.
- Overall `confidence` field: minimum of (spine median confidence, node-type median confidence, evidence-sample size sufficiency).
- Implementing agent picks exact thresholds at execution time (deferred per master artifact section 9).

When the operator confirms a field, that field's confidence is fixed at `1.0` and the substrate stops sampling for it. When the operator overrides, the new label inherits the original evidence count but resets confidence stability tracking.

When `> 5000` memory points exist, the inference run uses a stratified sample (most recent 1000 + uniform random 1000) to keep the lane non-disruptive.

---

## 7. Operator confirmation / override flow

1. Operator opens Atlas. Right rail shows "what this instance is becoming."
2. Operator sees a low-confidence spine (`Decisions`, 0.55).
3. Operator clicks `?` -- universal "why?" surfaces evidence (Phase Y): "12 memory points mentioning `decided`, `chose`, or `committed to`; clustered around projects."
4. Operator clicks **Confirm** -- step 1 highlights the row, step 2 locks the spine. `operator_overrides.spines` updates.
5. Alternatively, operator clicks **Override** -- renames `Decisions` to `Bets`. Step 1 shows pending state, step 2 commits.
6. The next `domain_inference` run reads `operator_overrides`, leaves `Bets` alone, and continues inferring around it.

There is **no** automatic publication of unconfirmed inferences -- per master artifact section 9, the default is "always show the panel and require operator confirmation." The substrate's derived definition is treated as a proposal until confirmed, but consumers (spine summariser, lenses, briefings) read the proposal in advisory mode so the operator sees the substrate's best guess immediately.

---

## 8. Test plan

- `tests/test_dynamic_domain.py`:
	- Unit: `domain_inference` crew produces a valid `domain.derived.yaml` for a synthetic memory corpus.
	- Unit: `operator_overrides` survive a re-run (substrate does not overwrite locked fields).
	- Unit: `ATLAS_TEMPLATE_HINT` is read on first run only; subsequent runs ignore it.
	- Unit: confidence math is deterministic for a fixed seed.
	- Integration: a full Atlas render with a mocked `domain.derived.yaml` produces the expected lens default and palette.
- Static: `tests/test_remnant_audit.py` Phase DD entry forbids any reference to the legacy `ATLAS_TEMPLATE` symbol once the migration lands.
- i18n: every new string in the "what this instance is becoming" panel has a key in `_EN` and `_DE`. `pytest tests/test_i18n_coverage.py -v` is green.
- a11y: the panel passes axe-core in the dashboard test harness (`docs/artifacts/accessibility_ci_tests.md`).

---

## 9. Definition of Done (Phase DD)

- `domain_inference` crew added to `agent/crews.yaml` (and structural mirror in `agent.example/crews.yaml`).
- `agent/domain.derived.yaml` is gitignored.
- `ATLAS_TEMPLATE` references removed; `ATLAS_TEMPLATE_HINT` documented in `BUILD.md` and present in `.env.example`.
- `domain_inference_runs` and `domain_signals` tables created via startup DDL in `src/backend/app/main.py`.
- "What this instance is becoming" panel renders in the Atlas, with confirm/override two-step flows per `AgentsWidget` pattern.
- All consumers (spine summariser, lenses, MemorySource plugins, briefings) read `domain.derived.yaml`, with the built-in `general` fallback only when the file does not yet exist.
- `pytest tests/test_dynamic_domain.py -v`, `pytest tests/test_i18n_coverage.py -v`, `pytest tests/test_remnant_audit.py -v` all green.
- Channel parity (rule 21): the panel's confirm/override actions emit the same status feedback to dashboard, Telegram, WhatsApp, and voice-edge ("substrate noted: spine Decisions confirmed").
- Artifact updated to mark Phase DD complete; deviations recorded.
