---
description: "Python coding conventions for the openZero backend"
applyTo: "**/*.py"
---

# Python Conventions (openZero)

## Indentation & Formatting
- Use **tabs** for indentation (not spaces).
- Line length limit: **200** characters.
- Remove trailing whitespace from modified lines.

## Ruff Rules
- Active rule sets: `F` (Pyflakes), `B` (flake8-bugbear), `S` (flake8-bandit), `E4`, `E7`.
- `B008` is suppressed: `Depends()`, `Query()`, `Header()` in FastAPI signatures are intentional.
- `E402` is suppressed: late imports for startup performance are acceptable.

## FastAPI Patterns
- Use `Depends()` for dependency injection in route signatures.
- Service functions should be `async def`.
- Pydantic models for request/response schemas.
- Use `APIRouter` with prefix for endpoint modules.

## Error Handling
- No bare `except:`. Always catch specific exceptions or use `except Exception:`.
- Log errors with `logger.error()` or `logger.warning()` before re-raising.

## Imports
- Standard library first, then third-party, then project imports.
- Late imports are acceptable when they prevent heavy module loading at startup.
