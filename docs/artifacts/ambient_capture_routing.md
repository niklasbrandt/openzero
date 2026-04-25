# Ambient Capture & Contextual Routing

> Architectural plan for zero-context intent inference and multi-system routing in openZero.
> Status: DRAFT | Author: conductor | Created: 2026-04-25
> Companion to: `ambient_intelligence.md` (state-diff engine, separate concern).

---

## 1. Problem Statement

> **Boundary with the state-diff engine** (`ambient_intelligence.md`): that engine reacts to *observed state changes* and fires crews proactively. This engine routes *inbound user messages* to the right destination. They share no code path beyond the unified pending queue (Section 5).

The current pipeline executes literal verbs deterministically (22 verbs across 11 languages via `intent_router.py`) and falls through to a chat LLM otherwise. Anything that is not a literal verb -- e.g. a bare phrase like "emperor angel" or "buy sourdough" -- is treated as conversation, not as a thing the user wants captured somewhere.

A real personal AI OS should treat such input the way a thoughtful assistant would:

- "emperor angel" -> that is a fish species. The user has a Reef Tank board. There is probably a Wishlist list there. Either save it silently with a brief confirm, or ask which destination fits best.
- "buy sourdough" -> that is a grocery item. The Nutrition crew already runs a weekly Shopping List. Append it there.
- "I prefer scrambled eggs" -> that is a personal preference. Store as a memory fact.
- "Marathon September 12" -> that is a calendar event.
- "I'm exhausted" -> conversational. Do not capture.

This artifact specifies the engine, signals, scoring, HITL flow, learning loop, and i18n discipline required to deliver this behaviour.

This is **additive only**. The deterministic verb pipeline remains the safety net.

> **Trust boundary**: every phrase entering this engine is **untrusted user input** that may also have been authored by a third party (e.g. forwarded message). Every signal derived from Planka content (board names, list names, card titles, descriptions) is likewise untrusted because the user can paste anything in. The engine's job is to *route*, never to *execute strings as instructions*. See Section 17 for the full security posture.

> **Single-user scope (v1)**: openZero is currently an internal single-operator tool. The Planka instance is single-tenant; multi-user / shared-board flows are out of scope for this engine and explicitly disabled (see Section 18). All threat modelling assumes one trusted operator and one untrusted message stream.

---

## 2. Decision Tree

```
User message
    |
    v
intent_bus.classify_universal_intent()
    |
    +-- PLANKA_VERB         -> existing intent_router.py (22 verbs, microseconds)
    +-- CALENDAR_INTENT     -> calendar service (CREATE_EVENT verb)
    +-- CREW_TRIGGER        -> crews.py (Nutrition crew for groceries, etc.)
    +-- MEMORY_FACT         -> memory.store_memory()
    +-- AMBIENT_CAPTURE     -> ambient_capture.py (the engine)
    +-- CHAT                -> router.py LLM fallback
```

The ambient engine only fires when no literal verb matches. Within the engine, four lanes:

| Lane | Confidence | Action |
|---|---|---|
| EXECUTE | >= silent_floor | Capture silently with brief confirm |
| ASK | >= ask_floor | Free-text HITL with top candidates |
| TEACH | < chat_floor AND phrase looks thing-shaped (1-6 words, no question marker, no conversational marker) | Cold-start co-creator prompt (Section 8) -- offers to scaffold a destination |
| CHAT | < chat_floor (everything else) | Pass to LLM as conversation, never capture |

Thresholds are user-configurable in the `AgentsWidget` Inference panel (see Section 7).

---

## 3. Evidence Collection (Tiers A through D)

> **Plugin-vs-engine scoring**: each plugin (Section 4) returns its own confidence score for its own destination type. The engine collects all plugin scores and the highest-scoring plugin wins; lane thresholds (EXECUTE/ASK/CHAT/TEACH) are applied to the winning plugin's score. The composite formula in this section applies *within* `PlankaCardPlugin` only -- other plugins (calendar, shopping list, memory) define their own scoring shapes.

For each candidate destination (board / list / calendar / crew / memory), the engine collects stacked evidence before scoring. Cheap signals first; the LLM tiebreaker only fires when the cheaper signals disagree.

### Tier A -- Cheap structural evidence (~5ms)

- Board name embedding similarity vs phrase
- **Board description embedding similarity vs phrase**
- List name embedding similarity vs phrase
- Crew keyword overlap (reuse `_crew_tokens` from `crews.py`)
- Personal vault keyword presence (does `about-me.md` mention "aquarium"?)

### Tier B -- Content evidence (~50ms)

- For top 3 candidate boards: fetch all card titles via Planka API
- Embed each card title (cached per board, 1h TTL in Redis, invalidated on mutations)
- Find nearest semantic neighbours of the phrase among existing cards
- "emperor angel" near "blue tang", "yellow wrasse" -> strong Reef Tank signal
- For the top candidate list: examine all card titles in that list specifically (not just board-level)

