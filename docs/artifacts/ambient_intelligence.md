# Ambient Intelligence -- Proactive State-Diff Engine

> Architectural plan for event-driven crew triggering in openZero.
> Status: DRAFT | Author: conductor | Created: 2026-04-12

---

## 1. Problem Statement

Z is fundamentally reactive. The crew scheduler runs on fixed cadences (cron / briefing-relative), not in response to observed state changes. The proactive follow-up system (`follow_up.py`) nudges on Today-list items but only checks card presence -- it does not correlate signals across data sources.

The next architectural leap is a lightweight **state-diff engine** that continuously snapshots data sources, computes meaningful deltas, evaluates trigger rules across domains, and autonomously fires crews or surfaces insights before the user asks.

**Concrete scenario:** Z notices three Planka cards in "In Progress" have not moved in 4 days, the calendar shows back-to-back meetings tomorrow, and HRV is trending down. It autonomously fires `flow` + `health` as a panel, produces a "you are overloaded" briefing, and pushes it to Telegram at a quiet moment.

---

## 2. Architecture Overview

```
                         Snapshot Loop (60s default)
                                  |
       +----------+----------+---+---+----------+----------+
       |          |          |       |          |          |
   [Planka]  [Calendar]  [Email] [Health]  [Hardware]  [Custom]
       |          |          |       |          |          |
       v          v          v       v          v          v
   Adapter    Adapter    Adapter  Adapter   Adapter    Adapter
       |          |          |       |          |          |
       +-----+----+----+----+---+---+----+-----+          |
             |              |            |                 |
         Snapshots     State Store   Diff Engine           |
             |              |            |                 |
             +--------------+----+-------+                 |
                                 |                         |
                          Trigger Rule Engine               |
                                 |                         |
                    +------------+------------+            |
                    |                         |            |
              Crew Dispatch            Direct Insight      |
                    |                         |            |
              Delivery Scheduler              |            |
                    |                         |            |
               bus.push_all()           bus.push_all()     |
```

### Core Components

| Component | Responsibility |
|-----------|---------------|
| **StateAdapter** | Fetches a typed snapshot from one data source |
| **StateStore** | Holds the last N snapshots per source in Redis |
| **DiffEngine** | Compares current vs. previous snapshot, emits typed `Signal` objects |
| **TriggerRuleEngine** | Evaluates rules that combine signals across sources into `Trigger` objects |
| **CrewDispatcher** | Maps triggers to crew firings with injected context |
| **DeliveryScheduler** | Holds triggers until a quiet delivery window, then pushes via `bus.push_all()` |

---

## 3. Data Source Adapters

Each adapter implements a common protocol:

```python
class StateAdapter(Protocol):
	source_id: str                     # e.g. "planka", "calendar", "email"
	poll_interval_s: int               # how often to snapshot (overridable in config)

	async def snapshot(self) -> dict:  # returns a JSON-serialisable state dict
		...
```

### 3.1 Planka Board Velocity

**Existing code:** `planka.get_activity_report()` already classifies cards as completed / in-progress / stalled / blocked and detects WIP violations. `get_project_tree()` returns full board structure with 1-min TTL cache.

**Snapshot schema:**
```python
{
	"in_progress": [{"name": str, "board": str, "days_active": int}],
	"stalled": [{"name": str, "board": str, "last_activity": str}],
	"blocked": [{"name": str, "board": str}],
	"completed_24h": int,
	"wip_violations": [{"board": str, "list": str, "count": int}],
	"today_count": int,           # cards on Operator Board Today list
	"this_week_count": int,       # cards on Operator Board This Week list
}
```

**Interesting diffs:**
- Card stall threshold crossed (0 -> N cards stalled > 4 days)
- WIP violation appeared (new board exceeding limit)
- Today list grew beyond 5 items (overcommitment signal)
- Completion velocity dropped (fewer cards done this period vs. previous)
- Blocked cards appeared or persisted beyond 48h

### 3.2 Calendar Density

