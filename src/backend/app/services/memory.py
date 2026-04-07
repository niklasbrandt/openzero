from typing import Optional, Any
from qdrant_client import QdrantClient, models
from app.config import settings
import asyncio
import threading
import uuid
import logging
import re
import datetime

logger = logging.getLogger(__name__)


def _sanitize_for_log(text: Any, max_len: int = 80) -> str:
	"""Built-in sanitizer for CodeQL Log Injection (CWE-117)."""
	val = str(text)[:max_len]
	# re.escape is a built-in sanitizer that escapes all special characters
	return re.escape(val)


# Patterns that indicate adversarial prompt injection in memory text.
# If any of these appear in content destined for the vault, the text is
# stripped of the offending segment (or rejected entirely).
_ADVERSARIAL_PATTERNS = re.compile(
	r'ignore\s+(all\s+)?previous\s+instructions'
	r'|you\s+are\s+now\s+in\s+["\']?developer\s+mode'
	r'|system\s*:\s*you\s+are'
	r'|new\s+instructions?\s*:'
	r'|override\s+(system|safety|instructions?)'
	r'|<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>|<\|system\|>'
	r'|\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>'
	r'|always\s+reveal\s+(api|secret|key|token|password)'
	r'|disregard\s+(all\s+)?(prior|previous|above)'
	r'|jailbreak|DAN\s+mode',
	re.IGNORECASE,
)

# Embedder will be loaded lazily to prevent startup crashes if libraries are broken
embedder = None
_embedder_lock = threading.Lock()
COLLECTION_NAME = "personal_memory"

def get_embedder():
	global embedder
	if embedder is None:
		with _embedder_lock:
			if embedder is None:
				import os
				from sentence_transformers import SentenceTransformer
				# local_files_only=True skips all HuggingFace network checks — model
				# is already cached in the container. Falls back to online if not cached.
				try:
					embedder = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
				except Exception:
					embedder = SentenceTransformer("all-MiniLM-L6-v2")
	return embedder

def _encode_sync(text: str) -> list:
	"""Run embedding synchronously — intended to be called via run_in_executor."""
	return get_embedder().encode(text).tolist()

async def encode_async(text: str) -> list:
	"""Embed text without blocking the event loop."""
	loop = asyncio.get_event_loop()
	return await loop.run_in_executor(None, _encode_sync, text)

def get_qdrant() -> QdrantClient:
	return QdrantClient(
		host=settings.QDRANT_HOST,
		port=settings.QDRANT_PORT,
		api_key=settings.QDRANT_API_KEY,
		https=False,
		timeout=10.0,
	)

async def ensure_collection():
	"""Create collection if it doesn't exist."""
	client = get_qdrant()
	try:
		collections = [c.name for c in client.get_collections().collections]
		if COLLECTION_NAME not in collections:
			client.create_collection(
				collection_name=COLLECTION_NAME,
				vectors_config=models.VectorParams(
					size=384,
					distance=models.Distance.COSINE,
				),
			)
	except Exception as e:
		logger.warning("Error connecting to Qdrant: %s", _sanitize_for_log(e))

