---
name: scaffold-feature
description: "Scaffold a complete full-stack feature: FastAPI endpoint, dashboard Web Component, i18n keys, test stubs, and documentation checks."
---

# Scaffold Feature Skill

Creates the skeleton for a complete full-stack openZero feature.

## Steps

1. **Ask** for:
   - Feature name (e.g. "Weather Dashboard").
   - Brief description of what it does.
   - Whether it needs a backend endpoint, frontend component, or both.

2. **Backend endpoint** (if needed):
   Use the `new-endpoint` skill template at `.github/skills/new-endpoint/references/endpoint-template.py`.
   - Create route in `src/backend/app/api/dashboard.py`.
   - Create Pydantic request/response models.
   - Create service function stub in `src/backend/app/services/`.

3. **Dashboard component** (if needed):
   Use the `new-component` skill template at `.github/skills/new-component/references/component-template.ts`.
   - Create component in `src/dashboard/components/`.
   - Register lazy-load in `vite.config.ts`.
   - Wire up `fetchData()` to the new API endpoint.

4. **i18n keys:**
   - Add title and any user-facing string keys to `_EN` and `_DE` in `src/backend/app/services/translations.py`.

5. **Test stubs:**
   - Add test cases or a test file for the new feature.
   - Ensure existing test suites still pass.

6. **Documentation check:**
   - If the feature introduces new env vars or setup steps, update `BUILD.md`.
   - If it's architecturally significant, create or update a `docs/artifacts/` file.

7. **Verify:**
   ```bash
   cd src/dashboard && npx tsc --noEmit
   ruff check src/backend/
   pytest tests/test_i18n_coverage.py -v
   ```
