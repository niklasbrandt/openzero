# Web Search Tool Architecture

Status: Implemented
Date: 2026-04-10

## Overview

openZero's cloud tier now supports autonomous web search via standard OpenAI
function-calling on `/v1/chat/completions`. The model decides when to search;
the backend executes the search and feeds results back.

## Design Decisions

### Provider-Agnostic Function Calling (not proprietary agent APIs)
- Mistral has `/v1/conversations` + built-in tools, Groq has `compound` models,
  OpenAI has `/v1/responses` -- all proprietary, non-interchangeable.
- Instead: inject tool definitions via the `tools` parameter on the standard
  `/v1/chat/completions` endpoint. Works identically on all providers.

### Self-Hosted SearXNG (meta-search, no API keys)
- Runs as a Docker container on the internal network (`searxng:8080`).
- Aggregates Google, Bing, DuckDuckGo, Wikipedia results in one query.
- Backend calls `GET /search?q=...&format=json` via httpx (already a dependency).
- No external API keys, no rate limits, full data sovereignty.
- Configuration: `infrastructure/searxng/settings.yml`.

### Single Tool Round (no infinite loops)
- First request includes `tools` + `tool_choice: auto`.
- If model returns `tool_calls`: execute them, append results, send follow-up
  request WITHOUT `tools` parameter.
- This caps the loop at exactly one tool invocation per user message.

### PII Sanitization on Tool Arguments
- When `CLOUD_LLM_SANITIZE=true`, the LLM prompt is already sanitized before
  the model sees it, so generated tool arguments should be clean.
- As a belt-and-suspenders measure, search queries are re-sanitized before
  execution if the original prompt had PII replacements.

## Files Modified

- `src/backend/app/services/web_search.py` -- NEW: tool definition + execution + LangChain wrapper
- `src/backend/app/services/llm.py` -- tool injection + SSE tool_calls accumulation + execution loop
- `src/backend/app/services/agent_actions.py` -- added `web_search` to AVAILABLE_TOOLS
- `src/backend/app/config.py` -- added `CLOUD_LLM_TOOLS` setting (default True)
- `infrastructure/searxng/settings.yml` -- NEW: SearXNG meta-search config
- `docker-compose.yml` -- added `searxng` service on internal network
- `BUILD.md` -- documented CLOUD_LLM_TOOLS setting
- `env_example_keys.txt` -- added CLOUD_LLM_SANITIZE, CLOUD_LLM_TOOLS

## Flow

```
User message --> chat_stream()
  |
  +--> Build request with tools=[web_search] + tool_choice=auto
  |
  +--> Stream SSE from /v1/chat/completions
  |     |
  |     +-- delta.content? --> yield tokens (normal path)
  |     +-- delta.tool_calls? --> accumulate {id, name, arguments}
  |
  +--> If tool_calls accumulated:
        |
        +--> Sanitize search query (PII)
        +--> execute_web_search(query) via SearXNG (httpx)
        +--> Append tool result to messages
        +--> Follow-up request (no tools) --> stream final answer
```

## Config

| Env Var | Default | Description |
|---------|---------|-------------|
| CLOUD_LLM_TOOLS | true | Enable tool-calling on cloud tier |
| CLOUD_LLM_SANITIZE | true | PII-strip outbound prompts and tool args |
