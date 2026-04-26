"""Top-level dispatcher skeleton (intent_bus).

Section 2 of the artifact. The bus replaces the bare call to
`intent_router.classify_structural_intent` as the engine matures. In Epoch 1
this module is a thin pass-through that ALWAYS delegates to the existing
intent_router and never invokes ambient capture -- ambient capture is gated
behind `settings.AMBIENT_CAPTURE_ENABLED` (default False).

When the flag is on (Epoch 2), the bus:
  1. Tries deterministic verbs (`intent_router.classify_structural_intent`)
  2. If that misses AND the message is non-conversational, runs the ambient
	 capture engine across registered plugins
  3. Otherwise falls through to the LLM chat router

The boundary with the state-diff engine (`ambient_intelligence.md`) is:
that engine reacts to OBSERVED state changes; this bus routes INBOUND
user messages. They share no code path beyond the unified pending queue.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Token floor: phrases shorter than this are almost always conversational particles
_MIN_PHRASE_TOKENS = 2

# Score thresholds (mirrored in planka_card.py; kept here as lane boundaries)
_EXECUTE_FLOOR = 0.72
_ASK_FLOOR = 0.40


def is_enabled() -> bool:
	"""Master kill-switch (Epoch 2 gate).

	Default False. Operator opts in per-channel via `AMBIENT_CAPTURE_ENABLED`.
	"""
	from app.config import settings
	return bool(getattr(settings, "AMBIENT_CAPTURE_ENABLED", False))


def _looks_like_thing(text: str) -> bool:
	"""Lightweight heuristic: is the phrase more likely a *thing to save* than
	small-talk?

	Returns True when the text has at least two whitespace-delimited tokens
	OR is a URL-like string, and does NOT start with a typical greeting verb.
	"""
	stripped = text.strip()
	if not stripped:
		return False
	tokens = stripped.split()
	if len(tokens) < _MIN_PHRASE_TOKENS:
		return False
	first = tokens[0].lower().rstrip("?!.,")
	# Conversational openers (not exhaustive; deterministic router handles real commands)
	_CHAT_OPENER = {
		"hi", "hey", "hello", "thanks", "thank", "ok", "okay", "yes", "yep", "yeah",
		"no", "nope", "nah", "sure", "bye", "ciao", "hola", "hm", "hmm", "lol", "haha",
	}
	if first in _CHAT_OPENER:
		return False
	# Questions are conversational
	if stripped.endswith("?"):
		return False
	return True


async def _run_plugin_capture(
	text: str,
	lang: str,
	channel: str,
	user_id: str,
) -> Optional[str]:
	"""Run the ambient capture plugin pipeline.

	Returns an i18n-resolved reply string if the bus handled the message
	(EXECUTE or ASK lane), or None to fall through to LLM chat.
	"""
	from app.services.ambient_capture.sanitiser import clamp_phrase
	from app.services.ambient_capture.plugin import registry, CaptureDecision
	from app.services.ambient_capture.pending import store_pending

	phrase = clamp_phrase(text)
	if not phrase:
		return None

	context: dict = {"lang": lang, "channel": channel, "user_id": user_id}

	# Score across all registered plugins
	best_score = None
	best_plugin = None
	runner_up = None
	runner_up_plugin = None

	for plugin in registry.all():
		try:
			ps = await plugin.score_match(phrase, context)
		except Exception as exc:
			logger.warning("ambient_capture: plugin %s score_match raised: %s", plugin.name, exc)
			continue
		if ps is None:
			continue
		if best_score is None or ps.score > best_score.score:
			runner_up = best_score
			runner_up_plugin = best_plugin
			best_score = ps
			best_plugin = plugin
		elif runner_up is None or ps.score > runner_up.score:
			runner_up = ps
			runner_up_plugin = plugin

	if best_score is None or best_score.score < _ASK_FLOOR:
		return None

	# Determine lane
	if best_score.score >= _EXECUTE_FLOOR:
		lane: str = "EXECUTE"
	else:
		lane = "ASK"

	decision = CaptureDecision(
		plugin_name=best_plugin.name,
		phrase=phrase,
		destination_id=best_score.destination_id,
		destination_label=best_score.destination_label,
		confidence=best_score.score,
		lane=lane,  # type: ignore[arg-type]
		channel=channel,
		user_id=user_id,
	)

	if lane == "EXECUTE":
		try:
			result = await best_plugin.execute_capture(decision)
		except Exception as exc:
			logger.error("ambient_capture: execute_capture failed: %s", exc)
			from app.services.translations import get_translation
			msg = get_translation("ambient_capture_failed", lang, "Couldn't save '{phrase}' — {reason}. Try again later.")
			return msg.replace("{phrase}", phrase).replace("{reason}", str(exc))
		return result.message

	# ASK lane — build alternatives list and store pending
	alternatives: list[dict] = []
	if runner_up is not None and runner_up.score >= _ASK_FLOOR:
		alternatives.append({
			"plugin_name": runner_up_plugin.name if runner_up_plugin else "",
			"destination_id": runner_up.destination_id,
			"destination_label": runner_up.destination_label,
			"score": runner_up.score,
		})

	await store_pending(
		user_id=user_id,
		channel=channel,
		plugin_name=best_plugin.name,
		phrase=phrase,
		destination_id=best_score.destination_id,
		destination_label=best_score.destination_label,
		confidence=best_score.score,
		alternatives=alternatives or None,
	)

	# Build the ask message
	from app.services.translations import get_translation
	if alternatives:
		alt_label = alternatives[0]["destination_label"]
		template = get_translation("ambient_ask_two_targets", lang, "Could be {target_a} or {target_b} for '{phrase}'. Which fits?")
		return (
			template
			.replace("{phrase}", phrase)
			.replace("{target_a}", best_score.destination_label)
			.replace("{target_b}", alt_label)
		)
	template = get_translation("ambient_ask_one_target", lang, "I'd put '{phrase}' on {target_path}. Different place?")
	return template.replace("{phrase}", phrase).replace("{target_path}", best_score.destination_label)


async def classify_universal_intent(
	text: str,
	lang: str,
	channel: str,
	user_id: str,
) -> Optional[Any]:
	"""Universal entry point. Returns a structural intent if the deterministic
	router matched, a reply string if the ambient engine handled it, else None.
	"""
	from app.services import intent_router

	# 1. Always try the deterministic verb router first (microseconds, safe)
	try:
		intent = await intent_router.classify_structural_intent(text, lang)
		if intent is not None:
			return intent
	except Exception as e:
		logger.warning("intent_bus: deterministic router failed: %s", e)

	# 2. Ambient capture branch (Epoch 2). Gated until flag is on.
	if is_enabled() and _looks_like_thing(text):
		try:
			reply = await _run_plugin_capture(text, lang, channel, user_id)
			if reply is not None:
				return reply
		except Exception as e:
			logger.warning("intent_bus: ambient capture pipeline failed: %s", e)

	# 3. Fall through to chat
	return None
