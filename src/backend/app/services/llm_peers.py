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
  - Each probe does a lightweight inference call (10-token completion) to
    measure real tokens/s and verify the model is actually responding correctly.
    A peer that passes /health but errors on completions is marked unhealthy.
  - An external peer is only preferred over the VPS when it measures at least
    _SPEED_MIN_RATIO (80 %) of the VPS tokens/s — i.e. the peer must actually
    be competitive. A much slower Tailscale device stays as standby only.
  - Automatic failover: if the active peer goes offline or its speed drops below
    the threshold, the next probe promotes the next-best candidate, no restart.
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

# Per-probe connect+read timeout for health checks (seconds).
_PROBE_TIMEOUT_S = 2.5

# Timeout for the inference speed probe (seconds). Short completion, generous timeout.
_SPEED_PROBE_TIMEOUT_S = 25.0

# Prompt used for speed probing — short enough to complete fast on any hardware.
_SPEED_PROBE_PROMPT = "Reply with exactly: ok"
_SPEED_PROBE_MAX_TOKENS = 10

# Minimum ratio of (external toks/s) / (VPS toks/s) required to prefer the
# external peer. 0.8 = external must be at least 80 % as fast as VPS.
# Set to 0.0 to always prefer external when online regardless of speed.
_SPEED_MIN_RATIO = 0.80


@dataclass
class PeerState:
	url: str						# base URL, no trailing slash
	model: str = ""					# detected or configured model name
	server_type: str = ""			# "llamacpp" | "ollama" | ""
	online: bool = False
	latency_ms: float = float("inf")
	toks_per_sec: float = 0.0		# measured inference speed; 0 = not yet known
	last_error: str = ""			# last inference error message, if any
	is_vps_local: bool = False		# True for the VPS Docker container fallback
	hostname: str = ""				# human-readable device name for the dashboard

# --------------------------------------------------------------------------- #
#  Module-level mutable state                                                 #
# --------------------------------------------------------------------------- #

_peers: list[PeerState] = []
_active: Optional[PeerState] = None
_lock = asyncio.Lock()


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
	except Exception as _e:
		logger.debug("llama.cpp probe failed: %s", _e)
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
	except Exception as _e:
		logger.debug("Ollama probe failed: %s", _e)
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
	except Exception as _e:
		logger.debug("llama.cpp model detect failed: %s", _e)
	return fallback


async def _measure_speed(url: str, server_type: str, model: str) -> tuple[float, str]:
	"""
	Send a minimal completion request and return (toks_per_sec, error_str).

	A non-zero error_str means the peer is reachable but malfunctioning.
	toks_per_sec is 0.0 on any error.
	"""
	try:
		async with httpx.AsyncClient(timeout=_SPEED_PROBE_TIMEOUT_S) as client:
			t0 = time.monotonic()
			if server_type == "ollama":
				payload = {
					"model": model,
					"prompt": _SPEED_PROBE_PROMPT,
					"stream": False,
					"options": {"num_predict": _SPEED_PROBE_MAX_TOKENS},
				}
				resp = await client.post(f"{url}/api/generate", json=payload)
				elapsed = time.monotonic() - t0
				if resp.status_code != 200:
					return 0.0, f"HTTP {resp.status_code}"
				data = resp.json()
				# Ollama reports eval_count (output tokens) and eval_duration (ns)
				n_eval = data.get("eval_count", 0)
				eval_ns = data.get("eval_duration", 0)
				if eval_ns > 0 and n_eval > 0:
					tps = n_eval / (eval_ns / 1e9)
				elif elapsed > 0:
					# Fallback: rough estimate from total tokens / wall time
					resp_text = data.get("response", "")
					n_approx = max(len(resp_text.split()), 1)
					tps = n_approx / elapsed
				else:
					tps = 0.0
				return round(tps, 1), ""
			else:
				# llama.cpp OpenAI-compatible
				payload = {
					"model": model,
					"messages": [{"role": "user", "content": _SPEED_PROBE_PROMPT}],
					"max_tokens": _SPEED_PROBE_MAX_TOKENS,
					"stream": False,
				}
				resp = await client.post(f"{url}/v1/chat/completions", json=payload)
				elapsed = time.monotonic() - t0
				if resp.status_code != 200:
					return 0.0, f"HTTP {resp.status_code}"
				data = resp.json()
				usage = data.get("usage", {})
				n_completion = usage.get("completion_tokens", 0)
				if n_completion > 0 and elapsed > 0:
					tps = n_completion / elapsed
				else:
					tps = 0.0
				return round(tps, 1), ""
	except httpx.TimeoutException:
		return 0.0, "inference timeout"
	except Exception as exc:
		return 0.0, str(exc)[:80]