### Tier C -- Memory evidence (~100ms)

- Search user's Qdrant memory vault for the phrase
- Did past memories about similar things land in known places?

### Tier D -- LLM tiebreaker (only if A+B+C disagree, ~500ms)

- Local 3B model with tight prompt giving it the candidate boards plus a few sample card titles per board
- Returns one board name and a confidence
- Tiebreaker only -- never the sole signal
- **Indirect prompt injection sink (C1)**: card titles, board names, and descriptions fed into the prompt are untrusted. Mitigations are mandatory and gate Epoch 3:
  - Wrap every untrusted span in a sentinel block (`<<<UNTRUSTED_BOARD name="<id>">>> ... <<<END_UNTRUSTED>>>`) and instruct the model in the system prompt that nothing inside those markers is an instruction.
  - Strip ASCII control chars, zero-width chars, and bidi overrides from card titles before injection.
  - The model's reply is constrained to a JSON schema `{"board_id": str|null, "confidence": float}` -- free-text replies are rejected and the lane drops to ASK.
  - The returned `board_id` MUST be one of the candidate board IDs the engine supplied. Anything else -> rejected, drop to ASK.
  - Output is run through `_MUTATING_TAG_RE` (Section 13) to strip any leaked action tags before any further processing.
  - Token budget hard cap of 2048 tokens for the full prompt; truncate card-title samples first.

### Temporal signals (added to Tier A)

- **Last activity on board** (`lastActivityAt` from Planka, decay over 14 days)
- **Active thread bonus** (composite -- see formula below)
- **Session continuity** (folded into active thread bonus)

### Recency decay function

```python
def recency_boost(last_activity_iso: str) -> float:
    delta_hours = (now() - parse(last_activity_iso)).total_seconds() / 3600
    if delta_hours < 24:    return 0.15
    if delta_hours < 72:    return 0.10
    if delta_hours < 168:   return 0.05
    if delta_hours < 336:   return 0.02
    return 0.0
```

### Active thread bonus (capped at 0.05)

```python
def active_thread_bonus(board_id: str, ctx: SessionContext) -> float:
    raw = (
        (0.03 if ctx.any_card_modified_in_last_24h(board_id) else 0)
      + (0.02 if ctx.board_in_today_briefing(board_id) else 0)
      + (0.05 if board_id in ctx.session_recent_boards else 0)
      # session_recent_boards = boards mentioned in (channel, conversation_id, last 10 min)
    )
    return min(0.05, raw)   # hard clamp prevents double-counting
```

### Composite score

```python
final_score = (
    0.20 * board_name_similarity +
    0.15 * board_description_similarity +
    0.25 * card_neighbourhood_similarity +
    0.15 * list_fit_score +
    0.10 * memory_history_match +
    0.10 * recency_boost +
    0.05 * active_thread_bonus
)
```

Each component bounded `[0, 1]`. **Recency safeguard:** if recency is the only signal pushing a board over `silent_floor` (i.e. without recency the score would fall in ASK range), automatically downgrade to ASK lane. Recency is a tiebreaker, not a judge.

---

## 4. Multi-System Routing (Plugin Architecture)

The engine is system-agnostic. Built-in plugins:

```python
class CapturePlugin(Protocol):
    name: str
    async def score_match(phrase: str, context: UserContext) -> PluginScore
    async def execute_capture(phrase: str, decision: CaptureDecision) -> ActionResult
    async def explain_routing(decision: CaptureDecision, lang: str) -> str

# v1 plugins:
PlankaCardPlugin
PlankaListPlugin
PlankaBoardPlugin
CalendarEventPlugin
ShoppingListPlugin       # routes to Nutrition crew via shopping_list.append_shopping_items()
MemoryFactPlugin
ReminderPlugin

# Future plugins:
EmailDraftPlugin, JournalEntryPlugin, HealthMetricPlugin,
LocationPlugin, PersonAddPlugin
```

Each plugin is a self-contained module with its own scoring logic and i18n keys. Adding a new system never requires touching the engine core.

### Plugin scope clamps (security)

Each plugin declares a static capability manifest enforced by the engine before `execute_capture` runs:

```python
class PluginCapabilities:
    can_create_resources: bool        # may create new boards/lists/events?
    can_modify_existing: bool         # may PATCH existing items?
    can_delete: bool                  # always False in v1 -- engine rejects on True
    requires_hitl_for: set[Literal["create", "modify", "overwrite_user_authored"]]
    max_capture_size_chars: int       # phrase + metadata combined; engine truncates
```

- `can_delete = True` is rejected at registration; ambient routing never deletes.
- `requires_hitl_for` is enforced **by the engine**, never by the plugin alone (defence in depth).
- A plugin returning a destination outside its declared scope is logged, dropped, and the engine falls back to the next-best plugin.

### Routing examples