**Existing code:** `calendar.fetch_calendar_events()` returns events from Google Calendar + CalDAV + local events with deduplication.

**Snapshot schema:**
```python
{
	"today_events": int,
	"today_meeting_hours": float,   # sum of event durations
	"today_gaps_minutes": [int],    # free gaps between events
	"tomorrow_events": int,
	"tomorrow_meeting_hours": float,
	"next_event_minutes": int,      # minutes until next event
	"travel_detected": bool,        # flight/trip keyword in upcoming events
	"back_to_back_count": int,      # sequences with <15min gap
}
```

**Interesting diffs:**
- Tomorrow meeting hours > 6 (calendar overload incoming)
- Back-to-back count > 3 (no recovery time)
- Travel detected (triggers travel crew consideration)
- Next event in < 30 minutes (suppress non-urgent pushes)
- Today has zero gaps > 30 minutes (deep work impossible)

### 3.3 Email Urgency

**Existing code:** `gmail.fetch_unread_emails()` returns unread messages. `email_poll.py` runs every 10 minutes. `EmailSummary` model stores processed emails with badges (`priority`, `action-required`, `finance`).

**Snapshot schema:**
```python
{
	"unread_count": int,
	"priority_count": int,           # emails badged priority/action-required
	"unread_age_hours_max": float,   # oldest unread
	"new_since_last": int,           # delta from previous snapshot
	"sender_clusters": dict,         # top senders with count
}
```

**Interesting diffs:**
- Priority email count crossed threshold (0 -> 1+)
- Unread count growing faster than processing (inbox overwhelm)
- Same sender sent 3+ emails in 2 hours (someone is waiting)
- Oldest unread > 24h and badged action-required

### 3.4 Health / Biometric Trends

**Existing code:** `personal/health.md` contains health context. The `health` crew has keywords for sleep, HRV, recovery, biometric, fatigue, stress, burnout, resting heart rate. Currently there is no live biometric feed -- health data is injected via personal context files.

**Snapshot schema (future-ready):**
```python
{
	"hrv_trend": str,               # "up" | "down" | "stable" | "unknown"
	"rhr_bpm": int | None,         # resting heart rate
	"sleep_hours": float | None,
	"recovery_score": int | None,   # 0-100 if wearable provides
	"strain_score": int | None,
	"stress_keywords_detected": bool, # from recent messages
}
```

**Bootstrap strategy:** Until a wearable API is integrated, this adapter has two signal sources:
1. **Personal context file** -- parse `personal/health.md` for structured data (weight targets, training schedule, known conditions)
2. **Conversational signals** -- scan recent GlobalMessage history for stress/fatigue/sleep keywords the user mentioned to Z

**Interesting diffs:**
- HRV trending down for 3+ consecutive days
- User mentioned sleep problems or fatigue in last 24h
- Recovery score below threshold
- No exercise-related conversation in 7+ days (sedentary drift)

### 3.5 Hardware Load

**Existing code:** `/api/system` endpoint returns CPU, memory, disk, Redis stats, Qdrant stats, Pi-hole stats, Docker container health. The `HardwareMonitor.ts` dashboard component consumes this.

**Snapshot schema:**
```python
{
	"cpu_percent": float,
	"memory_percent": float,
	"disk_percent": float,
	"container_unhealthy": list[str],  # names of unhealthy containers
	"llm_queue_depth": int,            # pending inference requests
	"qdrant_points": int,
}
```

**Interesting diffs:**
- Disk usage > 85% (cleanup needed)
- Container went unhealthy (service degradation)
- LLM queue depth > 5 (inference bottleneck)
- Memory > 90% (OOM risk)

### 3.6 Conversational Signals (Meta-Adapter)

**Existing code:** `message_bus.py` stores all messages in `GlobalMessage`. `message_watchdog.py` scans for unanswered messages. `follow_up.py` tracks active sessions.

**Snapshot schema:**
```python
{
	"messages_last_hour": int,
	"last_user_message_age_minutes": int,
	"active_tracking_sessions": int,
	"sentiment_keywords": list[str],  # extracted stress/positive indicators
	"unanswered_count": int,
}
```

