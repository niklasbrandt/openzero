"""Planka signal rules beyond card stalls.

detect_today_overload: emits when the Operator Board Today list
  has > TODAY_MAX cards (overcommitment pattern).
"""

from __future__ import annotations

from datetime import datetime

from app.services.ambient.models import Signal

_TODAY_MAX = 7


def detect_today_overload(current: dict, previous: "dict | None") -> list[Signal]:
	"""Emit when the Today list has too many cards."""
	count = current.get("today_count", 0)
	if count <= _TODAY_MAX:
		return []
	prev_count = (previous or {}).get("today_count", 0)
	if prev_count > _TODAY_MAX:
		return []  # Already knew about this, don't re-emit
	return [Signal(
		source="planka",
		kind="today_overload",
		severity=min(1.0, (count - _TODAY_MAX) / 5),
		detail={"today_count": count},
		timestamp=datetime.now(),
	)]
