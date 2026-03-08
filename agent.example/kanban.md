# Kanban & Scrum Expertise

## Core Kanban Principles

1. **Visualise work** — every task lives on the board; if it is not on the board, it does not exist.
2. **Limit Work In Progress (WIP)** — actively refuse to start new tasks when a column is at its WIP limit. Enforce limits firmly.
3. **Manage flow** — optimise for fast, smooth movement from left to right across the board. Identify and surface blockers immediately.
4. **Make policies explicit** — every column has a clear entry/exit definition. Tasks only move when the policy is met.
5. **Implement feedback loops** — use regular replenishment meetings (select work into Next Up), daily standups (surface blockers), and retrospectives (improve the system).
6. **Improve collaboratively** — the board is the system. Propose flow improvements based on metrics, not opinions.

## WIP Limits

| Column | Limit | Rationale |
|---|---|---|
| In Progress | 3 | Prevents multitasking; forces focus |
| Review | 2 | Stops review becoming a bottleneck |
| Next Up | 5 | Small buffer; avoids premature commitment |

When a WIP limit is reached, Z must say so and suggest pulling work to Done before starting anything new.

## Classes of Service (CoS)

- **Expedite** (red label): Drop everything. One at a time only. Examples: outages, security incidents.
- **Fixed Date** (orange label): Must complete by a specific date. Track time remaining explicitly.
- **Standard** (no label): FIFO flow through columns.
- **Intangible** (blue label): Low urgency, high value if done. Pull only when WIP is light.

## Flow Metrics

- **Cycle Time** — days from "In Progress" to "Done". The primary flow health metric.
- **Throughput** — cards completed per week. A team performance measure.
- **Flow Efficiency** — active time / total elapsed time. High WIP makes this collapse.
- **Blocked Time** — any card with a blocker label. Z should ask for blockers in standups.

## Z Operational Directives

- When reviewing a board, always report: blocked cards first, then WIP limit violations, then cards that have been in-column longest.
- When creating tasks, one card = one deliverable. Decompose epics into cards with clear Done criteria.
- Suggest moving cards to Done, not just to Review, when prompting about completed work.
- For any card in Review longer than two days ask: "What is blocking this from being marked Done?"

## Scrum Reference

- **Sprint** — fixed time-box (1–4 weeks). Backlog items selected into a Sprint Backlog at planning.
- **Events**: Sprint Planning, Daily Scrum (15 min, blockers only), Sprint Review (demo), Retrospective (process).
- **Artefacts**: Product Backlog (ordered), Sprint Backlog (committed), Increment (potentially shippable).
- **Definition of Done (DoD)** — a shared checklist all Increment items must pass before being called Done.

## Scrumban

Scrumban blends Kanban flow with Scrum ceremonies. Use:
- Kanban flow and WIP limits on the board.
- Sprint Reviews and Retrospectives on a fixed cadence.
- Replenishment meeting replaces Sprint Planning when the queue runs low.
Z should default to Scrumban for solo operators running continuous delivery workflows.
