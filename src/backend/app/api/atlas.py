"""Atlas API — navigable surface over the substrate's memory.

MA1: full implementations for all node/spine/diff/search/stats routes.
MA2+ will add semantic search, why-traces, and federation.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.models.db import AsyncSessionLocal

router = APIRouter(prefix="/api/atlas", tags=["atlas"])


async def get_db():
	async with AsyncSessionLocal() as session:
		yield session


# --- Pydantic request models ---

class NodeCreate(BaseModel):
	type: str
	label: str
	payload: dict = {}
	confidence: float = 0.5


class SpineCreate(BaseModel):
	label: str
	confidence: float = 0.5
	derived: bool = True


# --- Node operations ---

@router.get("/nodes")
async def list_nodes(
	limit: int = 50,
	offset: int = 0,
	node_type: str | None = None,
	db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
	"""List atlas nodes with optional type filter, ordered by recency."""
	try:
		if node_type:
			result = await db.execute(
				text("SELECT id, type, label, payload, confidence, created_at, updated_at, last_mentioned_at FROM atlas_nodes WHERE type = :node_type ORDER BY updated_at DESC LIMIT :limit OFFSET :offset"),
				{"node_type": node_type, "limit": limit, "offset": offset},
			)
		else:
			result = await db.execute(
				text("SELECT id, type, label, payload, confidence, created_at, updated_at, last_mentioned_at FROM atlas_nodes ORDER BY updated_at DESC LIMIT :limit OFFSET :offset"),
				{"limit": limit, "offset": offset},
			)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


@router.post("/nodes", status_code=201)
async def create_node(body: NodeCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""HITL node creation — operator or substrate creates a node directly."""
	try:
		import json
		result = await db.execute(
			text(
				"INSERT INTO atlas_nodes (type, label, payload, confidence) "
				"VALUES (:type, :label, :payload::jsonb, :confidence) "
				"RETURNING id, type, label, payload, confidence, created_at, updated_at, last_mentioned_at"
			),
			{"type": body.type, "label": body.label, "payload": json.dumps(body.payload), "confidence": body.confidence},
		)
		await db.commit()
		row = result.fetchone()
		return dict(row._mapping)
	except Exception:
		await db.rollback()
		raise HTTPException(status_code=500, detail="Failed to create node") from None


@router.get("/nodes/{node_id}")
async def get_node(node_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Get a single atlas node including full payload."""
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
	"""Return edges for a node, enriched with the other endpoint's label and type."""
	try:
		result = await db.execute(
			text(
				"SELECT e.id, e.source_node_id, e.target_node_id, e.kind, e.weight, e.payload, e.created_at, "
				"CASE WHEN e.source_node_id = :id THEN e.target_node_id ELSE e.source_node_id END AS other_node_id, "
				"n.label AS other_label, n.type AS other_type "
				"FROM atlas_edges e "
				"JOIN atlas_nodes n ON n.id = CASE WHEN e.source_node_id = :id THEN e.target_node_id ELSE e.source_node_id END "
				"WHERE e.source_node_id = :id OR e.target_node_id = :id "
				"ORDER BY e.weight DESC"
			),
			{"id": node_id},
		)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


# --- Spine operations ---

@router.get("/spines")
async def list_spines(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
	"""List all topic spines ordered by confidence."""
	try:
		result = await db.execute(
			text("SELECT id, label, confidence, derived, locked, updated_at FROM atlas_spines ORDER BY confidence DESC"),
		)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


@router.post("/spines", status_code=201)
async def create_spine(body: SpineCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Create a new topic spine."""
	try:
		result = await db.execute(
			text(
				"INSERT INTO atlas_spines (label, confidence, derived) "
				"VALUES (:label, :confidence, :derived) "
				"RETURNING id, label, confidence, derived, locked, updated_at"
			),
			{"label": body.label, "confidence": body.confidence, "derived": body.derived},
		)
		await db.commit()
		row = result.fetchone()
		return dict(row._mapping)
	except Exception:
		await db.rollback()
		raise HTTPException(status_code=500, detail="Failed to create spine") from None


@router.get("/spines/{spine_id}/summary")
async def get_spine_summary(spine_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Get the latest LLM-generated summary for a spine."""
	try:
		result = await db.execute(
			text("SELECT id, spine_id, generated_at, summary_text, source_refs FROM atlas_spine_summaries WHERE spine_id = :id ORDER BY generated_at DESC LIMIT 1"),
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


@router.get("/spines/{spine_id}/members")
async def get_spine_members(spine_id: int, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
	"""Return the nodes that belong to this spine with membership weight."""
	try:
		result = await db.execute(
			text(
				"SELECT sm.node_id, n.label, n.type, n.confidence, sm.weight "
				"FROM atlas_spine_members sm "
				"JOIN atlas_nodes n ON n.id = sm.node_id "
				"WHERE sm.spine_id = :spine_id "
				"ORDER BY sm.weight DESC"
			),
			{"spine_id": spine_id},
		)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


# --- Diff feed ---

@router.get("/diffs")
async def list_diffs(limit: int = 20, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
	"""Return recent diff entries ordered by recency (powers diff ribbon)."""
	try:
		result = await db.execute(
			text("SELECT id, node_id, spine_id, kind, since, until, summary, payload FROM atlas_diffs ORDER BY until DESC LIMIT :limit"),
			{"limit": limit},
		)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


# --- Search ---

@router.get("/search")
async def search_nodes(
	q: str = Query(..., min_length=1),
	limit: int = 20,
	db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
	"""Fast text search on node labels (ILIKE). Semantic search is MA2+."""
	try:
		result = await db.execute(
			text("SELECT id, type, label, confidence FROM atlas_nodes WHERE label ILIKE :q ORDER BY confidence DESC LIMIT :limit"),
			{"q": f"%{q}%", "limit": limit},
		)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


# --- Stats ---

@router.get("/stats")
async def atlas_stats(db: AsyncSession = Depends(get_db)) -> dict[str, int]:
	"""Return counts of core atlas objects."""
	try:
		counts = {}
		for table, key in [
			("atlas_nodes", "nodes"),
			("atlas_edges", "edges"),
			("atlas_spines", "spines"),
			("atlas_decisions", "decisions"),
			("atlas_contradictions", "contradictions"),
		]:
			r = await db.execute(text(f"SELECT COUNT(*) FROM {table}"))  # noqa: S608
			counts[key] = r.scalar() or 0
		return counts
	except Exception:
		return {"nodes": 0, "edges": 0, "spines": 0, "decisions": 0, "contradictions": 0}


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
