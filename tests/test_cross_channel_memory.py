"""
Cross-channel memory continuity regression test.
Guards the core openZero invariant: a fact stored via one channel
must be retrievable via any other channel.

This is the Phase 2 CI gate per docs/artifacts/refocus_plan.md section 16.

Channels exercised:
  Dashboard -> Telegram
  Telegram  -> Dashboard
  WhatsApp  -> Telegram
  Dashboard -> WhatsApp

Mocking strategy
----------------
- ``app.services.memory.get_qdrant`` is replaced with ``_InMemoryQdrant``,
  a pure-Python substitute that tracks upserted points in a plain dict
  and computes cosine similarity in pure Python.  No live Qdrant required.
- ``app.services.memory.encode_async`` is replaced with an AsyncMock that
  calls ``_text_to_vector``: a deterministic, SHA-256-based function that
  maps any string to a normalised 384-dim vector.  Identical text always
  produces the identical vector (score = 1.0); distinct UUID-based facts
  produce near-orthogonal vectors (score << 0.92), preventing false dedup.
- No HTTP calls are made.  No LLM is invoked.
- ``app.config`` is stubbed before the memory module is imported so the
  test can run without a live database or environment file.
"""

from __future__ import annotations

import hashlib
import math
import os
import sys
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap — backend must be on sys.path for static imports
# ---------------------------------------------------------------------------

_BACKEND_SRC = os.path.abspath(
	os.path.join(os.path.dirname(__file__), "..", "src", "backend")
)
if _BACKEND_SRC not in sys.path:
	sys.path.insert(0, _BACKEND_SRC)

# ---------------------------------------------------------------------------
# Stub out config and heavy external deps before any `from app...` import
# ---------------------------------------------------------------------------

_cfg_stub = MagicMock()
_cfg_stub.settings.QDRANT_HOST = "localhost"
_cfg_stub.settings.QDRANT_PORT = 6333
_cfg_stub.settings.QDRANT_API_KEY = ""
_cfg_stub.settings.MEMORY_MIN_SCORE = 0.72

for _mod in ("app.config",):
	if _mod not in sys.modules:
		sys.modules[_mod] = _cfg_stub

if "app.config" in sys.modules:
	sys.modules["app.config"].settings = _cfg_stub.settings

# Now it is safe to import the memory service.
from app.services.memory import (  # noqa: E402 — must follow stub setup
	delete_memory,
	semantic_search,
	semantic_search_raw,
	store_memory,
)

# ---------------------------------------------------------------------------
# Pure-Python in-memory Qdrant substitute
# ---------------------------------------------------------------------------

_VECTOR_DIM = 384


def _text_to_vector(text: str) -> list[float]:
	"""Return a deterministic, normalised 384-dim vector derived from *text*.

	Algorithm:
	  1. Repeatedly SHA-256-hash the input to generate raw bytes.
	  2. Map each byte (0-255) to a float in [-1.0, ~0.998] via ``(b - 127.5) / 127.5``.
	     This avoids NaN/Inf that ``struct.unpack("d", ...)`` can produce when
	     SHA-256 bytes happen to form IEEE-754 exponent-all-ones patterns.
	  3. L2-normalise the result so cosine similarity = dot product.

	Two calls with the same text always return the same vector (score = 1.0).
	Two calls with different UUID-based texts return near-orthogonal vectors
	(score << 0.92), so the semantic dedup check in ``store_memory`` never
	mistakes distinct test facts for duplicates.
	"""
	raw: list[float] = []
	seed = hashlib.sha256(text.encode()).digest()
	while len(raw) < _VECTOR_DIM:
		seed = hashlib.sha256(seed).digest()
		raw.extend((b - 127.5) / 127.5 for b in seed)
	vec = raw[:_VECTOR_DIM]
	magnitude = math.sqrt(sum(x * x for x in vec))
	if magnitude == 0.0:
		magnitude = 1.0
	return [x / magnitude for x in vec]


async def _encode_async_stub(text: str) -> list[float]:
	"""Async wrapper around ``_text_to_vector`` for use as an AsyncMock side_effect."""
	return _text_to_vector(text)


def _cosine_sim(v1: list[float], v2: list[float]) -> float:
	"""Cosine similarity of two pre-normalised vectors (= dot product)."""
	return sum(a * b for a, b in zip(v1, v2))


# --- Lightweight result types that mirror the qdrant_client API surface ---

class _ScoredPoint:
	__slots__ = ("id", "payload", "score")

	def __init__(self, pid: Any, payload: dict, score: float) -> None:
		self.id = pid
		self.payload = payload
		self.score = score


class _QueryResponse:
	__slots__ = ("points",)

	def __init__(self, points: list[_ScoredPoint]) -> None:
		self.points = points


class _CountResult:
	__slots__ = ("count",)

	def __init__(self, count: int) -> None:
		self.count = count


