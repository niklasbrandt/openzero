"""card_stall rule — Planka source.

Fires when >= 1 card has been stalled for >= STALL_DAYS days and has not
changed since the previous snapshot (prevents repeated re-firing on the same
stall set within a single session).

Signal emitted: kind="card_stall_threshold"
Trigger:        rule_id="card_stall", crew="flow", delivery="quiet_moment"

See docs/artifacts/ambient_intelligence.md §6.1.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.services.ambient.models import Signal, Trigger

logger = logging.getLogger(__name__)

_STALL_DAYS = 4


def detect_card_stalls(current: dict, previous: "dict | None") -> list[Signal]:
	"""Emit a stall signal when new stalled cards appear vs the previous snapshot."""
	stalled: list[dict] = current.get("stalled", [])
	if not stalled:
		return []

	# Only surface cards that were NOT already stalled in the previous snapshot
	# to avoid re-emitting the same signal every poll cycle.
	prev_names: set[str] = set()
	if previous:
		prev_names = {c["name"] for c in previous.get("stalled", [])}

	new_stalls = [c for c in stalled if c["name"] not in prev_names]
	# On first snapshot (no previous) treat all stalls as new — they may have
	# existed before the engine started, but we should still surface them once.
	if previous is None:
		new_stalls = stalled

	if not new_stalls:
		return []

	severity = min(1.0, len(new_stalls) * 0.2)
	return [
		Signal(
			source="planka",
			kind="card_stall_threshold",
			severity=severity,
			detail={"stalled_cards": new_stalls},
			timestamp=datetime.now(),
		)
	]


def rule_card_stall(signals: "list[Signal]") -> "Trigger | None":
	"""Convert a card_stall_threshold signal into a 'flow' crew trigger.

	Called by the RuleEngine after the DiffEngine has collected signals.
	"""
	stall_signals = [
		s for s in signals if s.source == "planka" and s.kind == "card_stall_threshold"
	]
	if not stall_signals:
		return None

	# Aggregate across multiple signals (shouldn't happen in P0 but future-proof)
	all_cards: list[dict] = []
	max_severity = 0.0
	for sig in stall_signals:
		all_cards.extend(sig.detail.get("stalled_cards", []))
		max_severity = max(max_severity, sig.severity)

	card_summary = ", ".join(
		f"'{c['name']}' ({c['board']}, last active {c.get('last_activity', '?')})"
		for c in all_cards[:5]   # cap context at 5 cards to avoid prompt bloat
	)
	if len(all_cards) > 5:
		card_summary += f" and {len(all_cards) - 5} more"

	context = (
		"AMBIENT_TRIGGER (proactive — user did not ask for this):\n"
		f"{len(all_cards)} card(s) in Planka have had no activity for {_STALL_DAYS}+ days: "
		f"{card_summary}.\n\n"
		"Review these stalled items. Recommend concrete next steps or suggest archiving "
		"items that are no longer relevant. Be concise — this is a push notification."
	)

	return Trigger(
		rule_id="card_stall",
		priority=3,
		crews=["flow"],
		context=context,
		cooldown_minutes=360,  # fire at most once per 6 hours
		delivery="quiet_moment",
	)
