from typing import Optional
from qdrant_client import QdrantClient, models
from app.config import settings
import uuid
import logging
import re
import datetime

logger = logging.getLogger(__name__)


def _log_safe(text: str, max_len: int = 80) -> str:
	"""Strip newlines from user-controlled strings before they reach the log.

	Prevents log-injection attacks where an attacker embeds CRLF sequences
	to forge additional log lines (CWE-117).
	"""
	clean = text[:max_len].replace('\r', ' ').replace('\n', ' ')
	return clean


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
COLLECTION_NAME = "personal_memory"

def get_embedder():
	global embedder
	if embedder is None:
		from sentence_transformers import SentenceTransformer
		embedder = SentenceTransformer("all-MiniLM-L6-v2")
	return embedder

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
		logger.warning("Error connecting to Qdrant: %s", e)

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

	# Adversarial content filter -- reject text containing known injection
	# phrases that could poison future prompt contexts.
	if _ADVERSARIAL_PATTERNS.search(distilled_text):
		logger.warning("Memory rejected (adversarial pattern detected): %s", _log_safe(distilled_text))
		return

	is_user_input = metadata and metadata.get("type") == "user_input"
	
	if is_user_input:
		from app.services.llm import chat
		distill_prompt = (
			"Distill the following user input into a single, permanent FACT or PREFERENCE statement. "
			"Rule 1: If it's a command, a greeting, or junk, reply ONLY with 'IGNORE'. "
			"Rule 2: No 'User likes...', just 'Likes...'. No mentions of 'Z' or 'Assistant'.\n\n"
			f"Input: {distilled_text}"
		)
		try:
			decision = await chat(distill_prompt, tier="instant")
			if "IGNORE" in decision.upper():
				return
			distilled_text = decision.strip().replace('"', '').replace("Fact: ", "")
		except Exception as e:
			logger.warning("Memory distillation failed, using raw (cleaned): %s", e)

	# 3. Semantic Deduplication
	client = get_qdrant()
	embedding = get_embedder().encode(distilled_text).tolist()
	
	try:
		# Search for existing duplicates with extremely high threshold
		dupes = client.query_points(
			collection_name=COLLECTION_NAME,
			query=embedding,
			limit=1
		)
		if dupes.points and dupes.points[0].score > 0.98:
			logger.info("Memory Deduplicator: Ignored existing fact: %s", _log_safe(distilled_text))
			return
	except Exception:
		pass  # dedup check optional; proceed with upsert if it fails

	# 4. Final Upsert
	final_metadata = {**(metadata or {}), "text": distilled_text, "stored_at": datetime.datetime.utcnow().isoformat()}
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

async def extract_and_store_facts(user_message: str):
	"""
	Post-processing memory extraction.
	Runs a fast instant-tier LLM call to extract learnable facts from user messages,
	then stores each fact via store_memory(). This is the primary learning mechanism
	because small local models are unreliable at emitting structured [ACTION: LEARN] tags.

	Designed to run as a background task (asyncio.create_task) so it never blocks
	the user-facing response.
	"""
	if not user_message or len(user_message.strip()) < 20:
		return

	# Skip trivial messages (greetings, confirmations, commands)
	from app.common.strings import TRIVIAL_PATTERNS
	msg_lower = user_message.lower().strip().rstrip('!?.,')
	if msg_lower in TRIVIAL_PATTERNS:
		return

	# Skip messages that are purely commands
	if user_message.strip().startswith('/'):
		return

	# Skip internal framing injected by coalescing
	clean_input = user_message
	if clean_input.startswith('[Follow-up'):
		clean_input = re.sub(r'^\[Follow-up[^\]]*\]\s*', '', clean_input)
	if clean_input.startswith('[Replying to'):
		clean_input = re.sub(r'^\[Replying to[^\]]*\]\s*', '', clean_input)

	try:
		from app.services.llm import chat
		extraction_prompt = (
			"Extract any personal facts, preferences, health information, skills, "
			"goals, relationships, or life updates from the following message. "
			"Return ONE fact per line, distilled into a clean permanent statement. "
			"Rules:\n"
			"- Only extract MEANINGFUL, PERMANENT facts worth remembering forever.\n"
			"- Skip greetings, questions, commands, and transient status updates.\n"
			"- DO NOT extract transient plans, isolated events, or short-term intentions (e.g. 'going to dinner tonight', 'ordered a present today', 'job application sent').\n"
			"- DO NOT extract system errors, technical issues, or agent self-references (e.g. 'I am having trouble reaching the local model').\n"
			"- No 'User likes...' or 'The user...' — just state the fact directly.\n"
			"- If there are NO learnable facts, reply ONLY with: NONE\n\n"
			f"Message: {clean_input}"
		)

		result = await chat(extraction_prompt, tier="instant")
		result = result.strip()

		# Parse result
		if not result or 'NONE' in result.upper():
			logger.debug("Memory extraction: no facts in '%s...' ", _log_safe(clean_input, 50))
			return

		# Store each extracted fact
		lines = [line.strip().lstrip('- ').lstrip('* ').strip() for line in result.split('\n')]
		stored_count = 0
		for fact in lines:
			# Skip empty, meta-commentary, or too-short lines
			if not fact or len(fact) < 10:
				continue
			if any(skip in fact.upper() for skip in ['NONE', 'NO LEARNABLE', 'NO FACTS', 'NO PERSONAL']):
				continue
			await store_memory(fact)
			stored_count += 1

		if stored_count > 0:
			logger.info("Memory extraction: stored %d fact(s) from '%s...'", stored_count, _log_safe(clean_input, 60))

	except Exception as e:
		logger.warning("Memory extraction failed (non-blocking): %s", e)


async def semantic_search(query: str, top_k: int = 5) -> str:
	"""Search memory and return formatted results."""
	client = get_qdrant()
	query_vector = get_embedder().encode(query).tolist()
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
		logger.warning("Memory stats error: %s", e)
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
		logger.error("Failed to delete memory: %s", e)
		return False

async def semantic_search_raw(query: str, top_k: int = 10) -> list[dict]:
	"""Search memory and return raw structured results with IDs."""
	client = get_qdrant()
	query_vector = get_embedder().encode(query).tolist()
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
		logger.error("list_memories failed: %s", e)
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
		cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=hours)).isoformat()
		# Scroll all points and filter by stored_at
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
		return [{"id": str(p.id), "text": p.payload.get("text", "")} for p in results]
	except Exception as e:
		logger.warning("get_recent_memories failed: %s", e)
		return []