**Interesting diffs:**
- User has been silent for 4+ hours during active hours (check-in opportunity)
- Rapid message burst (user is stressed or excited)
- Unanswered messages appeared (system recovery needed -- already handled by watchdog, but can feed broader context)

---

## 4. State Store

Redis-backed circular buffer per source. Each snapshot is stored as a JSON blob with a TTL.

**Key format:** `oz:ambient:{source_id}:snapshots` (Redis list, newest at head)

**Retention:** Last 24 snapshots per source (at 60s interval = 24 minutes of history; at 5min = 2 hours). Configurable per adapter.

**Implementation:** Use `LPUSH` + `LTRIM` for bounded storage. No schema migration needed -- this is ephemeral operational state, not persistent data.

```python
class StateStore:
	def __init__(self, redis_client: Redis, max_snapshots: int = 24):
		self.r = redis_client
		self.max = max_snapshots

	async def push(self, source_id: str, snapshot: dict) -> None:
		key = f"oz:ambient:{source_id}:snapshots"
		await self.r.lpush(key, json.dumps(snapshot))
		await self.r.ltrim(key, 0, self.max - 1)
		await self.r.expire(key, 7200)  # 2h TTL safety net

	async def latest(self, source_id: str, n: int = 2) -> list[dict]:
		key = f"oz:ambient:{source_id}:snapshots"
		raw = await self.r.lrange(key, 0, n - 1)
		return [json.loads(r) for r in raw]
```

---

## 5. Diff Engine

Compares the latest snapshot against the previous one (or the last N for trend detection) and emits typed `Signal` objects.

```python
@dataclass
class Signal:
	source: str           # adapter source_id
	kind: str             # e.g. "card_stall_threshold", "calendar_overload"
	severity: float       # 0.0 - 1.0
	detail: dict          # source-specific payload
	timestamp: datetime
```

Each adapter defines its own diff logic as a set of `SignalRule` functions:

```python
# Example: Planka stall detection
def detect_card_stalls(current: dict, previous: dict | None) -> list[Signal]:
	stalled = [c for c in current["stalled"] if c["days_active"] >= 4]
	if not stalled:
		return []
	return [Signal(
		source="planka",
		kind="card_stall_threshold",
		severity=min(1.0, len(stalled) * 0.2),
		detail={"stalled_cards": stalled},
		timestamp=datetime.now(),
	)]
```

The DiffEngine runs all registered signal rules after each snapshot cycle and collects emitted signals into a time-windowed buffer.

---

## 6. Trigger Rule Engine

Rules combine signals from multiple sources into actionable triggers. Each rule is a pure function that receives the current signal buffer and returns zero or one `Trigger`.

```python
@dataclass
class Trigger:
	rule_id: str              # e.g. "overload_composite"
	priority: int             # 1 (critical) to 5 (informational)
	crews: list[str]          # crew IDs to fire
	context: str              # injected into crew prompt
	cooldown_minutes: int     # minimum time before this rule can fire again
	delivery: str             # "immediate" | "quiet_moment" | "next_briefing"
```

### 6.1 Example Rules

**Overload Composite** (the scenario from the problem statement):
```python
def rule_overload_composite(signals: list[Signal]) -> Trigger | None:
	planka_stall = find_signal(signals, "planka", "card_stall_threshold")
	cal_pressure = find_signal(signals, "calendar", "meeting_overload")
	health_decline = find_signal(signals, "health", "hrv_declining")

	if planka_stall and cal_pressure:
		# Two of three is enough; health is an amplifier
		severity = planka_stall.severity + cal_pressure.severity
		if health_decline:
			severity += health_decline.severity
		if severity >= 0.8:
			return Trigger(
				rule_id="overload_composite",
				priority=2,
				crews=["flow", "health"],
				context=_build_overload_context(planka_stall, cal_pressure, health_decline),
				cooldown_minutes=360,  # max once per 6 hours
				delivery="quiet_moment",
			)
	return None
```