| Phrase | Route | Why |
|---|---|---|
| "emperor angel" | Planka card -> Reef Tank -> Wishlist | Card neighbourhood match |
| "Kaiserfisch" (DE) | Same | Cross-lingual embedding |
| "buy sourdough" | Shopping list (Nutrition crew weekly card) | Crew keyword + verb pattern |
| "sourdough" alone | ASK: shopping list or recipe board? | Ambiguous |
| "Marathon September 12" | Calendar event | Date pattern + event keyword |
| "I prefer scrambled eggs" | Memory fact | First-person preference |
| "every Monday water test" | Reef Tank -> Maintenance, recurring | Recurrence + board match |
| "I'm exhausted" | CHAT (no capture) | Conversational tone, low confidence |

---

## 5. Free-Text HITL (No Buttons)

WhatsApp does not render inline keyboards reliably across all clients, and openZero is conversational by design. All disambiguation is plain text the user replies to naturally.

### Phrasing templates (i18n keys, all 11 languages)

```
ambient_captured_silent      "Saved '{phrase}' to {board} -> {list}."
ambient_captured_confirm     "I think '{phrase}' belongs in {board} -> {list}. Saved it there -- let me know if it should go elsewhere."
ambient_ask_one_target       "I'd put '{phrase}' on {target_path}. Different place?"
ambient_ask_two_targets      "Could be {target_a} or {target_b} for '{phrase}'. Which fits?"
ambient_ask_three_targets    "A few possibilities for '{phrase}': {target_a}, {target_b}, or {target_c}. Or somewhere else?"
ambient_ask_open             "Want me to save '{phrase}' somewhere? Just say where in your own words."
ambient_capture_discarded    "Forgot it."
```

### Reply parser

| Reply pattern | Action |
|---|---|
| Number ("1", "2") or ordinal | Pick that candidate |
| Confirmation synonym ("yes", "ok", "ja", "si") | Accept default |
| Negation ("no", "skip", "forget", "nein") | Drop pending state |
| Phrase fuzzy-matches an offered candidate | Pick that candidate |
| Cosine sim < 0.3 to original phrase | Drop pending state, route fresh |

Confirmation/negation synonym lists are per-language in `translations.py`.

### Pending state

- Stored in Redis: `pending_capture:{user_id}:{channel}` -> `CaptureDecision` JSON (channel scoped to prevent confused-deputy across Telegram/WhatsApp/Dashboard -- H3)
- TTL: configurable in AgentsWidget (default 90 seconds)
- Cross-channel sync deferred to v2 (each channel handles its own pending state)
- If TTL expires, agent silently drops; no nagging
- Pending queue **unified** with existing `SENSITIVE_ACTIONS` HITL queue (one Redis namespace, one dashboard surface)
- **Confirmation hijack guard (C3)**: each pending entry stores the originating message hash + monotonic sequence. A reply is only accepted as confirmation if it arrives on the same `(user_id, channel)` AND no newer non-trivial inbound message has arrived in the interim. A second ambient-eligible message invalidates the pending state -- the agent re-asks rather than letting an arbitrary later reply confirm a stale capture.
- **Quote-in-confirm requirement**: the confirm reply parser requires either (a) a numeric/ordinal pick, (b) a confirmation synonym from the per-language list, OR (c) a phrase that fuzzy-matches the original capture phrase. A reply containing none of these does NOT confirm -- it is treated as a fresh inbound message.

**Cost note**: the cosine-similarity check in the reply parser triggers a 384-dim embedding compute per reply during pending state (~2-5ms via the local `all-MiniLM-L6-v2` model). This is acceptable since pending windows are short and per-user.

---

## 6. Failure Recovery & Retry

```python
class ActionExecution:
    intended_action: str
    attempts: list[Attempt]
    final_status: Literal["success", "retry_pending", "failed_reported"]

# After every action execution:
if not success:
    diagnose_failure(error)
    if recoverable:
        retry_with_corrected_params()    # board not found -> fuzzy retry
        retry_with_alternative_target()  # list missing -> fall back to Inbox + tell user
    else:
        report_to_user_clearly(intended_action, error_in_human_terms, lang)
```

Failure messages are templated in i18n. Never a generic "something went wrong". Always: what was attempted, what failed, what the user can do.

---

## 7. User Configuration (AgentsWidget Inference Panel)

A new "Inference & Autonomy" section in `AgentsWidget.ts`. Note: these thresholds activate *after* cold-start completes (see Section 8). During cold-start, the engine ignores `silent_floor` and always asks via the co-creator prompt.

### Threshold sliders

| Slider | Range | Default | Tooltip (en) |
|---|---|---|---|
| `inference_silent_floor` | 50-95% | 80% | "Above this confidence, Z saves your input silently with a brief confirm. Lower = bolder; higher = more cautious." |
| `inference_ask_floor` | 20-70% | 45% | "Above this confidence, Z asks once before saving. Below silent threshold, above this -> always asks." |
| `inference_chat_floor` | 0-40% | 20% | "Below this confidence, Z treats your input as conversation and never tries to save it." |

### Presets

