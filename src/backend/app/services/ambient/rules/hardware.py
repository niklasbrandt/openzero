"""Hardware / infrastructure signal rules.

signal rules:
  detect_disk_critical       — emits when disk >= 85%
  detect_memory_critical     — emits when memory >= 90%
  detect_container_failure   — emits when any container becomes unhealthy

trigger rules:
  rule_infra_critical        — P1 immediate alert (no crew; delivers to Telegram)
"""

from __future__ import annotations

from app.services.ambient.models import Signal, Trigger

_DISK_CRITICAL_PCT = 85.0
_MEMORY_CRITICAL_PCT = 90.0
_COOLDOWN_MINUTES = 120  # 2 hours between infra alerts


# ── Signal rules ─────────────────────────────────────────────────────────────

def detect_disk_critical(current: dict, previous: dict | None) -> list[Signal]:
	"""Fire when root disk usage crosses the critical threshold and is a new crossing."""
	if not current:
		return []
	pct = current.get("disk_percent", 0.0)
	if pct < _DISK_CRITICAL_PCT:
		return []
	prev_pct = (previous or {}).get("disk_percent", 0.0)
	if prev_pct >= _DISK_CRITICAL_PCT:
		return []  # Already in critical state, don't re-fire
	return [Signal(
		source="hardware",
		kind="disk_critical",
		severity=min(1.0, (pct - _DISK_CRITICAL_PCT) / 15),
		detail={"disk_percent": pct, "threshold": _DISK_CRITICAL_PCT},
	)]


def detect_memory_critical(current: dict, previous: dict | None) -> list[Signal]:
	"""Fire when RAM usage crosses the critical threshold."""
	if not current:
		return []
	pct = current.get("memory_percent", 0.0)
	if pct < _MEMORY_CRITICAL_PCT:
		return []
	prev_pct = (previous or {}).get("memory_percent", 0.0)
	if prev_pct >= _MEMORY_CRITICAL_PCT:
		return []
	return [Signal(
		source="hardware",
		kind="memory_critical",
		severity=min(1.0, (pct - _MEMORY_CRITICAL_PCT) / 10),
		detail={"memory_percent": pct, "threshold": _MEMORY_CRITICAL_PCT},
	)]


def detect_container_failure(current: dict, previous: dict | None) -> list[Signal]:
	"""Fire when containers flip from healthy to unhealthy."""
	if not current:
		return []
	curr_unhealthy: list[str] = current.get("container_unhealthy", [])
	prev_unhealthy: list[str] = (previous or {}).get("container_unhealthy", [])
	new_failures = [c for c in curr_unhealthy if c not in prev_unhealthy]
	if not new_failures:
		return []
	return [Signal(
		source="hardware",
		kind="container_failure",
		severity=min(1.0, len(new_failures) / 3),
		detail={"new_unhealthy": new_failures},
	)]


# ── Trigger rule ─────────────────────────────────────────────────────────────

def rule_infra_critical(signals: list[Signal]) -> Trigger | None:
	"""Convert hardware signals into a high-priority infra alert."""
	hw_sigs = [s for s in signals if s.source == "hardware" and s.kind in {
		"disk_critical", "memory_critical", "container_failure",
	}]
	if not hw_sigs:
		return None

	parts: list[str] = []
	for sig in hw_sigs:
		if sig.kind == "disk_critical":
			parts.append(f"Disk at {sig.detail.get('disk_percent', 0):.0f}%.")
		elif sig.kind == "memory_critical":
			parts.append(f"RAM at {sig.detail.get('memory_percent', 0):.0f}%.")
		elif sig.kind == "container_failure":
			names = sig.detail.get("new_unhealthy", [])
			parts.append(f"Container(s) unhealthy: {', '.join(names)}.")

	return Trigger(
		rule_id="rule_infra_critical",
		priority=1,
		crews=[],
		context="[INFRA] " + " ".join(parts),
		cooldown_minutes=_COOLDOWN_MINUTES,
		delivery="immediate",
	)
