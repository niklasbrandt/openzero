---
description: "Review staged git changes for quality, security, and convention adherence"
tools:
  - read
  - search
  - execute
---

# Review Changes

Review all staged changes before committing:

1. Run `git diff --staged` to see what will be committed.

2. Check every changed file for:
   - **Conventions:** tab indentation, `openZero` spelling (not OpenZero/Openzero/OPENZERO), no emojis in `.md` files, files end with single newline.
   - **i18n:** any new user-facing string uses `this.tr('key', 'fallback')` -- never hardcoded English.
   - **Secrets:** no API keys, passwords, tokens, real emails, IPs, or local paths leaked.
   - **CSS:** no hardcoded hex colors, `rem` not `em`, `var(--token)` usage.
   - **.example parity:** if a config file was modified, its `.example` counterpart must be updated too.

3. Flag if `BUILD.md` needs updating (new env vars, setup steps, config changes).

4. Flag if any `docs/artifacts/` file is stale based on the changes.

5. Provide a summary: PASS (ready to commit) or ISSUES FOUND (with list).
