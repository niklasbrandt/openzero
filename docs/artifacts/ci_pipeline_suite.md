# CI Pipeline Suite -- Design and Status

## Overview

openZero runs three GitHub Actions workflow files triggered on every push and
pull request to `main`. Together they enforce type safety, security, code
quality, accessibility compliance, and container hygiene before any code lands.

---

## Workflows

### 1. `ci.yml` -- Primary CI (8 jobs)

Trigger: push/PR to `main`

| # | Job | Tool | Blocks build? | Notes |
|---|-----|------|:---:|-------|
| 1 | `frontend` | tsc --noEmit + npm audit | yes | Strict TypeScript; high-severity JS dep audit |
| 2 | `backend` | py_compile + AST key-balance check | yes | All `.py` files; verifies `_EN` == `_DE` translation keys |
| 3 | `accessibility` | axe-core + Playwright (Chromium) | yes | WCAG 2.1 AA, Shadow DOM, 10 test cases -- needs `frontend` |
| 4 | `security` | pytest prompt-injection suite | yes | 268 tests across 25 classes -- needs `backend` |
| 5 | `lint` | ruff | yes | Backend app only -- needs `backend` |
| 6 | `sast` | bandit -ll -ii | yes | High-severity Python SAST -- needs `backend` |
| 7 | `dep-audit` | pip-audit | no | OWASP A6 informational; `continue-on-error: true` -- needs `backend` |
| 8 | `build` | docker build + Trivy + vite build | yes | CRITICAL/HIGH CVEs exit-code 1; needs all gate jobs |

**Job dependency graph:**

```
frontend ──┬──▶ accessibility
           │
backend ───┼──▶ security ──┐
           ├──▶ lint       ├──▶ build
           ├──▶ sast       │
           └──▶ dep-audit ─┘ (non-blocking)
```

`build` needs: `frontend`, `backend`, `security`, `lint`, `sast`

---

### 2. `codeql.yml` -- Static Application Security Testing

Trigger: push/PR to `main` + weekly schedule (Monday 03:00 UTC)

| Step | Detail |
|------|--------|
| Languages | `python`, `javascript` (matrix) |
| Queries | `security-and-quality` |
| Actions | `codeql-action/init@v3`, `autobuild@v3`, `analyze@v3` |
| Permissions | `security-events: write`, `contents: read` |
| Results | Uploaded to GitHub Security tab (SARIF) |

---

### 3. `secrets.yml` -- Secret Scanning

Trigger: push/PR to `main`

| Step | Detail |
|------|--------|
| Tool | Trufflehog OSS (`trufflesecurity/trufflehog@main`) |
| Mode | `--only-verified` (reduces false positives) |
| Scope | Full git history (`fetch-depth: 0`) |
| Base | `github.event.repository.default_branch` → HEAD diff |

---

## Security Test Suite -- Class Register

| Class | Name | Tests | Surface |
|-------|------|------:|---------|
| 1 | `TestInputSanitisation` | ~8 | Input cleaning |
| 2 | `TestDirectPromptInjection` | ~10 | DPI via chat |
| 3 | `TestIndirectPromptInjection` | ~10 | IPI via external data |
| 4 | `TestJailbreakAttempts` | ~12 | Jailbreak patterns |
| 5 | `TestContextManipulation` | ~8 | Context window attacks |
| 6 | `TestMemoryPoisoning` | ~8 | Qdrant write poisoning |
| 7 | `TestIdentityHijacking` | ~6 | Identity override |
| 8 | `TestDataExfiltration` | ~8 | Exfil via output formatting |
| 9 | `TestPrivilegeEscalation` | ~6 | Operator privilege abuse |
| 10 | `TestInstructionOverride` | ~8 | Instruction suppression |
| 11 | `TestEncodingAndObfuscation` | ~10 | Base64, ROT13, Unicode |
| 12 | `TestMultiTurnManipulation` | ~8 | Slow-burn multi-turn |
| 13 | `TestStructuredDataInjection` | ~10 | JSON/YAML/CSV injection |
| 14 | `TestTelegramSpecific` | ~10 | Telegram channel surface |
| 15 | `TestDashboardSpecific` | ~10 | Dashboard chat surface |
| 16 | `TestAPIEndpoints` | ~8 | REST API surface |
| 17 | `TestAdvancedCombinedAttacks` | ~15 | Chained/combined attacks |
| 18 | `TestResourceAbuse` | ~6 | DoS / resource exhaustion |
| 19 | `TestKnownVulnerabilities` | ~8 | CVE/OWASP regressions |
| 20 | `TestSecurityInvariants` | ~20 | Invariant properties |
| 21 | `TestOutputGuardrails` | 5 | sanitise_output: AWS/sk-/paths/echo |
| 22 | `TestInputGuardrailsExtended` | 4 | sanitise_input: HTML/Base64 |
| 23 | `TestPersonalContextSecurity` | 6 | personal_context.py injection defences |
| 24 | `TestRetrievalAdversarialFilter` | 6 | Qdrant retrieval adversarial filter |
| 25 | `TestPersonalContextDebugReport` | 8 | /personal command output safety |
| | **Total** | **268** | |

---

## Status Audit

| Item | Status | Evidence |
|------|--------|---------|
| TypeScript type-check job | done | ci.yml job `frontend` |
| Python syntax + translation key check | done | ci.yml job `backend` |
| axe-core Playwright accessibility job | done | ci.yml job `accessibility`; artifact spec in `accessibility_ci_tests.md` |
| Prompt injection security job | done | ci.yml job `security`; 268 tests |
| ruff lint job | done | ci.yml job `lint` |
| bandit SAST job | done | ci.yml job `sast` |
| pip-audit dep audit job (informational) | done | ci.yml job `dep-audit` |
| Docker build + Trivy container scan | done | ci.yml job `build` |
| CodeQL SAST (Python + JS, weekly) | done | codeql.yml |
| Trufflehog secret scanning | done | secrets.yml |
| Class 25 tests for /personal command | done | test_security_prompt_injection.py |

**All planned CI pipeline items are implemented and deployed.**

---

## Known Gaps / Future Work

- `dep-audit` is `continue-on-error: true` -- consider hardening once upstream
  packages (torch, pymupdf) shed their known unfixed CVEs that would block CI.
- `build` job Docker layer cache is not persisted between runs; consider
  `actions/cache` for the pip layer once build times exceed 5 min.
- Trufflehog uses `@main` pin -- consider pinning to a specific SHA for
  supply-chain safety (OWASP A8).
- `security` job installs only `pytest`; if future tests import `httpx` or
  `fastapi` the install step will need updating (mirrors the `backend` job step).
