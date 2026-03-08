# Planka Operational Guide

## Board Structure

Planka is the project management tool integrated into this system. Z has access to the Planka API to read and manage boards, lists, cards, and labels.

### Canonical Column Order

All boards use this standard column layout:

```
Backlog | Next Up | In Progress | Review | Done
```

Never create columns with different names without explicit user instruction. If a board is missing a column from this list, flag it as a structural inconsistency.

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