**Inbox Overwhelm:**
```python
def rule_inbox_overwhelm(signals: list[Signal]) -> Trigger | None:
	email_surge = find_signal(signals, "email", "priority_spike")
	if email_surge and email_surge.severity >= 0.6:
		return Trigger(
			rule_id="inbox_overwhelm",
			priority=3,
			crews=[],  # no crew -- direct insight
			context=f"Priority emails awaiting response: {email_surge.detail}",
			cooldown_minutes=120,
			delivery="quiet_moment",
		)
	return None
```

**Sedentary Drift:**
```python
def rule_sedentary_drift(signals: list[Signal]) -> Trigger | None:
	no_exercise = find_signal(signals, "health", "no_exercise_mention")
	if no_exercise and no_exercise.detail.get("days", 0) >= 5:
		return Trigger(
			rule_id="sedentary_drift",
			priority=4,
			crews=["health", "coach"],
			context="No exercise-related activity for 5+ days.",
			cooldown_minutes=1440,  # once per day
			delivery="quiet_moment",
		)
	return None
```

**Infrastructure Alert:**
```python
def rule_infra_critical(signals: list[Signal]) -> Trigger | None:
	disk = find_signal(signals, "hardware", "disk_critical")
	container = find_signal(signals, "hardware", "container_unhealthy")
	if disk or container:
		return Trigger(
			rule_id="infra_critical",
			priority=1,
			crews=[],
			context=_build_infra_context(disk, container),
			cooldown_minutes=30,
			delivery="immediate",
		)
	return None
```

### 6.2 Rule Registry

Rules are registered at startup. Adding a new rule requires no code changes to the engine -- just define the function and register it:

```python
rule_engine.register(rule_overload_composite, cooldown=360)
rule_engine.register(rule_inbox_overwhelm, cooldown=120)
rule_engine.register(rule_sedentary_drift, cooldown=1440)
rule_engine.register(rule_infra_critical, cooldown=30)
```

### 6.3 Cooldown & Deduplication

Each rule has a cooldown tracked in Redis (`oz:ambient:cooldown:{rule_id}` with TTL). A rule cannot fire again until its cooldown expires. This is the primary defense against alert fatigue.

Additional deduplication: if the same trigger (same rule_id + same crew set) fired within the cooldown window, it is suppressed even if signal conditions are met again.

---

## 7. Crew Dispatch

When a trigger fires, the dispatcher either:

1. **Fires crews** -- calls `execute_crew_programmatically(crew_id, context)` for each crew in the trigger, using the existing crew execution pipeline. Multi-crew triggers create a panel (same mechanism as the existing Jaccard-based panel system).

2. **Surfaces a direct insight** -- if `crews` is empty, the trigger produces a short LLM-generated insight message using the trigger context as prompt. This is lighter than a full crew execution.

### 7.1 Context Injection

The trigger's `context` field is prepended to the crew's instructions as an `AMBIENT_TRIGGER` block:

```
AMBIENT_TRIGGER (proactive -- user did not ask for this):
Three Planka cards in "In Progress" have not moved in 4+ days: [card names].
Calendar shows 7.5 hours of meetings tomorrow with only one 15-minute gap.
User mentioned being tired in conversation 6 hours ago.

Tailor your output to address this specific situation. Be actionable and concise.
This is a push notification -- keep it shorter than a scheduled crew run.
```

### 7.2 Output Format

Ambient crew outputs follow the same persistence rules as scheduled crews (Planka cards, Qdrant memory) but the Telegram/dashboard delivery is prefixed with a source indicator:

```
[Ambient] Flow + Health

Z noticed you might be heading into an overloaded week. Here is what the
flow and health crews suggest...
```

---

## 8. Delivery Timing

### 8.1 Quiet Moment Detection

The DeliveryScheduler holds non-immediate triggers in a queue and delivers them when conditions are met:

**Quiet moment heuristics:**
- No user message in the last 15 minutes (user is not actively chatting)
- No calendar event starting in the next 20 minutes
- Current time is within active hours (respects existing quiet hours from `Person.quiet_hours_*`)
- User is not in a tracked session (from `follow_up.check_active_tracking_sessions()`)

**Implementation:** A scheduler job runs every 5 minutes, checks the delivery queue, and for each pending trigger evaluates quiet-moment conditions. If conditions are met, it delivers. If the trigger has been queued for > 2 hours, it delivers regardless (staleness prevention).

### 8.2 Priority Delivery

| Priority | Delivery |
|----------|----------|
| 1 (critical) | Immediate -- bypass quiet moment check |
| 2 (high) | Next quiet moment, max 30 minutes wait |
| 3 (medium) | Next quiet moment, max 2 hours wait |
| 4-5 (low/info) | Next quiet moment, fold into next briefing if > 4 hours old |

### 8.3 Briefing Integration

Low-priority ambient insights that were not delivered in time are folded into the next morning/weekly briefing. The briefing prompt already has a `PROACTIVE SUGGESTIONS` section -- ambient insights append to this naturally.

**Implementation:** Undelivered triggers with priority 4-5 are written to a Redis list (`oz:ambient:briefing_queue`). The `morning_briefing()` task in `morning.py` reads and clears this queue, injecting the items into the briefing prompt.

---

## 9. Integration Points

### 9.1 Scheduler (`tasks/scheduler.py`)

Add one new job:

```python
from app.services.ambient import ambient_loop

scheduler.add_job(
	ambient_loop,
	IntervalTrigger(seconds=settings.AMBIENT_POLL_INTERVAL_S),
	id="ambient_intelligence",
	replace_existing=True,
)
```

The `ambient_loop` function orchestrates: snapshot all adapters -> diff -> evaluate rules -> dispatch triggers -> queue for delivery.

### 9.2 Message Bus (`services/message_bus.py`)

No changes to the bus itself. Ambient delivery uses `bus.push_all()` (already exists) to reach all registered channels. Ambient messages are saved to `GlobalMessage` with a `channel="ambient"` tag for attribution.

### 9.3 Crew System (`services/crews.py`, `services/crews_native.py`)

No changes to the crew execution pipeline. Ambient triggers call `execute_crew_programmatically()` (already exists in `services/agent_actions.py`) with the trigger context. The existing panel system handles multi-crew composition.

### 9.4 Notifier (`services/notifier.py`)

No changes needed. The notifier already provides `send_notification()` and `send_notification_html()` which are called by `bus.push()` -> registered Telegram handler.

### 9.5 Follow-up System (`services/follow_up.py`)

The follow-up system continues to operate independently for card-level nudges. The ambient system operates at a higher level (cross-source signal correlation). They do not conflict because:
- Follow-up nudges are per-card, per-interval
- Ambient triggers are rule-based, cross-domain, with their own cooldown

In future phases, the follow-up system could become an adapter feeding signals into the ambient engine.

### 9.6 Morning Briefing (`tasks/morning.py`)

Add a section to read `oz:ambient:briefing_queue` from Redis and inject undelivered ambient insights into the briefing prompt.

### 9.7 Dashboard

A new `AmbientWidget.ts` component (future phase) could display:
- Active signals and their severity
- Recent triggers and their delivery status
- Cooldown timers
- Rule enable/disable toggles

---

## 10. Configuration

### 10.1 New `config.py` Settings

```python
# Ambient Intelligence
AMBIENT_ENABLED: bool = False                  # master switch
AMBIENT_POLL_INTERVAL_S: int = 300             # snapshot interval (5 min default)
AMBIENT_QUIET_MOMENT_WINDOW_M: int = 15        # minutes of silence before delivery
AMBIENT_MAX_TRIGGERS_PER_HOUR: int = 3         # global rate limit
AMBIENT_BRIEFING_QUEUE_ENABLED: bool = True    # fold old insights into briefings
```

### 10.2 New `.env` Entries

