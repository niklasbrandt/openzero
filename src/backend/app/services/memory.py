from qdrant_client import QdrantClient, models
from app.config import settings
import uuid
import logging

logger = logging.getLogger(__name__)

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
		print(f"Error connecting to Qdrant: {e}")

async def store_memory(text: str, metadata: dict = None):
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
	is_user_input = metadata and metadata.get("type") == "user_input"
	
	if is_user_input:
		from app.services.llm import chat
		distill_prompt = (
			"Distill the following user input into a single, permanent FACT or PREFERENCE statement. "
			"Remove all conversational noise, timestamps, and 'User said' preambles.\n\n"
			"If the input is transient traffic (greetings, status updates, junk), reply ONLY with 'IGNORE'.\n"
			"Otherwise, return the distilled infrastructure fact.\n\n"
			f"Input: {text}"
		)
		try:
			decision = await chat(distill_prompt, provider="ollama", model=settings.OLLAMA_MODEL_FAST)
			if "IGNORE" in decision.upper():
				return
			distilled_text = decision.strip().replace('"', '').replace("Fact: ", "")
		except Exception as e:
			logger.warning(f"Memory distillation failed, using raw: {e}")

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
			logger.info(f"Memory Deduplicator: Ignored existing fact: {distilled_text}")
			return
	except:
		pass

	# 4. Final Upsert
	client.upsert(
		collection_name=COLLECTION_NAME,
		points=[
			models.PointStruct(
				id=str(uuid.uuid4()),
				vector=embedding,
				payload={"text": distilled_text, **(metadata or {})},
			)
		],
	)

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
		logger.error(f"Memory semantic search failed: {e}")
		return f"Memory system not initialized or unreachable."

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
		print(f"Memory stats error: {e}")
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
		logger.error(f"Failed to delete memory: {e}")
		return False

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
