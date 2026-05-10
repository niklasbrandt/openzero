"""Atlas API — navigable surface over the substrate's memory.

MA1: full implementations for all node/spine/diff/search/stats routes.
MA2: recompose operations, steel-manning, echo-finder.
MA3: decisions, contradictions, timeline, walkthroughs lens routes.
Phase DD: domain inference endpoints.
"""
import os
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


class NodeUpdate(BaseModel):
	label: str | None = None
	confidence: float | None = None


class SpineUpdate(BaseModel):
	label: str | None = None
	confidence: float | None = None


# --- Diff helper ---

async def _record_diff(conn: AsyncSession, kind: str, summary: str, node_id: int | None = None, spine_id: int | None = None) -> None:
	"""Insert a diff ribbon entry; errors are silently ignored to avoid blocking callers."""
	try:
		await conn.execute(
			text("INSERT INTO atlas_diffs (node_id, spine_id, kind, summary, since, until) VALUES (:node_id, :spine_id, :kind, :summary, NOW(), NOW())"),
			{"node_id": node_id, "spine_id": spine_id, "kind": kind, "summary": summary},
		)
	except Exception:
		pass


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


@router.put("/nodes/{node_id}")
async def update_node(node_id: int, body: NodeUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Update node label and/or confidence; auto-records a diff entry."""
	try:
		result = await db.execute(
			text("SELECT id, label, confidence FROM atlas_nodes WHERE id = :id"),
			{"id": node_id},
		)
		row = result.fetchone()
		if not row:
			raise HTTPException(status_code=404, detail="Node not found")
		old = dict(row._mapping)

		sets = []
		params: dict[str, Any] = {"id": node_id}
		if body.label is not None:
			sets.append("label = :label")
			params["label"] = body.label
		if body.confidence is not None:
			sets.append("confidence = :confidence")
			params["confidence"] = body.confidence
		if not sets:
			raise HTTPException(status_code=422, detail="No fields to update")
		sets.append("updated_at = NOW()")

		updated = await db.execute(
			text(f"UPDATE atlas_nodes SET {', '.join(sets)} WHERE id = :id RETURNING id, type, label, payload, confidence, created_at, updated_at, last_mentioned_at"),  # noqa: S608
			params,
		)
		new_row = updated.fetchone()
		if not new_row:
			raise HTTPException(status_code=404, detail="Node not found")

		summary_parts = []
		if body.label is not None and body.label != old["label"]:
			summary_parts.append(f"label '{old['label']}' -> '{body.label}'")
		if body.confidence is not None and body.confidence != old["confidence"]:
			summary_parts.append(f"confidence {round(float(old['confidence'] or 0), 2)} -> {round(body.confidence, 2)}")
		if summary_parts:
			await _record_diff(db, "update", f"Node #{node_id}: {'; '.join(summary_parts)}", node_id=node_id)

		await db.commit()
		return dict(new_row._mapping)
	except HTTPException:
		raise
	except Exception:
		await db.rollback()
		raise HTTPException(status_code=500, detail="Failed to update node") from None


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


@router.put("/spines/{spine_id}")
async def update_spine(spine_id: int, body: SpineUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Update spine label and/or confidence; auto-records a diff entry."""
	try:
		result = await db.execute(
			text("SELECT id, label, confidence FROM atlas_spines WHERE id = :id"),
			{"id": spine_id},
		)
		row = result.fetchone()
		if not row:
			raise HTTPException(status_code=404, detail="Spine not found")
		old = dict(row._mapping)

		sets = []
		params: dict[str, Any] = {"id": spine_id}
		if body.label is not None:
			sets.append("label = :label")
			params["label"] = body.label
		if body.confidence is not None:
			sets.append("confidence = :confidence")
			params["confidence"] = body.confidence
		if not sets:
			raise HTTPException(status_code=422, detail="No fields to update")
		sets.append("updated_at = NOW()")

		updated = await db.execute(
			text(f"UPDATE atlas_spines SET {', '.join(sets)} WHERE id = :id RETURNING id, label, confidence, derived, locked, updated_at"),  # noqa: S608
			params,
		)
		new_row = updated.fetchone()
		if not new_row:
			raise HTTPException(status_code=404, detail="Spine not found")

		summary_parts = []
		if body.label is not None and body.label != old["label"]:
			summary_parts.append(f"label '{old['label']}' -> '{body.label}'")
		if body.confidence is not None and body.confidence != old["confidence"]:
			summary_parts.append(f"confidence {round(float(old['confidence'] or 0), 2)} -> {round(body.confidence, 2)}")
		if summary_parts:
			await _record_diff(db, "update", f"Spine #{spine_id}: {'; '.join(summary_parts)}", spine_id=spine_id)

		await db.commit()
		return dict(new_row._mapping)
	except HTTPException:
		raise
	except Exception:
		await db.rollback()
		raise HTTPException(status_code=500, detail="Failed to update spine") from None


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


# --- MA3: Decisions lens ---

_DECISION_VALID_STATUSES = frozenset({"open", "revisit_due", "resolved"})


class DecisionCreate(BaseModel):
	node_id: int | None = None
	title: str | None = None
	rationale: str | None = None
	context: str | None = None
	options_considered: list[str] = []
	outcome: str | None = None
	confidence: float = 0.8
	revisit_when: str | None = None
	status: str = "open"
	payload: dict = {}


@router.get("/decisions")
async def list_decisions(
	status: str | None = None,
	due: bool = Query(default=False),
	db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
	"""List atlas decisions ordered by made_at DESC. Filter by ?status= and/or ?due=true (revisit_when <= today)."""
	from datetime import date as _date
	try:
		clauses = []
		params: dict[str, Any] = {}
		if status:
			clauses.append("status = :status")
			params["status"] = status
		if due:
			clauses.append("revisit_when IS NOT NULL AND revisit_when <= :today")
			params["today"] = _date.today().isoformat()
		where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
		result = await db.execute(
			text(f"SELECT id, node_id, made_at, title, rationale, context, options_considered, outcome, confidence, revisit_when, status, payload FROM atlas_decisions {where} ORDER BY made_at DESC"),  # noqa: S608
			params,
		)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


@router.post("/decisions", status_code=201)
async def create_decision(body: DecisionCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Create a new decision record and return the created row."""
	if body.status not in _DECISION_VALID_STATUSES:
		raise HTTPException(status_code=422, detail=f"Invalid status '{body.status}'. Valid: {sorted(_DECISION_VALID_STATUSES)}")
	try:
		import json
		result = await db.execute(
			text(
				"INSERT INTO atlas_decisions (node_id, title, rationale, context, options_considered, outcome, confidence, revisit_when, status, payload) "
				"VALUES (:node_id, :title, :rationale, :context, :options_considered::jsonb, :outcome, :confidence, :revisit_when, :status, :payload::jsonb) "
				"RETURNING id, node_id, made_at, title, rationale, context, options_considered, outcome, confidence, revisit_when, status, payload"
			),
			{
				"node_id": body.node_id,
				"title": body.title,
				"rationale": body.rationale,
				"context": body.context,
				"options_considered": json.dumps(body.options_considered),
				"outcome": body.outcome,
				"confidence": body.confidence,
				"revisit_when": body.revisit_when,
				"status": body.status,
				"payload": json.dumps(body.payload),
			},
		)
		await db.commit()
		row = result.fetchone()
		return dict(row._mapping)
	except HTTPException:
		raise
	except Exception:
		await db.rollback()
		raise HTTPException(status_code=500, detail="Failed to create decision") from None


@router.put("/decisions/{decision_id}/status")
async def update_decision_status(decision_id: int, body: dict, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Update the status field of a decision. Valid: open, revisit_due, resolved."""
	new_status = body.get("status", "")
	if new_status not in _DECISION_VALID_STATUSES:
		raise HTTPException(status_code=422, detail=f"Invalid status '{new_status}'. Valid: {sorted(_DECISION_VALID_STATUSES)}")
	try:
		result = await db.execute(
			text("UPDATE atlas_decisions SET status = :status WHERE id = :id RETURNING id, node_id, made_at, rationale, revisit_when, status, payload"),
			{"status": new_status, "id": decision_id},
		)
		row = result.fetchone()
		if not row:
			raise HTTPException(status_code=404, detail="Decision not found")
		await db.commit()
		return dict(row._mapping)
	except HTTPException:
		raise
	except Exception:
		await db.rollback()
		raise HTTPException(status_code=500, detail="Failed to update decision status") from None


# --- MA3: Contradictions lens ---

_CONTRADICTION_VALID_STATUSES = frozenset({"open", "dismissed", "resolved"})


class ContradictionCreate(BaseModel):
	primary_node_id: int | None = None
	opposing_node_id: int | None = None
	status: str = "open"
	payload: dict = {}


@router.get("/contradictions")
async def list_contradictions(
	status: str | None = None,
	db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
	"""List atlas contradictions ordered by detected_at DESC. Optional status filter."""
	try:
		if status:
			result = await db.execute(
				text("SELECT id, primary_node_id, opposing_node_id, detected_at, status, payload FROM atlas_contradictions WHERE status = :status ORDER BY detected_at DESC"),
				{"status": status},
			)
		else:
			result = await db.execute(
				text("SELECT id, primary_node_id, opposing_node_id, detected_at, status, payload FROM atlas_contradictions ORDER BY detected_at DESC"),
			)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


@router.post("/contradictions", status_code=201)
async def create_contradiction(body: ContradictionCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Create a new contradiction record and return the created row."""
	if body.status not in _CONTRADICTION_VALID_STATUSES:
		raise HTTPException(status_code=422, detail=f"Invalid status '{body.status}'. Valid: {sorted(_CONTRADICTION_VALID_STATUSES)}")
	try:
		import json
		result = await db.execute(
			text(
				"INSERT INTO atlas_contradictions (primary_node_id, opposing_node_id, status, payload) "
				"VALUES (:primary_node_id, :opposing_node_id, :status, :payload::jsonb) "
				"RETURNING id, primary_node_id, opposing_node_id, detected_at, status, payload"
			),
			{
				"primary_node_id": body.primary_node_id,
				"opposing_node_id": body.opposing_node_id,
				"status": body.status,
				"payload": json.dumps(body.payload),
			},
		)
		await db.commit()
		row = result.fetchone()
		return dict(row._mapping)
	except HTTPException:
		raise
	except Exception:
		await db.rollback()
		raise HTTPException(status_code=500, detail="Failed to create contradiction") from None


@router.put("/contradictions/{contradiction_id}/status")
async def update_contradiction_status(contradiction_id: int, body: dict, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Update the status field of a contradiction. Valid: open, dismissed, resolved."""
	new_status = body.get("status", "")
	if new_status not in _CONTRADICTION_VALID_STATUSES:
		raise HTTPException(status_code=422, detail=f"Invalid status '{new_status}'. Valid: {sorted(_CONTRADICTION_VALID_STATUSES)}")
	try:
		result = await db.execute(
			text("UPDATE atlas_contradictions SET status = :status WHERE id = :id RETURNING id, primary_node_id, opposing_node_id, detected_at, status, payload"),
			{"status": new_status, "id": contradiction_id},
		)
		row = result.fetchone()
		if not row:
			raise HTTPException(status_code=404, detail="Contradiction not found")
		await db.commit()
		return dict(row._mapping)
	except HTTPException:
		raise
	except Exception:
		await db.rollback()
		raise HTTPException(status_code=500, detail="Failed to update contradiction status") from None


# --- MA3: Timeline lens ---

@router.get("/timeline")
async def list_timeline(
	limit: int = 100,
	since: str | None = None,
	until: str | None = None,
	db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
	"""Return nodes ordered by created_at ASC for the timeline lens. Optional since/until ISO datetime bounds."""
	try:
		conditions = []
		params: dict[str, Any] = {"limit": limit}
		if since:
			conditions.append("created_at >= :since")
			params["since"] = since
		if until:
			conditions.append("created_at <= :until")
			params["until"] = until
		where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
		result = await db.execute(
			text(f"SELECT id, type, label, confidence, created_at, last_mentioned_at FROM atlas_nodes {where_clause} ORDER BY created_at ASC LIMIT :limit"),  # noqa: S608
			params,
		)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


# --- MA3: Walkthroughs (Phase W foundation) ---

class WalkthroughCreate(BaseModel):
	title: str
	briefing_id: int | None = None
	payload: dict = {}


@router.get("/walkthroughs")
async def list_walkthroughs(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
	"""List all walkthroughs ordered by created_at DESC."""
	try:
		result = await db.execute(
			text("SELECT id, title, briefing_id, payload, created_at FROM walkthroughs ORDER BY created_at DESC"),
		)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


@router.post("/walkthroughs", status_code=201)
async def create_walkthrough(body: WalkthroughCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Create a new walkthrough record and return the created row."""
	try:
		import json
		result = await db.execute(
			text(
				"INSERT INTO walkthroughs (title, briefing_id, payload) "
				"VALUES (:title, :briefing_id, :payload::jsonb) "
				"RETURNING id, title, briefing_id, payload, created_at"
			),
			{"title": body.title, "briefing_id": body.briefing_id, "payload": json.dumps(body.payload)},
		)
		await db.commit()
		row = result.fetchone()
		return dict(row._mapping)
	except Exception:
		await db.rollback()
		raise HTTPException(status_code=500, detail="Failed to create walkthrough") from None


@router.get("/walkthroughs/{walkthrough_id}")
async def get_walkthrough_by_id(walkthrough_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Return a single walkthrough with its stops."""
	try:
		wt_result = await db.execute(
			text("SELECT id, title, briefing_id, payload, created_at FROM walkthroughs WHERE id = :wid"),
			{"wid": walkthrough_id},
		)
		row = wt_result.fetchone()
		if not row:
			raise HTTPException(status_code=404, detail="Walkthrough not found")
		wt = dict(row._mapping)
		stops_result = await db.execute(
			text(
				"SELECT ws.id, ws.walkthrough_id, ws.stop_order, ws.node_id, ws.spine_id, ws.narration, ws.payload, "
				"n.label AS node_label, s.label AS spine_label "
				"FROM walkthrough_stops ws "
				"LEFT JOIN atlas_nodes n ON n.id = ws.node_id "
				"LEFT JOIN atlas_spines s ON s.id = ws.spine_id "
				"WHERE ws.walkthrough_id = :walkthrough_id "
				"ORDER BY ws.stop_order ASC"
			),
			{"walkthrough_id": walkthrough_id},
		)
		wt["stops"] = [dict(r._mapping) for r in stops_result.fetchall()]
		return wt
	except HTTPException:
		raise
	except Exception:
		raise HTTPException(status_code=500, detail="Failed to fetch walkthrough") from None


@router.get("/walkthroughs/{walkthrough_id}/stops")
async def list_walkthrough_stops(walkthrough_id: int, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
	"""Return stops for a walkthrough ordered by stop_order ASC, joined with node and spine labels."""
	try:
		result = await db.execute(
			text(
				"SELECT ws.id, ws.walkthrough_id, ws.stop_order, ws.node_id, ws.spine_id, ws.payload, "
				"n.label AS node_label, s.label AS spine_label "
				"FROM walkthrough_stops ws "
				"LEFT JOIN atlas_nodes n ON n.id = ws.node_id "
				"LEFT JOIN atlas_spines s ON s.id = ws.spine_id "
				"WHERE ws.walkthrough_id = :walkthrough_id "
				"ORDER BY ws.stop_order ASC"
			),
			{"walkthrough_id": walkthrough_id},
		)
		return [dict(r._mapping) for r in result.fetchall()]
	except Exception:
		return []


# --- Domain inference (Phase DD) ---

_DOMAIN_YAML_PATH = os.path.join(os.path.dirname(__file__), "../../../../agent/domain.derived.yaml")


@router.get("/domain")
async def get_domain() -> dict:
	"""Returns current agent/domain.derived.yaml content, or None if not yet generated."""
	import yaml
	if not os.path.exists(_DOMAIN_YAML_PATH):
		return {"domain": None, "message": "Domain not yet inferred. Run domain_inference crew."}
	with open(_DOMAIN_YAML_PATH) as f:
		domain = yaml.safe_load(f)
	return {"domain": domain}


@router.patch("/domain/confirm")
async def confirm_domain_field(body: dict) -> dict:
	"""Mark a field in agent/domain.derived.yaml as operator_confirmed: true."""
	import yaml
	if not os.path.exists(_DOMAIN_YAML_PATH):
		raise HTTPException(status_code=404, detail="Domain file not found")
	with open(_DOMAIN_YAML_PATH) as f:
		domain = yaml.safe_load(f)
	field = body.get("field", "")
	value = body.get("value")
	if field.startswith("identity."):
		key = field.split(".", 1)[1]
		if key in domain.get("identity", {}):
			domain["identity"][key] = value
			domain["identity"]["operator_confirmed"] = True
	elif field.startswith("spine."):
		spine_id = field.split(".", 1)[1]
		for spine in domain.get("spines", []):
			if spine["id"] == spine_id:
				spine["operator_confirmed"] = True
				if value:
					spine["label"] = value
	with open(_DOMAIN_YAML_PATH, "w") as f:
		yaml.dump(domain, f, allow_unicode=True, default_flow_style=False)
	return {"ok": True}


# --- Phase Y: Why? endpoint ---

_WHY_VALID_TYPES = frozenset({"node", "spine", "diff", "decision", "contradiction"})


@router.get("/why/{entity_type}/{entity_id}")
async def why_entity(entity_type: str, entity_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
	"""Return justification for any Atlas entity.
	entity_type: node | spine | diff | decision | contradiction
	Returns: {entity_type, entity_id, source_refs, confidence, rationale}
	"""
	if entity_type not in _WHY_VALID_TYPES:
		raise HTTPException(status_code=422, detail=f"Invalid entity_type '{entity_type}'. Valid: {sorted(_WHY_VALID_TYPES)}")
	try:
		eid = int(entity_id)
	except ValueError:
		raise HTTPException(status_code=422, detail="entity_id must be a positive integer") from None

	source_refs: list[Any] = []
	confidence: float = 0.5
	rationale: str = ""

	try:
		if entity_type == "node":
			result = await db.execute(
				text("SELECT id, label, payload, confidence FROM atlas_nodes WHERE id = :id"),
				{"id": eid},
			)
			row = result.fetchone()
			if not row:
				raise HTTPException(status_code=404, detail="Node not found")
			m = row._mapping
			payload = m["payload"] or {}
			source_refs = payload.get("source_refs", []) if isinstance(payload, dict) else []
			confidence = float(m["confidence"] or 0.5)
			rationale = str(m["label"])

		elif entity_type == "spine":
			result = await db.execute(
				text("SELECT id, label, confidence FROM atlas_spines WHERE id = :id"),
				{"id": eid},
			)
			row = result.fetchone()
			if not row:
				raise HTTPException(status_code=404, detail="Spine not found")
			m = row._mapping
			confidence = float(m["confidence"] or 0.5)
			rationale = str(m["label"])
			members_result = await db.execute(
				text("SELECT node_id FROM atlas_spine_members WHERE spine_id = :id ORDER BY weight DESC"),
				{"id": eid},
			)
			source_refs = [r._mapping["node_id"] for r in members_result.fetchall()]

		elif entity_type == "diff":
			result = await db.execute(
				text("SELECT id, kind, summary, node_id, spine_id FROM atlas_diffs WHERE id = :id"),
				{"id": eid},
			)
			row = result.fetchone()
			if not row:
				raise HTTPException(status_code=404, detail="Diff not found")
			m = row._mapping
			rationale = f"[{m['kind']}] {m['summary'] or ''}"
			source_refs = [ref for ref in [m["node_id"], m["spine_id"]] if ref is not None]
			confidence = 0.7

		elif entity_type == "decision":
			result = await db.execute(
				text("SELECT id, context, confidence FROM atlas_decisions WHERE id = :id"),
				{"id": eid},
			)
			row = result.fetchone()
			if not row:
				raise HTTPException(status_code=404, detail="Decision not found")
			m = row._mapping
			rationale = str(m["context"] or "")
			confidence = float(m["confidence"] or 0.8)
			source_refs = []

		elif entity_type == "contradiction":
			result = await db.execute(
				text("SELECT id, primary_node_id, opposing_node_id, status FROM atlas_contradictions WHERE id = :id"),
				{"id": eid},
			)
			row = result.fetchone()
			if not row:
				raise HTTPException(status_code=404, detail="Contradiction not found")
			m = row._mapping
			rationale = f"Contradiction detected (status: {m['status']})"
			source_refs = [ref for ref in [m["primary_node_id"], m["opposing_node_id"]] if ref is not None]
			confidence = 0.7

		# Log trace (fire-and-forget; ignore errors)
		try:
			import json
			await db.execute(
				text("INSERT INTO atlas_why_traces (subject_kind, subject_id, source_refs, confidence) VALUES (:kind, :eid, :refs::jsonb, :conf)"),
				{"kind": entity_type, "eid": eid, "refs": json.dumps(source_refs), "conf": confidence},
			)
			await db.commit()
		except Exception:
			try:
				await db.rollback()
			except Exception:
				pass

		return {
			"entity_type": entity_type,
			"entity_id": entity_id,
			"source_refs": source_refs,
			"confidence": confidence,
			"rationale": rationale,
		}
	except HTTPException:
		raise
	except Exception:
		raise HTTPException(status_code=500, detail="Why trace unavailable") from None


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