Dropdown with three presets, each with a descriptive tooltip:

| Preset | Silent | Ask | Tooltip (en) |
|---|---|---|---|
| Cautious | 95 | 30 | "Z almost always asks before saving anything ambient. Best for first weeks of use or sensitive workflows." |
| Confident butler (default) | 80 | 45 | "Z saves silently when very sure, asks gracefully when not. Recommended for most users." |
| Bold autopilot | 65 | 70 | "Z captures aggressively and rarely asks. Best when you trust Z and use undo to correct rare misses." |

### Other controls

| Setting | Default | Tooltip |
|---|---|---|
| Pending TTL | 90s (configurable 30s-10m) | "How long Z waits for you to answer a clarification before silently forgetting it." |
| Routing lesson retention | **never expire** (configurable 7d-365d or never) | "How long Z remembers your past corrections to improve routing. Lessons are stored as embeddings only, never as text -- so there is no privacy benefit to expiring them. Default keeps learning compounding indefinitely." |
| Reset routing intelligence | two-step button | "Wipe all learned routing lessons. Z reverts to default behaviour. **Two-step confirmation required**: first click reveals warning, second click executes. Wipe is logged in audit trail." |

All labels, presets, and tooltips localised in all 11 languages. Stored via existing identity persistence.

---

## 8. Cold-Start (Proactive Co-Creator Mode)

For users with `boards < 5 AND cards < 20` (both conditions, not either), the engine flips to teaching mode. AND ensures a user with 6 boards but only 3 cards stays in cold-start until structure is genuinely rich enough for silent routing.

```
User: "emperor angel"
Z:    "Let's set up where this lives. I'll create a 'Reef Tank' board with a
       'Wishlist' list and put 'emperor angel' there. Sound right? Or
       somewhere else?"
```

- Agent proposes the board -> list -> card triad in one move
- One free-text reply confirms or redirects
- After ~5-10 successful captures, structure is rich enough for silent routing
- Transition is automatic (no mode switch the user has to find)

This solves cold-start and delights -- first impression is "this thing helps me organise from scratch" not "please configure me first".

---

## 9. Privacy (Auto-Classified, Not Manual)

Manual `private: true` flags do not scale. Automatic privacy classification:

### Layer 1 -- Topic-based auto-classification

On every board profile build, the local LLM scores the board against sensitive domains: health/medical, finance/income/debt, relationships/intimate, legal/disputes, identity/credentials. Boards scoring high are automatically marked sensitive in the shadow profile.

**Re-evaluation cadence**: classification re-runs on every profile refresh (Epoch 1 spec: every 15 min batch + on-mutation invalidation). A board that becomes sensitive over time is re-classified within one refresh cycle. User overrides are respected and never auto-reverted.

### Layer 2 -- Semantic neighbour quarantine

Sensitive boards' embeddings live in a separate Qdrant collection `board_profiles_private` that is only queried when the user explicitly names the board. They never appear as semantic candidates from a bare phrase.

### Layer 3 -- Dashboard visibility

Per-board privacy posture panel in the dashboard:

```
This board is treated as: [Private |v]   <- dropdown: Public / Private / Auto
Reason: Health-related content detected
[Override] [Adjust auto-classification rules]
```

Auto is the default. Three i18n keys: `privacy_public`, `privacy_private`, `privacy_auto`. Reasoning strings localised.

### Layer 4 -- First-touch dignity

The first time a board is auto-classified as sensitive, send a one-time notification: "I've marked your 'Therapy Notes' board as private -- it won't surface in suggestions unless you name it directly. Adjust this in board settings." Once, ever, per board.

---

## 10. Persistent Learning (Embedding-Only Lessons)

Learn the routing function, not the content.

### Schema

```python
RoutingLesson {
    phrase_embedding: vector[384]   # NOT the phrase text
    chosen_destination_id: str       # "board_xyz/list_abc"
    confidence_at_decision: float
    user_action: "accepted" | "moved" | "deleted" | "renamed"
    timestamp: datetime
}
```

The phrase text is never stored -- only its 384-dim embedding. Embeddings are one-way: you cannot reconstruct "emperor angel" from `[0.12, -0.45, 0.91, ...]`.

### Application

```python
similar_lessons = qdrant.search(
    collection="routing_lessons",
    query=current_phrase_embedding,
    limit=5,
    score_threshold=0.75,
)
boost = sum(l.confidence * signal_weight(l.user_action) for l in similar_lessons)
```

### Signal weights

| User action within 24h | Signal | Weight |
|---|---|---|
| Did nothing | Mild positive (silent acceptance) | +0.1 |
| Edited card details | Strong positive (engaged with it) | +0.3 |
| Moved to different board/list | Strong negative (placement was wrong) | -0.5 |
| Deleted within 1h | Very strong negative (capture was unwanted) | -0.8 |

Negatives are weighted heavier than positives because corrections are costly and information-dense.

### Privacy guarantees

