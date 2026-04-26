"""ShoppingListPlugin — routes grocery/shopping phrases to the Nutrition crew
shopping list via shopping_list.append_shopping_items().

Epoch 3 plugin. Scores phrases that contain a grocery verb pattern or
recognisable grocery noun, then appends to the active shopping list.

Capabilities:
- can_create_resources: False  (appends to existing list)
- can_modify_existing: True    (appends items)
- can_delete: False
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.services.ambient_capture.plugin import (
	ActionResult,
	CaptureDecision,
	CapturePlugin,
	PluginCapabilities,
	PluginScore,
)

logger = logging.getLogger(__name__)

_BUY_VERB_RE = re.compile(
	r"\b(buy|get|pick up|grab|kaufen|besorgen|comprar|acheter|買う|купить|شراء)\b",
	re.I | re.UNICODE,
)

_GROCERY_NOUNS = frozenset({
	"milk", "bread", "eggs", "butter", "cheese", "yogurt", "cream",
	"apple", "banana", "orange", "lemon", "avocado", "tomato", "potato",
	"onion", "garlic", "carrot", "spinach", "lettuce", "pasta", "rice",
	"sourdough", "flour", "sugar", "salt", "pepper", "oil", "vinegar",
	"chicken", "beef", "pork", "salmon", "tuna", "coffee", "tea", "juice",
	"Milch", "Brot", "Käse", "Eier",  # DE
})

_MIN_SCORE = 0.25


def _verb_score(phrase: str) -> float:
	return 0.45 if _BUY_VERB_RE.search(phrase) else 0.0


def _noun_score(phrase: str) -> float:
	words = set(phrase.lower().split())
	hits = len(words & {n.lower() for n in _GROCERY_NOUNS})
	return min(0.55, hits * 0.28)


class ShoppingListPlugin:
	"""Append a phrase to the active shopping list (Nutrition crew)."""

	name = "shopping_list"
	capabilities = PluginCapabilities(
		can_create_resources=False,
		can_modify_existing=True,
		can_delete=False,
		requires_hitl_for=frozenset(),
		max_capture_size_chars=200,
	)

	async def score_match(self, phrase: str, context: dict) -> Optional[PluginScore]:
		verb_s = _verb_score(phrase)
		noun_s = _noun_score(phrase)
		score = min(1.0, verb_s + noun_s)
		if score < _MIN_SCORE:
			return None
		return PluginScore(
			score=score,
			destination_id="shopping_list",
			destination_label="Shopping List",
			reasoning={"verb_score": verb_s, "noun_score": noun_s},
		)

	async def execute_capture(self, decision: CaptureDecision) -> ActionResult:
		"""Append to shopping list via the Nutrition crew helper."""
		try:
			from app.services.shopping_list import append_shopping_items
			result = await append_shopping_items([decision.phrase])
			return ActionResult(success=True, message=str(result))
		except Exception as e:
			logger.warning("shopping_list: execute failed: %s", e)
			return ActionResult(success=False, message=str(e))

	async def explain_routing(self, decision: CaptureDecision, lang: str) -> str:
		return f"Shopping verb or grocery noun detected in '{decision.phrase}' → Shopping List"
