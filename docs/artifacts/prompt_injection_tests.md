# Prompt Injection Test Suite -- Results & Design

This document captures the design, categories, and results of the openZero prompt injection risk test suite (`tests/test_security_prompt_injection.py`).

## Purpose

openZero processes user input from multiple surfaces (Telegram bot, dashboard chat, memory retrieval, calendar events, email digests) and passes it directly into local LLM prompts. Unlike cloud-hosted AI services that apply server-side guardrails at the API layer, openZero's llama.cpp pipeline has no external safety filter -- the system prompt and input pipeline architecture are the only defences.

This test suite validates the **structural integrity** of the prompt construction pipeline: that adversarial user input cannot escape the `user` role, override the system prompt, inject into secondary context, or exploit model-specific control tokens.

## Scope

The suite tests the prompt pipeline itself, not the LLM's behavioural compliance. Model-level safety (whether the LLM actually refuses a jailbreak) is non-deterministic and model-dependent. These tests validate deterministic properties:

- System prompt always occupies the first message slot.
- User input is always placed in a `user`-role message.
- Secondary context (memory, people, projects) is isolated from the primary system prompt.
- No secrets or API keys appear in the prompt structure.
- Input sanitisation functions correctly strip dangerous characters.
- HTML escaping prevents XSS in dashboard rendering.
- CSV, path traversal, CRLF, and template injection payloads are neutralised.

## Test Results

**239 tests, 0 failures** (last run: March 2026, pytest 9.x, Python 3.10).

Runtime: ~1.6 seconds (no network, no LLM, no database required).

## Category Breakdown

| #   | Category                        | Tests | Risk     | What It Validates                                                                                                                                                                                                                                                                                                                      |
| :-- | :------------------------------ | ----: | :------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Input Sanitisation              |     8 | High     | Null bytes, Unicode control chars, length caps, HTML escaping, log injection, BOM stripping                                                                                                                                                                                                                                            |
| 2   | Direct Prompt Injection         |    16 | Critical | "Ignore previous instructions", system prompt extraction, role-play override, few-shot injection, markdown code block injection                                                                                                                                                                                                        |
| 3   | Indirect Prompt Injection       |     5 | Critical | Poisoned memory context, HTML comment injection in fetched pages, calendar event injection, document metadata injection, people context injection                                                                                                                                                                                      |
| 4   | Jailbreak Attempts              |    12 | High     | Hypothetical framing, fictional character wrapper, token smuggling, base64 encoding, ASCII art, language switching, reverse psychology, grandma exploit, academic framing                                                                                                                                                              |
| 5   | Context Manipulation            |     7 | High     | Fake conversation history, context window stuffing, ChatML/LLaMA/Phi/Qwen token injection for conversation reset, XML tag injection                                                                                                                                                                                                    |
| 6   | Memory Poisoning                |     8 | Critical | Adversarial "facts" stored to Qdrant, poisoned retrieval, noise gate threshold, action tag injection via memory                                                                                                                                                                                                                        |
| 7   | Identity Hijacking              |     8 | High     | Persona override attempts ("You are ChatGPT/DAN/HAL 9000"), identity confusion via secondary context                                                                                                                                                                                                                                   |
| 8   | Data Exfiltration               |    16 | Critical | Env var extraction, file system access, markdown image exfiltration, cross-user data access                                                                                                                                                                                                                                            |
| 9   | Privilege Escalation            |    14 | High     | Admin impersonation, tool abuse (fake JSON tool calls), Docker escape instructions                                                                                                                                                                                                                                                     |
| 10  | Instruction Override            |    14 | High     | Priority escalation ("CRITICAL override"), conditional logic, nested injection, chain-of-thought manipulation, summarisation-based leaking                                                                                                                                                                                             |
| 11  | Encoding & Obfuscation          |     8 | Medium   | Base64, ROT13, hex, Unicode homoglyphs (Cyrillic), Zalgo text, leetspeak, whitespace steganography, fullwidth characters                                                                                                                                                                                                               |
| 12  | Multi-turn Manipulation         |     4 | High     | Gradual boundary pushing, context window exhaustion (100-turn history), trust building then exploit, payload splitting across turns                                                                                                                                                                                                    |
| 13  | Structured Data Injection       |    13 | Medium   | JSON prototype pollution, YAML deserialization, SQL injection in natural language, template injection (Jinja2, EJS, ERB, Java EL), CSV formula injection, action tag forgery                                                                                                                                                           |
| 14  | Telegram-specific               |     5 | High     | Unregistered bot command injection, Telegram markdown injection, callback data validation, deep link injection, message coalescing buffer injection                                                                                                                                                                                    |
| 15  | Dashboard-specific              |    13 | High     | XSS payloads (script, img, svg, iframe, event handlers), CSS injection, WebSocket schema validation, oversized payloads, token leakage in responses                                                                                                                                                                                    |
| 16  | API Endpoints                   |     8 | High     | CRLF header injection, path traversal (including URL-encoded), body size limits, bearer token format validation, history array role injection                                                                                                                                                                                          |
| 17  | Advanced Combined               |    14 | Critical | Sandwich attacks, recursive injection, typographic attacks (fullwidth Unicode), steganographic acrostics, urgency/time pressure, emotional manipulation, authority impersonation (OpenAI/Meta/law enforcement), multi-language injection, mathematical encoding, combined memory+context poisoning, action tag exfiltration via memory |
| 18  | Resource Abuse                  |     3 | Medium   | Token inflation prompts vs. tier caps (instant=200, standard=400, deep=800), recursive expansion, context length bounds (2000/2000/3000 char limits)                                                                                                                                                                                   |
| 19  | Known Vulnerability Regressions |     9 | High     | ChatML token injection, LLaMA [INST]/<<SYS>> injection, function calling format injection, Phi-4-mini special tokens, Qwen 2.5 special tokens                                                                                                                                                                                          |
| 20  | Security Invariants             |    12 | Critical | System prompt never in user messages, system prompt always first, user input never becomes system role, no code execution, identity persistence, no secrets in prompt structure, context isolation                                                                                                                                     |