class _CollectionItem:
	__slots__ = ("name",)

	def __init__(self, name: str) -> None:
		self.name = name


class _CollectionsResponse:
	__slots__ = ("collections",)

	def __init__(self, names: list[str]) -> None:
		self.collections = [_CollectionItem(n) for n in names]


class _InMemoryQdrant:
	"""Drop-in replacement for ``qdrant_client.QdrantClient`` using a plain dict.

	All methods are synchronous (QdrantClient uses blocking I/O), matching the
	production code's usage pattern.
	"""

	def __init__(self) -> None:
		self._points: dict[str, dict] = {}	# id -> {collection, vector, payload}

	# ---- Collection management (no-ops; always treat collection as existing) ---

	def get_collections(self) -> _CollectionsResponse:
		names = list({p["collection"] for p in self._points.values()})
		return _CollectionsResponse(names)

	def create_collection(self, collection_name: str, **_kwargs: Any) -> None:
		pass  # collection is auto-created on first upsert

	# ---- Write ---------------------------------------------------------------

	def upsert(self, collection_name: str, points: list) -> None:
		for pt in points:
			self._points[str(pt.id)] = {
				"collection": collection_name,
				"vector": list(pt.vector),
				"payload": dict(pt.payload),
			}

	def delete(self, collection_name: str, points_selector: Any) -> None:
		for pid in points_selector.points:
			self._points.pop(str(pid), None)

	# ---- Read ----------------------------------------------------------------

	def count(self, collection_name: str, exact: bool = True) -> _CountResult:
		n = sum(1 for p in self._points.values() if p["collection"] == collection_name)
		return _CountResult(n)

	def query_points(
		self,
		collection_name: str,
		query: list[float],
		limit: int,
		score_threshold: float = 0.0,
	) -> _QueryResponse:
		scored: list[_ScoredPoint] = []
		for pid, p in self._points.items():
			if p["collection"] != collection_name:
				continue
			score = _cosine_sim(query, p["vector"])
			if score >= score_threshold:
				scored.append(_ScoredPoint(pid, p["payload"], score))
		scored.sort(key=lambda x: x.score, reverse=True)
		return _QueryResponse(scored[:limit])

	# ---- Introspection (test helpers) ----------------------------------------

	def point_count(self, collection_name: str = "personal_memory") -> int:
		return self.count(collection_name).count


# ---------------------------------------------------------------------------
# Shared pytest fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_memory():
	"""Yield a fresh _InMemoryQdrant wired into the memory service.

	``get_qdrant`` is patched to always return the *same* store instance so
	every call inside a single test (dedup lookup, upsert, search) sees the
	same state.  The store is discarded after each test, giving full isolation.
	"""
	store = _InMemoryQdrant()
	encode_mock = AsyncMock(side_effect=_encode_async_stub)

	with (
		patch("app.services.memory.get_qdrant", return_value=store),
		patch("app.services.memory.encode_async", encode_mock),
	):
		yield store


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _store_and_verify_not_present(fact: str) -> None:
	"""Sanity guard: the fact must NOT be in memory before we store it."""
	result = await semantic_search(fact)
	assert fact not in result, (
		f"Fact already present before test store — UUID collision or dirty state: {result!r}"
	)


async def _find_point_id(fact: str) -> str | None:
	"""Return the Qdrant point id of the first memory that contains *fact*."""
	raw = await semantic_search_raw(fact)
	for item in raw:
		if fact in item.get("text", ""):
			return item["id"]
	return None


# ---------------------------------------------------------------------------
# Test classes (one per channel direction)
# ---------------------------------------------------------------------------


class TestDashboardToTelegram:
	"""Fact stored via the dashboard channel is recalled by the Telegram retrieval path.

	Both channels call the same ``store_memory`` / ``semantic_search`` service
	functions; the test confirms the shared collection bridges the two.
	"""

	@pytest.mark.anyio
	async def test_fact_crosses_from_dashboard_to_telegram(self, mock_memory: _InMemoryQdrant) -> None:
		fact = f"The test canary value is {uuid.uuid4().hex}"

		# Dashboard path: the message bus writes a distilled fact to Qdrant.
		await store_memory(fact, metadata={"channel": "dashboard"})

		assert mock_memory.point_count() == 1, "store_memory did not write to the in-memory store"

		# Telegram path: the context builder calls semantic_search() to inject
		# relevant memories into the LLM prompt.  Query with the exact fact text
		# so the deterministic vector produces cosine sim = 1.0 >= threshold 0.72.
		result = await semantic_search(fact)

		assert fact in result, (
			f"Dashboard-stored fact not found via Telegram retrieval path.\n"
			f"search result: {result!r}"
		)

		# Cleanup: purge the test point from Qdrant (tests the delete path too).
		point_id = await _find_point_id(fact)
		assert point_id is not None, "Could not locate test memory point for cleanup"
		await delete_memory(point_id)
		assert mock_memory.point_count() == 0, "delete_memory did not remove the test point"


