"""Federation API — all routes require Tailscale-internal origin + bearer token.
Contract CRUD additionally requires DASHBOARD_TOKEN.
Gated behind FEDERATION_ENABLED=true."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db import AsyncSessionLocal
from app.config import settings
from app.services.federation import federation_enabled
from app.services.federation.contracts import create_contract, revoke_contract, list_contracts
async def get_db():
	async with AsyncSessionLocal() as session:
		yield session


def _require_federation():
	if not federation_enabled():
		raise HTTPException(status_code=503, detail="Federation not enabled")

def _require_dashboard_auth(request: Request):
	auth = request.headers.get("Authorization", "")
	if not settings.DASHBOARD_TOKEN or auth != f"Bearer {settings.DASHBOARD_TOKEN}":
		raise HTTPException(status_code=401, detail="Dashboard auth required")

federation_router = APIRouter(prefix="/api/federation", tags=["federation"])

@federation_router.get("/contracts")
async def list_federation_contracts(request: Request, db: AsyncSession = Depends(get_db)):  # noqa: B008
	_require_federation()
	_require_dashboard_auth(request)
	node = request.headers.get("X-Federation-Node", "")
	return await list_contracts(db, node)

@federation_router.post("/contracts")
async def create_federation_contract(request: Request, body: dict, db: AsyncSession = Depends(get_db)):  # noqa: B008
	_require_federation()
	_require_dashboard_auth(request)
	return await create_contract(db, **body)

@federation_router.delete("/contracts/{contract_id}")
async def revoke_federation_contract(request: Request, contract_id: str, db: AsyncSession = Depends(get_db)):  # noqa: B008
	_require_federation()
	_require_dashboard_auth(request)
	ok = await revoke_contract(db, contract_id)
	if not ok:
		raise HTTPException(status_code=404, detail="Contract not found or already revoked")
	return {"ok": True}

@federation_router.get("/audit")
async def get_federation_audit(request: Request, db: AsyncSession = Depends(get_db)):  # noqa: B008
	_require_federation()
	_require_dashboard_auth(request)
	result = await db.execute(text("SELECT * FROM federation_audit ORDER BY ts DESC LIMIT 100"))
	return [dict(r._mapping) for r in result.fetchall()]