- No phrase text stored, ever -- embeddings only
- Stored in user's own Qdrant instance (local-first by design)
- Lessons auto-expire (default 90 days, configurable in AgentsWidget incl. "never expire")
- One-button wipe in AgentsWidget
- Sensitive boards' lessons live in the same private collection as their profiles -- never cross-pollinate

### Anti-poisoning guards (C2)

Without guards, an attacker (or malformed automation) could rapid-fire confirmations to bias the routing function toward an attacker-chosen destination. Mitigations:

- **Per-window write rate**: at most 5 lessons written per `(user_id, 10-minute window)`. Excess is logged and dropped.
- **Embedding-cluster cap**: at most 3 lessons stored per cosine-similar cluster (sim >= 0.9) per 24h. Identical or near-identical phrases cannot stack into an arbitrary boost.
- **Boost ceiling**: total lesson-derived boost capped at `+/- 0.20` regardless of how many similar lessons match. Lessons inform, never override, the structural signals.
- **Negative-signal cooldown**: a destination that has accumulated `<= -1.0` total lesson signal is excluded from EXECUTE lane (still eligible for ASK) for the next 7 days, then re-evaluated.

---

## 11. Auto-Generated Board Descriptions

Agent extends Planka freely; HITL only on overwrite of user input.

| Scenario | Behaviour |
|---|---|
| Board has no description | Agent writes one directly. Visible immediately. No prompt. |
| Board has user-authored description | HITL: "Your Reef Tank description currently says 'Saltwater 200L'. I'd like to extend it with 'fish wishlist, water log, livestock'. Replace, append, or skip?" |
| Board has prior agent-authored description | Agent updates freely. Tracked via `agent_authored: true` in a Redis sidecar `planka_authorship` hash. |

Same pattern extends to lists, projects, and card descriptions.

**Generation trigger**: lazily on first profile build for each board. Re-generated only when the board has had >= 5 new cards added since the last description and the existing description's embedding similarity to the current card neighbourhood drops below 0.6 (i.e. the board's actual purpose has shifted). Never on a fixed timer.

**Reflected-injection sanitiser (M4)**: the LLM that drafts auto-descriptions is fed card titles as untrusted spans (same sentinel pattern as Tier D). The drafted output is then run through:

- ASCII control / zero-width / bidi-override stripping
- `_MUTATING_TAG_RE` (no leaked action tags written into Planka)
- Length cap: 500 chars
- URL allow-list: only `wikipedia.org`, `youtube.com`, `youtu.be`, plus user-configured allowed domains. Any other URL is dropped from the draft.
- Image / iframe / `javascript:` strip-out (Planka renders Markdown -- no script vectors, but defensive)

---

## 12. i18n Discipline

Every new key lands in all 11 language files before merge, enforced by `test_i18n_coverage.py`.

### New translation sections

1. **Inference settings UI** (~12 keys: section title, slider labels, slider help text, preset names, preset tooltips, pending TTL label, lesson retention label, reset button)
2. **Ambient capture phrasing** (~25 keys: ask templates, confirms, retry messages, failure reports)
3. **Cross-system routing confirmations** (~6 keys: captured_to_card, captured_to_calendar, captured_to_shopping_list, captured_to_memory, captured_to_crew_output, captured_to_reminder)
4. **Conversational markers per language** (3 keys per language: question_words, speech_markers, filler_words -- so the thing-detector knows what is a question vs a fact in each language)
5. **Privacy posture** (3 keys: privacy_public, privacy_private, privacy_auto + reasoning strings)
6. **Reasoning trace fragments** (~6 keys: reasoning_recent_activity, reasoning_dormant, reasoning_session_continuity, reasoning_card_neighbours, reasoning_memory_match, reasoning_user_history)

### Composition rule

Use full template strings per language (no concatenation):

```python
# WRONG
msg = tr("captured") + " '" + phrase + "' " + tr("to") + " " + board

# RIGHT
msg = tr("ambient_captured_silent").format(phrase=phrase, board=board, list=list_name)
```

Each language can reorder freely (DE word order, JA particles, AR RTL).

### No transliteration

Language-specific characters stored as literal Unicode. Enforced by existing tests for DE; same standard for all languages.

---

## 13. Architectural Cohesion

Cross-checked against actual files:

