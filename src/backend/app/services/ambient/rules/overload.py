"""Composite overload rule.

Combines Planka stalls + calendar pressure + health signals into a single
actionable trigger that fires the 'flow' (and optionally 'health') crews.

Rule: rule_overload_composite
  - Requires: planka 'card_stall_threshold' + calendar 'calendar_overload'
              or 'back_to_back_day'
  - Optional amplifier: health 'stress_detected' (if present, raises priority
    from 2 -> 1 and adds 'health' to the crew list)
  - Severity gate: combined severity >= 0.6 before firing

Cooldown: 360 minutes (max once per 6 hours).
"""

from __future__ import annotations

from app.services.ambient.models import Signal, Trigger

_MIN_COMBINED_SEVERITY = 0.6
_COOLDOWN_MINUTES = 360
_STALE_SIGNALS = {"card_stall_threshold"}
_CALENDAR_PRESSURE_SIGNALS = {"calendar_overload", "back_to_back_day"}
_HEALTH_SIGNALS = {"stress_detected", "fatigue_detected"}


def _find(signals: list[Signal], source: str, kinds: set[str]) -> Signal | None:
	"""Return the first signal matching source + any of the given kinds."""
	for s in signals:
		if s.source == source and s.kind in kinds:
			return s
	return None


def rule_overload_composite(signals: list[Signal]) -> Trigger | None:
	"""Fire when Planka stalls + calendar pressure cross the severity gate."""
	planka_sig = _find(signals, "planka", _STALE_SIGNALS)
	cal_sig = _find(signals, "calendar", _CALENDAR_PRESSURE_SIGNALS)
	if not planka_sig or not cal_sig:
		return None  # require both for this composite rule

	combined_severity = planka_sig.severity + cal_sig.severity
	health_sig = _find(signals, "health", _HEALTH_SIGNALS)
	if health_sig:
		combined_severity += health_sig.severity * 0.5  # health is an amplifier

	if combined_severity < _MIN_COMBINED_SEVERITY:
		return None

	# Build an informative context block for the crews
	stalled_cards = planka_sig.detail.get("stalled_cards", [])[:5]
	card_names = ", ".join(c.get("name", "?") for c in stalled_cards)
	if not card_names:
		card_names = "multiple stalled cards"

	cal_kind = cal_sig.kind
	if cal_kind == "calendar_overload":
		cal_desc = f"tomorrow has {cal_sig.detail.get('tomorrow_meeting_hours', 'N/A')}h of meetings"
	else:
		cal_desc = f"{cal_sig.detail.get('back_to_back_count', 'N/A')} back-to-back meetings detected"

	health_note = ""
	if health_sig:
		health_note = " User also showing stress/fatigue signals."

	context = (
		f"AMBIENT_TRIGGER (proactive -- user did not ask for this):\n"
		f"Stalled Planka cards ({planka_sig.detail.get('stalled_count', len(stalled_cards))}): {card_names}.\n"
		f"Calendar pressure: {cal_desc}.{health_note}\n"
		f"Combined severity: {combined_severity:.2f}.\n"
		f"Tailor your output to address this specific situation. Be actionable and concise.\n"
		f"This is a push notification -- keep it shorter than a scheduled crew run."
	)

	crews = ["flow"]
	priority = 2
	if health_sig:
		crews.append("health")
		priority = 1  # health amplifier raises to critical

	return Trigger(
		rule_id="rule_overload_composite",
		priority=priority,
		crews=crews,
		context=context,
		cooldown_minutes=_COOLDOWN_MINUTES,
		delivery="quiet_moment",
	)
