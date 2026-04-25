# Ambient Capture & Contextual Routing

> Architectural plan for zero-context intent inference and multi-system routing in openZero.
> Status: DRAFT | Author: conductor | Created: 2026-04-25
> Companion to: `ambient_intelligence.md` (state-diff engine, separate concern).

---

## 1. Problem Statement

The current pipeline executes literal verbs deterministically (22 verbs across 11 languages via `intent_router.py`) and falls through to a chat LLM otherwise. Anything that is not a literal verb -- e.g. a bare phrase like "emperor angel" or "buy sourdough" -- is treated as conversation, not as a thing the user wants captured somewhere.

A real personal AI OS should treat such input the way a thoughtful assistant would:

- "emperor angel" -> that is a fish species. The user has a Reef Tank board. There is probably a Wishlist list there. Either save it silently with a brief confirm, or ask which destination fits best.
- "buy sourdough" -> that is a grocery item. The Nutrition crew already runs a weekly Shopping List. Append it there.
- "I prefer scrambled eggs" -> that is a personal preference. Store as a memory fact.
- "Marathon September 12" -> that is a calendar event.
- "I'm exhausted" -> conversational. Do not capture.

This artifact specifies the engine, signals, scoring, HITL flow, learning loop, and i18n discipline required to deliver this behaviour.

This is **additive only**. The deterministic verb pipeline remains the safety net.

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

The ambient engine only fires when no literal verb matches. Within the engine, three lanes:

| Lane | Confidence | Action |
|---|---|---|
| EXECUTE | >= silent_floor | Capture silently with brief confirm |
| ASK | >= ask_floor | Free-text HITL with top candidates |
| CHAT | < chat_floor | Pass to LLM as conversation, never capture |

Thresholds are user-configurable in the `AgentsWidget` Inference panel (see Section 7).

---

## 3. Evidence Collection (Tiers A through D)

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

### Temporal signals (added to Tier A)

- **Last activity on board** (`lastActivityAt` from Planka, decay over 14 days)
- **Card velocity** (cards added in last 7 days)
- **Session continuity boost** (within `(channel, conversation_id, last 10 minutes)`, +0.10 for boards mentioned earlier in the same thread)

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

- Stored in Redis: `pending_capture:{user_id}` -> `CaptureDecision` JSON
- TTL: configurable in AgentsWidget (default 90 seconds)
- Cross-channel sync deferred to v2 (each channel handles its own pending state)
- If TTL expires, agent silently drops; no nagging
- Pending queue **unified** with existing `SENSITIVE_ACTIONS` HITL queue (one Redis namespace, one dashboard surface)

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

A new "Inference & Autonomy" section in `AgentsWidget.ts` with:

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
| Routing lesson retention | 90 days (configurable 7d-365d, also "never expire") | "How long Z remembers your past corrections to improve routing. Lessons are stored as embeddings only, never as text." |
| Reset routing intelligence | button | "Wipe all learned routing lessons. Z reverts to default behaviour." |

All labels, presets, and tooltips localised in all 11 languages. Stored via existing identity persistence.

---

## 8. Cold-Start (Proactive Co-Creator Mode)

For users with `< 5 boards` or `< 20 cards`, the engine flips to teaching mode.

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

---

## 11. Auto-Generated Board Descriptions

Agent extends Planka freely; HITL only on overwrite of user input.

| Scenario | Behaviour |
|---|---|
| Board has no description | Agent writes one directly. Visible immediately. No prompt. |
| Board has user-authored description | HITL: "Your Reef Tank description currently says 'Saltwater 200L'. I'd like to extend it with 'fish wishlist, water log, livestock'. Replace, append, or skip?" |
| Board has prior agent-authored description | Agent updates freely. Tracked via `agent_authored: true` in a Redis sidecar `planka_authorship` hash. |