| Existing piece | How the plan uses it |
|---|---|
| `intent_router.py` (22 verbs, regex) | Renamed to `planka_intent_router.py` when `intent_bus.py` lands, so router hierarchy is unambiguous. `intent_bus.py` is the single top-level dispatcher and calls `classify_structural_intent` first. |
| `agent_actions.py` executors | Plugins call existing executors. New: `execute_ambient_capture()`, `execute_capture_to_shopping_list()`. |
| `crews.py` `_crew_tokens`, `_jaccard` | Reused as Tier A evidence for crew routing. |
| `shopping_list.py` `append_shopping_items` | Called by `ShoppingListPlugin` -- no changes. |
| `memory.py` Qdrant + 384-dim embeddings | Provides Tier C evidence + embeds board content. New collections: `board_profiles`, `board_profiles_private`, `routing_lessons`. |
| `translations.py` + i18n CI gate | All new keys gated. No stubs. |
| `AgentsWidget.ts` | New "Inference" panel. Same render pattern as Personality. |
| Redis (Celery worker config) | Pending capture state, 90s TTL configurable. |
| `planka.py` `create_task` fuzzy match | Becomes the fallback below ambient routing. |
| `_MUTATING_TAG_RE` in `agent_actions.py` | Extended to cover any tag the Tier D / auto-description LLMs could plausibly emit. Output of every LLM call in this engine is run through it before it touches downstream code. |
| `SENSITIVE_ACTIONS` + `store_pending_thought` | Unified with ambient pending queue. One Redis namespace, one dashboard surface. |
| `_sanitize_for_log` in `agent_actions.py` | Mandatory wrapper for every phrase, board name, list name, and card title before any `logger.*` call in the engine (H1 -- prevents private content leaking into logs/Sentry/dashboard error toasts). |
| Single-user / single-tenant Planka | Engine assumes one operator (Section 18). All capture targets must belong to the operator's user; cross-user board IDs are rejected at plugin scope-check time. |

Nothing the system already does today gets removed or rewritten. This is purely additive intelligence.

---

## 14. Phasing (3 Epochs)

### Epoch 1 -- Foundation (no user-visible change)

- Board profile builder + Redis cache (incl. descriptions, recency, modification dates)
- `intent_bus.py` skeleton
- Plugin interface + capability manifests + tests
- Unified pending queue (refactor existing HITL into the new shape)
- Failure recovery layer
- **Security baseline (gate)**: `tests/test_ambient_capture_security.py` skeleton green, `_MUTATING_TAG_RE` extension landed, `_sanitize_for_log` wrappers landed, single-user scope check in plugin base class.
- Ships dark. No behaviour change. Only logs.

### Epoch 2 -- Intelligence (gated behind `AMBIENT_CAPTURE_ENABLED`)

- Tier A+B+C evidence collection
- Composite scoring with capped weights
- Free-text HITL on **all three channels** (Telegram, WhatsApp, Dashboard) -- the no-buttons design exists specifically because WhatsApp lacks reliable inline keyboards, so excluding it would defeat the rationale
- Ambient capture for Planka cards only (narrowest surface)
- Channel-scoped pending state with hijack guard (C3)
- Anti-poisoning guards on routing lessons (C2) live before lessons start writing
- Inference threshold sliders + tooltips in AgentsWidget (i18n)
- Operator opts in per channel.
- **Security gate**: full Epoch-2 row of `test_ambient_capture_security.py` green; manual prompt-injection review of HITL phrasing templates.

### Epoch 3 -- Expansion

- Multi-system plugins live (calendar, shopping list, memory, crew triggers)
- Tier D LLM tiebreaker (with C1 mitigations: sentinel wrapping, JSON schema, candidate-ID whitelist, output sanitiser)
- Reasoning trace in dashboard
- Cold-start teaching mode
- Negative-signal learning from undo
- Auto-generated board descriptions (with HITL on user-authored overwrite, M4 sanitiser, URL allow-list)
- Auto-classified privacy + first-touch dignity notifications
- Each plugin gates its own activation.
- **Security gate**: full Epoch-3 row of `test_ambient_capture_security.py` green; LLM-output schema validators in CI; auto-description draft sanitiser fuzz-tested; multi-user code paths re-audited if/when single-user assumption changes.

---

## 15. Acceptance Test Matrix

`tests/test_ambient_capture.py` -- parameterised across all 11 languages. Each phrase below has a native-language equivalent in **at least 5 of the 11 languages** (EN, DE, ES, FR, JA chosen as the v1 i18n acceptance set; remaining 6 languages added incrementally as native fluency reviews complete).

```
"emperor angel"                    -> Reef Tank -> Wishlist (silent)
"Kaiserfisch"           [DE]       -> Reef Tank -> Wishlist (silent, cross-lingual)
"pez ángel emperador"   [ES]       -> same
"poisson-ange empereur" [FR]       -> same
"エンペラーエンジェル"          [JA]       -> same
"sourdough bread"                  -> This week's shopping list
"Sauerteigbrot"         [DE]       -> same
"buy 2L milk"                      -> Shopping list (verb anchors it)
"sourdough" (alone)                -> ASK: shopping list or recipe board?
"Marathon September 12"            -> Calendar event
"I prefer scrambled eggs"          -> Memory fact
"every Monday water test"          -> Reef Tank -> Maintenance, recurring
"I'm exhausted"                    -> CHAT (no capture)
"Ich bin erschöpft"     [DE]       -> CHAT (no capture, marker-detected as conversational)
"thinking about getting an axolotl"-> ASK: research note or wishlist? (hedge detected)
```

