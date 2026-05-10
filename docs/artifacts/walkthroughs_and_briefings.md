# Walk-throughs and Briefings

> Briefings (morning / weekly / monthly / quarterly / yearly) become walk-throughs through the Memory Atlas. Every briefing is an ordered tour of substrate-selected nodes, each rendered with one-paragraph context and an optional suggested action. Walk-throughs can also be invoked ad-hoc from any Atlas node. Delivered with full channel parity (Telegram, WhatsApp, dashboard, voice-edge).
> Status: COMPLETE | Author: conductor | Created: 2026-05-10 | Shipped: 2026-05-10 (commit 228f398)
> Companions: `docs/artifacts/substrate_master_plan.md`, `docs/artifacts/memory_atlas.md`, `docs/artifacts/circle_removal.md`, `docs/artifacts/voice_edge_pod.md`, `agents.md` (rule 21).

---

## 1. Why this exists

Briefings are kept (per `docs/artifacts/substrate_master_plan.md` decision K1) because they entice the operator to keep up with projects instead of forgetting them while living life. But the previous briefing format -- a wall of generated text per channel -- is a **surface symptom**: it asks the operator to read prose and reconstruct context in their head.

A **walk-through** is the substrate-vs-surface answer. The briefing renders as an ordered list of substrate-selected Atlas nodes; each stop carries one paragraph of context and a deep-link back into the Atlas. Reading a briefing becomes walking the substrate's reasoning path, not parsing a wall of text. The same primitive is reusable: the operator can launch an ad-hoc walk-through from any Atlas node ("walk me through everything connected to this project"), and the substrate composes the same data structure.

---

## 2. Data model

A walk-through is a single typed object. One shape, four use cases (scheduled briefings + ad-hoc launches).

```python
class WalkthroughStop:
	atlas_node_ref: str          # e.g. "node:project:atlas-launch"
	context: str                 # one paragraph; substrate-authored prose
	suggested_action: str | None # optional; uses the existing action vocabulary allowlist
	source_refs: list[str]       # justification trace for Phase Y "why?" hook
	confidence: float            # 0.0..1.0

class Walkthrough:
	id: str                      # uuid
	kind: Literal["morning", "weekly", "monthly", "quarterly", "yearly", "ad_hoc"]
	generated_at: datetime
	for_operator: str            # operator identity ref
	stops: list[WalkthroughStop] # ordered
	summary: str                 # 1-3 sentence top-of-walkthrough framing
	deep_link: str               # oz://atlas/walkthrough/<id>
```

Persisted in a new `walkthroughs` table (Postgres, startup DDL per repo convention; no Alembic). Stops persist in a `walkthrough_stops` table with `walkthrough_id` FK and `position` ordering column.

---

## 3. Scheduler integration

The existing scheduled tasks under `src/backend/app/tasks/` (`morning.py`, `weekly.py`, `monthly.py`, `quarterly.py`, `yearly.py`) stop emitting wall-of-text briefings and instead:

1. Compose a `Walkthrough` object via a new `services/walkthroughs.py` builder.
2. Persist the `Walkthrough` and its stops.
3. Hand off to a new `services/walkthrough_renderer.py` per-channel renderer.
4. Push to all configured channels via the unified message bus (`bus.push_all`).

Stop selection logic lives in the builder and reads from:

- The Atlas spine summariser for the highest-confidence active spines.
- The diff ribbon (Phase D) for nodes that changed since the last briefing of the same `kind`.
- The contradiction crew (Phase C) for any unresolved contradiction nodes.
- The decision capture system (Phase DC) for any `decisions` nodes whose `revisit_when` predicate now evaluates true.

Default stop counts per kind (implementing agent may tune):

- `morning`: 3-5 stops, recency-weighted.
- `weekly`: 5-8 stops, spine-coverage-weighted.
- `monthly`: 8-12 stops, plus a spine-level summary stop.
- `quarterly`: 10-15 stops, plus a "what this instance is becoming" stop sourced from `agent/domain.derived.yaml` (per `docs/artifacts/dynamic_domain.md`).
- `yearly`: 15-25 stops, plus a year-over-year delta stop.

---

## 4. Ad-hoc invocation

From any Atlas node, the operator triggers `Walk me through this`:

- **Dashboard:** node context menu item, or `W` keystroke when a node is focused.
- **Voice-edge:** "walk me through this node", once the operator has focused a node by speaking its name.
- **Telegram / WhatsApp:** the `/walk <node-id-or-name>` command, plus a tap on the deep-link rendered in any prior briefing message.

Ad-hoc walk-throughs are stored with `kind="ad_hoc"`. They are not pushed to other channels by default (avoids surprise notifications); the operator can opt to share via the same per-channel render path.

---

## 5. Channel parity (rule 21)

Per `agents.md` rule 21, every walk-through MUST render on Telegram, WhatsApp, dashboard, and voice-edge. The renderer in `services/walkthrough_renderer.py` exposes one function per channel and is the single point of fan-out. Adding a new channel means adding one more renderer entry; no upstream code changes.

Per-channel render contracts:

### 5.1 Telegram

