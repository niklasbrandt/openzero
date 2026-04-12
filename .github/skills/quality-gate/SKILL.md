---
name: quality-gate
description: "Run all pre-commit quality checks in sequence: TypeScript, ruff, mypy, i18n coverage, static analysis, and security tests."
---

# Quality Gate Skill

Runs the full openZero pre-commit check suite. Each step must pass before proceeding.

## Steps

Run these commands in order. Stop and report on first failure:

1. **TypeScript type check:**
   ```bash
   cd src/dashboard && npx tsc --noEmit
   ```

2. **Python lint (ruff):**
   ```bash
   ruff check src/backend/
   ```

3. **Python type check (mypy):**
   ```bash
   mypy src/backend/app/ --ignore-missing-imports
   ```

4. **i18n key parity:**
   ```bash
   pytest tests/test_i18n_coverage.py -v
   ```

5. **Static analysis:**
   ```bash
   pytest tests/test_static_analysis.py -v
   ```

6. **Security tests:**
   ```bash
   pytest tests/test_security_prompt_injection.py -v
   ```

## Reporting

After all steps complete, provide a summary:
- PASS: all 6 checks passed.
- FAIL: list which checks failed with error excerpts.

You can also run the bundled script directly:
```bash
bash .github/skills/quality-gate/scripts/run-quality-gate.sh
```