async def _probe_peer(
	client: httpx.AsyncClient, peer: PeerState, fallback_model: str
) -> PeerState:
	"""Probe a single peer and return an updated PeerState.

	Does a two-phase check:
	1. Lightweight health probe (latency_ms determination).
	2. Real inference probe via _measure_speed — verifies the model is actually
	   responding and captures tokens/s.  A peer that passes health but errors
	   on completions is recorded as online=True with toks_per_sec=0 so it
	   still shows up in the dashboard but is excluded from routing.
	"""
	# Try llama.cpp first — faster probe since it needs only /health
	lat = await _probe_llamacpp(client, peer.url)
	if lat is not None:
		model = await _detect_model_llamacpp(client, peer.url, peer.model or fallback_model)
		tps, err = await _measure_speed(peer.url, "llamacpp", model)
		return PeerState(
			url=peer.url, model=model, server_type="llamacpp",
			online=True, latency_ms=lat,
			toks_per_sec=tps, last_error=err,
			is_vps_local=peer.is_vps_local, hostname=peer.hostname,
		)

	# Try Ollama
	ollama_result = await _probe_ollama(client, peer.url)
	if ollama_result is not None:
		lat, model_name = ollama_result
		model = model_name or peer.model or fallback_model
		tps, err = await _measure_speed(peer.url, "ollama", model)
		return PeerState(
			url=peer.url, model=model, server_type="ollama",
			online=True, latency_ms=lat,
			toks_per_sec=tps, last_error=err,
			is_vps_local=peer.is_vps_local, hostname=peer.hostname,
		)

	# Unreachable
	return PeerState(
		url=peer.url, model=peer.model, server_type=peer.server_type,
		online=False, latency_ms=float("inf"),
		is_vps_local=peer.is_vps_local, hostname=peer.hostname,
	)


# --------------------------------------------------------------------------- #
#  Selection policy                                                            #
# --------------------------------------------------------------------------- #

def _select_best(probed: list[PeerState]) -> Optional[PeerState]:
	"""
	Choose the best peer from the probed list.

	Rules:
	1. Must be online.
	2. An external (non-VPS) peer is only preferred when its measured tokens/s
	   is at least _SPEED_MIN_RATIO of the VPS tokens/s — ensuring we only route
	   away when the Tailscale device is actually faster or comparable.
	3. If VPS tokens/s is unknown (just started, or inference probe not yet done),
	   fall back to preferring external if it has a measured speed.
	4. Fall back to VPS when no external peer meets the threshold.
	5. If VPS is also offline, use the best-available external peer.
	"""
	online = [p for p in probed if p.online]
	if not online:
		return None

	vps = next((p for p in online if p.is_vps_local), None)
	ext = [p for p in online if not p.is_vps_local and p.toks_per_sec > 0]

	if ext and vps:
		vps_tps = vps.toks_per_sec
		if vps_tps > 0:
			# Only prefer external if it meets the speed threshold
			threshold = vps_tps * _SPEED_MIN_RATIO
			fast_ext = [p for p in ext if p.toks_per_sec >= threshold]
			if fast_ext:
				best = max(fast_ext, key=lambda p: p.toks_per_sec)
				logger.debug(
					"LLM peer: external %s qualifies (%.1f tok/s ≥ %.1f×%.2f VPS tok/s)",
					best.hostname, best.toks_per_sec, vps_tps, _SPEED_MIN_RATIO,
				)
				return best
			# No external meets threshold — keep VPS
			logger.debug(
				"LLM peer: external(s) too slow (best %.1f tok/s < %.1f threshold), staying on VPS",
				max(p.toks_per_sec for p in ext), threshold,
			)
			return vps
		else:
			# VPS speed not yet measured — prefer external if it has a known speed
			return max(ext, key=lambda p: p.toks_per_sec)

	if ext:
		# No VPS available — use best external
		return max(ext, key=lambda p: p.toks_per_sec)

	return vps


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
				"LLM peer: active → %s  [%s | %s | %.0f ms | %.1f tok/s]",
				best.url, best.server_type, best.model, best.latency_ms, best.toks_per_sec,
			)
	else:
		if prev is not None and prev.online:
			logger.warning(
				"LLM peer: all endpoints offline — requests will fail until a peer recovers."
			)


def _build_peer_list() -> list[PeerState]:
	"""Build the initial peer list from config at startup.

	Supports an optional display-name fragment appended to the URL:
	  LLM_PEER_CANDIDATES=http://100.x.y.z:11434#MacBook
	The fragment (#MacBook) becomes the hostname shown in the dashboard.
	If omitted, the IP address is used as the display name.
	"""
	from app.config import settings
	from urllib.parse import urlparse

	peers: list[PeerState] = []
	seen: set[str] = set()

	# Always include the VPS Docker container as the guaranteed fallback
	vps_url = settings.LLM_LOCAL_URL.rstrip("/")
	peers.append(PeerState(url=vps_url, model=settings.LLM_MODEL_LOCAL, is_vps_local=True, hostname="VPS"))
	seen.add(vps_url)

	# External candidates from LLM_PEER_CANDIDATES (comma-separated base URLs)
	candidates_raw = getattr(settings, "LLM_PEER_CANDIDATES", "")
	for raw in candidates_raw.split(","):
		raw = raw.strip()
		if not raw:
			continue
		if not raw.startswith("http"):
			raw = f"http://{raw}"
		# Extract optional display-name from URL fragment: http://ip:port#MacBook
		hostname_hint = ""
		if "#" in raw:
			raw, hostname_hint = raw.rsplit("#", 1)
			hostname_hint = hostname_hint.strip()
		url = raw.rstrip("/")
		if not hostname_hint:
			hostname_hint = urlparse(url).hostname or url
		if url not in seen:
			peers.append(PeerState(url=url, is_vps_local=False, hostname=hostname_hint))
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
	if getattr(start_discovery_loop, '_started', False):
		return
	start_discovery_loop._started = True

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
				"toks_per_sec": _active.toks_per_sec,
				"last_error": _active.last_error,
				"hostname": _active.hostname,
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
				"toks_per_sec": p.toks_per_sec,
				"last_error": p.last_error,
				"hostname": p.hostname,
				"is_vps_local": p.is_vps_local,
			}
			for p in _peers
		],
	}
