import asyncio
import logging
from fastapi import APIRouter, Depends
import httpx
from sqlalchemy import text
from app.config import settings
from app.models.db import AsyncSessionLocal
from app.api.dashboard import require_auth

router = APIRouter()
logger = logging.getLogger(__name__)

async def _probe_postgres() -> str:
	"""Execute a real SELECT 1 against Postgres."""
	try:
		async with AsyncSessionLocal() as session:
			await session.execute(text("SELECT 1"))
		return "reachable"
	except Exception as exc:
		logger.warning("Postgres health probe failed: %s", exc)
		return "unreachable"

async def _probe_qdrant() -> str:
	"""Call get_collections() on Qdrant to verify connectivity."""
	try:
		from app.services.memory import get_qdrant
		loop = asyncio.get_running_loop()
		await loop.run_in_executor(None, lambda: get_qdrant().get_collections())
		return "reachable"
	except Exception as exc:
		logger.warning("Qdrant health probe failed: %s", exc)
		return "unreachable"

@router.get("/health")
async def health_check():
	"""Public health probe — returns only overall status to avoid information disclosure."""
	postgres_status, qdrant_status = await asyncio.gather(
		_probe_postgres(),
		_probe_qdrant(),
	)
	critical_ok = postgres_status == "reachable" and qdrant_status == "reachable"
	overall = "online" if critical_ok else "degraded"
	return {"status": overall}


@router.get("/api/dashboard/health", dependencies=[Depends(require_auth)])
async def health_check_detailed():
	"""Authenticated detailed health endpoint — full service breakdown for operators."""
	postgres_status, qdrant_status = await asyncio.gather(
		_probe_postgres(),
		_probe_qdrant(),
	)

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

	services = {
		"postgres": postgres_status,
		"qdrant": qdrant_status,
		**llm_status,
	}

	critical_ok = postgres_status == "reachable" and qdrant_status == "reachable"
	overall = "online" if critical_ok else "degraded"

	return {
		"status": overall,
		"version": "1.0.0",
		"services": services,
	}
