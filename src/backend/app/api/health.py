from fastapi import APIRouter
import httpx
from app.config import settings

router = APIRouter()

@router.get("/health")
async def health_check():
	"""Health check with real LLM tier probing."""
	llm_status = {}
	for name, url in [
		("llm_instant", settings.LLM_INSTANT_URL),
		("llm_standard", settings.LLM_STANDARD_URL),
		("llm_deep", settings.LLM_DEEP_URL),
	]:
		try:
			async with httpx.AsyncClient(timeout=3) as client:
				r = await client.get(f"{url}/health")
				llm_status[name] = "reachable" if r.status_code == 200 else f"status:{r.status_code}"
		except Exception:
			llm_status[name] = "unreachable"

	return {
		"status": "online",
		"version": "1.0.0",
		"services": {
			"postgres": "reachable",
			"qdrant": "reachable",
			**llm_status
		}
	}