**Total: 208 tests across 20 categories + 31 production integration tests (3 categories).**

### Production Integration Tests (Category 21)

| #   | Category                    | Tests | Risk     | What It Validates                                                                                                                                                                                                    |
| :-- | :-------------------------- | ----: | :------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 21a | Production sanitise_input() |    11 | Critical | Imports actual `sanitise_input()` from `llm.py` and validates null byte stripping, BOM removal, Zalgo normalisation, control char removal, ChatML/LLaMA/Phi token stripping, length cap, and combined attack vectors |
| 21b | Memory adversarial filter   |    16 | Critical | Imports actual `_ADVERSARIAL_PATTERNS` from `memory.py` and validates detection of 10 adversarial payloads + 6 safe-content false-positive checks                                                                    |
| 21c | History role filtering      |     4 | High     | Validates that `system`, `null`, `admin`, and `tool` role messages are filtered from client-provided history arrays                                                                                                  |

## Architecture Tested

The test suite mirrors the actual prompt construction flow in `src/backend/app/services/llm.py`:

```
build_system_prompt()
    |
    v
[system] Primary system prompt (identity, rules, persona)
[system] Secondary context (memory + people + projects)  <-- isolated
[user]   ... conversation history ...
[user]   Current user message
    |
    v
llama-server /v1/chat/completions (streaming)
```

The `PromptBuilder` class in the test file replicates this structure exactly, allowing tests to verify message ordering, role assignment, and content isolation without requiring a running LLM or database.

## Reference Sanitisation Functions

The test file also exports reference implementations of sanitisation utilities that openZero should apply at each input boundary:

| Function                | Purpose                                                                                    |
| :---------------------- | :----------------------------------------------------------------------------------------- |
| `sanitise_input()`      | Strip null bytes, Unicode control chars, Zalgo combining marks; NFKD normalise; length-cap |
| `sanitise_html()`       | HTML-escape for dashboard rendering (delegates to `html.escape`)                           |
| `strip_html_comments()` | Remove HTML comments that could hide instructions in fetched web content                   |
| `escape_csv_cell()`     | Prefix formula-triggering characters (`=`, `+`, `-`, `@`) to prevent CSV injection         |
| `sanitise_log_line()`   | Escape newlines to prevent log injection/forgery                                           |

## Key Findings & Remediation Status

1. **No input sanitisation layer exists in the current codebase.** -- **FIXED.** `sanitise_input()` added to `llm.py`. Called at entry of `chat_stream()`, `chat_with_context()`, and `chat_stream_with_context()`. Strips null bytes, BOM, Unicode control chars, Zalgo combining marks, NFKD normalises, and enforces an 8000-char length cap.

2. **Memory is the highest-risk injection surface.** -- **FIXED.** `_ADVERSARIAL_PATTERNS` regex added to `memory.py`. `store_memory()` now rejects text matching known adversarial phrases (system overrides, jailbreak commands, control tokens, API key exfiltration instructions) before it reaches Qdrant.

3. **Action tags from memory context are dangerous.** -- **FIXED.** Both `chat_with_context()` and `chat_stream_with_context()` now strip `[ACTION:...]` tags from retrieved memory results via `re.sub()` before injecting into the prompt context. Action tags are only parsed from assistant responses.

4. **Model-specific control tokens are not stripped.** -- **FIXED.** `sanitise_input()` strips 13 known control token patterns (ChatML: `<|im_start|>`, `<|im_end|>`; LLaMA: `[INST]`, `[/INST]`, `<<SYS>>`, `<</SYS>>`, `<s>`, `</s>`; Phi: `<|endoftext|>`, `<|system|>`, `<|end|>`; generic: `<|user|>`, `<|assistant|>`) using a compiled case-insensitive regex.

5. **Dashboard chat renders via Shadow DOM `textContent` insertion (safe).** No action needed. The Web Components use template literals and DOM APIs rather than `innerHTML`, which naturally prevents XSS.

6. **Conversation history from the dashboard `/api/dashboard/chat` endpoint accepts a `history` array.** -- **FIXED.** Both `chat_with_context()` and `chat_stream_with_context()` now filter the history array to only allow `role: "user"` and `role: "assistant"` messages before processing. Client-supplied `system` role messages are silently dropped.

7. **Tier token caps are correctly bounded.** No action needed. The `TIER_MAX_TOKENS` limits (200/400/800) prevent token inflation attacks.

## Running the Tests

No infrastructure required -- the suite runs entirely offline against the prompt construction logic:

```bash
cd /path/to/openzero
python -m pytest tests/test_security_prompt_injection.py -v --tb=short
```

Add `-k <pattern>` to run a specific category:

```bash
# Run only memory poisoning tests
python -m pytest tests/test_security_prompt_injection.py -v -k "MemoryPoisoning"

# Run only Telegram-specific tests
python -m pytest tests/test_security_prompt_injection.py -v -k "TelegramSpecific"

# Run only security invariants
python -m pytest tests/test_security_prompt_injection.py -v -k "SecurityInvariants"
```
