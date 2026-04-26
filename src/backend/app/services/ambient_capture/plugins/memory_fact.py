"""MemoryFactPlugin — routes first-person preference/fact phrases to
memory.store_memory() as a persistent memory fact.

Epoch 3 plugin. Scores phrases that match first-person preference markers
("I prefer", "I like", "I always", "My favourite", etc.) then stores as a
memory point in Qdrant.

Capabilities:
- can_create_resources: True   (creates a new Qdrant memory point)
- can_modify_existing: False
- can_delete: False
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.services.ambient_capture.plugin import (
	ActionResult,
	CaptureDecision,
	PluginCapabilities,
	PluginScore,
)

logger = logging.getLogger(__name__)

# First-person preference patterns (multi-language subset).
_PREFERENCE_RE = re.compile(
	r"\b(i (prefer|like|love|hate|always|usually|never|think|believe|want|need)|"
	r"my (favourite|favorite|preferred|go-to)|"
	r"ich (mag|liebe|bevorzuge|immer|nie)|"
	r"me (gusta|encanta|parece)|"
	r"j[e\']? (préfère|aime|déteste)|"
	r"私は|나는|我)\b",
	re.I | re.UNICODE,
)

class MemoryFactPlugin:
	"""Store a first-person fact or preference as a memory point."""

	name = "memory_fact"
	capabilities = PluginCapabilities(
		can_create_resources=True,
		can_modify_existing=False,
		can_delete=False,
		requires_hitl_for=frozenset(),
		max_capture_size_chars=500,
	)

	async def score_match(self, phrase: str, context: dict) -> Optional[PluginScore]:
		if _PREFERENCE_RE.search(phrase):
			# Strong signal — first-person marker present
			score = 0.80
		else:
			return None
		return PluginScore(
			score=score,
			destination_id="memory_facts",
			destination_label="Memory Vault",
			reasoning={"pattern": "first_person_preference"},
		)

	async def execute_capture(self, decision: CaptureDecision) -> ActionResult:
		"""Store fact in Qdrant via the memory service."""
		try:
			from app.services.memory import store_memory
			await store_memory(decision.phrase, metadata={"source": "ambient_capture"})
			return ActionResult(success=True, message="Stored in memory.")
		except Exception as e:
			logger.warning("memory_fact: execute failed: %s", e)
			return ActionResult(success=False, message=str(e))

	async def explain_routing(self, decision: CaptureDecision, lang: str) -> str:
		return f"First-person preference detected in '{decision.phrase}' → Memory Vault"