Success metrics:
- Silent-capture accuracy: >= 85% after 30 days for active users
- HITL frequency: < 30% of ambient captures
- Wrong-board correction rate: < 5%
- Equal experience across all 11 languages (per-language accuracy delta < 10%)

### Security test matrix (`tests/test_ambient_capture_security.py`)

Gates each epoch (see Section 14). 50+ stubs across 12 attack classes -- see Section 17 for the full class list. Categories: prompt-injection in card titles, prompt-injection in board descriptions, RoutingLesson poisoning, pending-state hijack across channels, scope-clamp violations, log injection / private-content leakage, embedding-inference probes, regex DoS, URL exfiltration in auto-descriptions, retry-loop amplification, sentinel-bypass attempts, single-user-scope bypass attempts.

### Telemetry & observability

Each ambient decision logs a `CaptureEvent` row to a dedicated `capture_events` table:

```
capture_events {
    id: uuid
    timestamp: datetime
    user_id: str
    channel: "telegram" | "whatsapp" | "dashboard"
    phrase_embedding: vector[384]   # NOT the phrase text
    chosen_destination_id: str
    confidence: float
    lane: "EXECUTE" | "ASK" | "TEACH" | "CHAT"
    plugin_name: str
    user_action_within_24h: "accepted" | "moved" | "deleted" | "renamed" | null
}
```

The Diagnostics widget surfaces aggregate metrics: silent-capture accuracy, HITL frequency, wrong-board correction rate, per-channel breakdown, per-language breakdown. Same privacy posture as routing lessons -- embeddings only, no phrase text. Auto-purged on routing-lesson wipe.

---

## 16. Decisions Logged

| Question | Answer |
|---|---|
| Default preset for new users | "Confident butler" (with tooltip explaining trade-off) |
| Routing lesson retention | Configurable in AgentsWidget; default **never expire** (embedding-only, no privacy benefit to decay); 7d-365d also available |
| Cold-start threshold | `boards < 5 AND cards < 20` (both, not either); auto-transition; agent's summarised confirms remain the user's "wrong action" alert |
| Pending capture TTL | 90s default; configurable 30s-10m in AgentsWidget |
| Cross-channel pending sync | Deferred to v2 |
| Auto board descriptions | Allowed freely; HITL only on overwrite of user-authored content; sanitiser + URL allow-list (Section 11) |
| Privacy classification | Automatic per-board via local LLM topic scoring; transparent in dashboard; one-time first-touch notification |
| Persistent learning | Embedding-only `RoutingLesson` records; negative-signal weighted; auto-expire; user-wipeable; private boards isolated; anti-poisoning guards (Section 10) |
| Operator scope | **Single-user / single-tenant** (Section 18). Multi-user Planka integration explicitly disabled in v1. Cross-user board IDs rejected at plugin scope check. |
| Intent router regex hard cap | Raised from 80/120 to **200 chars** for all card / list / board name slots in `intent_router.py` to accommodate longer titles without forcing fallback to LLM routing. |

---

## 17. Security Posture

Full threat model and mitigations. Every Epoch is gated by the corresponding row of `tests/test_ambient_capture_security.py` going green.

### Threat classes

| ID | Class | Vector | Mitigation | Section |
|---|---|---|---|---|
| C1 | Indirect prompt injection (Tier D) | Card titles / board descriptions injected as instructions to the LLM tiebreaker | Sentinel wrapping, control-char strip, JSON-schema reply, candidate-ID whitelist, `_MUTATING_TAG_RE` on output | 3 |
| C2 | Routing-lesson poisoning | Forced-confirmation flood biases routing function | Per-window rate limit, embedding-cluster cap, boost ceiling +/-0.20, negative-signal cooldown | 10 |
| C3 | Confirmation hijack | Stale pending state confirmed by an unrelated later message | Channel-scoped Redis key, monotonic sequence + invalidation on new ambient message, quote-in-confirm requirement | 5 |
| H1 | Private-content leakage via logs | Board names / phrases written to logs, Sentry, dashboard error toasts | Mandatory `_sanitize_for_log` wrapper, sensitive boards excluded from any error string surfaced cross-user | 13 |
| H2 | Cold-start privilege escalation | Phrase contains injection -> co-creator scaffolds attacker-controlled board+list+card | Cold-start runs through the same Tier D sanitiser; HITL is mandatory in TEACH lane (no silent execution); proposed names sanitised before display | 8, 17.2 |
| H3 | Confused-deputy across channels | Pending on Telegram confirmed via WhatsApp reply | Channel-scoped pending key (Section 5) | 5 |
| H4 | Tag leakage from LLM outputs | Tier D / auto-description LLM emits action tags that downstream parser executes | Extended `_MUTATING_TAG_RE` applied to every LLM output in the engine | 13 |
| M1 | Telemetry side-channel | `capture_events` table reveals private board IDs to anyone with DB read access | Embeddings-only; chosen_destination_id hashed if board is private; admin-only DB access | 15, 17.3 |
| M2 | Embedding inference attack | Stored embeddings + known model -> reconstruct phrases via nearest-neighbour search | Local-only Qdrant; `routing_lessons` collection access-controlled to backend service account; user-wipe button (Section 10) |
| M3 | Regex catastrophic backtracking | Crafted phrase triggers exponential backtracking in conversational-marker regex | Linear non-overlapping patterns only (per repo rule 20); per-call regex timeout via `regex` package or pre-length-check | 17.4 |
| M4 | Reflected injection in auto-descriptions | LLM draft contains `javascript:` URL or external image tracker | Sanitiser + URL allow-list (Section 11) |
| M5 | Retry-loop amplification | Failure recovery retries trigger downstream rate-limit / cost spike | Hard retry cap (3), exponential backoff, circuit breaker per plugin | 6, 17.5 |

