"""Three-stage phantom-confirmation detector.

Stage A (always-on, ~50 µs): fast regex pre-filter via shared PHANTOM_RE.
Stage B (~500 µs): embedding-based similarity check against synthetic prototypes
                   via the existing Qdrant infra. Catches paraphrases the regex misses.
Stage C (opt-in, async, never blocks delivery): cloud LLM classifier for ambiguous cases.
                   Controlled by PHANTOM_ASYNC_CLASSIFIER in config. Ships disabled.

Hard rule: stages A+B must add < 1 ms to the response path P95. Stage C is fire-and-forget.

Usage::

	from app.services.phantom_detector import detect_phantom

	result = await detect_phantom(reply, executed_cmds)
	# result.is_phantom — True / False
	# result.confidence — 0.0..1.0
	# result.stage — "A" | "B" | "none"
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.common.phantom import PHANTOM_RE, _MAX_PHANTOM_SCAN

logger = logging.getLogger(__name__)

# Stage B cosine threshold — above this we call it a phantom.
_STAGE_B_THRESHOLD = 0.82


@dataclass
class PhantomResult:
	is_phantom: bool
	confidence: float
	stage: str		# "A" | "B" | "none"


async def detect_phantom(reply: str, executed_cmds: list) -> PhantomResult:
	"""Run Stage A then Stage B. Stage C fires async if configured, never blocks."""
	# If actions actually executed, this is NOT a phantom by definition.
	if executed_cmds:
		return PhantomResult(is_phantom=False, confidence=0.0, stage="none")

	text = reply[:_MAX_PHANTOM_SCAN]

	# ── Stage A — regex (fast, always-on) ────────────────────────────────────
	if PHANTOM_RE.search(text):
		logger.debug("PhantomDetector Stage A: match")
		_maybe_fire_stage_c(reply)
		return PhantomResult(is_phantom=True, confidence=0.95, stage="A")

	# ── Stage B — embedding similarity (local, ~500µs) ─────────────────────
	try:
		score = await _stage_b_score(text)
		if score >= _STAGE_B_THRESHOLD:
			logger.debug("PhantomDetector Stage B: score=%.3f >= threshold", score)
			_maybe_fire_stage_c(reply)
			return PhantomResult(is_phantom=True, confidence=score, stage="B")
	except Exception as _e:
		logger.debug("PhantomDetector Stage B failed: %s — skipping", _e)

	return PhantomResult(is_phantom=False, confidence=0.0, stage="none")


async def _stage_b_score(text: str) -> float:
	"""Return max cosine similarity between text and phantom prototypes via Qdrant."""
	try:
		from app.config import settings
		from qdrant_client import AsyncQdrantClient
		from qdrant_client.models import NamedVector
		import httpx

		# Embed via the llama.cpp local server (same endpoint used for memory).
		# Short timeout — if embedding is slow, skip gracefully.
		async with httpx.AsyncClient(timeout=0.8) as client:
			resp = await client.post(
				f"{settings.LLM_LOCAL_URL}/embedding",
				json={"content": text[:500]},
			)
			resp.raise_for_status()
			vector = resp.json().get("embedding") or resp.json().get("data", [{}])[0].get("embedding")

		if not vector:
			return 0.0

		qc = AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT, api_key=settings.QDRANT_API_KEY or None)
		hits = await qc.search(
			collection_name="phantom_prototypes",
			query_vector=vector,
			limit=1,
			score_threshold=0.5,
		)
		await qc.close()
		return hits[0].score if hits else 0.0
	except Exception as _e:
		logger.debug("Stage B embedding/search failed: %s", _e)
		return 0.0


def _maybe_fire_stage_c(reply: str) -> None:
	"""Fire async Stage C classifier if PHANTOM_ASYNC_CLASSIFIER enabled. Never blocks delivery."""
	try:
		from app.config import settings
		if not settings.PHANTOM_ASYNC_CLASSIFIER:
			return
		import asyncio
		asyncio.create_task(_stage_c_async(reply), name="phantom_stage_c")
	except Exception as _e:
		logger.debug("Stage C dispatch failed: %s", _e)


async def _stage_c_async(reply: str) -> None:
	"""Async cloud classifier for phantom detection. Result is logged only — never gates delivery.

	Builds the phantom prototype corpus over time (aggregate counts, never raw text).
	"""
	try:
		from app.services.llm import chat as _chat
		prompt = (
			"Does the following AI assistant reply CLAIM to have performed an action "
			"(saved, created, added, moved, etc.) without presenting any evidence or receipt? "
			"Answer YES or NO only.\n\n"
			f"Reply: {reply[:600]}"
		)
		result = await _chat(prompt, tier="cloud")
		is_phantom_c = result.strip().upper().startswith("YES")
		logger.info("PhantomDetector Stage C (async): is_phantom=%s", is_phantom_c)
		# Record aggregate metric only — no user text stored.
		if is_phantom_c:
			try:
				from app.services.metrics import increment_counter
				increment_counter("phantom_stage_c_confirmed_total")
			except Exception:
				pass
	except Exception as _e:
		logger.debug("Stage C classifier failed: %s", _e)
