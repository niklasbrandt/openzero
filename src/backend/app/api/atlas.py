"""Atlas API — navigable surface over the substrate's memory.

Routes are stubs in MA0. Full implementations land in MA1..MA3.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.models.db import AsyncSessionLocal

router = APIRouter(prefix="/api/atlas", tags=["atlas"])


async def get_db():
	async with AsyncSessionLocal() as session:
		yield session


# --- Node operations ---

@router.get("/nodes")
async def list_nodes(
	limit: int = 50,
	offset: int = 0,
	node_type: str | None = None,
	db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
	"""MA0 stub: list atlas nodes. Full implementation in MA1."""
	try:
		if node_type:
			result = await db.execute(
				text("SELECT id, type, label, confidence, created_at, updated_at FROM atlas_nodes WHERE type = :node_type ORDER BY updated_at DESC LIMIT :limit OFFSET :offset"),
				{"node_type": node_type, "limit": limit, "offset": offset},
			)
		else:
			result = await db.execute(
				text("SELECT id, type, label, confidence, created_at, updated_at FROM atlas_nodes ORDER BY updated_at DESC LIMIT :limit OFFSET :offset"),
				{"limit": limit, "offset": offset},
			)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


@router.get("/nodes/{node_id}")
async def get_node(node_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""MA0 stub: get a single atlas node."""
	try:
		result = await db.execute(
			text("SELECT id, type, label, payload, confidence, created_at, updated_at, last_mentioned_at FROM atlas_nodes WHERE id = :id"),
			{"id": node_id},
		)
		row = result.fetchone()
		if not row:
			raise HTTPException(status_code=404, detail="Node not found")
		return dict(row._mapping)
	except HTTPException:
		raise
	except Exception:
		raise HTTPException(status_code=500, detail="Atlas unavailable") from None


@router.get("/nodes/{node_id}/edges")
async def get_node_edges(node_id: int, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
	"""MA0 stub: get edges for a node."""
	try:
		result = await db.execute(
			text("SELECT id, source_node_id, target_node_id, kind, weight FROM atlas_edges WHERE source_node_id = :id OR target_node_id = :id ORDER BY weight DESC"),
			{"id": node_id},
		)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


# --- Spine operations ---

@router.get("/spines")
async def list_spines(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
	"""MA0 stub: list topic spines."""
	try:
		result = await db.execute(
			text("SELECT id, label, confidence, derived, locked, updated_at FROM atlas_spines ORDER BY confidence DESC"),
		)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


@router.get("/spines/{spine_id}/summary")
async def get_spine_summary(spine_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""MA0 stub: get the latest summary for a spine."""
	try:
		result = await db.execute(
			text("SELECT spine_id, generated_at, summary_text, source_refs FROM atlas_spine_summaries WHERE spine_id = :id ORDER BY generated_at DESC LIMIT 1"),
			{"id": spine_id},
		)
		row = result.fetchone()
		if not row:
			raise HTTPException(status_code=404, detail="No summary yet")
		return dict(row._mapping)
	except HTTPException:
		raise
	except Exception:
		raise HTTPException(status_code=500, detail="Atlas unavailable") from None


# --- Diff feed ---

@router.get("/diffs")
async def list_diffs(limit: int = 20, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
	"""MA0 stub: list recent diff entries (powers diff ribbon in Phase D)."""
	try:
		result = await db.execute(
			text("SELECT id, node_id, spine_id, kind, since, until, summary FROM atlas_diffs ORDER BY until DESC LIMIT :limit"),
			{"limit": limit},
		)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


# --- Health ---

@router.get("/health")
async def atlas_health(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Atlas readiness probe."""
	try:
		result = await db.execute(text("SELECT COUNT(*) FROM atlas_nodes"))
		node_count = result.scalar() or 0
		spine_result = await db.execute(text("SELECT COUNT(*) FROM atlas_spines"))
		spine_count = spine_result.scalar() or 0
		return {"status": "ok", "node_count": node_count, "spine_count": spine_count}
	except Exception:
		return {"status": "degraded", "node_count": 0, "spine_count": 0}