```
# Ambient Intelligence (all optional, disabled by default)
AMBIENT_ENABLED=false
AMBIENT_POLL_INTERVAL_S=300
AMBIENT_QUIET_MOMENT_WINDOW_M=15
AMBIENT_MAX_TRIGGERS_PER_HOUR=3
```

### 10.3 `config.example.yaml` / `.env.example`

Add corresponding entries with comments explaining each setting. The feature is opt-in (`AMBIENT_ENABLED=false` by default) so existing deployments are unaffected.

---

## 11. File Layout

```
src/backend/app/services/
	ambient/
		__init__.py              # ambient_loop(), init_ambient()
		adapters/
			__init__.py
			base.py              # StateAdapter protocol
			planka.py            # Planka board velocity adapter
			calendar.py          # Calendar density adapter
			email.py             # Email urgency adapter
			health.py            # Health / biometric adapter
			hardware.py          # Hardware load adapter
			conversation.py      # Conversational signals meta-adapter
		state_store.py           # Redis-backed circular buffer
		diff_engine.py           # Signal computation
		rules/
			__init__.py          # RuleEngine class + registry
			overload.py          # Composite overload rule
			inbox.py             # Email overwhelm rule
			drift.py             # Sedentary / stagnation rules
			infra.py             # Infrastructure alert rules
		dispatcher.py            # Crew dispatch + direct insight
		delivery.py              # Quiet moment scheduler
		models.py                # Signal, Trigger dataclasses
```

---

## 12. Phased Implementation

### P0 -- Foundation (estimated scope: scaffolding + one adapter)

**Goal:** Prove the architecture end-to-end with a single data source.

- [ ] Create `services/ambient/` package with base protocol and models
- [ ] Implement `StateStore` (Redis circular buffer)
- [ ] Implement `DiffEngine` with signal emission
- [ ] Implement Planka adapter (wrapping existing `get_activity_report()`)
- [ ] Implement `TriggerRuleEngine` with cooldown tracking
- [ ] Write one rule: `rule_card_stall` (Planka stall > 4 days -> fire `flow` crew)
- [ ] Implement `DeliveryScheduler` with immediate-only delivery
- [ ] Add `ambient_loop` to `scheduler.py` (gated behind `AMBIENT_ENABLED`)
- [ ] Add config entries to `config.py` and `.env.example`
- [ ] Unit tests for StateStore, DiffEngine, RuleEngine cooldown

### P1 -- Multi-Source Signals

**Goal:** Add remaining high-value adapters.

- [ ] Calendar density adapter
- [ ] Email urgency adapter
- [ ] Hardware load adapter
- [ ] Conversational signals adapter (GlobalMessage scan)
- [ ] Health adapter (personal context file parsing + message keyword scan)
- [ ] Signal tests for each adapter

### P2 -- Composite Rules + Smart Delivery

**Goal:** Cross-source rules and quiet-moment delivery.

- [ ] `rule_overload_composite` (Planka + calendar + health)
- [ ] `rule_inbox_overwhelm` (email surge)
- [ ] `rule_sedentary_drift` (health + conversation)
- [ ] `rule_infra_critical` (hardware)
- [ ] Quiet moment detection logic
- [ ] Priority-based delivery queue
- [ ] Briefing queue integration (`morning.py` reads `oz:ambient:briefing_queue`)
- [ ] Integration tests: trigger -> crew fire -> delivery

### P3 -- Polish + Dashboard

**Goal:** User-facing visibility and control.

- [ ] `AmbientWidget.ts` dashboard component (active signals, trigger history, toggles)
- [ ] Per-rule enable/disable via dashboard (stored in Redis, read by RuleEngine)
- [ ] Ambient history endpoint (`/api/ambient/history`)
- [ ] Ambient configuration endpoint (`/api/ambient/config`)
- [ ] i18n keys for all ambient-related UI strings
- [ ] Documentation update to `README.md` crews section

### P4 -- Wearable Integration (future)

**Goal:** Live biometric feed replaces file-based health adapter.

