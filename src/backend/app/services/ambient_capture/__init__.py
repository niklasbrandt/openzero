"""Ambient capture & contextual routing engine.

Epoch 2 -- Intelligence. Ships gated behind AMBIENT_CAPTURE_ENABLED. Adds:
  - scoring: pure composite Tier A+B+C scorer
  - hitl: free-text HITL reply parser
  - plugins: PlankaCardPlugin (Planka card creation target)
  - intent_bus: Epoch 2 pipeline branch (plugin scoring + lane routing)

Epoch 1 -- Foundation. Ships dark (no behaviour change). Provides:
  - intent_bus: top-level dispatcher skeleton
  - plugin: capability-manifested plugin protocol + registry
  - profiles: board profile builder + Redis cache
  - pending: unified pending-state queue (channel-scoped, hijack-guarded)
  - recovery: failure recovery / retry / circuit breaker
  - operator_scope: single-user scope guard (Section 18)
  - sanitiser: shared input/output sanitisers (control-char strip, sentinel wrap)

See docs/artifacts/ambient_capture_routing.md for the full architectural plan.
"""

from app.services.ambient_capture.operator_scope import (
	get_operator_user_id,
	require_operator_user_id,
	is_operator_owned_board,
)
from app.services.ambient_capture.sanitiser import (
	clamp_phrase,
	strip_control_chars,
	wrap_untrusted,
	MAX_AMBIENT_PHRASE_CHARS,
)
from app.services.ambient_capture.plugin import (
	CapturePlugin,
	PluginCapabilities,
	PluginScore,
	CaptureDecision,
	ActionResult,
	PluginRegistry,
	registry,
)
from app.services.ambient_capture.profiles import (
	BoardProfile,
	BoardProfileBuilder,
	get_profile_builder,
)
from app.services.ambient_capture.pending import (
	PendingCapture,
	store_pending,
	consume_pending,
	invalidate_pending,
	pending_key,
)
from app.services.ambient_capture.recovery import (
	ActionExecution,
	Attempt,
	CircuitBreaker,
	get_breaker,
)
from app.services.ambient_capture import scoring
from app.services.ambient_capture import hitl as hitl_module
from app.services.ambient_capture.hitl import parse_hitl_reply, HitlAction
from app.services.ambient_capture.plugins import PlankaCardPlugin


def _register_default_plugins() -> None:
	"""Register built-in plugins once at import time when the flag is on."""
	from app.config import settings
	if not bool(getattr(settings, "AMBIENT_CAPTURE_ENABLED", False)):
		return
	if registry.get("planka_card") is None:
		try:
			registry.register(PlankaCardPlugin())
		except Exception as exc:
			import logging
			logging.getLogger(__name__).warning(
				"ambient_capture: failed to auto-register PlankaCardPlugin: %s", exc
			)


_register_default_plugins()

__all__ = [
	"get_operator_user_id",
	"require_operator_user_id",
	"is_operator_owned_board",
	"clamp_phrase",
	"strip_control_chars",
	"wrap_untrusted",
	"MAX_AMBIENT_PHRASE_CHARS",
	"CapturePlugin",
	"PluginCapabilities",
	"PluginScore",
	"CaptureDecision",
	"ActionResult",
	"PluginRegistry",
	"registry",
	"BoardProfile",
	"BoardProfileBuilder",
	"get_profile_builder",
	"PendingCapture",
	"store_pending",
	"consume_pending",
	"invalidate_pending",
	"pending_key",
	"ActionExecution",
	"Attempt",
	"CircuitBreaker",
	"get_breaker",
	"scoring",
	"hitl_module",
	"parse_hitl_reply",
	"HitlAction",
	"PlankaCardPlugin",
]
