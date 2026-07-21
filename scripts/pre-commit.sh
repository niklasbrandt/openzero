#!/bin/bash
# Pre-commit hook — openZero Data Leak Mitigation
# Blocks commits if private files, real credentials, or unsanitized templates are staged.

STAGED_FILES=$(git diff --cached --name-only)

FORBIDDEN_PATTERNS=(
	"^personal/"
	"^agent/"
	"user_crews\.yaml"
	"domain\.derived\.yaml"
	"^config\.yaml$"
	"^\.env$"
	"^\.env\.remote$"
	"^\.env\.planka$"
)

LEAKED=""
for file in $STAGED_FILES; do
	if [[ "$file" == *".example"* ]]; then
		# Check staged .example templates for real secrets or real tokens
		if git diff --cached "$file" | grep -qE "sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{30,}|[0-9]{8,10}:[a-zA-Z0-9_-]{35}"; then
			LEAKED="$LEAKED  - $file (contains real API key/token)\n"
		fi
		continue
	fi

	for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
		if echo "$file" | grep -qE "$pattern"; then
			LEAKED="$LEAKED  - $file\n"
		fi
	done
done

if [ -n "$LEAKED" ]; then
	echo -e "\033[31m[ABORT] DATA LEAK PREVENTION HOOK TRIGGERED!\033[0m"
	echo -e "You are attempting to commit private files or unsanitized templates:\n"
	echo -e "$LEAKED"
	echo -e "Run 'git reset HEAD <file>' to unstage private files before committing."
	exit 1
fi
