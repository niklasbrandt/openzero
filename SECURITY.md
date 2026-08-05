# Security Policy

## Supported Versions

openZero follows a rolling-release model. Only the current `main` branch receives security patches.

| Version | Supported |
|---|---|
| `main` (latest) | Yes |
| Older pinned commits | No |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.** Public disclosure before a fix is available puts every self-hosting operator at risk.

Use GitHub's built-in private reporting instead:

1. Navigate to the [Security tab](https://github.com/niklasbrandt/openzero/security) of this repository.
2. Click **"Report a vulnerability"** under "Private vulnerability reporting".
3. Describe the vulnerability, steps to reproduce, and potential impact.

GitHub encrypts the report end-to-end. Only the repository maintainer can read it.

**Response timeline:** Best-effort acknowledgment within 7 days. Patches are prioritised by severity.

## Scope

**In scope:**

- Backend API (`src/backend/`) — authentication, prompt injection, data leakage
- Dashboard (`src/dashboard/`) — XSS, auth bypass, sensitive data exposure
- Docker Compose configuration (`docker-compose.yml`) — port exposure, privilege escalation
- Sync and deployment scripts (`scripts/`) — credential handling, path traversal
- Firewall and network configuration (`BUILD.md` guidance)

**Out of scope:**

- Third-party container images (Qdrant, Planka, Redis, Pi-hole, SearXNG, Whisper, openedai-speech) — report those to their respective upstream projects
- Self-hosted infrastructure configuration made by the operator (VPS hardening, Tailscale ACLs, UFW rules beyond what `BUILD.md` specifies)
- Vulnerabilities requiring physical access to the server

## Security Tooling

openZero runs the following security checks on every push and pull request to `main`:

| Tool | What it checks |
|---|---|
| [Trufflehog OSS](https://github.com/trufflesecurity/trufflehog) | Secret and credential leaks in the full Git diff |
| [CodeQL](https://codeql.github.com/) | SAST for Python and JavaScript |
| [Bandit](https://bandit.readthedocs.io/) | Python-specific high-severity SAST patterns |
| [Trivy](https://trivy.dev/) | Container image vulnerabilities (CRITICAL and HIGH block CI) |
| [pip-audit](https://pypi.org/project/pip-audit/) | Python dependency CVEs |
| [npm audit](https://docs.npmjs.com/cli/commands/npm-audit) | Node dependency vulnerabilities |

Additionally, the test suite includes **268 prompt injection tests across 25 attack classes** (`tests/test_security_prompt_injection.py`), a static analysis gate (`tests/test_static_analysis.py`), and automated WCAG 2.1 AA accessibility audits via Playwright and axe-core.

SARIF reports from Trivy and CodeQL are uploaded to the GitHub Security dashboard on every CI run.
