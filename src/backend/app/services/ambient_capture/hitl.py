"""Free-text HITL reply parser for the ambient capture engine.

Section 5 of the artifact. Language-agnostic design — per-language synonym
lists come from translations.py (keys: ambient_confirm_synonyms,
ambient_reject_synonyms). Falls back to English synonyms if the lang code
is not found.

Reply classification:
  - "accept"  : user confirmed the default destination
  - "choose"  : user picked a specific alternative (chosen_index 0-based)
  - "reject"  : user wants to discard the capture
  - "fresh"   : not a HITL reply; treat as a new inbound message

The cosine-similarity fuzzy check runs only when the pending entry has a
phrase embedding stored (Epoch 3). In Epoch 2 it uses token-overlap only.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type + constants
# ---------------------------------------------------------------------------

HitlActionType = Literal["accept", "choose", "reject", "fresh"]

# Ordinal words per language as a small inline table (not growable via i18n
# because they are purely numeric resolution helpers, not user-facing strings).
_ORDINALS: dict[str, list[str]] = {
	"en": ["first", "second", "third", "one", "two", "three"],
	"de": ["erste", "zweite", "dritte", "eins", "zwei", "drei"],
	"es": ["primero", "segundo", "tercero", "uno", "dos", "tres"],
	"fr": ["premier", "deuxième", "troisième", "un", "deux", "trois"],
	"ja": ["一", "二", "三", "1番", "2番", "3番"],
	"ko": ["첫", "둘", "셋", "첫째", "둘째", "셋째"],
	"zh": ["一", "二", "三", "第一", "第二", "第三"],
	"ar": ["أول", "ثاني", "ثالث", "واحد", "اثنين", "ثلاثة"],
	"pt": ["primeiro", "segundo", "terceiro", "um", "dois", "três"],
	"hi": ["पहला", "दूसरा", "तीसरा", "एक", "दो", "तीन"],
	"ru": ["первый", "второй", "третий", "раз", "два", "три"],
}

# Fallback synonyms used if translations.py cannot be loaded
_FALLBACK_CONFIRM = {"yes", "ok", "sure", "yep", "yeah"}
_FALLBACK_REJECT = {"no", "skip", "forget", "nope", "never"}

_DIGIT_RE = re.compile(r"\b([1-9])\b")


@dataclass
class HitlAction:
	"""Resolved reply intent."""

	action: HitlActionType
	# Set when action == "choose"; 0-based index into alternatives list
	chosen_index: Optional[int] = None


# ---------------------------------------------------------------------------
# Synonym helpers
# ---------------------------------------------------------------------------

def _load_synonyms(lang: str) -> tuple[set[str], set[str]]:
	"""Return (confirm_set, reject_set) for the given language code."""
	try:
		from app.services.translations import get_translation
		raw_confirm = get_translation("ambient_confirm_synonyms", lang, fallback="yes,ok,sure,yep,yeah")
		raw_reject = get_translation("ambient_reject_synonyms", lang, fallback="no,skip,forget,nope,never")
		confirm = {s.strip().lower() for s in raw_confirm.split(",") if s.strip()}
		reject = {s.strip().lower() for s in raw_reject.split(",") if s.strip()}
		return confirm, reject
	except Exception as e:
		logger.debug("hitl: could not load synonyms for %s: %s", lang, e)
		return _FALLBACK_CONFIRM, _FALLBACK_REJECT


# ---------------------------------------------------------------------------
# Token overlap helper (Epoch 2 fuzzy match — no embedding needed)
# ---------------------------------------------------------------------------

def _token_overlap(a: str, b: str) -> float:
	"""Jaccard token overlap. Words only, case-insensitive."""
	tokens_a = set(re.findall(r"\w+", a.lower()))
	tokens_b = set(re.findall(r"\w+", b.lower()))
	if not tokens_a or not tokens_b:
		return 0.0
	inter = tokens_a & tokens_b
	union = tokens_a | tokens_b
	return len(inter) / len(union)


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_hitl_reply(
	reply_text: str,
	original_phrase: str,
	alternatives: list[dict],
	lang: str = "en",
) -> HitlAction:
	"""Classify a user reply during a pending HITL window.

	Parameters
	----------
	reply_text:
		Raw incoming message text (already stripped of control chars by sanitiser).
	original_phrase:
		The ambient phrase the pending entry was created for (used for fuzzy match).
	alternatives:
		List of alternative candidate dicts from the PendingCapture. May be empty.
	lang:
		ISO-639-1 language code for synonym lookup.

	Returns
	-------
	HitlAction with one of: accept, choose (with chosen_index), reject, fresh.
	"""
	text = reply_text.strip().lower()
	if not text:
		return HitlAction(action="fresh")

	confirm_set, reject_set = _load_synonyms(lang)

	# 1. Explicit digit pick ("1", "2", "3")
	dm = _DIGIT_RE.search(text)
	if dm:
		idx = int(dm.group(1)) - 1  # convert to 0-based
		if alternatives and 0 <= idx < len(alternatives):
			return HitlAction(action="choose", chosen_index=idx)
		if idx == 0:
			# "1" with no alternatives = accept default
			return HitlAction(action="accept")

	# 2. Ordinal word
	ordinals = _ORDINALS.get(lang, _ORDINALS["en"])
	for i, word in enumerate(ordinals[:3]):  # only first 3 (ordinals for 1,2,3)
		if word in text:
			position = i % 3  # map "first/one" -> 0, "second/two" -> 1, ...
			if alternatives and 0 <= position < len(alternatives):
				return HitlAction(action="choose", chosen_index=position)
			if position == 0:
				return HitlAction(action="accept")

	# 3. Negation synonyms
	for neg in reject_set:
		if neg in text:
			return HitlAction(action="reject")

	# 4. Confirmation synonyms (check after negation to avoid "don't ok" being accept)
	for conf in confirm_set:
		if conf in text:
			return HitlAction(action="accept")

	# 5. Fuzzy match against original phrase (token overlap >= 0.5)
	if _token_overlap(text, original_phrase) >= 0.5:
		return HitlAction(action="accept")

	# 6. Fuzzy match against offered alternative labels
	for i, alt in enumerate(alternatives):
		label = alt.get("destination_label", "")
		if label and _token_overlap(text, label) >= 0.5:
			return HitlAction(action="choose", chosen_index=i)

	# Nothing matched — treat as a fresh inbound message
	return HitlAction(action="fresh")
