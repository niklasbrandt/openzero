---
name: deploy-vps
description: "Run the full openZero deploy pipeline: build dashboard, commit, push, sync to VPS, and optionally run live regression tests."
---

# Deploy VPS Skill

Deploys the current state of the openZero repository to the production VPS.

## Steps

1. **Build dashboard:**
   ```bash
   cd src/dashboard && npm run build
   ```

2. **Stage and commit** (if there are uncommitted changes):
   ```bash
   git add -A && git status
   ```
   Ask the user for a one-line commit message. Commit:
   ```bash
   git commit -m "<user message>"
   ```

3. **Push to remote:**
   ```bash
   git push
   ```

4. **Sync to VPS:**
   ```bash
   bash scripts/sync.sh
   ```

5. **Optional: Live regression test** (if user requested `--test`):
   ```bash
   pytest tests/test_live_regression.py -v
   ```

## Post-Deploy Checklist
- Verify the dashboard loads at the production URL.
- Check container health: `docker compose ps` on VPS.
- Monitor logs for startup errors: `docker compose logs --tail=20 backend`.

## Safety
- Never include private details in commit messages.
- The sync script respects rsync exclusions (personal/, .env, .git/, node_modules/).
