# openZero Refocus Plan

> Single source of truth for the May 2026 repositioning of openZero from "thinking substrate" back into a sharp, hackable, self-hosted AI companion that lives in your messengers. This artifact overrules `docs/artifacts/substrate_master_plan.md` and `docs/artifacts/substrate_pivot.md` wherever they conflict.
> Status: LOCKED -- all operator decisions resolved 2026-05-18 | Phase 1 ready to start
> Companions: `docs/artifacts/semantic_routing.md` (router spec), `docs/artifacts/substrate_master_plan.md` (historical, partially overruled), `agents.md`, `README.md`, `BUILD.md`.

---

## 1. TL;DR

- openZero is being refocused from an ambitious "thinking substrate" into a tight, hackable, self-hosted personal AI you talk to in Telegram, WhatsApp, and a dashboard, with one shared memory across all three.
- The Atlas, federation, ambient capture, voice edge pod, walkthroughs, and the auto-domain/contradiction crews are cut. ~12k LOC + ~270 LOC DDL + ~140 LOC of orphan i18n disappear.
- The router stops being keyword Jaccard and becomes semantic (see `docs/artifacts/semantic_routing.md`). `workspace` and `signal_interpreter` crews fold into Z-core. `nutrition` is renamed `recipe`. `general` and `flow` crews die.
- Visionary verdict on the operator's "one weekend" goal: **"One-weekend is fiction."** Realistic Phase 1 weekend = teardown + loader merge + Z-core absorption + briefing prompt rewrite + rename. Semantic router, multi-crew synthesis, proactive coach mode, and any CrewBuilder widget slip to Phases 2 and 3.
- The non-negotiable soul of the product: **memory that survives across channels and accumulates like a relationship does.** A cross-channel continuity regression test must land before any Phase 2 work.

---

## 2. Positioning

**Operator's draft:** *"Customizable, self-hosted AI operations layer with messenger + dashboard interface."*

**Visionary verdict (verbatim):** that line is marketing fog. "Operations layer" tells nobody what it does. The product is not infrastructure -- it's a personality that lives in your chats and remembers everything.

**Candidate one-liners** (historical -- all struck through, kept for record). "Second brain" is explicitly **out** per operator's earlier prompt.

1. ~~*"A self-hosted AI that runs your life off your chat history."*~~
2. ~~*"Personal AI, on your hardware, in your messenger."*~~
3. ~~*"The AI you text. On hardware you own. With memory that doesn't reset."*~~
4. ~~*"Your own AI, living in Telegram and WhatsApp, remembering everything."*~~
5. ~~*"A sovereign AI companion you message like a friend."*~~

**LOCKED tagline: "A self-hosted AI assistant that runs on your hardware and works across your messengers."**

---

## 3. The North Star

Verbatim from the visionary review, preserved here so no future agent waters it down:

> The one thing that makes openZero itself: **memory that survives across channels and accumulates like a relationship does.** WhatsApp on the train -> Telegram at home -> dashboard on the laptop = same Z, same conversation, same memory, six months later. Make cross-channel context continuity a tested non-negotiable regression. That test is the soul of the product.

Operationalised: see section 16. No Phase 2 work begins until `tests/test_cross_channel_memory.py` exists and passes in CI.

---

## 4. What openZero IS (after this refocus)

- A self-hosted AI you talk to in Telegram, WhatsApp, and a web dashboard, with full feature parity across all three.
- A single shared memory (Qdrant + Redis + `/personal/*.md`) that follows you across channels and accumulates.
- A small, opinionated crew system you can extend in YAML (`personal/crews.yaml`) without forking the repo.
- A Planka board backend the AI writes to on your behalf (Project > Board > List > Card > TaskList), with HITL on writes.
- A Recipe crew + Fitness crew that can earn the right to proactively message you (see section 9g).
- A Coach crew that actually triggers (rebuilt on semantic routing).
- Email read, Calendar read, Vision (multimodal), Web search (injection-hardened), Backup/Export. Opt-in, off by default.
- A configurable Z persona; default tone: *"never weird humor, only verifiable good humor, uplifting, helpful, proactive/suggestive."*

---

## 5. What openZero is NOT

- Not an Atlas visualisation of your knowledge graph. The Atlas concept is retired.
- Not a federated memory mesh between people or instances.
- Not an ambient-capture surveillance product. No always-on mic, no passive screen scraping.
- Not an autonomous agent that takes irreversible actions without confirmation.
- Not a competitor to any named product. The README and dashboard never name-drop competitors.
- Not a substrate for arbitrary domains. It is a personal AI for one operator (multi-instance is a hackability concession, not a product).

