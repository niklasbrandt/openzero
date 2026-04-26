"""Hardware load adapter.

Reads system metrics from psutil (disk, RAM) and the Docker socket (container
health).  Returns a lightweight snapshot used by the infra_critical rule.

Snapshot schema (see §3.5 of ambient_intelligence.md):
{
    "cpu_percent": float,
    "memory_percent": float,
    "disk_percent": float,
    "container_unhealthy": [str],   # container names with status != healthy/running
    "llm_queue_depth": int,         # pending inference requests (0 if unavailable)
    "qdrant_points": int,
}

Failures in individual metrics are silenced — the adapter always returns a
structurally valid dict so downstream rules can compare keys safely.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class HardwareAdapter:
	source_id = "hardware"
	poll_interval_s = 300

	async def snapshot(self) -> dict:
		try:
			return await _fetch_hardware_snapshot()
		except Exception as exc:
			logger.warning("HardwareAdapter.snapshot failed: %s", exc)
			return _empty_snapshot()


async def _fetch_hardware_snapshot() -> dict:
	import platform
	from app.config import settings

	snap = _empty_snapshot()

	# --- CPU (Linux /proc/stat; macOS psutil fallback) ---
	try:
		import psutil
		snap["cpu_percent"] = psutil.cpu_percent(interval=0.1)
	except Exception as exc:
		logger.debug("HardwareAdapter: CPU unavailable: %s", exc)

	# --- RAM ---
	try:
		if platform.system() == "Linux":
			with open("/proc/meminfo") as f:
				mem: dict[str, int] = {}
				for line in f:
					parts = line.split(":")
					if len(parts) == 2:
						mem[parts[0].strip()] = int(parts[1].strip().split()[0])
				total = mem.get("MemTotal", 0)
				avail = mem.get("MemAvailable", mem.get("MemFree", 0))
				if total:
					snap["memory_percent"] = round((1 - avail / total) * 100, 1)
		else:
			import psutil
			snap["memory_percent"] = psutil.virtual_memory().percent
	except Exception as exc:
		logger.debug("HardwareAdapter: RAM unavailable: %s", exc)

	# --- Disk ---
	try:
		import psutil
		snap["disk_percent"] = round(psutil.disk_usage("/").percent, 1)
	except Exception as exc:
		logger.debug("HardwareAdapter: disk unavailable: %s", exc)

	# --- Docker container health (via Docker socket) ---
	try:
		import httpx
		async with httpx.AsyncClient(
			transport=httpx.AsyncHTTPTransport(uds="/var/run/docker.sock"),
			base_url="http://docker",
			timeout=5.0,
		) as dc:
			resp = await dc.get("/containers/json?all=false")
			if resp.status_code == 200:
				containers = resp.json()
				unhealthy: list[str] = []
				for c in containers:
					state = c.get("State", "")
					health = (c.get("Status") or "").lower()
					name = (c.get("Names") or ["?"])[0].lstrip("/")
					if state != "running" or "unhealthy" in health:
						unhealthy.append(name)
				snap["container_unhealthy"] = unhealthy
	except Exception as exc:
		logger.debug("HardwareAdapter: Docker socket unavailable: %s", exc)

	# --- LLM queue depth (llama.cpp /slots endpoint) ---
	try:
		import httpx
		llm_url = getattr(settings, "LLM_LOCAL_URL", "")
		if llm_url:
			async with httpx.AsyncClient(timeout=3.0) as client:
				slots_resp = await client.get(f"{llm_url.rstrip('/')}/slots")
				if slots_resp.status_code == 200:
					slots = slots_resp.json()
					# A slot is "busy" when its state != 0 (idle)
					snap["llm_queue_depth"] = sum(
						1 for s in (slots if isinstance(slots, list) else [])
						if s.get("state", 0) != 0
					)
	except Exception as exc:
		logger.debug("HardwareAdapter: LLM queue unavailable: %s", exc)

	# --- Qdrant points ---
	try:
		import httpx
		qdrant_url = getattr(settings, "QDRANT_URL", "http://qdrant:6333")
		async with httpx.AsyncClient(timeout=3.0) as client:
			qdrant_resp = await client.get(f"{qdrant_url.rstrip('/')}/collections")
			if qdrant_resp.status_code == 200:
				cols = qdrant_resp.json().get("result", {}).get("collections", [])
				total_points = 0
				for col in cols:
					snap["qdrant_points"] = total_points  # approximate; updated below
				# Quick count: sum vectors_count across all collections
				cnames = [c["name"] for c in cols]
				for cname in cnames[:5]:  # cap to avoid flooding
					try:
						cr = await client.get(f"{qdrant_url.rstrip('/')}/collections/{cname}")
						if cr.status_code == 200:
							vc = cr.json().get("result", {}).get("vectors_count") or 0
							total_points += vc
					except Exception:
						pass
				snap["qdrant_points"] = total_points
	except Exception as exc:
		logger.debug("HardwareAdapter: Qdrant unavailable: %s", exc)

	return snap


def _empty_snapshot() -> dict:
	return {
		"cpu_percent": 0.0,
		"memory_percent": 0.0,
		"disk_percent": 0.0,
		"container_unhealthy": [],
		"llm_queue_depth": 0,
		"qdrant_points": 0,
	}
