"""Email urgency signal rules.

signal rules:
  detect_priority_spike — emits kind="priority_spike" when priority email count
                           increases from 0 (or grows by 3+)

trigger rules:
  rule_inbox_overwhelm  — P3 advisory when inbox is in an overwhelmed state
"""

from __future__ import annotations

from app.services.ambient.models import Signal, Trigger

_SPIKE_THRESHOLD = 1          # any new priority email counts
_COOLDOWN_MINUTES = 60        # max one nag per hour
_REPEAT_SENDER_PRIORITY = 2   # boost priority when repeat sender detected


# ── Signal rules ─────────────────────────────────────────────────────────────

def detect_priority_spike(current: dict, previous: dict | None) -> list[Signal]:
	"""Fire when the priority inbox count materially increases."""
	if not current:
		return []
	curr_count = current.get("priority_count", 0)
	if curr_count < _SPIKE_THRESHOLD:
		return []
	prev_count = (previous or {}).get("priority_count", 0)
	if curr_count <= prev_count:
		return []  # Not a new spike
	delta = curr_count - prev_count
	return [Signal(
		source="email",
		kind="priority_spike",
		severity=min(1.0, curr_count / 10),
		detail={
			"priority_count": curr_count,
			"delta": delta,
			"priority_sender_repeat": current.get("priority_sender_repeat", 0),
			"unread_age_hours_max": current.get("unread_age_hours_max", 0.0),
		},
	)]


def detect_inbox_surge(current: dict, previous: dict | None) -> list[Signal]:
	"""Fire when total unread count grows rapidly (3+ new since last check)."""
	if not current:
		return []
	curr = current.get("unread_count", 0)
	prev = (previous or {}).get("unread_count", 0)
	delta = curr - prev
	if delta < 3:
		return []
	return [Signal(
		source="email",
		kind="inbox_surge",
		severity=min(1.0, delta / 20),
		detail={"unread_count": curr, "delta": delta},
	)]


# ── Trigger rule ─────────────────────────────────────────────────────────────

def rule_inbox_overwhelm(signals: list[Signal]) -> Trigger | None:
	"""Convert email signals into an advisory trigger."""
	email_sigs = [s for s in signals if s.source == "email"]
	if not email_sigs:
		return None

	priority_sigs = [s for s in email_sigs if s.kind == "priority_spike"]
	surge_sigs = [s for s in email_sigs if s.kind == "inbox_surge"]

	if not priority_sigs and not surge_sigs:
		return None

	summary_parts: list[str] = []
	parts = summary_parts
	priority_level = 3

	if priority_sigs:
		sig = priority_sigs[0]
		parts.append(f"{sig.detail.get('priority_count', 0)} priority emails waiting.")
		repeats = sig.detail.get("priority_sender_repeat", 0)
		if repeats:
			parts.append(f"{repeats} sender(s) sent 3+ emails recently.")
			priority_level = _REPEAT_SENDER_PRIORITY

	if surge_sigs:
		sig = surge_sigs[0]
		parts.append(f"{sig.detail.get('delta', 0)} new emails arrived since last check.")

	return Trigger(
		rule_id="rule_inbox_overwhelm",
		priority=priority_level,
		crews=[],
		context=" ".join(parts),
		cooldown_minutes=_COOLDOWN_MINUTES,
	)