---

## 6. Cut list

### 6.1 Locked cuts (operator already approved)

| Subsystem                             | Files / locations                                                                  | LOC      | Risk                                                  | Effort |
| ------------------------------------- | ---------------------------------------------------------------------------------- | -------- | ----------------------------------------------------- | ------ |
| Atlas (UI)                            | `src/dashboard/components/MemoryAtlas.ts`                                          | ~2952    | Low (no writer feeds it)                              | 1h     |
| Atlas (API)                           | `src/backend/app/api/atlas.py`                                                     | ~1068    | Low                                                   | 1h     |
| Atlas (service scaffold)              | `src/backend/app/services/atlas/`                                                  | ~81      | Low                                                   | 15m    |
| Atlas (DDL)                           | `atlas_*` tables                                                                   | ~270     | Medium -- **defer drop to a `v0.next` migration**; remove writers/readers now, drop tables next release (backend pushback) | 30m   |
| Federation                            | `src/backend/app/services/federation/`                                             | ~230     | Low                                                   | 30m    |
| Ambient capture                       | `src/backend/app/services/ambient_capture/`                                        | ~2500    | Low (no consumers after delivery cut)                 | 1-2h   |
| Ambient delivery                      | `src/backend/app/services/ambient/`                                                | ~700     | Touches router + morning briefing -- cut delivery first, capture second | 1-2h   |
| Voice edge pod                        | doc + service stubs                                                                | ~150     | Low                                                   | 15m    |
| Walkthroughs (service + renderer)     | `services/walkthroughs.py` etc.                                                    | ~571     | **Pushback: ship Telegram + WhatsApp `/walk` stub message in the same commit -- not silent removal.** Stub: *"Walk-throughs retired. Try `/day` or `/week`."* | 1-2h |
| Walkthrough UI trio                   | `WalkthroughViewer`, `DiffRibbon`, `DecisionCapture`                               | ~1243    | Low                                                   | 1h     |
| `contradiction_detector` crew         | `agent/crews.yaml` entry + writer                                                  | small    | Low (no writer feeds it)                              | 15m    |
| `domain_inference` crew + derived YAML | `agent/crews.yaml` entry + `agent/domain.derived.yaml`                            | small    | Low (no writer anywhere -- confirmed dead)            | 15m    |
| `general` crew                        | `agent/crews.yaml`                                                                 | small    | None (no hard refs)                                   | 5m     |
| `flow` crew                           | `agent/crews.yaml`                                                                 | small    | None (not in `router.py` whitelist anyway)            | 5m     |
| `workspace` crew                      | folded into Z-core (section 9b)                                                    | small    | Low                                                   | -      |
| `signal_interpreter` crew             | folded into Z-core (section 9b)                                                    | small    | Low                                                   | -      |
| Nutrition naming                      | rename to `recipe` everywhere; **keep "Nutrition" Planka board name as alias for one release** (backend pushback) | small | Low | 1-2h |
| `agent.example/` divergence           | regenerate from live `agent/` via script                                           | -        | Low                                                   | 30m    |
| Orphan i18n keys                      | ~70 keys (~140 lines) across `_EN` and `_DE`                                       | ~140     | Gated by `tests/test_i18n_coverage.py`                | 1h     |

**Total deletable: ~12,140 LOC + ~270 LOC DDL + ~140 LOC i18n.**

### 6.2 Bonus cuts (locked outcomes)

All items below resolved 2026-05-18:

- **ZProtocols widget:** **KEEP** (operator override -- value as visible capability surface for adopters).
- **Consolidate `HardwareMonitor` + `DiagnosticsWidget` + `SystemBenchmark` into `SystemHealth`:** **CUT/MERGE** (locked).
- **Telegram slash sprawl:** cut **only `/skills`**. All others kept including `/think` (with new semantic per 9a/9f), `/custom`, `/protocols`, `/agent`, `/tree`.
- **Deep-tier HITL gate:** **autonomous default OFF on single-object ops.** Hard-gate when >2 objects created/modified/deleted in one action. Always-gate on `PURGE_MEMORY`, `DELETE_PROJECT`, `DELETE_BOARD` regardless of count.
- **`/quarter` and `/year` briefings:** **cut scheduler, keep slash commands** (on-demand only).
- **Dormant crews audit:** **defer to Phase 3** (after semantic router is live, so the audit measures semantic relevance, not keyword accidents).

