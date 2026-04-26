"""Health signal rules.

detect_stress_detected: emits when the HealthAdapter's last snapshot
  contains stress_keywords_detected=True or high fatigue_mention_count.

detect_no_exercise_mention: emits when no_exercise_days >= threshold,
  for use by the sedentary drift composite rule.
"""

from __future__ import annotations

from datetime import datetime

from app.services.ambient.models import Signal

_FATIGUE_COUNT_THRESHOLD = 2  # 2+ fatigue mentions in 24h = signal
_NO_EXERCISE_DAYS_THRESHOLD = 5


def detect_stress_detected(current: dict, previous: "dict | None") -> list[Signal]:
	"""Emit when the last health snapshot shows stress/fatigue keyword presence."""
	stress = current.get("stress_keywords_detected", False)
	fatigue = current.get("fatigue_mention_count", 0)
	if not stress and fatigue < _FATIGUE_COUNT_THRESHOLD:
		return []
	# Only fire if this is a new appearance (previous didn't have it)
	prev_stress = (previous or {}).get("stress_keywords_detected", False)
	prev_fatigue = (previous or {}).get("fatigue_mention_count", 0)
	if prev_stress or prev_fatigue >= _FATIGUE_COUNT_THRESHOLD:
		return []
	return [Signal(
		source="health",
		kind="stress_detected",
		severity=min(1.0, 0.4 + fatigue * 0.1),
		detail={"stress_keywords": stress, "fatigue_mention_count": fatigue},
		timestamp=datetime.now(),
	)]


def detect_no_exercise_mention(current: dict, previous: "dict | None") -> list[Signal]:
	"""Emit when no exercise mention is found for >= threshold days."""
	days = current.get("no_exercise_days", 0)
	if days < _NO_EXERCISE_DAYS_THRESHOLD or days == 999:
		return []
	prev_days = (previous or {}).get("no_exercise_days", 0)
	# Only emit on threshold crossing or once per day (large jump)
	if prev_days >= _NO_EXERCISE_DAYS_THRESHOLD and (days - prev_days) < 1:
		return []
	return [Signal(
		source="health",
		kind="no_exercise_mention",
		severity=min(1.0, (days - _NO_EXERCISE_DAYS_THRESHOLD) / 7),
		detail={"days": days, "no_exercise_days": days},
		timestamp=datetime.now(),
	)]
