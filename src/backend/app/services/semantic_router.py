"""Semantic crew router — cosine similarity over all-MiniLM-L6-v2 profile vectors.

Replaces keyword-Jaccard crew selection.  The embedder is shared with
services/memory.py via get_embedder() — no second model instance is loaded.
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
	from app.services.crews import CrewConfig

logger = logging.getLogger(__name__)


def _sanitize_for_log(text: str, max_len: int = 80) -> str:
	"""Strip newlines from user-controlled text before writing to logs (CWE-117)."""
	return str(text)[:max_len].replace('\n', '\\n').replace('\r', '\\r')

# ---------------------------------------------------------------------------
# Config path resolution — tries /app/config.yaml (Docker), then repo root
# ---------------------------------------------------------------------------
_DOCKER_CONFIG = Path("/app/config.yaml")
try:
	_REPO_CONFIG = Path(__file__).parents[4] / "config.yaml"
except IndexError:
	_REPO_CONFIG = Path("config.yaml")

_CONFIG_PATH = _DOCKER_CONFIG if _DOCKER_CONFIG.exists() else _REPO_CONFIG

_ROUTING_CFG: Optional[dict] = None


def _load_routing_config() -> dict:
	"""Load routing thresholds from config.yaml routing: block, falling back to defaults."""
	defaults: dict = {
		"t_match": 0.35,
		"t_opt_in": 0.33,
		"gap": 0.06,
		"max_crews": 3,
		"cont_bias": 0.05,
		"debate_gap": 0.06,
	}
	try:
		import yaml
		with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
			cfg = yaml.safe_load(f)
		if isinstance(cfg, dict) and isinstance(cfg.get("routing"), dict):
			r = cfg["routing"]
			return {k: r.get(k, v) for k, v in defaults.items()}
	except Exception as _e:
		logger.debug("semantic_router: could not load config.yaml routing block: %s", _e)
	return defaults


def get_routing_config() -> dict:
	"""Return routing config, always re-reading from disk for hot-reload support."""
	return _load_routing_config()


def invalidate_routing_config() -> None:
	"""Force re-read of config.yaml on the next get_routing_config() call."""
	global _ROUTING_CFG
	_ROUTING_CFG = None


# ---------------------------------------------------------------------------
# Crew profile text builder
# ---------------------------------------------------------------------------

def build_crew_profile(cfg: "CrewConfig") -> str:
	"""Build a ~500-char text profile from a crew's identity fields.

	Format: name + description + character names/roles + first 300 chars of
	instructions.  No example prompts, agent-rules, or LLM output — pure
	declarative identity surface for embedding.
	"""
	parts = [cfg.name, cfg.description or ""]
	if cfg.characters:
		char_parts: list[str] = []
		for ch in cfg.characters:
			n = (ch.get("name") or "").strip()
			r = (ch.get("role") or "").strip()
			if n and r:
				char_parts.append(f"{n}: {r}")
			elif n:
				char_parts.append(n)
		if char_parts:
			parts.append("Characters: " + "; ".join(char_parts))
	if getattr(cfg, "instructions", None):
		parts.append(str(cfg.instructions).strip()[:300])
	profile = ". ".join(p.strip() for p in parts if p.strip())
	return profile[:500]


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
	"""Cosine similarity between two 1-D float arrays."""
	denom = float(np.linalg.norm(a)) * float(np.linalg.norm(b))
	if denom == 0.0:
		return 0.0
	return float(np.dot(a, b) / denom)


# ---------------------------------------------------------------------------
# Follow-up signal heuristic (parity with crews._FOLLOWUP_SIGNALS)
# ---------------------------------------------------------------------------

_FOLLOWUP_TOKENS: frozenset = frozenset([
	"it", "this", "that", "them", "those", "these",
	"again", "redo",
	"instead",
	"now", "next", "then",
	"continue", "proceed", "more",
	"ok", "okay", "sure", "fine", "great",
])


def _has_followup_signal(text: str) -> bool:
	"""Return True when the text contains referential continuation language."""
	tokens: set[str] = set()
	for w in text[:500].lower().split():
		i, j = 0, len(w)
		while i < j and not w[i].isalnum():
			i += 1
		while j > i and not w[j - 1].isalnum():
			j -= 1
		if i < j:
			tokens.add(w[i:j])
	return bool(tokens & _FOLLOWUP_TOKENS)


# ---------------------------------------------------------------------------
# Main semantic routing function
# ---------------------------------------------------------------------------

async def route_semantic(
	message: str,
	history: list,
	channel: Optional[str],
	*,
	think_mode: bool = False,
	lang: str = "en",
) -> list[str]:
	"""Semantic crew router — returns ordered list of crew IDs (primary first).

	An empty list means Z handles the message directly without crew involvement.

	Args:
		message:    Incoming user message (may include '/think ' prefix).
		history:    Rolling conversation history list.
		channel:    Channel identifier ("telegram", "dashboard", "whatsapp").
		            Pass None to scan all channels for continuity state.
		think_mode: When True, use relaxed thresholds (T_MATCH 0.50, T_OPT_IN
		            0.45, MAX_CREWS unlimited).  Callers must disable ACTION tags.
		lang:       User's configured locale — accepted for API compat, unused
		            for routing (embeddings are language-agnostic).
	"""
	# Detect /think prefix — overrides think_mode if present.
	_msg = message
	if _msg.strip().lower().startswith("/think"):
		_msg = re.sub(r"^/think\s*", "", _msg, flags=re.IGNORECASE).strip()
		think_mode = True

	from app.services.crews import (
		crew_registry,
		_SYSTEM_ACTION_RE,
		_OPERATIONAL_QUERY_RE,
		get_active_crew_session,
		_last_attributed_crew,
	)
	from app.services.memory import get_embedder

	await crew_registry.reload_if_changed()

	profile_vectors: dict[str, np.ndarray] = getattr(crew_registry, "_profile_vectors", {})
	if not profile_vectors:
		logger.warning("semantic_router: no profile vectors — Z-direct (embedder may not be initialised yet)")
		return []

	# ── Guard bypasses ──────────────────────────────────────────────────────
	if _SYSTEM_ACTION_RE.search(message[:500]):
		logger.debug("semantic_router: system action — Z-direct")
		return []
	if _OPERATIONAL_QUERY_RE.search(message[:2000]):
		logger.debug("semantic_router: operational query — Z-direct")
		return []

	# ── Threshold selection ─────────────────────────────────────────────────
	cfg_vals = get_routing_config()
	if think_mode:
		t_match: float = 0.50
		t_opt_in: float = 0.45
		max_crews: int = 0  # 0 = unlimited
	else:
		t_match = float(cfg_vals["t_match"])
		t_opt_in = float(cfg_vals["t_opt_in"])
		max_crews = int(cfg_vals["max_crews"])
	gap = float(cfg_vals["gap"])
	cont_bias = float(cfg_vals.get("cont_bias", 0.05))

	# ── Active routable crews ────────────────────────────────────────────────
	active_crews = [
		c for c in crew_registry.list_active()
		if not getattr(c, "routing_disabled", False)
	]
	if not active_crews:
		return []

	# ── L1: explicit crew ID mention ─────────────────────────────────────────
	lower_msg = _msg.lower()
	for crew in active_crews:
		pattern = r"(?<![a-z0-9])" + re.escape(crew.id.lower()) + r"(?![a-z0-9])"
		if re.search(pattern, lower_msg):
			logger.debug("semantic_router: explicit crew mention '%s'", crew.id)
			return [crew.id]

	# ── L2: embed the incoming message ───────────────────────────────────────
	loop = asyncio.get_event_loop()
	try:
		q_vec: np.ndarray = await loop.run_in_executor(
			None, lambda: np.array(get_embedder().encode(_msg[:1000]))
		)
	except Exception as _e:
		logger.warning("semantic_router: embed failed (%s) — Z-direct", _e)
		return []

	# ── Score each routable crew ─────────────────────────────────────────────
	routable_ids = {c.id for c in active_crews}
	scores: list[tuple[str, float]] = [
		(cid, _cosine(q_vec, vec))
		for cid, vec in profile_vectors.items()
		if cid in routable_ids
	]
	scores.sort(key=lambda x: -x[1])

	if not scores:
		return []

	# ── Continuity bias ──────────────────────────────────────────────────────
	if _has_followup_signal(_msg):
		prev_crew: Optional[str] = None
		if channel:
			prev_crew = get_active_crew_session(channel)
		if not prev_crew:
			# Single-user system — scan all channels for a recent session.
			for _ch in ("telegram", "dashboard", "whatsapp"):
				prev_crew = get_active_crew_session(_ch)
				if prev_crew:
					break
		if not prev_crew:
			prev_crew = _last_attributed_crew(history)
		if prev_crew:
			scores = [
				(cid, s + cont_bias if cid == prev_crew else s)
				for cid, s in scores
			]
			scores.sort(key=lambda x: -x[1])
			logger.debug("semantic_router: continuity bias +%.2f → '%s'", cont_bias, _sanitize_for_log(prev_crew))

	top_id, top_score = scores[0]
	if top_score < t_match:
		logger.warning(
			"semantic_router: score miss — top '%s'=%.3f < T_MATCH=%.2f — Z-direct. All scores: %s",
			top_id, top_score, t_match,
			", ".join(f"{cid}={s:.3f}" for cid, s in scores[:5]),
		)
		return []

	# ── Build panel ──────────────────────────────────────────────────────────
	panel = [top_id]
	primary_cfg = crew_registry.get(top_id)
	exclude = set((primary_cfg.panel_exclude or []) if primary_cfg else [])
	for cid, score in scores[1:]:
		if max_crews > 0 and len(panel) >= max_crews:
			break
		if score < t_opt_in:
			break
		if (top_score - score) > gap:
			break
		if cid in exclude:
			continue
		panel.append(cid)

	logger.info(
		"semantic_router: '%s...' → %s (scores: %s, think=%s)",
		_sanitize_for_log(_msg[:40]),
		panel,
		", ".join(f"{cid}={s:.3f}" for cid, s in scores[:5]),
		think_mode,
	)
	return panel
