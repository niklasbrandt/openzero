#!/usr/bin/env bash
# deploy.sh -- Full deploy pipeline: build, commit, push, sync
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

echo "=== Building dashboard ==="
(cd src/dashboard && npm run build)

echo "=== Checking for uncommitted changes ==="
if ! git diff --quiet || ! git diff --cached --quiet; then
	echo "Uncommitted changes detected. Stage and provide commit message."
	exit 1
fi

echo "=== Pushing to remote ==="
git push

echo "=== Syncing to VPS ==="
bash scripts/sync.sh

echo "=== Deploy complete ==="
