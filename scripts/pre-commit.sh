#!/bin/bash
# Pre-commit hook — openZero Data Leak Mitigation
# Blocks commits if private files or credentials are staged.

STAGED_FILES=$(git diff --cached --name-only)

FORBIDDEN_PATTERNS=(
	"^personal/"
	"^agent/"
	"user_crews\.yaml"
	"domain\.derived\.yaml"
	"^\.env$"
	"^\.env\.remote$"
	"^\.env\.planka$"
)

LEAKED=""
for file in $STAGED_FILES; do
	# Allow sanitized .example templates
	if [[ "$file" == *".example"* ]]; then
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
	echo -e "You are attempting to commit private files or credentials:\n"
	echo -e "$LEAKED"
	echo -e "Run 'git reset HEAD <file>' to unstage private files before committing."
	exit 1
fi
