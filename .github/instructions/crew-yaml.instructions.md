---
description: "Crew YAML schema and conventions for openZero native crews"
applyTo: "**/crews.yaml"
---

# Crew YAML Conventions (openZero)

## Schema Reference
Each crew entry requires:
- `id`: unique lowercase string identifier
- `name`: descriptive crew name (use Semantic Priming for quality)
- `description`: one-line purpose
- `group`: "basic" | "business" | "education" | "private"
- `type`: "agent"
- `instructions`: multi-line instruction block for the LLM
- `feeds_briefing`: "/day" | "/week" | "/month" | "/quarter" | "/year" (which briefing cadence)
- `briefing_day`: "MON" | "SUN" etc. (for /week cadence)
- `keywords`: array of trigger words for automatic crew routing
- `characters`: array of `{name, role}` objects (Semantic Priming archetypes)

Optional: `schedule` (cron syntax for non-briefing crews), `panels`, `panel_exclude`, `lead_time`.

## Planka Persistence (ACTION Tags)
Crew instructions should include Planka ACTION tags when output must be persisted:
- `[ACTION: CREATE_TASK | BOARD: board_name | LIST: list_name]`
- `[ACTION: UPDATE | TASK_ID: id | FIELD: field]`
- Tasks MUST target the correct crew board, never the Operator Board for crew outputs.
- Direct user task creation goes to Operator Board only.

## Naming
- Crew `id` values: lowercase, underscores, no spaces.
- Character names: use evocative professional archetypes (e.g. "The Systems Auditor" not "Helper").