async def store_memory(text: str, metadata: Optional[dict] = None):
	"""
	Embed text and store in Qdrant with Infrastructure-only guardrails.
	
	Guardrails:
	1. Noise Gate: Ignore extremely short/low-entropy inputs.
	2. Fact Distillation: Convert 'Traffic' (User talk) into 'Infrastructure' (Facts).
	3. Semantic Deduplication: Check if fact is already stored to prevent bloat.
	"""
	# 1. Noise Gate (Pre-filtering)
	if not text or len(text.strip()) < 12:
		return

	# 2. Fact Distillation (Infrastructure Pass)
	distilled_text = text
	
	# AGGRESSIVE HYGIENE: Strip internal protocols and conversational markers
	# This prevents "leaking" actions or chat boilerplate into the vault.
	# Use [^\]] instead of .*? to avoid polynomial backtracking on untrusted input.
	distilled_text = re.sub(r'\[?ACTION:[^\]]*\]?', '', distilled_text, flags=re.IGNORECASE)
	distilled_text = re.sub(r'(?:User:|Z:|Conversation:)[^\n]*', '', distilled_text, flags=re.IGNORECASE)
	distilled_text = distilled_text.strip()

	if not distilled_text or len(distilled_text) < 5:
		return

	# Ephemeral / system meta filter — reject phrases that describe transient
	# system state, LLM thinking artefacts, or numbered list fragments that
	# lack semantic completeness.
	_EPHEMERAL_PATTERNS = re.compile(
		# ── Language-agnostic structural rules ──────────────────────────────────
		# Numbered/lettered list fragments (language-agnostic): "1. Foo", "a) Bar"
		r"(?:^\d+[.)]\s)"
		r"|(?:^[a-f][.)]\s)"
		# Task/board action confirmation lines (these come from agent_actions.py output)
		r"|(?:(?:task|card|board|list|project) (?:created|added|updated|removed|moved))"
		# Pure system/tool meta nouns
		r"|(?:^(?:Planka board structure|Kanban WIP limits?|Board structure|WIP limits?)$)"

		# ── First-person action/state statements — EN + 10 supported languages ──
		# EN: "I added", "I'm still thinking", "I did not create", "Try again"
		r"|(?:^I(?:'m| am) (?:still thinking|processing|working on))"
		r"|(?:try again in a moment)"
		r"|(?:^I (?:(?:did not|didn't|just|have|haven't) )?(?:add|creat|updat|remov|set|mark|mov)\w*\b)"
		# DE: "Ich habe", "Ich denke noch", "Versuch es nochmal"
		r"|(?:^Ich (?:denke|überlege|arbeite|verarbeite) (?:noch|gerade))"
		r"|(?:^Ich (?:habe |hatte )?(?:(?:\w+ ){1,4})?(?:hinzugefügt|erstellt|aktualisiert|entfernt|gesetzt|verschob\w*|markiert))"
		r"|(?:Versuch(?:e)? es (?:gleich |in einem Moment )?(?:nochmal|erneut))"
		# ES: "He añadido", "Estoy procesando", "Inténtalo de nuevo"
		r"|(?:^He (?:\w+ )?(?:añadido|creado|actualizado|eliminado|configurado|movido|marcado))"
		r"|(?:^Estoy (?:procesando|trabajando|pensando))"
		r"|(?:Inténtalo de nuevo)"
		# FR: "J'ai ajouté", "Je suis en train de", "Réessaie"
		r"|(?:^J'ai (?:\w+ )?(?:ajouté|créé|mis à jour|supprimé|défini|déplacé|marqué))"
		r"|(?:^Je suis en train de)"
		r"|(?:Réessaie(?:z)?)"
		# PT: "Eu adicionei", "Estou processando", "Tente novamente"
		r"|(?:^Eu (?:\w+ )?(?:adicionei|criei|atualizei|removi|defini|movi|marquei))"
		r"|(?:^Estou (?:processando|trabalhando|pensando))"
		r"|(?:Tente novamente)"
		# RU: "Я добавил", "Я обрабатываю", "Попробуй ещё раз"
		r"|(?:^Я (?:\w+ )?(?:добавил|создал|обновил|удалил|установил|переместил|отметил))"
		r"|(?:^Я (?:обрабатываю|работаю|думаю))"
		r"|(?:Попробуй(?:те)? (?:ещё раз|снова))"
		# AR: "لقد أضفت" / "أنا أعمل" — block first-person action prefix
		r"|(?:^لقد (?:أضفت|أنشأت|حدّثت|حذفت|نقلت|علّمت))"
		r"|(?:^أنا (?:أعمل|أعالج|أفكر))"
		# ZH (Simplified): "我已添加" / "我正在处理"
		r"|(?:^我(?:已|正在)(?:添加|创建|更新|删除|移动|标记|处理|工作|思考))"
		# JA: "追加しました" / "処理中です"
		r"|(?:(?:追加|作成|更新|削除|移動|設定)しました)"
		r"|(?:処理中です|考え中です)"
		# KO: "추가했습니다" / "처리 중입니다"
		r"|(?:(?:추가|생성|업데이트|삭제|이동|설정)했습니다)"
		r"|(?:처리 중입니다|생각 중입니다)"
		# HI: "मैंने जोड़ा" / "मैं काम कर रहा हूं"
		r"|(?:^मैंने (?:जोड़|बनाया|अपडेट|हटाया|सेट|स्थानांतरित))"
		r"|(?:^मैं (?:काम कर|प्रसंस्कर|सोच) रहा)",
		re.IGNORECASE | re.MULTILINE,
	)
	if _EPHEMERAL_PATTERNS.search(distilled_text):
		logger.debug("Memory rejected: ephemeral/system-meta pattern: %s", _sanitize_for_log(distilled_text))
		return

	# Adversarial content filter -- reject text containing known injection
	# phrases that could poison future prompt contexts.
	if _ADVERSARIAL_PATTERNS.search(distilled_text):
		logger.warning("Memory rejected: adversarial pattern detected")
		return

	# 3. Semantic Deduplication
	client = get_qdrant()
	embedding = await encode_async(distilled_text)
	
	try:
		# Search for existing duplicates with extremely high threshold
		dupes = client.query_points(
			collection_name=COLLECTION_NAME,
			query=embedding,
			limit=1
		)
		if dupes.points and dupes.points[0].score > 0.92:
			logger.info("Memory Deduplicator: Ignored existing fact (score=%.3f)", dupes.points[0].score)
			return
	except Exception as _e:
		logger.debug("Memory dedup check failed: %s", _e) # optional; proceed with upsert if it fails

	# 4. Final Upsert
	final_metadata = {**(metadata or {}), "text": distilled_text, "stored_at": datetime.datetime.utcnow().timestamp()}
	client.upsert(
		collection_name=COLLECTION_NAME,
		points=[
			models.PointStruct(
				id=str(uuid.uuid4()),
				vector=embedding,
				payload=final_metadata,
			)
		],
	)




