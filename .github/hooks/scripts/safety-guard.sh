#!/usr/bin/env bash
# safety-guard.sh -- PreToolUse hook: block destructive commands
# Reads tool invocation JSON from stdin, denies dangerous patterns.
set -euo pipefail

INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")
TOOL_INPUT=$(echo "$INPUT" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('tool_input',{})))" 2>/dev/null || echo "{}")

deny() {
	echo "BLOCKED: $1" >&2
	exit 2
}

# Only inspect terminal / execute / bash tools
case "$TOOL_NAME" in
	*bash*|*terminal*|*execute*|*shell*|*run_in_terminal*)
		CMD=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('command','') or d.get('input','') or d.get('script',''))" 2>/dev/null || echo "")

		# Block rm -rf
		echo "$CMD" | grep -qiE '\brm\s+(-[a-z]*r[a-z]*f|--recursive.*--force|-[a-z]*f[a-z]*r)\b' && deny "rm -rf is blocked by safety policy"

		# Block docker compose down -v
		echo "$CMD" | grep -qiE 'docker\s+compose\s+down\s+.*-v' && deny "docker compose down -v is blocked (destroys volumes)"

		# Block git push --force
		echo "$CMD" | grep -qiE 'git\s+push\s+.*--force' && deny "git push --force is blocked by safety policy"

		# Block git reset --hard
		echo "$CMD" | grep -qiE 'git\s+reset\s+.*--hard' && deny "git reset --hard is blocked by safety policy"

		# Block writes to personal/ (not personal.example/)
		echo "$CMD" | grep -qiE '(>|>>|tee|cp|mv|rsync)\s+[^;|&]*personal/' && deny "Writing to personal/ directory is blocked"

		# Block writes to .env (allow .env.example)
		echo "$CMD" | grep -qiE '(>|>>|tee|cp|mv)\s+[^;|&]*\.env(\s|$)' && deny "Writing to .env is blocked (use .env.example)"
		;;
	*editFiles*|*create_file*|*replace_string*|*write*)
		FILE=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('filePath','') or d.get('path','') or d.get('file',''))" 2>/dev/null || echo "")

		# Block edits to personal/ directory
		echo "$FILE" | grep -qE '/personal/' && deny "Editing files in personal/ is blocked"

		# Block edits to .env (allow .env.example)
		echo "$FILE" | grep -qE '/\.env$' && deny "Editing .env is blocked (use .env.example)"
		;;
esac

# Allow everything else
exit 0