class TestTelegramToDashboard:
	"""Fact stored via the Telegram channel is recalled by the dashboard retrieval path."""

	@pytest.mark.anyio
	async def test_fact_crosses_from_telegram_to_dashboard(self, mock_memory: _InMemoryQdrant) -> None:
		fact = f"The test canary value is {uuid.uuid4().hex}"

		# Telegram path: /learn command or bus.commit_reply writes fact to Qdrant.
		await store_memory(fact, metadata={"channel": "telegram"})

		assert mock_memory.point_count() == 1

		# Dashboard path: the dashboard /memory/search endpoint calls
		# semantic_search_raw(); the dashboard chat SSE loop calls semantic_search().
		result = await semantic_search(fact)

		assert fact in result, (
			f"Telegram-stored fact not found via Dashboard retrieval path.\n"
			f"search result: {result!r}"
		)

		point_id = await _find_point_id(fact)
		assert point_id is not None
		await delete_memory(point_id)
		assert mock_memory.point_count() == 0


class TestWhatsAppToTelegram:
	"""Fact stored via the WhatsApp channel is recalled by the Telegram retrieval path."""

	@pytest.mark.anyio
	async def test_fact_crosses_from_whatsapp_to_telegram(self, mock_memory: _InMemoryQdrant) -> None:
		fact = f"The test canary value is {uuid.uuid4().hex}"

		# WhatsApp path: _handle_inbound -> route_message_stream -> bus.commit_reply
		# -> store_memory.  Here we call store_memory directly to isolate the
		# memory layer from the router/LLM.
		await store_memory(fact, metadata={"channel": "whatsapp"})

		assert mock_memory.point_count() == 1

		# Telegram path: retrieval
		result = await semantic_search(fact)

		assert fact in result, (
			f"WhatsApp-stored fact not found via Telegram retrieval path.\n"
			f"search result: {result!r}"
		)

		point_id = await _find_point_id(fact)
		assert point_id is not None
		await delete_memory(point_id)
		assert mock_memory.point_count() == 0


class TestDashboardToWhatsApp:
	"""Fact stored via the dashboard channel is recalled by the WhatsApp retrieval path."""

	@pytest.mark.anyio
	async def test_fact_crosses_from_dashboard_to_whatsapp(self, mock_memory: _InMemoryQdrant) -> None:
		fact = f"The test canary value is {uuid.uuid4().hex}"

		# Dashboard path
		await store_memory(fact, metadata={"channel": "dashboard"})

		assert mock_memory.point_count() == 1

		# WhatsApp path: _handle_inbound calls route_message_stream which injects
		# the Z-core context built from semantic_search().  semantic_search_raw()
		# is also called by the dashboard /memory/search endpoint.
		result = await semantic_search(fact)
		raw = await semantic_search_raw(fact)

		assert fact in result, (
			f"Dashboard-stored fact not found via WhatsApp retrieval path (semantic_search).\n"
			f"search result: {result!r}"
		)
		assert any(fact in item.get("text", "") for item in raw), (
			f"Dashboard-stored fact not found via WhatsApp retrieval path (semantic_search_raw).\n"
			f"raw results: {raw!r}"
		)

		point_id = await _find_point_id(fact)
		assert point_id is not None
		await delete_memory(point_id)
		assert mock_memory.point_count() == 0


# ---------------------------------------------------------------------------
# Bonus: verify isolation between test runs (parallel-safe UUID uniqueness)
# ---------------------------------------------------------------------------


class TestIsolation:
	"""Confirm that distinct UUID facts do not bleed across test instances."""

	@pytest.mark.anyio
	async def test_two_distinct_facts_are_both_stored_and_individually_retrievable(
		self, mock_memory: _InMemoryQdrant
	) -> None:
		fact_a = f"The test canary value is {uuid.uuid4().hex}"
		fact_b = f"The test canary value is {uuid.uuid4().hex}"

		await store_memory(fact_a, metadata={"channel": "dashboard"})
		await store_memory(fact_b, metadata={"channel": "telegram"})

		assert mock_memory.point_count() == 2, (
			"Expected 2 distinct facts in store; dedup may have incorrectly merged them"
		)

		result_a = await semantic_search(fact_a)
		result_b = await semantic_search(fact_b)

		assert fact_a in result_a, f"fact_a not found: {result_a!r}"
		assert fact_b in result_b, f"fact_b not found: {result_b!r}"

		# Cleanup both
		for fact in (fact_a, fact_b):
			pid = await _find_point_id(fact)
			if pid:
				await delete_memory(pid)

		assert mock_memory.point_count() == 0