- [ ] Wearable API adapter (WHOOP, Oura, Apple Health export, or generic webhook)
- [ ] Real-time HRV/sleep/strain signals
- [ ] Richer health rules with actual biometric thresholds
- [ ] Privacy controls: wearable data never leaves the VPS

---

## 13. Risks and Mitigations

### Alert Fatigue

**Risk:** Too many ambient notifications annoy the user and get ignored.

**Mitigations:**
- Per-rule cooldowns (minimum 30 minutes, most rules 2-6 hours)
- Global rate limit (`AMBIENT_MAX_TRIGGERS_PER_HOUR=3`)
- Priority-based delivery (low-priority insights fold into briefings instead of pushing)
- Quiet moment detection prevents interrupting active work
- Master switch (`AMBIENT_ENABLED`) to disable entirely
- Per-rule toggles in dashboard (P3)

### False Positives

**Risk:** Rules fire incorrectly (e.g., cards are "stalled" because the user is on vacation).

**Mitigations:**
- High severity thresholds (require multiple corroborating signals)
- Cooldowns prevent repeated firing on the same false state
- Calendar travel detection suppresses non-urgent triggers during trips
- User can dismiss/snooze via dashboard (P3)

### Resource Usage

**Risk:** Polling 6 data sources every 60 seconds adds CPU, network, and API load.

**Mitigations:**
- Default poll interval is 300 seconds (5 minutes), not 60
- Planka adapter reuses the existing 1-minute TTL cache (`get_project_tree`)
- Calendar and email adapters piggyback on existing poll cycles (10-minute email poll, calendar fetched at briefing time)
- Adapters that fail are silently skipped with exponential backoff
- Redis storage is bounded (24 snapshots * ~2KB = ~48KB per source)
- The entire ambient loop is a single async function; no new threads or processes

### Privacy

**Risk:** Ambient intelligence requires broad read access to personal data.

**Mitigations:**
- All data stays on the user's own VPS (no external calls for ambient processing)
- PII sanitisation applies to any cloud LLM calls (existing `CLOUD_LLM_SANITIZE` setting)
- Health data from wearables (P4) is stored only in Redis with TTL, never in Postgres
- Conversational signal adapter reads only keyword presence, not message content -- it counts mentions of "tired", "stressed", etc. without storing the actual messages

### Crew Overhead

**Risk:** Ambient triggers fire expensive crew runs that compete with user-initiated requests.

**Mitigations:**
- Ambient crew runs use the same LLM queue as scheduled crews -- they do not preempt interactive chat
- The delivery scheduler checks LLM queue depth before dispatching (from hardware adapter)
- Ambient crew outputs are shorter than scheduled runs (prompt instructs conciseness)
- Maximum 3 ambient triggers per hour bounds total crew invocations

---

## 14. Open Questions

1. **Should ambient triggers be logged to Qdrant?** Pro: Z can recall "I flagged you as overloaded on Tuesday." Con: pollutes semantic memory with meta-observations. Recommendation: log to a separate `ambient_events` collection with short TTL.

2. **Should the user be able to define custom rules in YAML?** The crew system proves that YAML-defined behaviour is powerful. Custom trigger rules could follow the same pattern. Deferred to post-P2 evaluation.

3. **Should ambient insights have their own Planka board?** A dedicated "Ambient" board could track triggered insights as cards. This would give the user a backlog of Z's observations. Deferred to P3.

4. **How does this interact with the existing `feeds_briefing` crew scheduler?** They are complementary: scheduled crews run at fixed cadences to feed briefings; ambient triggers fire in response to state changes. A crew can be triggered both ways. No conflict, but the briefing should deduplicate if a crew ran both ambiently and on schedule.

---

## 15. Success Criteria

- P0: A single ambient trigger (card stall -> flow crew) fires correctly, respects cooldown, and delivers via Telegram.
- P1: Three or more data sources produce signals that appear in the state store.
- P2: A composite rule combining two sources fires a multi-crew panel and delivers at a quiet moment.
- P3: The dashboard shows ambient activity and the user can toggle rules.
- Overall: The user reports receiving useful proactive insights at least twice per week without feeling spammed.