- One message per stop. The `summary` lands as the first message.
- Each stop: `*<position>. <node label>*\n<context>\n<suggested_action if any>\n[Open in Atlas](https://<host>/atlas?node=<id>)`.
- Long stops respect the 4096-char limit by chunking the `context` paragraph (existing chunking helper, do not duplicate).
- Final message: `[Open full walk-through](https://<host>/atlas/walkthrough/<id>)`.

### 5.2 WhatsApp

- Same as Telegram structurally, with WhatsApp's link / formatting conventions (no Markdown bold; use plain text emphasis).
- Image-context stops (when a `MemorySource` produced an image-derived node) include the image as media per the existing image path in `src/backend/app/api/whatsapp.py`.

### 5.3 Dashboard

- Renders inside the Atlas as an in-page overlay (or a dedicated `/walkthrough/:id` route) with one stop visible at a time, prev/next controls, keyboard navigation (`J`/`K` or arrow keys).
- Each stop's node is highlighted in the underlying Atlas graph/list lens behind the overlay.
- Universal "why?" (Phase Y): `?` keystroke on the active stop reveals `source_refs` and `confidence`.
- Persistent ChatPrompt at bottom edge (per master artifact A4) lets the operator ask "tell me more about stop 3" without leaving the walk-through.

### 5.4 Voice-edge

- Spoken summary, then each stop spoken in order with a 2-second pause between stops for the operator to interject.
- Suggested actions spoken as "I can <action>; say 'do it' to confirm." (HITL via existing two-step confirm).
- Deep-links spoken as "Atlas node <short label>; say 'open node' to navigate" -- the dashboard companion (if open) follows.
- Voice-edge prosody and pacing details deferred to `docs/artifacts/voice_edge_pod.md`.

### 5.5 Deep-link format

- Canonical URI: `oz://atlas/node/<node_id>` for nodes, `oz://atlas/walkthrough/<walkthrough_id>` for walk-throughs.
- Channel-specific rendering rewrites the URI to a clickable HTTPS URL pointing at the operator's instance host. The instance host is read from existing config (no new env var).
- The dashboard's deep-link handler resolves both URI forms.

---

## 6. Briefing-as-walk-through migration

The implementing agent in Phase W:

1. Adds `services/walkthroughs.py` and `services/walkthrough_renderer.py`.
2. Adds `walkthroughs` and `walkthrough_stops` tables via startup DDL in `src/backend/app/main.py`.
3. Rewires `src/backend/app/tasks/morning.py`, `weekly.py`, `monthly.py`, `quarterly.py`, `yearly.py` to compose and dispatch walk-throughs.
4. Removes the legacy wall-of-text briefing prose paths and any "Inner Circle"-style person enumeration (the latter is already gone after Phase P4 per `docs/artifacts/circle_removal.md`).
5. Adds a new `WalkthroughViewer.ts` Web Component for the dashboard render, following Shadow DOM + `${ACCESSIBILITY_STYLES}` + `this.tr()` per `agents.md` rules 12, 18, 19.
6. Adds the `/walk` command to `src/backend/app/api/telegram_bot.py` and `src/backend/app/api/whatsapp.py` (channel parity rule 21 -- both in the same commit).
7. Updates `BriefingHistory.ts` to render past walk-throughs (each row links to the stored walk-through).

---

## 7. Test plan

- `tests/test_walkthroughs.py`:
	- Unit: `services/walkthroughs.py` builder produces a valid `Walkthrough` for a synthetic memory corpus across all five briefing kinds plus `ad_hoc`.
	- Unit: stop selection respects spine confidence ordering and includes any `revisit_when`-triggered decisions and unresolved contradictions.
	- Unit: per-channel renderer outputs are deterministic for a fixed `Walkthrough` input.
	- Unit: deep-link rewriting handles both `oz://atlas/...` URIs.
- Integration: end-to-end morning briefing dispatch hits all four channel push paths (mocked transport) with consistent stop content.
- a11y: `WalkthroughViewer.ts` passes axe-core in the dashboard test harness (`docs/artifacts/accessibility_ci_tests.md`); arrow-key navigation works; min 44x44 px controls; visible focus ring.
- i18n: every new string lives in `_EN` and `_DE`. `pytest tests/test_i18n_coverage.py -v` green.
- Channel parity: a new test in `tests/test_live_regression.py` (or a dedicated `tests/test_channel_parity.py`) asserts that scheduled briefings appear on every configured channel within a tolerance window.
- Static: `tests/test_remnant_audit.py` Phase W entry forbids any reference to the legacy `_format_morning_briefing_text`-style functions once removed.

---

## 8. Definition of Done (Phase W)

- Briefings on all five cadences render as walk-throughs across Telegram, WhatsApp, dashboard, and voice-edge.
- Ad-hoc walk-throughs launchable from the dashboard (`W` keystroke), Telegram and WhatsApp (`/walk`), and voice-edge ("walk me through this").
- `WalkthroughViewer.ts` ships with full Shadow DOM, `${ACCESSIBILITY_STYLES}`, `this.tr()`, axe-clean.
- Deep-link format `oz://atlas/...` documented in `BUILD.md` (per `agents.md` rule 10) and resolved correctly by all channels.
- Universal "why?" (Phase Y) hooks into each stop.
- Diff ribbon (Phase D) reflects new walk-throughs.
- All tests green; remnant audit Phase W entry populated.
- Artifact updated to mark Phase W complete; deviations recorded.
