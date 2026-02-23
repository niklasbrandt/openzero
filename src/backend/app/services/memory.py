from qdrant_client import QdrantClient, models
from app.config import settings
import uuid

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
    """Embed text and store in Qdrant."""
    client = get_qdrant()
    embedding = get_embedder().encode(text).tolist()
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={"text": text, **(metadata or {})},
            )
        ],
    )

async def semantic_search(query: str, top_k: int = 5) -> str:
    """Search memory and return formatted results."""
    client = get_qdrant()
    query_vector = get_embedder().encode(query).tolist()
    try:
        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k,
        )
    except Exception:
        return "Memory system not initialized or unreachable."

    if not results:
        return "No memories found."
    lines = []
    for i, hit in enumerate(results, 1):
        lines.append(f"{i}. (score: {hit.score:.2f}) {hit.payload['text']}")
    return "\n".join(lines)

async def get_memory_stats() -> dict:
    """Return point counts and collection status."""
    client = get_qdrant()
    try:
        info = client.get_collection(COLLECTION_NAME)
        return {
            "points": info.points_count,
            "status": str(info.status),
            "vectors": info.vectors_count if hasattr(info, 'vectors_count') else info.points_count
        }
    except Exception as e:
        print(f"Memory stats error: {e}")
        return {"points": 0, "status": "error", "vectors": 0}

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
