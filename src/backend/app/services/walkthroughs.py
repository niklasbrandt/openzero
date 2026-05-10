"""Walk-through builder for openZero scheduled and ad-hoc Atlas tours."""
import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


async def build_walkthrough(kind: str, limit: int | None = None, node_id: int | None = None) -> dict[str, Any]:
	"""
	Build and persist a walk-through for the given kind.
	Returns a dict with keys: id, kind, title, summary, deep_link, stops, created_at.
	"""
	from app.models.db import AsyncSessionLocal
	from sqlalchemy import text

	stops: list[dict[str, Any]] = []

	async with AsyncSessionLocal() as db:
		if kind == "morning":
			_limit = limit or 5
			result = await db.execute(
				text(
					"SELECT n.id, n.type, n.label, n.payload, n.confidence, n.updated_at "
					"FROM atlas_nodes n "
					"ORDER BY n.updated_at DESC LIMIT :lim"
				),
				{"lim": _limit},
			)
			rows = result.fetchall()
			for i, row in enumerate(rows, 1):
				payload = row.payload if isinstance(row.payload, dict) else {}
				context_text = payload.get("summary", row.label)
				source_refs = await _get_spine_labels(db, row.id)
				stops.append({
					"position": i,
					"node_id": row.id,
					"spine_id": None,
					"atlas_node_ref": f"node:{row.type}:{row.label}",
					"context": context_text,
					"source_refs": source_refs,
					"confidence": row.confidence,
					"suggested_action": None,
					"node_label": row.label,
				})

		elif kind == "weekly":
			_limit = limit or 8
			# One stop per active spine (highest confidence first)
			spine_result = await db.execute(
				text(
					"SELECT s.id, s.label, s.confidence, s.payload "
					"FROM atlas_spines s "
					"ORDER BY s.confidence DESC NULLS LAST LIMIT :lim"
				),
				{"lim": _limit},
			)
			spine_rows = spine_result.fetchall()
			seen_node_ids: set[int] = set()
			for i, srow in enumerate(spine_rows, 1):
				spine_payload = srow.payload if isinstance(srow.payload, dict) else {}
				stops.append({
					"position": i,
					"node_id": None,
					"spine_id": srow.id,
					"atlas_node_ref": f"node:spine:{srow.label}",
					"context": spine_payload.get("summary", srow.label),
					"source_refs": [srow.label],
					"confidence": srow.confidence,
					"suggested_action": None,
					"node_label": srow.label,
				})
			# Fill remaining with atlas_diffs nodes
			remaining = _limit - len(stops)
			if remaining > 0:
				diff_result = await db.execute(
					text(
						"SELECT DISTINCT d.node_id, n.type, n.label, n.payload, n.confidence "
						"FROM atlas_diffs d "
						"JOIN atlas_nodes n ON n.id = d.node_id "
						"WHERE d.node_id IS NOT NULL "
						"ORDER BY d.until DESC NULLS LAST LIMIT :lim"
					),
					{"lim": remaining},
				)
				for row in diff_result.fetchall():
					if row.node_id in seen_node_ids:
						continue
					seen_node_ids.add(row.node_id)
					payload = row.payload if isinstance(row.payload, dict) else {}
					context_text = payload.get("summary", row.label)
					source_refs = await _get_spine_labels(db, row.node_id)
					stops.append({
						"position": len(stops) + 1,
						"node_id": row.node_id,
						"spine_id": None,
						"atlas_node_ref": f"node:{row.type}:{row.label}",
						"context": context_text,
						"source_refs": source_refs,
						"confidence": row.confidence,
						"suggested_action": None,
						"node_label": row.label,
					})

		elif kind == "monthly":
			_limit = limit or 12
			spine_result = await db.execute(
				text("SELECT s.id, s.label, s.confidence, s.payload FROM atlas_spines s ORDER BY s.confidence DESC NULLS LAST"),
			)
			for srow in spine_result.fetchall():
				if len(stops) >= _limit:
					break
				spine_payload = srow.payload if isinstance(srow.payload, dict) else {}
				stops.append({
					"position": len(stops) + 1,
					"node_id": None,
					"spine_id": srow.id,
					"atlas_node_ref": f"node:spine:{srow.label}",
					"context": spine_payload.get("summary", srow.label),
					"source_refs": [srow.label],
					"confidence": srow.confidence,
					"suggested_action": None,
					"node_label": srow.label,
				})
			# Add unresolved contradictions
			if len(stops) < _limit:
				contra_result = await db.execute(
					text(
						"SELECT ac.id, ac.primary_node_id, ac.payload, n.label AS primary_label, n.type, n.payload AS node_payload, n.confidence "
						"FROM atlas_contradictions ac "
						"JOIN atlas_nodes n ON n.id = ac.primary_node_id "
						"WHERE ac.status = 'open' "
						"LIMIT :lim"
					),
					{"lim": _limit - len(stops)},
				)
				for row in contra_result.fetchall():
					node_payload = row.node_payload if isinstance(row.node_payload, dict) else {}
					contra_payload = row.payload if isinstance(row.payload, dict) else {}
					context_text = contra_payload.get("summary", node_payload.get("summary", row.primary_label))
					source_refs = await _get_spine_labels(db, row.primary_node_id)
					stops.append({
						"position": len(stops) + 1,
						"node_id": row.primary_node_id,
						"spine_id": None,
						"atlas_node_ref": f"node:{row.type}:{row.primary_label}",
						"context": context_text,
						"source_refs": source_refs,
						"confidence": row.confidence,
						"suggested_action": None,
						"node_label": row.primary_label,
					})

		elif kind == "quarterly":
			_limit = limit or 15
			# spine + contradictions (same as monthly)
			spine_result = await db.execute(
				text("SELECT s.id, s.label, s.confidence, s.payload FROM atlas_spines s ORDER BY s.confidence DESC NULLS LAST"),
			)
			for srow in spine_result.fetchall():
				if len(stops) >= _limit:
					break
				spine_payload = srow.payload if isinstance(srow.payload, dict) else {}
				stops.append({
					"position": len(stops) + 1,
					"node_id": None,
					"spine_id": srow.id,
					"atlas_node_ref": f"node:spine:{srow.label}",
					"context": spine_payload.get("summary", srow.label),
					"source_refs": [srow.label],
					"confidence": srow.confidence,
					"suggested_action": None,
					"node_label": srow.label,
				})
			if len(stops) < _limit:
				contra_result = await db.execute(
					text(
						"SELECT ac.primary_node_id, ac.payload, n.label AS primary_label, n.type, n.payload AS node_payload, n.confidence "
						"FROM atlas_contradictions ac "
						"JOIN atlas_nodes n ON n.id = ac.primary_node_id "
						"WHERE ac.status = 'open' "
						"LIMIT :lim"
					),
					{"lim": _limit - len(stops)},
				)
				for row in contra_result.fetchall():
					node_payload = row.node_payload if isinstance(row.node_payload, dict) else {}
					contra_payload = row.payload if isinstance(row.payload, dict) else {}
					context_text = contra_payload.get("summary", node_payload.get("summary", row.primary_label))
					source_refs = await _get_spine_labels(db, row.primary_node_id)
					stops.append({
						"position": len(stops) + 1,
						"node_id": row.primary_node_id,
						"spine_id": None,
						"atlas_node_ref": f"node:{row.type}:{row.primary_label}",
						"context": context_text,
						"source_refs": source_refs,
						"confidence": row.confidence,
						"suggested_action": None,
						"node_label": row.primary_label,
					})
			# Check for domain.derived.yaml — add evolution stop if present
			domain_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "agent", "domain.derived.yaml")
			if os.path.exists(domain_path) and len(stops) < _limit:
				stops.append({
					"position": len(stops) + 1,
					"node_id": None,
					"spine_id": None,
					"atlas_node_ref": "node:domain:evolution",
					"context": "Domain evolution — inferred ontology has been updated this quarter.",
					"source_refs": [],
					"confidence": None,
					"suggested_action": None,
					"node_label": "Domain evolution",
				})

		elif kind == "yearly":
			_limit = limit or 20
			# Full spine sweep
			spine_result = await db.execute(
				text("SELECT s.id, s.label, s.confidence, s.payload FROM atlas_spines s ORDER BY s.confidence DESC NULLS LAST"),
			)
			for srow in spine_result.fetchall():
				if len(stops) >= _limit:
					break
				spine_payload = srow.payload if isinstance(srow.payload, dict) else {}
				stops.append({
					"position": len(stops) + 1,
					"node_id": None,
					"spine_id": srow.id,
					"atlas_node_ref": f"node:spine:{srow.label}",
					"context": spine_payload.get("summary", srow.label),
					"source_refs": [srow.label],
					"confidence": srow.confidence,
					"suggested_action": None,
					"node_label": srow.label,
				})
			# All unresolved contradictions
			if len(stops) < _limit:
				contra_result = await db.execute(
					text(
						"SELECT ac.primary_node_id, ac.payload, n.label AS primary_label, n.type, n.payload AS node_payload, n.confidence "
						"FROM atlas_contradictions ac "
						"JOIN atlas_nodes n ON n.id = ac.primary_node_id "
						"WHERE ac.status = 'open' "
						"LIMIT :lim"
					),
					{"lim": _limit - len(stops)},
				)
				for row in contra_result.fetchall():
					node_payload = row.node_payload if isinstance(row.node_payload, dict) else {}
					contra_payload = row.payload if isinstance(row.payload, dict) else {}
					context_text = contra_payload.get("summary", node_payload.get("summary", row.primary_label))
					source_refs = await _get_spine_labels(db, row.primary_node_id)
					stops.append({
						"position": len(stops) + 1,
						"node_id": row.primary_node_id,
						"spine_id": None,
						"atlas_node_ref": f"node:{row.type}:{row.primary_label}",
						"context": context_text,
						"source_refs": source_refs,
						"confidence": row.confidence,
						"suggested_action": None,
						"node_label": row.primary_label,
					})
			# Nodes from diffs older than 365 days
			if len(stops) < _limit:
				old_diff_result = await db.execute(
					text(
						"SELECT DISTINCT d.node_id, n.type, n.label, n.payload, n.confidence "
						"FROM atlas_diffs d "
						"JOIN atlas_nodes n ON n.id = d.node_id "
						"WHERE d.node_id IS NOT NULL "
						"AND d.until < NOW() - INTERVAL '365 days' "
						"LIMIT :lim"
					),
					{"lim": _limit - len(stops)},
				)
				existing_node_ids = {s["node_id"] for s in stops if s.get("node_id")}
				for row in old_diff_result.fetchall():
					if row.node_id in existing_node_ids:
						continue
					existing_node_ids.add(row.node_id)
					payload = row.payload if isinstance(row.payload, dict) else {}
					context_text = payload.get("summary", row.label)
					source_refs = await _get_spine_labels(db, row.node_id)
					stops.append({
						"position": len(stops) + 1,
						"node_id": row.node_id,
						"spine_id": None,
						"atlas_node_ref": f"node:{row.type}:{row.label}",
						"context": context_text,
						"source_refs": source_refs,
						"confidence": row.confidence,
						"suggested_action": None,
						"node_label": row.label,
					})

		elif kind == "ad_hoc":
			# Anchor node + edge neighbours
			if node_id is not None:
				anchor_result = await db.execute(
					text("SELECT id, type, label, payload, confidence FROM atlas_nodes WHERE id = :nid"),
					{"nid": node_id},
				)
				anchor = anchor_result.fetchone()
				if anchor:
					payload = anchor.payload if isinstance(anchor.payload, dict) else {}
					context_text = payload.get("summary", anchor.label)
					source_refs = await _get_spine_labels(db, anchor.id)
					stops.append({
						"position": 1,
						"node_id": anchor.id,
						"spine_id": None,
						"atlas_node_ref": f"node:{anchor.type}:{anchor.label}",
						"context": context_text,
						"source_refs": source_refs,
						"confidence": anchor.confidence,
						"suggested_action": None,
						"node_label": anchor.label,
					})
					# Neighbours via atlas_edges
					edge_result = await db.execute(
						text(
							"SELECT n.id, n.type, n.label, n.payload, n.confidence "
							"FROM atlas_edges e "
							"JOIN atlas_nodes n ON (n.id = CASE WHEN e.source_node_id = :nid THEN e.target_node_id ELSE e.source_node_id END) "
							"WHERE (e.source_node_id = :nid OR e.target_node_id = :nid) AND n.id != :nid "
							"LIMIT 5"
						),
						{"nid": node_id},
					)
					for row in edge_result.fetchall():
						payload = row.payload if isinstance(row.payload, dict) else {}
						context_text = payload.get("summary", row.label)
						source_refs = await _get_spine_labels(db, row.id)
						stops.append({
							"position": len(stops) + 1,
							"node_id": row.id,
							"spine_id": None,
							"atlas_node_ref": f"node:{row.type}:{row.label}",
							"context": context_text,
							"source_refs": source_refs,
							"confidence": row.confidence,
							"suggested_action": None,
							"node_label": row.label,
						})
			# Fallback: recent nodes if no node_id
			if not stops:
				result = await db.execute(
					text("SELECT id, type, label, payload, confidence FROM atlas_nodes ORDER BY updated_at DESC LIMIT 5"),
				)
				for i, row in enumerate(result.fetchall(), 1):
					payload = row.payload if isinstance(row.payload, dict) else {}
					context_text = payload.get("summary", row.label)
					source_refs = await _get_spine_labels(db, row.id)
					stops.append({
						"position": i,
						"node_id": row.id,
						"spine_id": None,
						"atlas_node_ref": f"node:{row.type}:{row.label}",
						"context": context_text,
						"source_refs": source_refs,
						"confidence": row.confidence,
						"suggested_action": None,
						"node_label": row.label,
					})

		# Build metadata
		summary = f"Walk-through ({kind}): {len(stops)} stop(s) selected from the Memory Atlas."
		title = f"Atlas Walk-through — {kind.capitalize()}"

		# Persist walkthrough
		wt_payload = json.dumps({"kind": kind, "summary": summary, "for_operator": "operator"})
		insert_result = await db.execute(
			text(
				"INSERT INTO walkthroughs (title, payload) "
				"VALUES (:title, :payload::jsonb) "
				"RETURNING id, created_at"
			),
			{"title": title, "payload": wt_payload},
		)
		wt_row = insert_result.fetchone()
		wt_id = wt_row.id
		created_at = wt_row.created_at

		deep_link = f"oz://atlas/walkthrough/{wt_id}"

		# Update payload with deep_link now that we have the id
		await db.execute(
			text("UPDATE walkthroughs SET payload = :payload::jsonb WHERE id = :wid"),
			{"payload": json.dumps({"kind": kind, "summary": summary, "deep_link": deep_link, "for_operator": "operator"}), "wid": wt_id},
		)

		# Persist stops
		for stop in stops:
			stop_payload = json.dumps({
				"source_refs": stop.get("source_refs", []),
				"confidence": stop.get("confidence"),
				"suggested_action": stop.get("suggested_action"),
				"atlas_node_ref": stop.get("atlas_node_ref"),
			})
			await db.execute(
				text(
					"INSERT INTO walkthrough_stops (walkthrough_id, stop_order, node_id, spine_id, narration, payload) "
					"VALUES (:walkthrough_id, :stop_order, :node_id, :spine_id, :narration, :payload::jsonb)"
				),
				{
					"walkthrough_id": wt_id,
					"stop_order": stop["position"],
					"node_id": stop.get("node_id"),
					"spine_id": stop.get("spine_id"),
					"narration": stop.get("context", ""),
					"payload": stop_payload,
				},
			)

		await db.commit()
		logger.info("build_walkthrough: persisted walkthrough id=%d kind=%s stops=%d", wt_id, kind, len(stops))

	return {
		"id": wt_id,
		"kind": kind,
		"title": title,
		"summary": summary,
		"deep_link": deep_link,
		"stops": stops,
		"created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at),
	}


async def _get_spine_labels(db: Any, nid: int) -> list[str]:
	"""Return spine labels for a given node id via atlas_spine_members."""
	from sqlalchemy import text
	try:
		result = await db.execute(
			text(
				"SELECT s.label FROM atlas_spines s "
				"JOIN atlas_spine_members sm ON sm.spine_id = s.id "
				"WHERE sm.node_id = :nid"
			),
			{"nid": nid},
		)
		return [row.label for row in result.fetchall()]
	except Exception as e:
		logger.debug("_get_spine_labels failed for node %d: %s", nid, e)
		return []


async def get_walkthrough(walkthrough_id: int) -> dict[str, Any] | None:
	"""Returns walkthrough dict with stops ordered by stop_order."""
	from app.models.db import AsyncSessionLocal
	from sqlalchemy import text

	async with AsyncSessionLocal() as db:
		wt_result = await db.execute(
			text("SELECT id, title, briefing_id, payload, created_at FROM walkthroughs WHERE id = :wid"),
			{"wid": walkthrough_id},
		)
		row = wt_result.fetchone()
		if not row:
			return None
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
