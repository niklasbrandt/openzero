"""Health / biometric adapter.

P1 bootstrap strategy: two signal sources until a wearable API is integrated.
  1. personal/health.md  —  structured data (training schedule, conditions)
  2. GlobalMessage scan  —  keyword presence in last 24h of user messages
     (counts occurrences of sleep/fatigue/stress keywords WITHOUT storing text)

Snapshot schema (see §3.4 of ambient_intelligence.md):
{
    "hrv_trend": "up" | "down" | "stable" | "unknown",
    "rhr_bpm": int | null,
    "sleep_hours": float | null,
    "recovery_score": int | null,   # 0-100 if wearable provides (null for now)
    "strain_score": int | null,
    "stress_keywords_detected": bool,
    "fatigue_mention_count": int,   # # of fatigue/sleep mentions in last 24h
    "no_exercise_days": int,        # approximate days since exercise mention
}
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Keyword sets — keyword presence only, text never stored
_STRESS_KEYWORDS = {
	"stressed", "overwhelming", "anxious", "anxiety", "burnout", "burn out",
	"overwhelmed", "panic", "can't cope", "cannot cope",
	"gestresst", "überwältigt", "ausgebrannt", "panik",
}
_FATIGUE_KEYWORDS = {
	"tired", "exhausted", "fatigue", "fatigued", "sleepy", "no sleep",
	"bad sleep", "woke up early", "couldn't sleep", "insomnia",
	"müde", "erschöpft", "schlaflos", "kein schlaf",
}
_EXERCISE_KEYWORDS = {
	"workout", "gym", "run", "running", "training", "exercise", "sport",
	"cycling", "swim", "swimming", "yoga", "walked", "walk",
	"training", "laufen", "sport gemacht",
}


class HealthAdapter:
	source_id = "health"
	poll_interval_s = 600  # 10 minutes — health changes slowly

	async def snapshot(self) -> dict:
		try:
			return await _fetch_health_snapshot()
		except Exception as exc:
			logger.warning("HealthAdapter.snapshot failed: %s", exc)
			return _empty_snapshot()


async def _fetch_health_snapshot() -> dict:
	snap = _empty_snapshot()

	# --- Source 1: GlobalMessage keyword scan ---
	try:
		from sqlalchemy import select
		from app.models.db import AsyncSessionLocal, GlobalMessage
		cutoff = datetime.utcnow() - timedelta(hours=24)
		async with AsyncSessionLocal() as session:
			res = await session.execute(
				select(GlobalMessage.content)
				.where(GlobalMessage.role == "user")
				.where(GlobalMessage.created_at >= cutoff)
				.order_by(GlobalMessage.created_at.asc())
			)
			contents: list[str] = [row[0].lower() for row in res.all() if row[0]]

		fatigue_count = 0
		stress_detected = False
		last_exercise_age_days = 999

		for content in contents:
			for kw in _FATIGUE_KEYWORDS:
				if kw in content:
					fatigue_count += 1
					break
			for kw in _STRESS_KEYWORDS:
				if kw in content:
					stress_detected = True
					break

		# Exercise — approximate days since last mention by scanning all recent messages
		# (scan up to 30 days back to estimate days without activity)
		exercise_cutoff = datetime.utcnow() - timedelta(days=30)
		async with AsyncSessionLocal() as session:
			res2 = await session.execute(
				select(GlobalMessage.content, GlobalMessage.created_at)
				.where(GlobalMessage.role == "user")
				.where(GlobalMessage.created_at >= exercise_cutoff)
				.order_by(GlobalMessage.created_at.desc())
			)
			recent_msgs = [(row[0].lower(), row[1]) for row in res2.all() if row[0]]

		for content_lower, msg_dt in recent_msgs:
			if any(kw in content_lower for kw in _EXERCISE_KEYWORDS):
				days_ago = (datetime.utcnow() - msg_dt).days
				last_exercise_age_days = days_ago
				break

		snap["stress_keywords_detected"] = stress_detected
		snap["fatigue_mention_count"] = fatigue_count
		if last_exercise_age_days < 999:
			snap["no_exercise_days"] = last_exercise_age_days

	except Exception as exc:
		logger.debug("HealthAdapter: GlobalMessage scan failed: %s", exc)

	return snap


def _empty_snapshot() -> dict:
	return {
		"hrv_trend": "unknown",
		"rhr_bpm": None,
		"sleep_hours": None,
		"recovery_score": None,
		"strain_score": None,
		"stress_keywords_detected": False,
		"fatigue_mention_count": 0,
		"no_exercise_days": 999,  # sentinel: "haven't seen exercise mention"
	}
