# openZero -- Copilot Workspace Instructions

> Canonical reference: `agents.md` at repository root. Read it, `docs/artifacts/DESIGN.md`, and `README.md` at the start of every task. Scan `docs/artifacts/` for existing context before starting work.

## Project Identity

- Spell the project name as **openZero** (lowercase 'o', uppercase 'Z'). Never "OpenZero", "Openzero", or "OPENZERO".
- Stack: Python 3.12 / FastAPI / TypeScript / Vite / PostgreSQL / Redis / Qdrant / Docker Compose / Tailscale zero-trust / llama.cpp local LLM.

## Editor Conventions

- **Indentation:** Use TABS everywhere except where required by schema (YAML frontmatter uses spaces).
- **Trailing whitespace:** Remove from modified lines.
- **File endings:** Every file ends with a single newline.
- **No emojis** in Markdown (`.md`) files.

## Frontend -- Dashboard Web Components

- Shadow DOM CSS lives inside the component `.ts` file via template literals. Never extract into separate CSS files.
- Use `rem` for all spacing. The only acceptable use of `em` is `letter-spacing`.
- Use `var(--token, fallback)` for all colors. Never hardcode hex. HSLA format (`hsla(H, S%, L%, A)`).
- Full token chain: `-h`, `-s`, `-l`, `-rgb`, composite. Update the entire chain when changing a color.
- Every component MUST include `${ACCESSIBILITY_STYLES}` and its own `@media (prefers-reduced-motion: reduce)` and `@media (forced-colors: active)` blocks.
- WCAG 2.1 Level AA + EN 301 549 baseline. Native HTML elements first. Visible focus states. Min 44x44px touch targets. `aria-live` for dynamic content.

## Localisation

- ALL user-facing strings (including `aria-label`, `placeholder`, `title`) MUST use `this.tr('key', 'English fallback')`.
- Every new key goes into `_EN` and `_DE` in `src/backend/app/services/translations.py`.
- Key parity enforced: every key in `_EN` must exist in every non-empty language dict.
- Run `pytest tests/test_i18n_coverage.py -v` after any translation change.

## Backend -- Python / FastAPI

- Tab indentation, line length 200.
- Ruff rules: F, B, S, E4, E7. No bare `except:`. Use `async def` for service functions.
- `Depends()` in FastAPI signatures (B008 suppressed).
- Static analysis over dynamic imports in scripts/tests (avoid triggering full app startup).

## Secrets and Data Sovereignty

- NEVER commit real secrets, personal identifiers, or local paths. Use placeholders in `.example` files.
- When modifying config structure, synchronise the `.example` counterpart (agents.md rule 4).
- NEVER overwrite data on remote servers. Exclude `.git/`, `node_modules/`, `personal/`, `.DS_Store` from sync.
- NEVER use `docker compose down -v` unless explicitly instructed.

## Commit and Deploy

- One-line commit messages only. No body, no bullet points. No private details.
- After committing: always push and run `scripts/sync.sh`. Treat commit + push + sync as one atomic step.

## Dependency Awareness

- Verify the installed version of any dependency before suggesting config. Behaviours change between major versions (e.g. Pi-hole v5 vs v6).
- Check version-specific docs rather than guessing.

## BUILD.md and Artifacts

- After completing changes, check if `BUILD.md` needs updating (new env vars, manual setup steps, config changes).
- Before starting a task, check `docs/artifacts/` for existing context. After significant changes, create or update the relevant artifact.
