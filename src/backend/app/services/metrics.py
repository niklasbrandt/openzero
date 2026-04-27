"""Lightweight in-process metrics counters for openZero.

No external Prometheus dependency required. Counters are kept in memory and can be
read by the /health endpoint or exported as a log summary by the daily 09:00 task.

Usage::

	from app.services.metrics import increment_counter, get_all_counters

	increment_counter("phantom_confirmations_total", channel="telegram", language="de")
	increment_counter("state_query_planka_lookups_total")
	snapshot = get_all_counters()
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# In-process counter store. Thread-safe under CPython's GIL (asyncio is single-threaded).
# Key: (counter_name, frozenset_of_label_pairs)    Value: int
_COUNTERS: dict[tuple[str, frozenset], int] = defaultdict(int)


def increment_counter(name: str, **labels: Any) -> None:
	"""Increment a named counter, optionally tagged with keyword-argument labels."""
	key = (name, frozenset(labels.items()))
	_COUNTERS[key] += 1


def get_counter(name: str, **labels: Any) -> int:
	"""Return current value of a counter (0 if never incremented)."""
	key = (name, frozenset(labels.items()))
	return _COUNTERS.get(key, 0)


def get_all_counters() -> dict[str, int]:
	"""Return all counters as a flat dict keyed by 'name{label=value,...}'.

	Returns an empty dict if no counters have been incremented.
	"""
	result: dict[str, int] = {}
	for (name, label_pairs), count in _COUNTERS.items():
		if label_pairs:
			label_str = ",".join(f"{k}={v}" for k, v in sorted(label_pairs))
			full_key = f"{name}{{{label_str}}}"
		else:
			full_key = name
		result[full_key] = count
	return result


def log_daily_summary() -> None:
	"""Write a one-line daily summary of all counters to the application logger."""
	counters = get_all_counters()
	if not counters:
		logger.info("Metrics daily summary: no counters recorded")
		return
	parts = [f"{k}={v}" for k, v in sorted(counters.items())]
	logger.info("Metrics daily summary: %s", "  ".join(parts))