---

## 7. Keep & harden

| Feature                                 | Current state                                            | Hardening action                                                                                                                                            | Effort |
| --------------------------------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Telegram + WhatsApp + Dashboard chat    | Wired, healthy                                           | Slash command parity (all commands available on dashboard); cross-channel memory regression test                                                            | 2h     |
| Planka boards backend                   | CRUD wired, ACTION pipeline gated                        | Empty-board auto-setup (section 9e); board-name alias map during rename                                                                                     | 2-3h   |
| Recipe crew (renamed from nutrition)    | Wired                                                    | Rename; shopping-cart widget tied to recipe output; earn proactive mode via section 9g                                                                      | 2h     |
| Fitness crew                            | Wired                                                    | Rebuild description for semantic router; earn proactive mode via section 9g                                                                                 | 1h     |
| Coach crew                              | Never triggers (no keywords)                             | Rewrite description to load goals/avoidance/time-pressure semantics; relies on semantic router (section 9a)                                                 | 1h     |
| Email read, Calendar read               | Wired, opt-in                                            | Keep. Email already invisible when `EMAIL_ENABLED` unset (agents.md cut). No change.                                                                        | -      |
| Vision (Telegram + WhatsApp)            | Wired                                                    | Keep                                                                                                                                                        | -      |
| Web search                              | Wired                                                    | Audit injection hardening (already exists -- verify still in pipeline)                                                                                      | 1h     |
| Backup / Export                         | Wired                                                    | Keep                                                                                                                                                        | -      |
| Briefings (skeleton + formatter)        | Wired, prompt broken                                     | **Rewrite prompt** at `src/backend/app/services/morning.py` L251 -- the literal *"You are a formatter"* opener is the bug                                   | 2h     |
| Crew YAML loader                        | Loads `agent/crews.yaml` only                            | Merge `agent/crews.yaml` (default) with `personal/crews.yaml` (operator overrides, gitignored) -- see section 9c                                            | 3-4h   |
| Z persona                               | Hardcoded                                                | Make configurable; default tone string in `config.example.yaml`: *"never weird humor, only verifiable good humor, uplifting, helpful, proactive/suggestive"* | 1h    |
| Crew output preamble                    | Starts with robotic recap                                | Add explicit *"no preamble, no recap"* clause to crew system prompt (section 9a / 9d)                                                                       | 30m    |
| ACTION retry                            | Sometimes fails silently                                 | Add retry-once + surface the failure to user instead of dropping                                                                                            | 2h     |

---

## 8. Hidden keeps -- do NOT cut by accident

- **Walkthroughs as a delivery FORMAT** -- step-by-step paginated briefings on mobile. Keep the format. Rebuild on plain briefing text. Drop only the Atlas-backed implementation.
- **"What changed since last week"** -- the concept in briefings. One prompt sentence, not a subsystem. Keep.
- **`personal_context.py`** -- reads `/personal/*.md` into prompts. Not Atlas. Keep.
- **The `/why` instinct** -- *"where did you get that?"* follow-up. Keep as a one-line prompt addendum.
- **Two-tier LLM routing (fast / deep)** -- keep.
- **Briefing prompts** -- REWRITE, do not delete. *"You are a formatter"* is the bug, not the feature.
- **HEALTH_CONTEXT flag** -- per-crew; renaming nutrition -> recipe does not break it (keep flag on the recipe entry).

---

## 9. Architectural refactors

### 9a. Semantic intent router

Replace keyword Jaccard with embedding-based routing using the existing `all-MiniLM-L6-v2` from `services/memory.py`.

**Crew profile** = `name + description + characters` PLUS `instructions` and `examples` truncated to a combined ~500 chars (operator override of original spec excluding them entirely -- the truncated tail still carries useful signal without dominating the embedding).

**Thresholds (default mode), live in `config.yaml`:**

