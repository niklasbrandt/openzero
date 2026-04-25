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


def is_enabled() -> bool:
	"""Master kill-switch (Epoch 2 gate).

	Default False. Operator opts in per-channel via `AMBIENT_CAPTURE_ENABLED`.
	"""
	from app.config import settings
	return bool(getattr(settings, "AMBIENT_CAPTURE_ENABLED", False))


async def classify_universal_intent(
	text: str,
	lang: str,
	channel: str,
	user_id: str,
) -> Optional[Any]:
	"""Universal entry point. Returns a structural intent if the deterministic
	router matched, else None.

	In Epoch 1 this is a verbatim pass-through to the existing router so we
	can land the new module without behaviour change. Epoch 2 adds the
	ambient capture branch.
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
	if is_enabled():
		# Imported lazily so Epoch 1 startup never touches the engine code.
		try:
			from app.services.ambient_capture import engine  # noqa: F401
			# Engine.classify(...) returns a CaptureDecision or None and is
			# wired in Epoch 2. For now we leave the branch dormant.
			pass
		except ImportError:
			pass
		except Exception as e:
			logger.warning("intent_bus: ambient capture failed: %s", e)

	# 3. Fall through to chat
	return None