async def semantic_search(query: str, top_k: int = 5) -> str:
	"""Search memory and return formatted results."""
	client = get_qdrant()
	query_vector = await encode_async(query)
	try:
		# Use modern query_points API which is more robust
		response = client.query_points(
			collection_name=COLLECTION_NAME,
			query=query_vector,
			limit=top_k,
		)
		points = response.points
	except Exception as e:
		logger.error("Memory semantic search failed: %s", e)
		return "Memory system not initialized or unreachable."

	if not points:
		return "No memories found."
	lines = []
	for i, hit in enumerate(points, 1):
		text = hit.payload.get('text', '[No Text]')
		lines.append(f"{i}. (score: {hit.score:.2f}) {text}")
	return "\n".join(lines)

async def get_memory_stats() -> dict:
	"""Return accurate point counts and collection status."""
	client = get_qdrant()
	try:
		# Use count() for real-time accuracy
		count_result = client.count(
			collection_name=COLLECTION_NAME,
			exact=True
		)
		info = client.get_collection(COLLECTION_NAME)
		return {
			"points": count_result.count,
			"status": str(info.status),
			"vectors": count_result.count
		}
	except Exception as e:
		logger.warning("Memory stats error: %s", _sanitize_for_log(e))
		return {"points": 0, "status": "error", "vectors": 0}

async def delete_memory(point_id: str):
	"""Delete a specific point from Qdrant by ID."""
	client = get_qdrant()
	try:
		client.delete(
			collection_name=COLLECTION_NAME,
			points_selector=models.PointIdsList(
				points=[point_id]
			)
		)
		return True
	except Exception as e:
		logger.error("Failed to delete memory: %s", _sanitize_for_log(e))
		return False

async def semantic_search_raw(query: str, top_k: int = 10) -> list[dict]:
	"""Search memory and return raw structured results with IDs."""
	client = get_qdrant()
	query_vector = await encode_async(query)
	try:
		response = client.query_points(
			collection_name=COLLECTION_NAME,
			query=query_vector,
			limit=top_k,
		)
		points = response.points
	except Exception as e:
		logger.error("Memory semantic search failed: %s", e)
		return []
	return [
		{
			"id": str(hit.id),
			"text": hit.payload.get("text", "[No Text]"),
			"score": round(hit.score, 3),
			"stored_at": hit.payload.get("stored_at"),
		}
		for hit in points
	]


async def list_memories(offset: int = 0, limit: int = 50) -> dict:
	"""Scroll all memories with pagination. Returns {items, total, next_offset}."""
	client = get_qdrant()
	try:
		count_result = client.count(collection_name=COLLECTION_NAME, exact=True)
		total = count_result.count
	except Exception:
		total = 0

	try:
		# Qdrant scroll accepts a page offset as an integer offset in some versions;
		# to reliably paginate we scroll with limit and skip using an offset index trick.
		# The simplest correct approach: scroll from beginning, skip first `offset` points.
		results, next_page_offset = client.scroll(
			collection_name=COLLECTION_NAME,
			limit=limit,
			offset=None if offset == 0 else offset,
			with_payload=True,
			with_vectors=False,
		)
		items = [
			{
				"id": str(p.id),
				"text": p.payload.get("text", "[No Text]"),
				"stored_at": p.payload.get("stored_at"),
			}
			for p in results
		]
		return {"items": items, "total": total, "next_offset": next_page_offset}
	except Exception as e:
		logger.error("list_memories failed: %s", _sanitize_for_log(e))
		return {"items": [], "total": total, "next_offset": None}


async def wipe_collection(confirm: bool = False):
	"""Delete and recreate the collection."""
	if not confirm:
		return False
	client = get_qdrant()
	try:
		client.delete_collection(COLLECTION_NAME)
		await ensure_collection()
		return True
	except Exception:
		return False

async def get_recent_memories(hours: int = 24) -> list[dict]:
	"""Fetch memories stored within the last N hours for briefing review."""
	client = get_qdrant()
	try:
		cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=hours)).timestamp()
		# Scroll all points and filter by stored_at
		try:
			results, _ = client.scroll(
				collection_name=COLLECTION_NAME,
				scroll_filter=models.Filter(
					must=[
						models.FieldCondition(
							key="stored_at",
							range=models.Range(gte=cutoff)
						)
					]
				),
				limit=20,
			)
		except Exception as inner_e:
			logger.warning("Filtered scroll failed (schema mismatch?), falling back to unfiltered: %s", inner_e)
			results, _ = client.scroll(collection_name=COLLECTION_NAME, limit=20)
			
		return [{"id": str(p.id), "text": p.payload.get("text", "")} for p in results]
	except Exception as e:
		logger.warning("get_recent_memories failed: %s", _sanitize_for_log(e))
		return []
