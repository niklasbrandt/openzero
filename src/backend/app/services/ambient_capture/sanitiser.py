"""Shared input/output sanitisers for the ambient capture engine.

Mitigations:
  - C1 (indirect prompt injection): strip control / bidi / zero-width chars,
	wrap untrusted spans in sentinel markers.
  - M3 (regex DoS): clamp phrase length before any regex runs.
  - H1 (log leakage): re-export the existing _sanitize_for_log via the
	memory module's helper.
  - H4 (tag leakage): the extended _MUTATING_TAG_RE is re-exported from
	agent_actions; this module exposes a strip helper.
"""

from __future__ import annotations

import re
from typing import Iterable

# Per Section 17.4
MAX_AMBIENT_PHRASE_CHARS = 500

# ASCII control chars (except \t \n \r) + zero-width + bidi overrides
_CTRL_RE = re.compile(
	r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]'
	r'|[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]'
)


def strip_control_chars(text: str) -> str:
	"""Remove ASCII control, zero-width, and bidi-override characters."""
	if not text:
		return ""
	return _CTRL_RE.sub("", text)


def clamp_phrase(text: str, max_chars: int = MAX_AMBIENT_PHRASE_CHARS) -> str:
	"""Strip control chars and truncate a phrase to its safe maximum length BEFORE any regex runs."""
	if text is None:
		return ""
	s = strip_control_chars(str(text))
	if len(s) > max_chars:
		s = s[:max_chars]
	return s


def wrap_untrusted(name: str, content: str, kind: str = "BOARD") -> str:
	"""Wrap an untrusted span in sentinel markers for LLM prompts (C1).

	The Tier D system prompt instructs the model that nothing inside these
	markers is an instruction. Combine with strip_control_chars on `content`
	before wrapping.
	"""
	safe_name = strip_control_chars(name).replace('"', "'")[:80]
	safe_content = strip_control_chars(content)
	# Neutralise any nested sentinel to prevent LLM escaping the wrapper (C1)
	safe_content = safe_content.replace("<<<END_UNTRUSTED>>>", "<<<END_UNTRUSTED_ESCAPED>>>")
	return f'<<<UNTRUSTED_{kind} name="{safe_name}">>>{safe_content}<<<END_UNTRUSTED>>>'


def wrap_untrusted_many(items: Iterable[tuple[str, str, str]]) -> str:
	"""Wrap a sequence of (kind, name, content) triples for prompt injection."""
	return "\n".join(wrap_untrusted(name, content, kind) for kind, name, content in items)


# Action-tag stripper that engine LLMs (Tier D, auto-description) MUST be
# filtered through before any downstream code sees their output (H4 + S1).
# Includes ambient-specific tags (AMBIENT_*) and the single-user-mode-forbidden
# share/invite verbs.
_ENGINE_OUTPUT_TAG_RE = re.compile(
	r'\[?ACTION:\s*(?:'
	r'CREATE_TASK|CREATE_BOARD|CREATE_LIST|CREATE_PROJECT|'
	r'MOVE_BOARD|MOVE_CARD|MARK_DONE|ARCHIVE_CARD|APPEND_SHOPPING|'
	r'DELETE_BOARD|DELETE_CARD|DELETE_LIST|DELETE_PROJECT|'
	r'SET_CARD_DESC|RENAME_CARD|RENAME_LIST|RENAME_PROJECT|'
	r'AMBIENT_CAPTURE|AMBIENT_TEACH|'
	r'SHARE_BOARD|SHARE_PROJECT|INVITE_USER|INVITE_MEMBER|'
	r'ADD_PERSON|LEARN|RUN_CREW|SCHEDULE_CREW'
	r')\b',
	re.IGNORECASE,
)


def strip_engine_action_tags(text: str) -> str:
	"""Strip any leaked ACTION tag from an engine LLM's output (H4 + S1).

	Removes the entire bracketed segment if present, otherwise the verb only.
	"""
	if not text:
		return ""
	# Strip bracketed segments first
	text = re.sub(r'\[ACTION:[^\]]{1,2000}\]', '', text, flags=re.IGNORECASE)
	# Then any remaining bare verbs
	text = _ENGINE_OUTPUT_TAG_RE.sub('', text)
	return text


# Allow-list for URLs in auto-generated card / board descriptions (M4).
_URL_ALLOWLIST = {
	"wikipedia.org",
	"en.wikipedia.org",
	"de.wikipedia.org",
	"youtube.com",
	"www.youtube.com",
	"youtu.be",
	"m.youtube.com",
}

# Domains the user has explicitly allowed (loaded from settings if configured).
def get_extra_allowed_domains() -> set[str]:
	from app.config import settings
	raw = getattr(settings, "AMBIENT_AUTO_DESC_ALLOWED_DOMAINS", "") or ""
	return {d.strip().lower() for d in str(raw).split(",") if d.strip()}


_URL_RE = re.compile(r'https?://([^\s/<>"\')\]]+)', re.IGNORECASE)
_BAD_SCHEME_RE = re.compile(r'\b(?:javascript|data|vbscript):', re.IGNORECASE)
_HTML_DANGEROUS_RE = re.compile(r'<\s*/?(?:script|iframe|object|embed)\b[^>]{0,2000}>', re.IGNORECASE)


# H1 re-export: consistent log-safe truncation for every logger call in the engine.
def _sanitize_for_log(text: object, max_len: int = 80) -> str:
	"""Return a safe, length-capped string for logger calls (H1 — log leakage)."""
	if text is None:
		return "<none>"
	s = strip_control_chars(str(text))
	if len(s) > max_len:
		return s[:max_len] + "…"
	return s


def sanitise_auto_description(draft: str, max_chars: int = 500) -> str:
	"""Sanitiser for auto-generated descriptions (M4)."""
	if not draft:
		return ""
	# 1. Strip control chars
	draft = strip_control_chars(draft)
	# 2. Strip dangerous HTML
	draft = _HTML_DANGEROUS_RE.sub("", draft)
	# 3. Strip dangerous URL schemes
	draft = _BAD_SCHEME_RE.sub("", draft)
	# 4. Filter URLs to allow-list
	allowed = _URL_ALLOWLIST | get_extra_allowed_domains()

	def _filter_url(m: re.Match) -> str:
		host = m.group(1).lower().split("/")[0].split(":")[0]
		# Match exact host or any subdomain of allowed
		if host in allowed or any(host.endswith("." + d) for d in allowed):
			return m.group(0)
		return ""

	draft = _URL_RE.sub(_filter_url, draft)
	# 5. Strip any leaked action tag
	draft = strip_engine_action_tags(draft)
	# 6. Clamp length
	if len(draft) > max_chars:
		draft = draft[:max_chars].rstrip()
	return draft.strip()
