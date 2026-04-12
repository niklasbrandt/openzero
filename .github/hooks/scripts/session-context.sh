#!/usr/bin/env bash
# session-context.sh -- SessionStart hook: inject project version + git branch
set -euo pipefail

VERSION="unknown"
BRANCH="unknown"

if [ -f "src/backend/app/VERSION" ]; then
	VERSION=$(head -1 src/backend/app/VERSION)
fi

if command -v git &>/dev/null; then
	BRANCH=$(git branch --show-current 2>/dev/null || echo "detached")
fi

python3 -c "
import json, sys
ctx = 'openZero v${VERSION} on branch ${BRANCH}'
print(json.dumps({'hookSpecificOutput': {'additionalContext': ctx}}))
"