### 17.1 What the plan already gets right

- Embedding-only learning -- no plaintext storage of phrases anywhere persistent.
- Privacy auto-classification -- removes manual-flag burden and human error.
- Local embedder (`all-MiniLM-L6-v2`) -- no third-party content exfiltration.
- i18n discipline -- no English-string assumptions that could be bypassed in other languages.
- Two-step confirmation for routing-intelligence wipe -- prevents accidental destruction.
- Recency safeguard -- recency alone can't push a silent destination over the threshold.
- Plugin isolation with capability manifests -- defence in depth.
- Unified pending queue -- single audit surface.

### 17.2 H2 detail (cold-start)

Cold-start is a privileged path because it can create new boards, lists, and cards in one turn. Hardening:

- Cold-start NEVER silently executes. Always TEACH lane -> HITL.
- Proposed board / list / card names are sanitised (control chars, length cap 100, sentinel-stripped) before being shown to the user in the confirm prompt.
- A single TEACH confirm authorises exactly one board+list+card triad. Subsequent input restarts the flow.
- Cold-start scaffolding is rate-limited: at most 3 boards / 10 lists / 30 cards per `(user_id, hour)`. Exceeding triggers a soft pause and a dashboard notice.

### 17.3 Telemetry (M1)

- `capture_events.chosen_destination_id` is hashed (`hmac-sha256` with a per-instance secret) when the destination is on a private board, so even a DB dump does not reveal which private boards were targeted.
- `phrase_embedding` is rounded to int8 quantisation in the events table (full precision only in `routing_lessons`) to reduce inference attack surface.
- The Diagnostics widget shows aggregate metrics only -- per-event drill-down is dashboard-auth gated.

### 17.4 Regex DoS (M3)

- All conversational-marker / thing-shape regexes use linear, non-overlapping patterns (per repo `agents.md` rule 20).
- Phrases longer than `MAX_AMBIENT_PHRASE_CHARS` (default 500) are clamped before any regex runs -- the engine treats the truncated form as the canonical phrase.
- A per-classification wall-clock budget of 50ms is enforced; exceeding it logs and falls back to CHAT lane.

### 17.5 Failure recovery hardening (M5)

- Per-plugin circuit breaker: 5 consecutive failures within 60s -> plugin disabled for 5 min, falls back to next-best plugin.
- Hard retry cap of 3 per `ActionExecution`, exponential backoff (200ms, 800ms, 3.2s).
- Retry loop never re-enters Tier D -- once tiebreaker has fired, retries reuse the same decision rather than re-prompting the LLM.

### 17.6 Security CI gates

- `tests/test_ambient_capture_security.py` -- 50+ stubs, parameterised across attack classes above. Must be all green before each Epoch ships.
- Bandit + ruff `S` rules clean for all new modules.
- Manual prompt-injection review checkpoint required before Epoch 3 (Tier D LLM goes live).

---

## 18. Single-User / Single-Tenant Mode (v1)

openZero is currently an internal personal AI OS for one operator. The Planka instance is single-tenant. Until that changes, the engine operates under explicit single-user assumptions:

- **No board sharing**: the engine refuses to capture into boards owned by any user other than the configured operator. Cross-user board IDs surfaced by the Planka API are filtered out at the `PlankaCardPlugin.score_match` stage.
- **No project sharing**: same rule for projects.
- **No multi-user HITL**: pending states are scoped to the single operator's `user_id`. There is no "assigned to" or "mention" routing.
- **No external invites**: the agent never suggests inviting users, sharing boards, or generating share links. Any such request from the LLM is stripped by a dedicated rule in `_MUTATING_TAG_RE`'s extended set.
- **Operator identity**: derived from a single env var / config setting (`OPERATOR_USER_ID`); failing to resolve aborts engine startup rather than defaulting open.

If the project ever moves to multi-user, this section is the explicit checklist that must be re-audited before flipping the switch. Each of the threat classes in Section 17 must be re-evaluated under a hostile-user-on-shared-board model -- in particular C2 (lesson poisoning between users), C3 (cross-user confirmation hijack), H1 (board content leaking across user boundaries), and M1 (telemetry cross-user inference).
