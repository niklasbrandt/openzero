"""Calendar-based signal rules.

signal rules (pure functions, no I/O):
  detect_calendar_overload  — emits kind="calendar_overload" when tomorrow is packed
  detect_back_to_back       — emits kind="back_to_back_day" when no recovery gaps

trigger rules (take signals, return Trigger | None):
  rule_calendar_advisory    — fires 'ponder' crew with P3 advisory suggestion
"""

from __future__ import annotations

from app.services.ambient.models import Signal, Trigger

_OVERLOAD_HOURS_THRESHOLD = 6.0
_BACK_TO_BACK_THRESHOLD = 3
_COOLDOWN_MINUTES = 480  # 8 hours — only nag once per day at most


# ── Signal (diff) rules ──────────────────────────────────────────────────────

def detect_calendar_overload(current: dict, previous: dict | None) -> list[Signal]:
	"""Fire when tomorrow's meeting hours crosses the overload threshold."""
	if not current:
		return []
	tomorrow_hours = current.get("tomorrow_meeting_hours", 0.0)
	if tomorrow_hours <= _OVERLOAD_HOURS_THRESHOLD:
		return []
	# Only fire if this is a fresh crossing (previous was below threshold)
	if previous and previous.get("tomorrow_meeting_hours", 0.0) > _OVERLOAD_HOURS_THRESHOLD:
		return []
	return [Signal(
		source="calendar",
		kind="calendar_overload",
		severity=min(1.0, (tomorrow_hours - _OVERLOAD_HOURS_THRESHOLD) / 4),
		detail={"tomorrow_meeting_hours": tomorrow_hours},
	)]


def detect_back_to_back(current: dict, previous: dict | None) -> list[Signal]:
	"""Fire when back-to-back meeting count exceeds threshold."""
	if not current:
		return []
	count = current.get("back_to_back_count", 0)
	if count <= _BACK_TO_BACK_THRESHOLD:
		return []
	prev_count = (previous or {}).get("back_to_back_count", 0)
	if prev_count > _BACK_TO_BACK_THRESHOLD:
		return []  # Already knew about this
	return [Signal(
		source="calendar",
		kind="back_to_back_day",
		severity=min(1.0, count / 6),
		detail={"back_to_back_count": count},
	)]


# ── Trigger rule ─────────────────────────────────────────────────────────────

def rule_calendar_advisory(signals: list[Signal]) -> Trigger | None:
	"""Convert calendar signals into a P3 advisory suggestion."""
	cal_sigs = [s for s in signals if s.source == "calendar" and s.kind in {
		"calendar_overload", "back_to_back_day",
	}]
	if not cal_sigs:
		return None

	lead_sig = cal_sigs[0]
	if lead_sig.kind == "calendar_overload":
		context_msg = (
			f"Tomorrow has {lead_sig.detail.get('tomorrow_meeting_hours', 'N/A')}h of meetings. "
			"Consider blocking focus time or rescheduling a slot."
		)
	else:
		context_msg = (
			f"{lead_sig.detail.get('back_to_back_count', 'N/A')} back-to-back meetings detected. "
			"No recovery time in the day — consider adding buffer gaps."
		)

	return Trigger(
		rule_id="rule_calendar_advisory",
		priority=3,
		crews=[],  # insight-only, no crew fire
		context=context_msg,
		cooldown_minutes=_COOLDOWN_MINUTES,
	)
