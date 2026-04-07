"""
LLM Peer Discovery Service
--------------------------
Autonomously discovers and manages available LLM inference endpoints across the
local network and any Tailscale-connected peers. Runs as a background loop with
no operator intervention after initial configuration.

Supported server types:
  - llama.cpp (llama-server):  detected via GET /health
  - Ollama:                    detected via GET /api/tags (first model auto-selected)

Configuration (set once in .env, never touch again):
  LLM_PEER_CANDIDATES=http://100.x.y.z:8081,http://100.a.b.c:11434

  Comma-separated list of candidate base URLs. Standard ports:
    llama.cpp  → 8081
    Ollama     → 11434

Routing policy:
  - Probes all candidates + VPS Docker container every 30 s.
  - Lowest-latency responding peer is selected as the active endpoint.
  - External (non-VPS) peers are preferred when their latency is within 20 %
    of the VPS container — i.e. a Tailscale Mac that is only slightly slower
    still wins because it has much more compute headroom.
  - Automatic failover: if the active peer goes offline, the next probe
    (within 30 s) promotes the next-best candidate with no restart.
  - Falls back to settings.LLM_LOCAL_URL if every peer is unreachable.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# How often to re-probe all peers (seconds).
_PROBE_INTERVAL_S = 30

# Per-probe connect+read timeout (seconds). Short: dead peers must not block inference.
_PROBE_TIMEOUT_S = 2.5

# External peers are preferred when their latency <= VPS * this factor.
_EXT_PREFERENCE_FACTOR = 1.20


@dataclass
class PeerState:
	url: str					# base URL, no trailing slash
	model: str = ""				# detected or configured model name
	server_type: str = ""		# "llamacpp" | "ollama" | ""
	online: bool = False
	latency_ms: float = float("inf")
	is_vps_local: bool = False	# True for the VPS Docker container fallback


# --------------------------------------------------------------------------- #
#  Module-level mutable state                                                 #
# --------------------------------------------------------------------------- #

_peers: list[PeerState] = []
_active: Optional[PeerState] = None
_lock = asyncio.Lock()
_started = False


# --------------------------------------------------------------------------- #
#  Probe helpers                                                               #
# --------------------------------------------------------------------------- #

async def _probe_llamacpp(client: httpx.AsyncClient, url: str) -> Optional[float]:
	"""Return latency_ms if a llama.cpp /health endpoint responds, else None."""
	try:
		t0 = time.monotonic()
		resp = await client.get(f"{url}/health", timeout=_PROBE_TIMEOUT_S)
		latency_ms = (time.monotonic() - t0) * 1000
		if resp.status_code in (200, 503):
			return latency_ms
	except Exception:
		pass
	return None


async def _probe_ollama(
	client: httpx.AsyncClient, url: str
) -> Optional[tuple[float, str]]:
	"""Return (latency_ms, first_model_name) if an Ollama /api/tags responds, else None."""
	try:
		t0 = time.monotonic()
		resp = await client.get(f"{url}/api/tags", timeout=_PROBE_TIMEOUT_S)
		latency_ms = (time.monotonic() - t0) * 1000
		if resp.status_code == 200:
			models = resp.json().get("models", [])
			model_name = models[0].get("name", "") if models else ""
			return latency_ms, model_name
	except Exception:
		pass
	return None


async def _detect_model_llamacpp(client: httpx.AsyncClient, url: str, fallback: str) -> str:
	"""Try to read the loaded model name from llama.cpp /props."""
	try:
		resp = await client.get(f"{url}/props", timeout=_PROBE_TIMEOUT_S)
		if resp.status_code == 200:
			data = resp.json()
			mp = (
				data.get("model_path")
				or data.get("default_generation_settings", {}).get("model", "")
			)
			if mp:
				return os.path.basename(mp)
	except Exception:
		pass
	return fallback


async def _probe_peer(
	client: httpx.AsyncClient, peer: PeerState, fallback_model: str
) -> PeerState:
	"""Probe a single peer and return an updated PeerState."""
	# Try llama.cpp first — faster probe since it needs only /health
	lat = await _probe_llamacpp(client, peer.url)
	if lat is not None:
		model = await _detect_model_llamacpp(client, peer.url, peer.model or fallback_model)
		return PeerState(
			url=peer.url, model=model, server_type="llamacpp",
			online=True, latency_ms=lat, is_vps_local=peer.is_vps_local,
		)

	# Try Ollama
	ollama_result = await _probe_ollama(client, peer.url)
	if ollama_result is not None:
		lat, model_name = ollama_result
		return PeerState(
			url=peer.url, model=model_name or peer.model or fallback_model,
			server_type="ollama", online=True, latency_ms=lat,
			is_vps_local=peer.is_vps_local,
		)

	# Unreachable
	return PeerState(
		url=peer.url, model=peer.model, server_type=peer.server_type,
		online=False, latency_ms=float("inf"), is_vps_local=peer.is_vps_local,
	)


# --------------------------------------------------------------------------- #
#  Selection policy                                                            #
# --------------------------------------------------------------------------- #

def _select_best(probed: list[PeerState]) -> Optional[PeerState]:
	"""
	Choose the best peer from the probed list.

	Rules:
	1. Must be online.
	2. External (non-VPS) peers are preferred when their latency is within
	   _EXT_PREFERENCE_FACTOR of the best VPS latency.  A Tailscale Mac that
	   replies within 20 % of the VPS container wins because it has far more
	   compute (GPU, more cores) — the extra 5 ms round-trip is recouped in
	   token-generation speed.
	3. Tie-break: lowest latency.
	"""
	online = [p for p in probed if p.online]
	if not online:
		return None

	vps = [p for p in online if p.is_vps_local]
	ext = [p for p in online if not p.is_vps_local]

	if not ext:
		return min(vps, key=lambda p: p.latency_ms)

	best_ext = min(ext, key=lambda p: p.latency_ms)

	if not vps:
		return best_ext

	best_vps = min(vps, key=lambda p: p.latency_ms)

	if best_ext.latency_ms <= best_vps.latency_ms * _EXT_PREFERENCE_FACTOR:
		return best_ext

	return best_vps


# --------------------------------------------------------------------------- #
#  Probe loop                                                                  #
# --------------------------------------------------------------------------- #

async def _probe_all() -> None:
	"""Probe every known peer concurrently and update the active endpoint."""
	global _active

	if not _peers:
		return

	from app.config import settings  # deferred — avoids circular import at module load

	async with httpx.AsyncClient() as client:
		tasks = [_probe_peer(client, p, settings.LLM_MODEL_LOCAL) for p in _peers]
		results = await asyncio.gather(*tasks, return_exceptions=True)

	probed: list[PeerState] = [r for r in results if isinstance(r, PeerState)]

	# Replace the shared list in-place so callers that hold a reference see fresh data
	_peers.clear()
	_peers.extend(probed)

	best = _select_best(probed)

	async with _lock:
		prev = _active
		_active = best

	if best:
		if prev is None or prev.url != best.url:
			logger.info(
				"LLM peer: active → %s  [%s | %s | %.0f ms]",
				best.url, best.server_type, best.model, best.latency_ms,
			)
	else:
		if prev is not None and prev.online:
			logger.warning(
				"LLM peer: all endpoints offline — requests will fail until a peer recovers."
			)


def _build_peer_list() -> list[PeerState]:
	"""Build the initial peer list from config at startup."""
	from app.config import settings

	peers: list[PeerState] = []
	seen: set[str] = set()

	# Always include the VPS Docker container as the guaranteed fallback
	vps_url = settings.LLM_LOCAL_URL.rstrip("/")
	peers.append(PeerState(url=vps_url, model=settings.LLM_MODEL_LOCAL, is_vps_local=True))
	seen.add(vps_url)

	# External candidates from LLM_PEER_CANDIDATES (comma-separated base URLs)
	candidates_raw = getattr(settings, "LLM_PEER_CANDIDATES", "")
	for raw in candidates_raw.split(","):
		raw = raw.strip()
		if not raw:
			continue
		if not raw.startswith("http"):
			raw = f"http://{raw}"
		url = raw.rstrip("/")
		if url not in seen:
			peers.append(PeerState(url=url, is_vps_local=False))
			seen.add(url)

	return peers


# --------------------------------------------------------------------------- #
#  Public API                                                                  #
# --------------------------------------------------------------------------- #

async def start_discovery_loop() -> None:
	"""
	Start the background peer probe loop.

	Called once from main.py lifespan.  Safe to call multiple times (idempotent).
	Runs an initial probe synchronously before yielding so that the first
	inference request after startup already has a valid active endpoint.
	"""
	global _started, _peers

	if _started:
		return
	_started = True

	_peers[:] = _build_peer_list()

	n_ext = sum(1 for p in _peers if not p.is_vps_local)
	if n_ext == 0:
		logger.info(
			"LLM peer discovery: no external candidates configured "
			"(LLM_PEER_CANDIDATES empty). Using VPS local only. "
			"Set LLM_PEER_CANDIDATES=http://<tailscale-ip>:<port> to add peers."
		)
	else:
		logger.info(
			"LLM peer discovery: starting — %d candidate(s): %s",
			len(_peers), [p.url for p in _peers],
		)

	# Initial synchronous probe so _active is set before first request
	await _probe_all()

	# Background loop
	async def _loop() -> None:
		while True:
			await asyncio.sleep(_PROBE_INTERVAL_S)
			try:
				await _probe_all()
			except Exception as exc:
				logger.warning("LLM peer probe error: %s", exc)

	asyncio.create_task(_loop())


def get_active_local_endpoint() -> tuple[str, str]:
	"""
	Return (base_url, model_name) for the current best local inference endpoint.

	Called on every request from select_tier() in llm.py.  The returned URL
	points to whichever peer (Tailscale Mac, local container, etc.) is currently
	the fastest and online.  Falls back to settings values if the registry has
	not yet initialised or all peers are offline.
	"""
	from app.config import settings

	if _active and _active.online:
		return _active.url, _active.model or settings.LLM_MODEL_LOCAL

	return settings.LLM_LOCAL_URL, settings.LLM_MODEL_LOCAL


def get_peer_status() -> dict:
	"""Return a serialisable snapshot of peer states for the dashboard."""
	return {
		"active": (
			{
				"url": _active.url,
				"model": _active.model,
				"server_type": _active.server_type,
				"latency_ms": round(_active.latency_ms, 1),
				"is_vps_local": _active.is_vps_local,
			}
			if _active and _active.online
			else None
		),
		"candidates": [
			{
				"url": p.url,
				"model": p.model,
				"server_type": p.server_type,
				"online": p.online,
				"latency_ms": round(p.latency_ms, 1) if p.online else None,
				"is_vps_local": p.is_vps_local,
			}
			for p in _peers
		],
	}