Same pattern extends to lists, projects, and card descriptions.

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
| `intent_router.py` (22 verbs, regex) | Untouched. Runs first. Engine fires only when no verb matches. |
| `agent_actions.py` executors | Plugins call existing executors. New: `execute_ambient_capture()`, `execute_capture_to_shopping_list()`. |
| `crews.py` `_crew_tokens`, `_jaccard` | Reused as Tier A evidence for crew routing. |
| `shopping_list.py` `append_shopping_items` | Called by `ShoppingListPlugin` -- no changes. |
| `memory.py` Qdrant + 384-dim embeddings | Provides Tier C evidence + embeds board content. New collections: `board_profiles`, `board_profiles_private`, `routing_lessons`. |
| `translations.py` + i18n CI gate | All new keys gated. No stubs. |
| `AgentsWidget.ts` | New "Inference" panel. Same render pattern as Personality. |
| Redis (Celery worker config) | Pending capture state, 90s TTL configurable. |
| `planka.py` `create_task` fuzzy match | Becomes the fallback below ambient routing. |
| `_MUTATING_TAG_RE` in `agent_actions.py` | Unchanged. Ambient capture emits the same tags so existing dedup, HITL, and audit logging all work. |
| `SENSITIVE_ACTIONS` + `store_pending_thought` | Unified with ambient pending queue. One Redis namespace, one dashboard surface. |

Nothing the system already does today gets removed or rewritten. This is purely additive intelligence.

---

## 14. Phasing (3 Epochs)

### Epoch 1 -- Foundation (no user-visible change)

- Board profile builder + Redis cache (incl. descriptions, recency, modification dates)
- `intent_bus.py` skeleton
- Plugin interface + tests
- Unified pending queue (refactor existing HITL into the new shape)
- Failure recovery layer
- Ships dark. No behaviour change. Only logs.

### Epoch 2 -- Intelligence (gated behind `AMBIENT_CAPTURE_ENABLED`)

- Tier A+B+C evidence collection
- Composite scoring with capped weights
- Free-text HITL (Telegram + Dashboard first)
- Ambient capture for Planka cards only (narrowest surface)
- Inference threshold sliders + tooltips in AgentsWidget (i18n)
- Operator opts in per channel.

### Epoch 3 -- Expansion

- Multi-system plugins live (calendar, shopping list, memory, crew triggers)
- Tier D LLM tiebreaker
- Reasoning trace in dashboard
- Cold-start teaching mode
- Negative-signal learning from undo
- Auto-generated board descriptions (with HITL on user-authored overwrite)
- Auto-classified privacy + first-touch dignity notifications
- Each plugin gates its own activation.

---

## 15. Acceptance Test Matrix

`tests/test_ambient_capture.py` -- parameterised across all 11 languages where translatable.

```
"emperor angel"                    -> Reef Tank -> Wishlist (silent)
"Kaiserfisch"           [DE]       -> Reef Tank -> Wishlist (silent, cross-lingual)
"sourdough bread"                  -> This week's shopping list
"buy 2L milk"                      -> Shopping list (verb anchors it)
"sourdough" (alone)                -> ASK: shopping list or recipe board?
"Marathon September 12"            -> Calendar event
"I prefer scrambled eggs"          -> Memory fact
"every Monday water test"          -> Reef Tank -> Maintenance, recurring
"I'm exhausted"                    -> CHAT (no capture)
"thinking about getting an axolotl"-> ASK: research note or wishlist? (hedge detected)
```

Success metrics:
- Silent-capture accuracy: >= 85% after 30 days for active users
- HITL frequency: < 30% of ambient captures
- Wrong-board correction rate: < 5%
- Equal experience across all 11 languages (per-language accuracy delta < 10%)

---

## 16. Decisions Logged

| Question | Answer |
|---|---|
| Default preset for new users | "Confident butler" (with tooltip explaining trade-off) |
| Routing lesson retention | Configurable in AgentsWidget; default 90 days; "never expire" option available |
| Cold-start threshold | < 5 boards OR < 20 cards (whichever takes longer); auto-transition; agent's summarised confirms remain the user's "wrong action" alert |
| Pending capture TTL | 90s default; configurable 30s-10m in AgentsWidget |
| Cross-channel pending sync | Deferred to v2 |
| Auto board descriptions | Allowed freely; HITL only on overwrite of user-authored content |
| Privacy classification | Automatic per-board via local LLM topic scoring; transparent in dashboard; one-time first-touch notification |
| Persistent learning | Embedding-only `RoutingLesson` records; negative-signal weighted; auto-expire; user-wipeable; private boards isolated |