- `T_MATCH 0.55`
- `T_OPT_IN 0.52`
- `GAP 0.06`
- `MAX_CREWS 3` (operator override of visionary's cap of 2)
- `CONT_BIAS +0.05`
- `DEBATE_GAP 0.06`

**Thresholds (`/think` mode -- consult-all panel):**

- `T_MATCH 0.50`
- `T_OPT_IN 0.45`
- `MAX_CREWS unlimited`

Multi-crew synthesis (section 9f) is **always-on**. `/think` only widens the panel via lower thresholds + uncapped `MAX_CREWS`; it does not toggle synthesis on or off.

**Full spec: `docs/artifacts/semantic_routing.md`.** Do not duplicate here.

### 9b. Z-core absorbs `workspace` and `signal_interpreter`

Both crews always-fire today, which means they aren't crews -- they're Z's always-on faculties. New file: `src/backend/app/services/z_core.py`. Their prompt content folds into `agent/agent-rules.md` so Z runs them inline on every message. Their YAML entries are deleted in the same commit. No router score is consumed by them.

### 9c. Crew YAML loader merge

`agent/crews.yaml` ships defaults. `personal/crews.yaml` (gitignored, optional) is the operator's override layer. Loader:

1. Load `agent/crews.yaml`.
2. If `personal/crews.yaml` exists, deep-merge: by crew `id` -- replace if id matches, append if new.
3. Hot-reload on file mtime change so the operator can edit personal crews live (see section 11).

This is a **blocker for any CrewBuilder widget** (section 11) -- the substrate alternative to that widget is "edit `personal/crews.yaml` in your editor + Z reloads on save."

### 9d. Briefing prompt rewrite

File: `src/backend/app/services/morning.py` L251.

Current opener (the bug):

```
You are a formatter.
```

Rewrite as a real briefing voice prompt (operator's persona-default tone). Add explicit *"no preamble, no recap, no 'Here is your briefing' opener"* clause. Add a one-sentence *"what changed since last briefing"* clause referencing prior briefing snapshot.

### 9e. Empty-board auto-setup

When Z is asked to act on a board that exists but has zero lists: auto-create lists matching the board's purpose (inferred from board name + description), then create the cards. HITL gate on creation; one confirmation covers the full set.

### 9f. Multi-crew labeled-section response + Z synthesis

When the router returns 2 crews (cap at 2 per visionary -- *"three voices is noise"*), Z fires both in parallel, 180 tokens each, then synthesises with the final overruling word using long-term Qdrant memory + session context.

**Visionary's UX rules (non-negotiable):**

- Section-prefix style (e.g. `Fitness: ...` / `Recipe: ...`) **only when crews materially disagree**. Otherwise Z silently merges.
- **Debate-OFF rule:** no decision verb in user message, OR top-two gap > 0.06, OR message < 5 tokens, OR user asked for single answer -> single crew, no panel.
- **Kill switch:** if any crew contribution < 40 tokens or restates another, drop it.
- ACTION tags disabled in panel mode (ambiguous attribution).
- **Always-on.** `/think` widens the panel via lower thresholds + unlimited crews (per 9a). ACTION tags disabled when `MAX_CREWS=unlimited` (panel mode).

### 9g. Recipe + Fitness proactive coach mode

Crews earn the right to proactively message the operator (outside briefings) only after the visionary's earning rule:

> A crew earns proactive messaging only after **2 consecutive weeks of operator reading scheduled output without skipping.** Otherwise passive only.

Tracked via briefing read receipts (already collected). New service: `services/coach_earning.py` reads receipts, flips a per-crew `proactive: true` flag in runtime state.

### 9h. Channel parity

- All slash commands available on dashboard chat (currently partial).
- Recipe + Fitness proactive messages dispatched on whichever channel the operator last used (Telegram / WhatsApp / dashboard) -- not all three simultaneously.
- Per `agents.md` rule 21: any fix to one channel patches the others in the same commit.

### 9i. Reminder system

- **Phase 2 deliverable -- recurring reminders.** Extension of the existing reminder service with cron-style storage. Syntax: `/remind weekly mon 19:00 ...`, `/remind daily 08:00 ...`. Effort: ~3h.
- **Phase 3 deliverable -- adaptive crew-driven nudges.** Recipe + Fitness crews may ping the operator when N consecutive days of silence on their domain coincide with no related memory activity. Coupled to the earning rule in 9g: only crews that have earned `proactive: true` may nudge. Effort: ~4-6h.

---

## 10. Stable contracts for adopters

> **API freeze: changing these is a breaking release.** Document each in `BUILD.md` under a new "Hackability contracts" section.

1. **`agent/crews.yaml` schema** -- the YAML keys a crew entry supports.
2. **Chat pipeline boundary function** -- the single function any new channel must call to participate in Z (signature stable across releases).
3. **`/api/crews/trigger/<id>` + `/api/crews/list`** -- HTTP contract.
4. **`personal/` directory layout** -- file names, formats, what each file is read for.

---

## 11. CrewBuilder widget -- open question

Operator wants a dashboard widget to create crews via UI. Backend + visionary push back: it's an 8-12h surface that duplicates `personal/crews.yaml` editing, violates `agents.md` rule 22 (substrate vs surface), and ages badly as the YAML schema evolves.

**Substrate alternative:** loader merge (section 9c) + hot-reload on file mtime + `BUILD.md` doc snippet. Operator edits `personal/crews.yaml` in their editor; Z reloads on save.

| Option                  | Pros                                                     | Cons                                                                              |
| ----------------------- | -------------------------------------------------------- | --------------------------------------------------------------------------------- |
| CrewBuilder widget      | UX for non-CLI adopters; visible capability              | 8-12h; schema-coupling debt; another surface; ages badly                          |
| Edit YAML + hot-reload  | ~1h on top of loader merge; aligns with `agents.md` r22  | Requires editor + filesystem access; less marketable to non-developer adopters    |

**LOCKED: no widget. `personal/crews.yaml` + hot-reload only (substrate-aligned per `agents.md` rule 22).**

---

## 12. Weekend scope -- Phase 1 only (~16-20h, realistic)

The visionary's line, preserved:

> **"One-weekend is fiction."** Realistic weekend cut: (1) Atlas teardown + dead code purge, (2) loader merge agent/+personal/crews.yaml, (3) Z-core absorbs workspace + signal_interpreter. That's it. Everything else slips.

Concrete Phase 1 deliverables:

1. **Teardown batch** (backend Phases 1+2+3 sequenced):
	- Leaf cuts in parallel: atlas scaffold, federation, flow crew, general crew, voice_edge_pod doc, dashboard `/board` parity.
	- Ambient stack sequenced: delivery first, capture second, then `contradiction_detector` + `domain_inference` crews.
	- Walkthrough + Atlas sequential: walkthroughs service -> trio components -> `MemoryAtlas.ts` -> `atlas.py` API. **Defer `atlas_*` DDL drop to a `v0.next` migration file.**
2. **`/walk` stub message** shipped on Telegram + WhatsApp in the same commit as walkthroughs service removal.
3. **i18n orphan sweep** -- gated by `tests/test_i18n_coverage.py`. Remove ~70 keys / ~140 lines.
4. **Crew YAML loader merge** -- `agent/` + `personal/crews.yaml` with hot-reload on mtime (section 9c).
5. **Z-core absorbs `workspace` + `signal_interpreter`** -- new `services/z_core.py` + `agent-rules.md` additions (section 9b).
6. **Briefing prompt rewrite** at `src/backend/app/services/morning.py` L251 (section 9d).
7. **`nutrition` -> `recipe` rename** -- everywhere, with **board-name alias for "Nutrition"** during one release (backend pushback).
8. **`agent.example/` regenerate-from-live script** -- one-shot, idempotent.

**Total: ~16-20h.** Anything beyond this slips to Phase 2.

---

## 13. Phase 2 -- Weekend 2

1. **Semantic router rebuild** per `docs/artifacts/semantic_routing.md`. Includes:
	- Eval harness (synthetic + replay of last 30 days of real messages, scored against operator labels).
	- Threshold tuning against the eval harness, not vibes.
	- Embedder cache invalidation on YAML mtime change (ties to 9c).
2. **Multi-crew labeled-section response + synthesis** -- **always-on** with default thresholds per 9a. `/think` widens the panel.
3. **Empty-board auto-setup** (section 9e).
4. **Cross-channel memory regression test must already be in CI** before any Phase 2 commit (section 16).
5. **Recurring reminders** via `/remind weekly|daily ...` per section 9i.

---

## 14. Phase 3 -- Weekend 3+

1. **Recipe + Fitness coach-mode proactive messaging** -- only for crews that earn it per section 9g.
2. **Adaptive crew-driven nudges** per section 9i (only crews that earned the `proactive` flag).
3. Audit dormant crews per section 6.2 last item; move losers to `agent.example/` (deferred here so the audit measures semantic relevance, not keyword accidents).

---

## 15. Locked decisions (resolved 2026-05-18)

All questions from the draft resolved. Phase 1 is unblocked.

| ID  | Topic                              | Final answer                                                                                                                                              |
| --- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Q1  | Router thresholds                  | Default: `T_MATCH 0.55`, `T_OPT_IN 0.52`, `GAP 0.06`, `MAX_CREWS 3`, `CONT_BIAS +0.05`, `DEBATE_GAP 0.06`. `/think`: `T_MATCH 0.50`, `T_OPT_IN 0.45`, `MAX_CREWS unlimited` |
| Q2  | `contradiction_detector` + `domain_inference` | Cut entirely now (no `routing_disabled` parking)                                                                                              |
| Q3  | No-keyword fallback                | Confirmed. If embedder dies, Z handles directly with no router scores                                                                                     |
| Q4  | Crew profile content               | `name + description + characters` PLUS `instructions` + `examples` truncated to ~500 chars combined (operator override of original spec)                  |
| Q5  | Tagline                            | **"A self-hosted AI assistant that runs on your hardware and works across your messengers."**                                                             |
| Q6  | ZProtocols widget                  | **KEEP** (operator override)                                                                                                                              |
| Q7  | SystemHealth consolidation         | CUT/MERGE                                                                                                                                                 |
| Q8  | Slash command sprawl               | Cut **only `/skills`**; keep `/think`, `/custom`, `/protocols`, `/agent`, `/tree`                                                                         |
| Q9  | Deep-tier HITL                     | Autonomous default OFF on single-object ops. Hard-gate when >2 objects in one action. Always-gate on `PURGE_MEMORY`, `DELETE_PROJECT`, `DELETE_BOARD`     |
| Q10 | `/quarter` + `/year` briefings     | Cut scheduler, keep slash commands (on-demand only)                                                                                                       |
| Q11 | Dormant crew audit                 | Defer to Phase 3 (after semantic router live, so audit measures semantic relevance)                                                                       |
| Q12 | CrewBuilder widget                 | **No widget.** `personal/crews.yaml` + hot-reload only (substrate-aligned per `agents.md` rule 22)                                                        |
| Q13 | Multi-crew synthesis               | **Always-on.** `/think` only widens the panel; does not toggle synthesis                                                                                  |
| Q14 | MemorySource plugin contract       | **Cut.** Substrate framing walked back; not promised as a stable adopter contract                                                                         |
| Q9i | Reminder system                    | Phase 2: recurring `/remind weekly|daily ...`. Phase 3: adaptive crew-driven nudges gated by 9g earning rule                                              |

**Conflict resolved:** `/think` is kept (Q8) and synthesis is always-on (Q13). `/think` semantic changes from "gate synthesis" to "widen panel" (lower thresholds + uncapped crews).

---

## 16. Cross-channel memory regression test (non-negotiable)

**File:** `tests/test_cross_channel_memory.py` (new).

**Spec (brief):**

1. Send a message containing a unique memorable fact via dashboard chat API.
2. Wait for memory ingest to settle (or poke the ingest path directly).
3. Poll Telegram bot test harness (or its in-process equivalent) with a follow-up that requires recall of that fact.
4. Assert recall in the response.
5. Repeat the reverse direction (Telegram -> dashboard) and (WhatsApp -> Telegram) and (dashboard -> WhatsApp).
6. Cleanup: purge the test memory point from Qdrant.

This is the soul of the product. **Must land before any Phase 2 commit.** CI-gated.

---

## 17. Out of scope -- do NOT build

Permanently retired from the openZero roadmap as of this artifact:

- Atlas as a visualisation (UI, API, DDL, writers, walkthroughs as Atlas-backed).
- Federation (any flavour -- federated memory, federated reasoning, peer instances sharing slices).
- Ambient capture (passive screen, mic, sensor pipelines).
- Voice edge pod (dedicated mic appliance).
- `domain_inference` writing `agent/domain.derived.yaml` automatically.
- `contradiction_detector` as a scheduled background crew.
- Walkthroughs as an Atlas-backed format (the paginated mobile FORMAT is retained per section 8; the substrate is not).
- MemorySource plugin contract (cut per Q14 -- not promised as a stable adopter contract).
- CrewBuilder dashboard widget (substrate alternative chosen per Q12 -- edit `personal/crews.yaml` + hot-reload).
- Automatic `/quarter` and `/year` scheduled briefings (slash commands kept on-demand per Q10; scheduler dropped).

`docs/artifacts/substrate_master_plan.md` and `docs/artifacts/substrate_pivot.md` remain on disk for historical reference. **Where they conflict with this artifact, this artifact wins.** Future agents must read `refocus_plan.md` first.
