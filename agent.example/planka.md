# Planka Operational Guide

## Board Structure

Planka is the project management tool integrated into this system. Z has access to the Planka API to read and manage boards, lists, cards, and labels.

### Board Type: Task/Workflow Board vs Reference/Content Board

Before creating any lists on a new board, determine its type:

**Task/workflow board** — used when the work has a lifecycle: something moves from "not started" through "doing" to "done". Examples: software releases, fitness programmes, job applications, complex projects with subtasks.

**Reference/content board** — used when the board is a collection of information on a topic with no inherent workflow. Examples: aquarium planning, reading lists, recipe collections, travel ideas, hobby research, shopping categories, reference notes.

### Canonical Column Order (task/workflow boards only)

Task/workflow boards use this standard column layout:

```
Backlog | Next Up | In Progress | Review | Done
```

Never create columns with different names on a task board without explicit user instruction. If a task board is missing a column from this list, flag it as a structural inconsistency.

### Lists for Reference/Content Boards

Reference/content boards MUST NOT use workflow columns (Backlog, In Progress, Done, etc.). Instead, create one or a few thematic lists that reflect the natural categories of the topic.

**Rules:**
- When in doubt about what lists the user wants, create ONE list named after the board topic and stop. Let the user add more lists later.
- If the topic suggests obvious natural categories, create those directly (e.g. an aquarium board → "Species", "Equipment", "Notes").
- Never exceed three lists on initial scaffold unless the user specified them.
- Never add "To Do", "In Progress", "Done", "Backlog", "Next Up", or "Review" lists to a reference/content board.

## Card Conventions

- **Title format**: Action verb + object. Example: "Add email validation to signup form", not "Email signup".
- **Description**: Include acceptance criteria as a checklist. At minimum: what done looks like.
- **Due dates**: Set for Fixed Date CoS cards. Do not set speculative due dates.
- **Labels**: Mirror the Class of Service from the Kanban skill module (Expedite, Fixed Date, Intangible). Standard cards carry no label.

## WIP Enforcement

Follow the WIP limits defined in the Kanban skill module. When creating or moving cards:
1. Check the target column count before moving.
2. If at limit, report the violation and ask which existing card should be moved or blocked instead.
3. Never silently exceed a WIP limit.

## Task Decomposition

When a user describes a large piece of work:
1. Create one card per discrete deliverable.
2. Add a parent card or use the card description to link related cards if Planka does not support sub-tasks.
3. Place new cards in Backlog unless the user explicitly asks for Next Up or In Progress.

## Board Hygiene

- Cards in Done older than 30 days should be archived, not deleted.
- Blocked cards must have a comment explaining the blocker and tagging a label "Blocked" if available.
- Empty columns other than Backlog are fine — do not fill them with placeholder cards.
- Duplicate card detection: if a user asks to create a card similar to an existing one, flag the potential duplicate before creating.

## Z Directives for Planka

- On any board summary request, always report: total open cards, WIP violations, and oldest card in In Progress.
- When moving a card to Done, ask: "Should I archive any old Done cards while I'm here?"
- When asked for a standup summary, pull all In Progress and Review cards, report blockers first.
- If the Planka API is unavailable, report the outage clearly. Do not silently skip board operations.

---

## Moving Boards Between Projects

Planka has no native UI to drag a board from one project to another. The Planka REST API supports this via a PATCH on the board's `projectId`. Use the `MOVE_BOARD` action tag to do this:

```
[ACTION: MOVE_BOARD | BOARD: <board name> | TO_PROJECT: <project name>]
```

### "My Projects" vs "Operations" — critical distinction

These two Planka projects are completely different and must NEVER be confused:

| Project | Purpose | Owner |
|---|---|---|
| **My Projects** | User's personal board folder. All single-topic user boards live here (shopping lists, hobby planning, reading lists, one-off tasks). | User |
| **Operations** | Z's own internal operator board project. Contains Z's task-tracking board ("Operator Board"). | Z / system |

Rules:
- When a user asks to move a board to "My Projects", use `TO_PROJECT: My Projects` — never substitute "Operations".
- Never route a user board into "Operations". That project belongs to Z's internal bookkeeping.
- Never tell a user that "Operations" is where their personal boards go.
- If a user mentions "My Projects" by name, take it literally — that exact Planka project name.

## Operator Board — ID-Anchored Lookup

The "Operations" project and "Operator Board" board are located by their Planka IDs, which are stored in the `preferences` DB table (`operator_project_id`, `operator_board_id`) after first creation. This means:

- Renaming these entities in Planka directly does NOT create duplicates — the system finds them by ID on restart.
- When the user changes their interface language, Z renames the existing project/board/lists to the new language rather than creating new entities.
- If you need to delete the operator board (e.g., to reset), also clear the `preferences` rows with keys `operator_project_id` and `operator_board_id` from the DB so the system re-creates and re-anchors on next startup.
