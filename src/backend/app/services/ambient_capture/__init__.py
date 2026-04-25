"""Ambient capture & contextual routing engine.

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
]
