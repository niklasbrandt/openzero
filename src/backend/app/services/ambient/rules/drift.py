"""Sedentary drift and stagnation rules.

rule_sedentary_drift:
  - Source: health (no_exercise_days >= 5) + optionally conversation (silence)
  - Crew: 'health', 'coach'
  - Priority: 4
  - Cooldown: 1440 min (once per day)

rule_today_list_overload:
  - Source: planka (today_count > 7 signals overcommitment)
  - Crew: 'flow' (to help reprioritise)
  - Priority: 3
  - Cooldown: 480 min (8 hours)
"""

from __future__ import annotations

from app.services.ambient.models import Signal, Trigger

_SEDENTARY_DAYS_THRESHOLD = 5
_SEDENTARY_COOLDOWN = 1440
_TODAY_OVERLOAD_COOLDOWN = 480


def _find(signals: list[Signal], source: str, kind: str) -> Signal | None:
	for s in signals:
		if s.source == source and s.kind == kind:
			return s
	return None


def rule_sedentary_drift(signals: list[Signal]) -> Trigger | None:
	"""Fire when no exercise has been mentioned for 5+ days."""
	# Health adapter exposes no_exercise_days in detail of a synthetic signal,
	# or we can derive it from the snapshot stored via the health adapter.
	# Since we receive signals (not raw snapshots) here, we look for a
	# "no_exercise_mention" signal or fall back to checking the health signals.
	drift_sig = _find(signals, "health", "no_exercise_mention")
	if drift_sig is None:
		return None

	days = drift_sig.detail.get("days", drift_sig.detail.get("no_exercise_days", 0))
	if days < _SEDENTARY_DAYS_THRESHOLD:
		return None

	context = (
		f"AMBIENT_TRIGGER (proactive -- user did not ask for this):\n"
		f"No exercise-related conversation detected for {days}+ days.\n"
		f"Gently check in on fitness habits and suggest restarting.\n"
		f"Keep it brief and supportive -- this is a nudge, not a lecture.\n"
		f"This is a push notification -- keep it shorter than a scheduled crew run."
	)
	return Trigger(
		rule_id="rule_sedentary_drift",
		priority=4,
		crews=["health", "coach"],
		context=context,
		cooldown_minutes=_SEDENTARY_COOLDOWN,
		delivery="quiet_moment",
	)


def rule_today_list_overload(signals: list[Signal]) -> Trigger | None:
	"""Fire when the Planka Today list is dangerously over-committed."""
	# Planka adapter emits "today_overload" when today_count > threshold
	today_sig = _find(signals, "planka", "today_overload")
	if today_sig is None:
		return None

	count = today_sig.detail.get("today_count", 0)
	context = (
		f"AMBIENT_TRIGGER (proactive -- user did not ask for this):\n"
		f"Today list has {count} cards -- likely overcommitted for a single day.\n"
		f"Help the user identify which cards to defer to 'This Week' or 'Backlog'.\n"
		f"Be direct. List candidates by name. This is a push notification -- keep it brief."
	)
	return Trigger(
		rule_id="rule_today_list_overload",
		priority=3,
		crews=["flow"],
		context=context,
		cooldown_minutes=_TODAY_OVERLOAD_COOLDOWN,
		delivery="quiet_moment",
	)
