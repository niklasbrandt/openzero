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


# --- Recompose operations (MA2) ---

class MergePreviewRequest(BaseModel):
	node_ids: list[int]


class MergeConfirmRequest(BaseModel):
	node_ids: list[int]
	label: str
	type: str


class SplitPreviewRequest(BaseModel):
	node_id: int
	split_labels: list[str]


class SteelManRequest(BaseModel):
	node_id: int | None = None
	spine_id: int | None = None


@router.post("/recompose/merge/preview")
async def merge_preview(body: MergePreviewRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Preview a proposed node merge — no DB write."""
	if len(body.node_ids) < 2:
		raise HTTPException(status_code=422, detail="At least 2 node_ids required for merge")
	try:
		placeholders = ", ".join(f":id{i}" for i in range(len(body.node_ids)))
		params = {f"id{i}": nid for i, nid in enumerate(body.node_ids)}
		result = await db.execute(
			text(f"SELECT id, type, label FROM atlas_nodes WHERE id IN ({placeholders}) ORDER BY confidence DESC"),  # noqa: S608
			params,
		)
		rows = result.fetchall()
		if not rows:
			raise HTTPException(status_code=404, detail="No nodes found for provided IDs")
		proposed_type = rows[0]._mapping["type"]
		proposed_label = " / ".join(dict.fromkeys(r._mapping["label"] for r in rows))
		return {
			"proposed_label": proposed_label,
			"proposed_type": proposed_type,
			"node_ids": body.node_ids,
			"source_refs": [],
			"action": "merge",
		}
	except HTTPException:
		raise
	except Exception:
		raise HTTPException(status_code=500, detail="Merge preview failed") from None


@router.post("/recompose/merge/confirm")
async def merge_confirm(body: MergeConfirmRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Execute a node merge: insert merged node, re-point edges and spine members, delete originals, write diff."""
	if len(body.node_ids) < 2:
		raise HTTPException(status_code=422, detail="At least 2 node_ids required for merge")
	try:
		new_row = await db.execute(
			text("INSERT INTO atlas_nodes (type, label, payload, confidence) VALUES (:type, :label, '{}'::jsonb, 0.7) RETURNING id"),
			{"type": body.type, "label": body.label},
		)
		new_id: int = new_row.fetchone()._mapping["id"]

		placeholders = ", ".join(f":id{i}" for i in range(len(body.node_ids)))
		params = {f"id{i}": nid for i, nid in enumerate(body.node_ids)}

		# Re-point edges to the new merged node
		await db.execute(text(f"UPDATE atlas_edges SET source_node_id = :new_id WHERE source_node_id IN ({placeholders})"), {"new_id": new_id, **params})  # noqa: S608
		await db.execute(text(f"UPDATE atlas_edges SET target_node_id = :new_id WHERE target_node_id IN ({placeholders})"), {"new_id": new_id, **params})  # noqa: S608

		# Re-point spine members (insert new memberships then remove old ones to avoid PK conflict)
		await db.execute(
			text(f"INSERT INTO atlas_spine_members (spine_id, node_id, weight) SELECT spine_id, :new_id, MAX(weight) FROM atlas_spine_members WHERE node_id IN ({placeholders}) GROUP BY spine_id ON CONFLICT (spine_id, node_id) DO NOTHING"),  # noqa: S608
			{"new_id": new_id, **params},
		)
		await db.execute(text(f"DELETE FROM atlas_spine_members WHERE node_id IN ({placeholders})"), params)  # noqa: S608

		# Delete original nodes (CASCADE removes any remaining edges/spine_members)
		await db.execute(text(f"DELETE FROM atlas_nodes WHERE id IN ({placeholders})"), params)  # noqa: S608

		# Write diff ribbon entry
		await db.execute(
			text("INSERT INTO atlas_diffs (node_id, kind, summary, since, until) VALUES (:node_id, 'merge', :summary, NOW(), NOW())"),
			{"node_id": new_id, "summary": f"Merged {len(body.node_ids)} nodes into '{body.label}'"},
		)

		await db.commit()
		return {"new_node_id": new_id, "merged_count": len(body.node_ids)}
	except HTTPException:
		raise
	except Exception:
		await db.rollback()
		raise HTTPException(status_code=500, detail="Merge confirm failed") from None


@router.post("/recompose/split/preview")
async def split_preview(body: SplitPreviewRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Preview a proposed node split (MA2: preview only; confirm endpoint reserved for MA3)."""
	try:
		result = await db.execute(
			text("SELECT id, type, label FROM atlas_nodes WHERE id = :id"),
			{"id": body.node_id},
		)
		row = result.fetchone()
		if not row:
			raise HTTPException(status_code=404, detail="Node not found")
		node_type = row._mapping["type"]
		return {
			"proposed_splits": [{"label": s, "type": node_type} for s in body.split_labels],
			"source_node_id": body.node_id,
			"action": "split",
		}
	except HTTPException:
		raise
	except Exception:
		raise HTTPException(status_code=500, detail="Split preview failed") from None


@router.post("/recompose/steel-man")
async def steel_man(body: SteelManRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Generate the strongest counter-argument to a node or spine belief using the LLM (no DB write)."""
	if body.node_id is None and body.spine_id is None:
		raise HTTPException(status_code=422, detail="Provide node_id or spine_id")
	try:
		from app.services.llm import chat as llm_chat

		belief_text: str = ""
		source_node_id: int | None = None
		source_spine_id: int | None = None

		if body.node_id is not None:
			result = await db.execute(text("SELECT id, label FROM atlas_nodes WHERE id = :id"), {"id": body.node_id})
			row = result.fetchone()
			if not row:
				raise HTTPException(status_code=404, detail="Node not found")
			belief_text = row._mapping["label"]
			source_node_id = body.node_id
		else:
			result = await db.execute(text("SELECT id FROM atlas_spines WHERE id = :id"), {"id": body.spine_id})
			if not result.fetchone():
				raise HTTPException(status_code=404, detail="Spine not found")
			summary_result = await db.execute(
				text("SELECT summary_text FROM atlas_spine_summaries WHERE spine_id = :id ORDER BY generated_at DESC LIMIT 1"),
				{"id": body.spine_id},
			)
			summary_row = summary_result.fetchone()
			if not summary_row:
				raise HTTPException(status_code=404, detail="No summary available for spine")
			belief_text = summary_row._mapping["summary_text"]
			source_spine_id = body.spine_id

		system_prompt = (
			"You are the Steel-man Engine. Given the following belief/statement from the operator's memory substrate, "
			"generate the strongest possible counter-argument using only evidence that would plausibly exist in the same knowledge domain. "
			"Do not invent facts. Format: one paragraph, direct, no hedging."
		)
		response = await llm_chat(f"Belief/Statement: {belief_text}", system_override=system_prompt, tier="local", _feature="atlas_steel_man")
		return {
			"steel_man": response.strip(),
			"source_node_id": source_node_id,
			"source_spine_id": source_spine_id,
			"contradiction_candidate": True,
		}
	except HTTPException:
		raise
	except Exception:
		raise HTTPException(status_code=500, detail="Steel-man failed") from None


_ECHO_STOP_WORDS = frozenset({"the", "a", "an", "is", "of", "in", "and", "or"})


@router.get("/recompose/echo-finder/{node_id}")
async def echo_finder(node_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Find near-duplicate nodes via label similarity heuristic (Postgres ILIKE on first significant word)."""
	try:
		result = await db.execute(text("SELECT id, label FROM atlas_nodes WHERE id = :id"), {"id": node_id})
		row = result.fetchone()
		if not row:
			raise HTTPException(status_code=404, detail="Node not found")
		label: str = row._mapping["label"]

		first_word = ""
		for word in label.split():
			clean = word.strip(".,!?;:'\"").lower()
			if clean and clean not in _ECHO_STOP_WORDS:
				first_word = clean
				break

		if not first_word:
			return {"target_node_id": node_id, "candidates": []}

		candidates_result = await db.execute(
			text("SELECT id, type, label, confidence FROM atlas_nodes WHERE label ILIKE :pattern AND id != :node_id ORDER BY confidence DESC LIMIT 10"),
			{"pattern": f"%{first_word}%", "node_id": node_id},
		)
		candidates = [{**dict(r._mapping), "similarity": "textual"} for r in candidates_result.fetchall()]
		return {"target_node_id": node_id, "candidates": candidates}
	except HTTPException:
		raise
	except Exception:
		raise HTTPException(status_code=500, detail="Echo-finder failed") from None


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
