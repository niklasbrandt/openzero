---
description: "Auto-fix Python (ruff) and TypeScript (ESLint) lint issues"
tools:
  - execute
  - read
---

# Fix Lint

Run all auto-fixable lint corrections for the openZero codebase:

1. **Python (ruff):**
   ```bash
   cd /Users/n/n/openzero && ruff check --fix src/backend/
   ```

2. **TypeScript (ESLint):**
   ```bash
   cd /Users/n/n/openzero/src/dashboard && npx eslint --fix .
   ```

3. Report any remaining unfixable issues with file paths and line numbers.
