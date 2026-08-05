# Contributing to openZero

Thank you for your interest in contributing. This guide covers how to set up a local development environment, the code standards the project enforces, and what is expected in a pull request.

## Prerequisites

| Requirement | Version |
|---|---|
| Docker + Docker Compose | Latest stable |
| Node.js | 22+ |
| Python | 3.12+ |
| Tailscale | Latest stable (required for network access to a deployed instance) |

## Local Development Setup

See [BUILD.md](BUILD.md) for the full operator setup guide. For development, the minimal path is:

```bash
# Clone the repository
git clone https://github.com/niklasbrandt/openzero.git
cd openzero

# Backend dependencies
cd src/backend && pip install -r requirements.txt

# Dashboard dependencies
cd src/dashboard && npm install

# Configuration
cp .env.example .env          # Fill in the required values
cp config.example.yaml config.yaml
cp -r agent.example agent     # Edit crews.yaml and agent-rules.md
cp -r personal.example personal  # Edit with your context
```

The `agent/` and `personal/` folders are in `.gitignore` and are never committed. They are bind-mounted read-only into the backend container at runtime.

## Code Standards

All of the following are enforced by CI and must pass before a PR can merge.

**Python (`src/backend/`)**

- Formatter and linter: `ruff` (configured in `ruff.toml`)
- Type checker: `mypy` (strict mode)
- Run locally: `cd src/backend && ruff check app/ && mypy app/`

**TypeScript (`src/dashboard/`)**

- Type checker: `tsc --noEmit` (strict mode)
- Linter: ESLint
- Run locally: `cd src/dashboard && npx tsc --noEmit && npx eslint src/`

**General**

- Indentation: **tabs**, not spaces (enforced by `.editorconfig`)
- No trailing whitespace
- Files must end with a single newline

## Running the Full Quality Gate

Before opening a PR, run:

```bash
# TypeScript type check
cd src/dashboard && npx tsc --noEmit

# Python linting
cd src/backend && ruff check app/

# i18n key parity (all keys in _EN must exist in _DE)
pytest tests/test_i18n_coverage.py -v

# Security and static analysis
pytest tests/test_security_prompt_injection.py tests/test_static_analysis.py -v
```

CI runs the full suite including Playwright accessibility audits (WCAG 2.1 AA) and a live regression suite.

## Security Rules for Contributors

- **No secrets in commits.** Do not commit `.env`, `config.yaml`, API keys, passwords, or tokens. These are in `.gitignore`. If you accidentally commit a secret, rotate it immediately.
- **No hardcoded absolute paths.** Use relative paths (`./models/`) or environment variables. Never commit paths containing `/Users/`, `/home/`, or `C:\`.
- **Maintain `.example` parity.** If you add a new environment variable to `.env` or `config.yaml`, add the corresponding entry with a placeholder value to `.env.example` or `config.example.yaml`. This is enforced by review.
- **Shadow DOM encapsulation.** Component CSS stays inside the `.ts` file. Do not extract to separate CSS files.
- **No new translation keys without German (`_DE`) parity.** The i18n gate will block the PR.

## Pull Request Process

1. Fork the repository and create a branch from `main`.
2. Make your changes, following the code standards above.
3. Run the full quality gate locally before pushing.
4. Open a PR against `main`. Describe what changed and why.
5. CI must be fully green. Address any failures before requesting review.
6. All new user-facing strings must go through `this.tr('key', 'English fallback')` and have a corresponding `_EN` and `_DE` entry in `translations.py`.

For security-sensitive changes, open a [Security Advisory](https://github.com/niklasbrandt/openzero/security/advisories/new) instead of a public PR.
