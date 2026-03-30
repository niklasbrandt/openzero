# openZero Test Suite

All tests live in `tests/`. Two files, two scopes:

| File | Requires stack | When to run |
|---|---|---|
| `test_live_regression.py` | yes | After every deployment (auto-runs via `sync.sh`) |
| `test_security_prompt_injection.py` | no | After changes to `llm.py` or `memory.py` |

---

## test_live_regression.py

Full end-to-end suite covering every command in `/help` plus Planka connectivity and core API endpoints. Runs automatically at the end of every `scripts/sync.sh` deployment. Always cleans up after itself via `POST /api/dashboard/regression-cleanup`, even on failure.

**Requires:** running backend, Qdrant, Planka, a valid `DASHBOARD_TOKEN`

**Usage:**

```
python3 tests/test_live_regression.py --url http://YOUR_SERVER_IP --token your_token
# or via env var:
DASHBOARD_TOKEN=your_token python3 tests/test_live_regression.py --url http://YOUR_SERVER_IP
```

**Test sequence:**

| Group | Commands / endpoints covered |
|---|---|
| System health | `GET /api/dashboard/system` -- verifies `ram_total_gb` present |
| Planka connectivity | `GET /api/dashboard/projects` -- confirms Planka is reachable and authenticated |
| /help | Checks help text is returned and contains expected command keys |
| /protocols | Verifies action tag documentation is returned |
| /tree | Life-tree overview command -- project tree + inner circle + timeline |
| Life-tree API | `GET /api/dashboard/life-tree` -- raw endpoint used by the dashboard widget |
| Crews: /crews + /crew | Lists autonomous agents, executes `nutrition` crew, verifies 200 in chat |
| Memory: /add + /search | Stores `TEST_MEMORY_TOKEN_991823`, recalls via `/search`, verifies Qdrant round-trip |
| Memory: /memories | Lists all stored facts, verifies non-empty reply |
| Memory: /unlearn | Stores `TEST_UNLEARN_TOKEN_887712`, then removes it, verifies confirmation |
| Briefings: /day /week /month /quarter /year | Sends each command, verifies 200 (content not asserted -- LLM output varies) |
| /remind | Sends a natural language reminder, verifies 200 |
| /custom | Sends a natural language schedule request, verifies 200 |
| Action tags: Planka | Injects `CREATE_PROJECT + CREATE_BOARD + CREATE_LIST + CREATE_TASK` tags, checks `actions` field |
| Action tags: life-tree | Injects `ADD_PERSON + CREATE_EVENT` tags, verifies 200 |
| /think | Deep reasoning command -- verifies 200 and logs which model tier responded |

**Test data created and cleaned up on every run:**

| Artefact | System | Identifier |
|---|---|---|
| Qdrant memory point | Qdrant | text: `TEST_MEMORY_TOKEN_991823` |
| Qdrant memory point | Qdrant | text: `TEST_UNLEARN_TOKEN_887712` (removed during test) |
| Planka project | Planka | `REGRESSION_TEST_PROJECT_ALPHA` |
| Planka board | Planka | `REGRESSION_BOARD` |
| Planka list | Planka | `REGRESSION_LIST` |
| Planka card | Planka | `REGRESSION_TASK` |
| Life-tree person | DB | name: `TEST_PERSON_BETA`, relationship: Tester, circle: outer |
| Calendar event | DB | title: `REGRESSION_EVENT_GAMMA`, 2040-01-01 10:00-11:00 |

All identifiers are uppercase and uniquely suffixed so they cannot collide with real user data. The far-future event date (2040) means it will never surface in real timeline views.

A Markdown report is saved to `docs/artifacts/regression_results.md` after each run (overwritten, not committed).


---

## test_security_prompt_injection.py

Offline security suite -- 239 tests across 23 attack categories. No LLM, database, or network required.

Prompt injection is the class of attack where malicious user input attempts to override or escape the instructions given to the LLM. Because openZero processes messages from external channels (Telegram, dashboard, email) and stores content in long-term memory that later gets injected back into prompts, the attack surface is non-trivial.

This suite unit-tests the prompt construction code directly -- feeding attack payloads into the same functions the backend uses and verifying the output is sanitised, Z's identity is preserved, no secrets leak, and the structural format cannot be corrupted by hostile input.

**Requires:** nothing (pure Python + pytest)

**Usage:**

```
python -m pytest tests/test_security_prompt_injection.py -v --tb=short

# Run a specific category:
python -m pytest tests/test_security_prompt_injection.py -v -k "MemoryPoisoning"
python -m pytest tests/test_security_prompt_injection.py -v -k "TelegramSpecific"
python -m pytest tests/test_security_prompt_injection.py -v -k "SecurityInvariants"
```

**Attack categories covered:**

1. Input Sanitisation
2. Direct Prompt Injection (DPI)
3. Indirect Prompt Injection (IPI)
4. Jailbreak Attempts
5. Context Manipulation
6. Memory Poisoning
7. Identity Hijacking
8. Data Exfiltration
9. Privilege Escalation
10. Instruction Override
11. Encoding & Obfuscation
12. Multi-turn Manipulation
13. Markup / Structured Data Injection
14. Telegram-specific Attacks
15. Dashboard-specific Attacks
16. API Endpoint Attacks
17. Combined / Advanced Attacks
18. Resource Abuse
19. Known Vulnerability Regressions
20. Security Invariants
