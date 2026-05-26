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
	"""Build a ~2000-char text profile from a crew's identity fields.

	Format: name + description + keywords + character names/roles + first 1000 chars of
	instructions.  No example prompts, agent-rules, or LLM output — pure
	declarative identity surface for embedding.
	"""
	parts = [cfg.name, cfg.description or ""]
	if cfg.keywords:
		parts.append("Keywords: " + ", ".join(cfg.keywords))
	if cfg.keywords_i18n:
		for lang, kws in cfg.keywords_i18n.items():
			parts.append(f"Keywords ({lang}): " + ", ".join(kws))
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
		parts.append(str(cfg.instructions).strip()[:1000])
	profile = ". ".join(p.strip() for p in parts if p.strip())
	return profile[:2000]



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

	await crew_registry.reload_if_changed()

	# ── Guard bypasses ──────────────────────────────────────────────────────
	if _SYSTEM_ACTION_RE.search(message[:500]):
		logger.debug("semantic_router: system action — Z-direct")
		return []
	if _OPERATIONAL_QUERY_RE.search(message[:2000]):
		logger.debug("semantic_router: operational query — Z-direct")
		return []

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

	routable_ids = {c.id for c in active_crews}

	# ── L2: Primary Cloud LLM Routing ────────────────────────────────────────
	logger.info("semantic_router: evaluating user intent using primary Cloud LLM router")
	try:
		from app.services.llm import chat as cloud_chat
		
		# Build a detailed, clean crew manifest
		crew_manifest = []
		for crew in active_crews:
			kws = ", ".join(crew.keywords or [])
			crew_manifest.append(f"- ID: {crew.id}\n  Name: {crew.name}\n  Description: {crew.description}\n  Keywords: {kws}")
		
		crews_list_str = "\n\n".join(crew_manifest)
		
		routing_prompt = (
			f"User Message: \"{_msg[:1000]}\"\n\n"
			f"Available Expert Crews:\n{crews_list_str}\n\n"
			"Your task is to determine if this message should be handled by one or more specialized expert crews. "
			"Reply with a comma-separated list of the expert crew IDs that are highly relevant to answering the user's message. "
			"Choose at most 3 crews. Order them with the most important crew first. "
			"If the message is purely general conversation (greetings, simple thanks, small talk) and does not touch any of the specialized crew domains, reply with 'NO'."
		)
		
		# Execute the routing decision on cloud LLM with a 5.0 second timeout
		decision = await asyncio.wait_for(
			cloud_chat(
				routing_prompt,
				tier="cloud",
				system_override="You are openZero's master router. Analyze the user's query and return a comma-separated list of relevant crew IDs, or 'NO'."
			),
			timeout=5.0
		)
		
		decision = decision.strip()
		logger.info("semantic_router: cloud routing moderator returned '%s'", decision[:50])
		
		if not (decision.upper().startswith("NO") or decision.upper().startswith("'NO")):
			raw_list = re.split(r'[,|]', decision)
			selected = [re.sub(r'[^a-z0-9_]', '', c.strip().lower()) for c in raw_list]
			selected = [c for c in selected if c]
			valid_selected = [c for c in selected if c in routable_ids]
			
			if valid_selected:
				logger.info("semantic_router: cloud routing success → %s", valid_selected)
				return valid_selected
		else:
			logger.info("semantic_router: cloud router decided 'NO' (Z-direct)")
			return []
			
	except Exception as _e:
		logger.warning("semantic_router: primary cloud router failed/timed out (%s) — falling back to local similarity check", _e)

	# ── L3: Local Embedding Fallback ──────────────────────────────────────────
	logger.info("semantic_router: executing local embedding fallback check")
	from app.services.memory import get_embedder
	profile_vectors: dict[str, np.ndarray] = getattr(crew_registry, "_profile_vectors", {})
	if not profile_vectors:
		logger.warning("semantic_router: no profile vectors — skipping local embedding check")
		scores = []
	else:
		loop = asyncio.get_event_loop()
		try:
			q_vec: np.ndarray = await loop.run_in_executor(
				None, lambda: np.array(get_embedder().encode(_msg[:1000]))
			)
			scores = [
				(cid, _cosine(q_vec, vec))
				for cid, vec in profile_vectors.items()
				if cid in routable_ids
			]
			scores.sort(key=lambda x: -x[1])
		except Exception as _e:
			logger.warning("semantic_router: local embed fallback failed (%s)", _e)
			scores = []

	# ── Threshold selection for local embedding ──────────────────────────────
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

	# ── Continuity bias ──────────────────────────────────────────────────────
	if scores and _has_followup_signal(_msg):
		prev_crew: Optional[str] = None
		if channel:
			prev_crew = get_active_crew_session(channel)
		if not prev_crew:
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

	if scores:
		top_id, top_score = scores[0]
		if top_score >= t_match:
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
				"semantic_router: local embedding success '%s...' → %s (scores: %s)",
				_sanitize_for_log(_msg[:40]),
				panel,
				", ".join(f"{cid}={s:.3f}" for cid, s in scores[:5]),
			)
			return panel

		logger.warning(
			"semantic_router: local embedding miss — top '%s'=%.3f < T_MATCH=%.2f. Falling back to local keyword sweep.",
			top_id, top_score, t_match
		)

	# ── L4: Local Keyword Fallback ────────────────────────────────────────────
	logger.info("semantic_router: executing local prefix-bounded keyword sweep fallback")
	fallback_scores: list[tuple[str, int]] = []
	for crew in active_crews:
		kws = set()
		if crew.keywords:
			for k in crew.keywords:
				kws.add(str(k).lower())
		if crew.keywords_i18n:
			for lang_kws in crew.keywords_i18n.values():
				for k in lang_kws:
					kws.add(str(k).lower())
		
		match_count = 0
		matched_kws = []
		for kw in kws:
			if re.search(r"(?<![a-zA-Z])" + re.escape(kw), lower_msg):
				match_count += 1
				matched_kws.append(kw)
		
		if match_count > 0:
			fallback_scores.append((crew.id, match_count))
			logger.debug("semantic_router local fallback: crew '%s' matched keywords: %s", crew.id, matched_kws)

	if fallback_scores:
		semantic_score_map = {cid: s for cid, s in scores} if scores else {}
		fallback_scores.sort(key=lambda x: (-x[1], -semantic_score_map.get(x[0], 0.0)))
		fallback_panel = [cid for cid, _ in fallback_scores]
		logger.info(
			"semantic_router: local keyword fallback success → %s (matches: %s)",
			fallback_panel,
			", ".join(f"{cid}={count}" for cid, count in fallback_scores),
		)
		return fallback_panel

	logger.warning("semantic_router: all routing layers missed. Routing to Z-direct.")
	return []
