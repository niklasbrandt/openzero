"""Provider-agnostic action extractor (Layer 4 anti-hallucination).

Implements a three-tier capability ladder behind a single interface so openZero
can run on any LLM provider without code changes. The active tier is detected at
startup from config and cached for the process lifetime.

Tier A — Native tool/function calling (OpenAI-compatible or Anthropic tools)
Tier B — Constrained JSON output (response_format json_schema / Ollama format)
Tier C — Tagged text + deterministic parser + auto-repair (universal fallback)

All three tiers surface the same `list[ParsedAction]` to the caller. The router
and agent_actions.py never need to know which tier produced the result.

Usage::

	from app.services.action_extractor import get_extractor

	extractor = get_extractor()
	clean_reply, actions = await extractor.extract(raw_llm_reply)
	# actions: list[ParsedAction] — ready for execute_action()
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Maximum chars of reply to scan for action tags (CWE-1333 guard).
_MAX_SCAN = 20_000

# Valid action type names (upper-case). Extractor rejects unknown verbs.
_VALID_ACTION_TYPES: frozenset[str] = frozenset({
	"CREATE_TASK", "CREATE_BOARD", "CREATE_LIST", "CREATE_PROJECT",
	"MOVE_BOARD", "MOVE_CARD", "MARK_DONE", "ARCHIVE_CARD",
	"APPEND_SHOPPING", "DELETE_BOARD", "DELETE_CARD", "DELETE_LIST",
	"DELETE_PROJECT", "SET_CARD_DESC", "RENAME_CARD", "RENAME_LIST",
	"RENAME_BOARD", "RENAME_PROJECT", "AMBIENT_CAPTURE", "AMBIENT_TEACH",
	"ADD_CARD_TASK", "CHECK_CARD_TASK", "UNCHECK_CARD_TASK", "RENAME_CARD_TASK",
	"DELETE_CARD_TASK", "ROUTE",
})

# Regex for a well-formed tag: [ACTION: TYPE | KEY: val ...]
# The closing ] is mandatory for a tag to be considered valid.
_VALID_TAG_RE = re.compile(
	r'\[ACTION:\s*([A-Z_]+)\s*(\|[^\]]{0,2000})?\]',
	re.IGNORECASE,
)

# Regex to detect a tag that opened but never closed (potential malformed tag).
_OPEN_TAG_RE = re.compile(
	r'\[ACTION:\s*[A-Z_]+[^\]]{0,2000}$',
	re.IGNORECASE,
)

# Key-value pair inside a tag body: | KEY: value
_KV_RE = re.compile(r'\|\s*([A-Z_]+)\s*:\s*([^|]{0,500})', re.IGNORECASE)


@dataclass
class ParsedAction:
	"""One parsed and structurally validated action from an LLM reply."""
	action_type: str					# e.g. "CREATE_TASK"
	params: dict[str, str] = field(default_factory=dict)
	raw_tag: str = ""					# original tag text including brackets
	repaired: bool = False				# True if auto-repair round-trip was performed


@runtime_checkable
class ActionExtractor(Protocol):
	"""Common interface — all tiers implement this."""

	async def extract(self, raw_reply: str) -> tuple[str, list[ParsedAction]]:
		"""Parse action tags from *raw_reply*.

		Returns:
		    (clean_reply, actions)
		    clean_reply — raw_reply with all well-formed tags removed.
		    actions     — list of ParsedAction, structurally valid, ready for dispatch.
		"""
		...


# ── Tier C: Tagged text extractor with auto-repair ───────────────────────────

def _parse_tags(text: str) -> list[ParsedAction]:
	"""Extract all valid [ACTION: TYPE | KEY: val ...] tags from *text*."""
	actions: list[ParsedAction] = []
	for m in _VALID_TAG_RE.finditer(text[:_MAX_SCAN]):
		raw_tag = m.group(0)
		action_type = m.group(1).upper()
		if action_type not in _VALID_ACTION_TYPES:
			logger.debug("action_extractor: unknown action type '%s' — skipped", action_type)
			continue
		body = m.group(2) or ""
		params = {
			kv.group(1).upper(): kv.group(2).strip().strip('"\'')
			for kv in _KV_RE.finditer(body)
		}
		actions.append(ParsedAction(action_type=action_type, params=params, raw_tag=raw_tag))
	return actions


async def _attempt_repair(raw_tag: str) -> ParsedAction | None:
	"""One auto-repair round-trip to the LLM. Hard timeout 3 s.

	Sends the broken tag + schema to the cloud LLM and asks for a corrected
	JSON object. Returns a ParsedAction if repair succeeded, None otherwise.

	Auto-repair is only safe to run when NOT in an interactive stream (the
	caller — TaggedTextExtractor.extract — suppresses it when streaming=True).
	"""
	prompt = (
		"The following ACTION tag is malformed. Fix it and return ONLY the corrected tag "
		"in the format [ACTION: TYPE | KEY: value | KEY: value] — no prose, no explanation.\n\n"
		f"Malformed tag: {raw_tag[:500]}\n\n"
		"Valid format example: [ACTION: CREATE_TASK | TITLE: Buy milk | BOARD: Shopping]\n"
		"Corrected tag:"
	)
	try:
		from app.services.llm import chat as _llm_chat
		import asyncio
		raw = await asyncio.wait_for(_llm_chat(prompt, tier="cloud"), timeout=3.0)
		raw = raw.strip()
		# Try to extract a valid tag from the repair response
		m = _VALID_TAG_RE.search(raw[:2000])
		if not m:
			logger.debug("action_extractor: repair produced no valid tag for: %s", raw_tag[:80])
			return None
		action_type = m.group(1).upper()
		if action_type not in _VALID_ACTION_TYPES:
			return None
		body = m.group(2) or ""
		params = {
			kv.group(1).upper(): kv.group(2).strip().strip('"\'')
			for kv in _KV_RE.finditer(body)
		}
		return ParsedAction(
			action_type=action_type, params=params,
			raw_tag=m.group(0), repaired=True,
		)
	except Exception as _e:
		logger.debug("action_extractor: repair attempt failed: %s", _e)
		return None


class TaggedTextExtractor:
	"""Tier C extractor — tagged text with deterministic parser and optional auto-repair.

	This is the universal fallback that works on ANY LLM, including small local
	models without tool-calling support.

	*streaming* should be set True when called from a live stream path so that
	the auto-repair round-trip (which adds up to 3 s) is suppressed.
	"""

	def __init__(self, auto_repair: bool = True, streaming: bool = False) -> None:
		self.auto_repair = auto_repair
		self.streaming = streaming

	async def extract(self, raw_reply: str) -> tuple[str, list[ParsedAction]]:
		actions = _parse_tags(raw_reply)

		# Detect any unclosed [ACTION: ... without a ] — candidate for repair.
		if self.auto_repair and not self.streaming:
			open_m = _OPEN_TAG_RE.search(raw_reply[:_MAX_SCAN])
			if open_m:
				broken_tag = open_m.group(0)
				repaired = await _attempt_repair(broken_tag)
				if repaired:
					actions.append(repaired)
					logger.info(
						"action_extractor: auto-repaired malformed tag → %s",
						repaired.action_type,
					)
				else:
					logger.warning(
						"action_extractor: could not repair malformed tag '%s...' — dropped",
						broken_tag[:60],
					)

		# Build clean_reply: strip all valid tags from the reply.
		clean = _VALID_TAG_RE.sub("", raw_reply).strip()

		return clean, actions


# ── Tier stubs (A and B) — Not yet implemented; fall back to Tier C ──────────

class NativeToolExtractor:
	"""Tier A — Native tool/function calling (OpenAI-compatible tools=[...]).

	Not yet implemented. Falls back to TaggedTextExtractor at runtime.
	Raises NotImplementedError when called directly (kept for future use).
	"""

	async def extract(self, raw_reply: str) -> tuple[str, list[ParsedAction]]:  # noqa: F811
		raise NotImplementedError("Tier A native tool extraction not yet implemented.")


class JsonSchemaExtractor:
	"""Tier B — Constrained JSON output (response_format json_schema).

	Not yet implemented. Falls back to TaggedTextExtractor at runtime.
	Raises NotImplementedError when called directly (kept for future use).
	"""

	async def extract(self, raw_reply: str) -> tuple[str, list[ParsedAction]]:  # noqa: F811
		raise NotImplementedError("Tier B JSON schema extraction not yet implemented.")


# ── Capability detection ──────────────────────────────────────────────────────

def detect_tier() -> str:
	"""Return the highest action-extraction tier supported by the current provider.

	Returns one of "A", "B", "C".

	Detection logic:
	  - If LLM_TOOL_CALLING_TIER is set in config, use it directly (operator override).
	  - Otherwise default to "C" (universal fallback) until Tier A/B are implemented.
	  - Once Tier A/B are implemented, probe the provider at startup.

	Result is cached per process. Call reset_tier_cache() in tests to clear it.
	"""
	try:
		from app.config import settings
		tier_cfg = getattr(settings, "LLM_TOOL_CALLING_TIER", "auto").lower()
		if tier_cfg in ("a", "native"):
			return "A"
		if tier_cfg in ("b", "json"):
			return "B"
		# "auto" or "c" / "tagged" → always pick C until A/B are production-ready.
		return "C"
	except Exception:
		return "C"


_TIER_CACHE: str | None = None


def get_extractor(streaming: bool = False) -> TaggedTextExtractor:
	"""Return the appropriate extractor for the runtime provider.

	Always returns a TaggedTextExtractor (Tier C) until Tier A/B are ready.
	*streaming* suppresses auto-repair round-trips on the hot stream path.
	"""
	global _TIER_CACHE
	if _TIER_CACHE is None:
		_TIER_CACHE = detect_tier()
		logger.info("action_extractor: provider tier detected as '%s'", _TIER_CACHE)
	# Tier A and B not yet implemented — fall back to C regardless of tier.
	return TaggedTextExtractor(auto_repair=True, streaming=streaming)


def reset_tier_cache() -> None:
	"""Clear the cached tier detection. Used in tests."""
	global _TIER_CACHE
	_TIER_CACHE = None
