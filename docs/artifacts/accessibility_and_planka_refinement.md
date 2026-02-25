# Artifact: Accessibility Refinement & Planka Integration Fixes

## Overview
This artifact summarizes the current efforts to enhance the OpenZero dashboard's accessibility and resolve persistent issues with Planka task/board creation.

## Objectives
1.  **Strict Accessibility Compliance:**
    *   Ensure all interactive elements have visible focus states (`focus-visible`).
    *   Add `aria-label` to icon-only buttons or buttons with generic text (e.g., "Edit", "Delete").
    *   Implement `aria-live="polite"` for dynamic content areas like chat messages.
    *   Use native semantic elements (e.g., `<button>` for accordions).

2.  **Robust Planka Integration:**
    *   **Normalization:** Correctly map "Boards" or "openZero" prompts to the "Operator Board" project.
    *   **Search Reliability:** Improve project and board lookup logic to handle different API response structures (e.g., `included` vs direct list).
    *   **Feature Completeness:** Support `description` field for cards created via agent actions.
    *   **Action Parsing:** Ensure the `CREATE_BOARD` action correctly identifies target projects.

## Implementation Status

### Accessibility
- [x] **EmailRules.ts**: Added `aria-label` to edit/delete buttons; added `focus-visible` styles.
- [x] **CircleManager.ts**: Added `aria-label` to edit/remove buttons; added global `focus-visible` styles.
- [x] **ChatPrompt.ts**: Added `aria-live="polite"` to messages container.
- [x] **UserCard.ts**: Added `aria-label` to profile edit button; added `focus-visible` styles.
- [x] **BriefingHistory.ts**: Refactored accordion headers to `<button>`; added `aria-expanded` and focus styles.

### Planka Integration
- [x] **planka.py**: Updated `create_task` with better normalization and search logic. Added `description` support.
- [ ] **agent_actions.py**: (Pending) Update code to pass `DESCRIPTION` to `create_task` and fix `CREATE_BOARD` project lookup.

## Known Issues & Next Steps
- **Indentation:** Codebase is being unified to use **TABS** as per `agents.md`.
- **Planka Creation:** The user reports that board/card creation via agent is still failing. Need to verify API payloads and response parsing.
- **Project Tree:** Ensure the visual tree remains clickable and accurately reflects the state of all projects.
