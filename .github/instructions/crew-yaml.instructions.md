---
description: "Crew YAML schema and conventions for openZero native crews"
applyTo: "**/crews.yaml"
---

# Crew YAML Conventions (openZero)

## Schema Reference
Each crew entry requires:
- `id`: unique lowercase string identifier
- `name`: descriptive crew name (use Semantic Priming for quality)
- `type`: "agent"

Recommended (almost always present):
- `description`: one-line purpose
- `group`: "basic" | "business" | "education" | "private"
- `instructions`: multi-line instruction block for the LLM
- `characters`: array of `{name, role}` objects (Semantic Priming archetypes)
- `keywords`: array of trigger words for automatic crew routing

Scheduling (use one approach):
- `feeds_briefing`: "/day" | "/week" | "/month" | "/quarter" | "/year" — briefing-relative scheduling
- `briefing_day`: "MON" | "SUN" etc. (required when `feeds_briefing` is "/week")
- `briefing_dom`: day-of-month integer or comma string e.g. `1`, `15`, `"1,15"` (for `/month` cadence)
- `briefing_months`: comma string of months e.g. `"1,4,7,10"` (for `/quarter` cadence)
- `schedule`: 5-field cron string for crews that run independently of briefings
- `lead_time`: per-crew override in minutes (default: global `crew_lead_time_minutes`)

Other optional:
- `panels`: list of crew IDs that run alongside this crew
- `panel_exclude`: crew IDs explicitly blocked from co-running in panels
- `enabled`: boolean (default: true)

## Planka Persistence (ACTION Tags)
Crew instructions should include Planka ACTION tags when output must be persisted:
- `[ACTION: CREATE_TASK | BOARD: board_name | LIST: list_name]`
- `[ACTION: UPDATE | TASK_ID: id | FIELD: field]`
- Tasks MUST target the correct crew board, never the Operator Board for crew outputs.
- Direct user task creation goes to Operator Board only.

## Naming
- Crew `id` values: lowercase, underscores, no spaces.
- Character names: use evocative professional archetypes (e.g. "The Systems Auditor" not "Helper").
