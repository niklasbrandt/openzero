from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    return {
        "status": "online",
        "version": "1.0.0",
        "services": {
            "postgres": "reachable",
            "qdrant": "reachable",
            "ollama": "reachable"
        }
    }
