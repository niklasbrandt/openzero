#!/usr/bin/env bash
# run-quality-gate.sh -- Run all pre-commit quality checks
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

PASS=0
FAIL=0

run_check() {
	local name="$1"
	shift
	echo "=== $name ==="
	if "$@"; then
		echo "PASS: $name"
		((PASS++))
	else
		echo "FAIL: $name"
		((FAIL++))
	fi
	echo ""
}

run_check "TypeScript (tsc)" bash -c "cd src/dashboard && npx tsc --noEmit"
run_check "Python lint (ruff)" ruff check src/backend/
run_check "Python types (mypy)" mypy src/backend/app/ --ignore-missing-imports
run_check "i18n coverage" pytest tests/test_i18n_coverage.py -v
run_check "Static analysis" pytest tests/test_static_analysis.py -v
run_check "Security tests" pytest tests/test_security_prompt_injection.py -v

echo "================================"
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
	exit 1
fi
echo "All checks passed."
