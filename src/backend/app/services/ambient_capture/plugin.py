"""Plugin protocol + capability manifest + registry.

Plugins are self-contained capture targets (Planka card, calendar event,
shopping list, memory fact, reminder, ...). The engine collects scores from
all registered plugins and the highest-scoring one wins.

Section 4 of the artifact. Capability manifests enforce hard scope clamps
(no plugin may delete; HITL requirements honoured by engine, not plugin).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


HitlReason = Literal["create", "modify", "overwrite_user_authored"]
Lane = Literal["EXECUTE", "ASK", "TEACH", "CHAT"]


@dataclass(frozen=True)
class PluginCapabilities:
	"""Static capability manifest enforced by the engine before execute_capture."""

	can_create_resources: bool = False
	can_modify_existing: bool = False
	can_delete: bool = False  # MUST stay False in v1; rejected at registration
	requires_hitl_for: frozenset[HitlReason] = field(default_factory=frozenset)
	max_capture_size_chars: int = 500


@dataclass
class PluginScore:
	"""A plugin's confidence that the phrase belongs to its destination type."""

	score: float  # [0.0, 1.0]
	destination_id: str  # plugin-internal opaque id (e.g. "board_xyz/list_abc")
	destination_label: str  # human-readable label for HITL phrasing
	reasoning: dict  # arbitrary diagnostic payload (not surfaced in v1)


@dataclass
class CaptureDecision:
	"""Resolved capture intent ready for execution or HITL."""

	plugin_name: str
	phrase: str
	destination_id: str
	destination_label: str
	confidence: float
	lane: Lane
	channel: str  # "telegram" | "whatsapp" | "dashboard"
	user_id: str  # operator user id


@dataclass
class ActionResult:
	"""Outcome of a plugin's execute_capture call."""

	success: bool
	message: str  # i18n-resolved confirmation or failure report
	resource_id: Optional[str] = None  # created/affected resource id


@runtime_checkable
class CapturePlugin(Protocol):
	name: str
	capabilities: PluginCapabilities

	async def score_match(self, phrase: str, context: dict) -> Optional[PluginScore]:
		"""Return a PluginScore if the phrase plausibly belongs to this plugin's
		destination type, else None. Called only after the phrase has been
		clamped and operator-scope-checked.
		"""
		pass

	async def execute_capture(self, decision: CaptureDecision) -> ActionResult:
		"""Perform the actual capture. Engine has already enforced HITL gates."""
		pass

	async def explain_routing(self, decision: CaptureDecision, lang: str) -> str:
		"""Return a one-sentence i18n explanation for the dashboard reasoning trace."""
		pass


class PluginRegistry:
	"""Central registry. Engine iterates over registered plugins per capture."""

	def __init__(self) -> None:
		self._plugins: dict[str, CapturePlugin] = {}

	def register(self, plugin: CapturePlugin) -> None:
		# Hard scope clamps: no plugin may delete; engine enforces this.
		if plugin.capabilities.can_delete:
			raise ValueError(
				f"ambient_capture: plugin '{plugin.name}' declares can_delete=True; "
				f"refusing to register. Ambient routing never deletes (Section 4)."
			)
		if plugin.name in self._plugins:
			logger.warning("ambient_capture: re-registering plugin %s", plugin.name)
		self._plugins[plugin.name] = plugin
		logger.info("ambient_capture: registered plugin %s", plugin.name)

	def unregister(self, name: str) -> None:
		self._plugins.pop(name, None)

	def all(self) -> list[CapturePlugin]:
		return list(self._plugins.values())

	def names(self) -> list[str]:
		return list(self._plugins.keys())

	def get(self, name: str) -> Optional[CapturePlugin]:
		return self._plugins.get(name)

	def __len__(self) -> int:
		return len(self._plugins)


# Module-level registry. Plugins register themselves at import time once
# Epoch 2 wires them up.
registry = PluginRegistry()
