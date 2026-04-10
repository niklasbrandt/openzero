"""
Web Search Tool
---------------
Provider-agnostic web search for openZero's LLM tool-calling pipeline.

Uses DuckDuckGo by default (zero config, no API key). Falls back gracefully
when the network is unavailable or rate-limited.

The module exposes:
- ``WEB_SEARCH_TOOL_DEF``: OpenAI-compatible tool definition dict (for injection
  into /v1/chat/completions ``tools`` parameter).
- ``execute_web_search(query)``: async function that performs the search and
  returns a formatted result string the LLM can consume.
- ``web_search`` LangChain @tool wrapper for the LangGraph agent path.

PII note: The *caller* (llm.py) is responsible for sanitising tool_call
arguments before passing them here. This module performs the search as-is.
"""

import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definition — injected into the ``tools`` array on chat completions
# ---------------------------------------------------------------------------

WEB_SEARCH_TOOL_DEF: dict = {
	"type": "function",
	"function": {
		"name": "web_search",
		"description": (
			"Search the web for current information. Use this when the user asks about "
			"recent events, live data, prices, weather, news, or anything that requires "
			"up-to-date knowledge beyond your training cutoff."
		),
		"parameters": {
			"type": "object",
			"properties": {
				"query": {
					"type": "string",
					"description": "The search query to look up on the web.",
				},
			},
			"required": ["query"],
		},
	},
}


# ---------------------------------------------------------------------------
# Search execution — DuckDuckGo (no API key)
# ---------------------------------------------------------------------------

async def execute_web_search(query: str, max_results: int = 5) -> str:
	"""Run a web search and return a formatted string of results.

	Returns a human-readable summary suitable for injection into an LLM
	context window as a tool response.  On failure returns an error message
	the model can relay to the user.
	"""
	if not query or not query.strip():
		return "Error: empty search query."

	try:
		from duckduckgo_search import DDGS
	except ImportError:
		logger.error("web_search: duckduckgo-search not installed — run: pip install duckduckgo-search")
		return "Web search unavailable (dependency missing)."

	try:
		# DDGS is synchronous — run in a thread to avoid blocking the event loop
		def _search() -> list[dict]:
			with DDGS() as ddgs:
				return list(ddgs.text(query, max_results=max_results))

		results = await asyncio.to_thread(_search)

		if not results:
			return f"No web results found for: {query}"

		# Format results compactly for the LLM context window
		lines: list[str] = [f"Web search results for: {query}\n"]
		for i, r in enumerate(results, 1):
			title = r.get("title", "")
			body = r.get("body", "")
			href = r.get("href", "")
			lines.append(f"{i}. {title}")
			if body:
				lines.append(f"   {body}")
			if href:
				lines.append(f"   Source: {href}")
			lines.append("")

		return "\n".join(lines).strip()

	except Exception as e:
		logger.warning("web_search failed for query %r: %s", query, e)
		return f"Web search temporarily unavailable ({type(e).__name__}). Please try again later."


# ---------------------------------------------------------------------------
# LangChain @tool wrapper — for the LangGraph agent path
# ---------------------------------------------------------------------------

try:
	from langchain_core.tools import tool as _lc_tool

	@_lc_tool
	async def web_search(query: str) -> str:
		"""Search the web for current information. Use when the user needs
		up-to-date data: news, weather, prices, recent events, or anything
		beyond your training knowledge cutoff."""
		return await execute_web_search(query)

except ImportError:
	# LangChain not available — define a plain async function as fallback
	async def web_search(query: str) -> str:  # type: ignore[misc]
		"""Search the web (LangChain not available — plain function)."""
		return await execute_web_search(query)
