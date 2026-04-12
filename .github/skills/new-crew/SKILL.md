---
name: new-crew
description: "Scaffold a new openZero native crew entry in agent/crews.yaml with characters, keywords, scheduling, and Planka persistence."
---

# New Crew Skill

Creates a new crew definition in `agent/crews.yaml` following openZero conventions.

## Steps

1. **Ask** for:
   - Crew purpose/domain (e.g. "fitness tracking", "code review").
   - Group: `basic`, `business`, `education`, or `private`.
   - Briefing cadence: `/day`, `/week`, `/month`, `/quarter`, `/year`, or fixed cron.

2. **Create crew entry** in `agent/crews.yaml` using the template in `references/crew-template.yaml`. Generate:
   - `id`: lowercase, underscores (e.g. `fitness_tracker`).
   - `name`: use Semantic Priming -- evocative professional title, not generic.
   - `description`: one clear sentence.
   - `keywords`: 8-15 routing trigger words covering synonyms and related concepts.
   - `characters`: 2-3 archetypes with hyper-specific role names.
   - `instructions`: detailed multi-line prompt with Planka ACTION tag guidance.

3. **Add Planka persistence** to instructions if the crew produces actionable output:
   ```
   When you produce actionable items, emit:
   [ACTION: CREATE_TASK | BOARD: <crew board name> | LIST: <appropriate list>]
   ```

4. **Cross-reference** `agent/agent-rules.md` to ensure the new crew aligns with Z's behavioral guidelines.

5. **Verify** the YAML is valid:
   ```bash
   python3 -c "import yaml; yaml.safe_load(open('agent/crews.yaml'))"
   ```
