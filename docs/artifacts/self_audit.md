# Self-Audit System — Design & Architecture

## Purpose

The self-audit system is a background integrity layer for the openZero AI assistant (Z).
It runs periodically and surfaces three classes of issues as advisory reports via the
existing Telegram/Dashboard notifier. Duplicate cards are automatically removed; all
other findings remain advisory.

## Three Checks

### 1. Action Fulfillment Verification

Z tags every confirmed structural action in its replies with an `[AUDIT:...]` marker
(see `agent/agent-rules.md` for the tagging protocol). The verifier scans
`global_messages` for these tags and cross-references them against Planka's live state.

Currently checked:

- `[AUDIT:create_project:Name]` — project exists in Planka; if a "My Projects" parent
  project exists, the item should have landed as a board under it, not as a root project.
- `[AUDIT:create_task:Title|board=BoardName]` — a card matching the title exists; if a
  board hint is provided, the card is on the correct board.
- `[AUDIT:create_list:Name|board=BoardName]` — a list matching the name exists on the
  stated board.

### 2. Hallucination / Contradiction Detection

Z's recent replies are scanned for simple factual assertions about the user
("you prefer X", "you are a Y", "you never Z"). Each assertion's subject phrase is
checked against the personal context block (`/personal/*.md`). If the personal context
contains an explicit negation ("not X", "don't X", "never X"), a flag is raised.

This is heuristic-only — no LLM call is required for the check. False positives are
possible; the user is expected to review and dismiss irrelevant flags.

### 3. Redundancy / Coherence Audit

- Duplicate card names on the same Planka board are **automatically deleted** — the oldest
  card (earliest `createdAt`, tie-broken by id) is kept and all later duplicates are
  removed via `DELETE /api/cards/{id}`. The audit report states what was removed (or
  "could not remove" if the API call fails).
- Lists whose names contain a crew id keyword but reside on a board other than the
  expected crew board are flagged as potentially misplaced (advisory only).

### 4. Missing Descriptions (advisory)

Cards on task boards are flagged when they are likely to need a description but lack one.
A card is flagged when **all** of the following apply:

- The board is a task board — board name does not contain any of the list-board keywords:
  `nutrition`, `shopping`, `grocery`, `einkauf`, `lebensmittel`, `rezept`, `recipe`.
- The card has no description.
- The card has no checklist tasks (a checklist is treated as self-documenting).
- The card name is vague — fewer than 4 words (e.g. "Fix thing", "Review", "New task").

This check is advisory only. No cards are modified automatically.

Crew-to-board mapping is derived from `crews.yaml` at runtime (crew id/name matched
against Planka board names).

## Tag Format

```
[AUDIT:create_project:ProjectName]
[AUDIT:create_task:TaskTitle|board=BoardName]
[AUDIT:create_list:ListName|board=BoardName]
```

These tags are distinct from `[ACTION:...]` tool-dispatch tags and survive the
`parse_and_execute_actions` stripper — they are stored in `global_messages.content`
for the verifier to retrieve.

## Data Sources

| Source                             | Used for                                                 |
| ---------------------------------- | -------------------------------------------------------- |
| `global_messages` (PostgreSQL)     | Extract Z's `[AUDIT:...]` claims and assertion sentences |
| Planka REST API                    | Fetch live projects / boards / lists / cards snapshot    |
| `/personal/*.md` (disk)            | Ground-truth personal context for contradiction checks   |
| `crews.yaml` (via `crew_registry`) | Crew-to-board mapping for hygiene checks                 |

## Implementation

| File                                      | Role                                                                                         |
| ----------------------------------------- | -------------------------------------------------------------------------------------------- |
| `src/backend/app/services/self_audit.py`  | All three check functions + `run_full_audit()`                                               |
| `src/backend/app/tasks/self_audit.py`     | Thin task wrapper — calls `run_full_audit()` and notifies                                    |
| `src/backend/app/tasks/scheduler.py`      | Registers `run_self_audit` on `IntervalTrigger(hours=AUDIT_INTERVAL_HOURS)`                  |
| `src/backend/app/services/message_bus.py` | Calls `_schedule_reactive_audit()` in `commit_reply` when `[AUDIT:` is detected in raw reply |
| `agent/agent-rules.md`                    | Action-tagging protocol for Z                                                                |

## Configuration

| Variable                       | Default         | Purpose                                                                                         |
| ------------------------------ | --------------- | ----------------------------------------------------------------------------------------------- |
| `AUDIT_MY_PROJECTS_PARENT`     | `"My Projects"` | Planka project that should contain user project boards                                          |
| `AUDIT_INTERVAL_HOURS`         | `6`             | Hours between full audit runs                                                                   |
| `AUDIT_REACTIVE_DELAY_SECONDS` | `15`            | Seconds to wait after a reply containing `[AUDIT:...]` before the reactive one-shot audit fires |

All settings are optional and have safe defaults.

## Output

When flags are found the audit delivers a single Telegram/Dashboard message:

```
*Self-Audit Report* — 2026-04-18 14:00 UTC

*Action Fulfillment Gaps*
• Project 'Q3 Roadmap' was created as a top-level project instead of under 'My Projects'.

*Possible Contradictions*
• Z said 'you prefer early mornings...' — personal context contains: 'not early mornings'.

*Redundancy / Coherence*
• Duplicate card 'onboarding flow' appears 2x on board 'Product'.

_These are advisory recommendations only. Nothing has been changed._
```

When all checks are clean, no notification is sent.

## Scheduling

The audit fires in two modes:

**Periodic (background):** APScheduler `IntervalTrigger` at startup. Default: every 6 hours.
Controlled by `AUDIT_INTERVAL_HOURS` in `.env`.

**Reactive (event-driven):** `MessageBus.commit_reply` detects `[AUDIT:` in Z's raw reply
and calls `_schedule_reactive_audit()`, which adds a one-shot `DateTrigger` job firing after
`AUDIT_REACTIVE_DELAY_SECONDS` (default 15 s). A debounce guard skips scheduling if a
reactive job with id prefix `self_audit_reactive_` is already queued, so rapid consecutive
replies only produce one verification pass.

## Security Notes

- The Planka snapshot uses the existing admin auth via `get_planka_auth_token()`.
- All log output passes through `_sanitize_for_log()` to prevent CWE-117 log injection.
- Regex patterns use linear, non-overlapping alternatives to avoid catastrophic backtracking.
- The hallucination scanner is read-only: it never writes to memory or Planka.
