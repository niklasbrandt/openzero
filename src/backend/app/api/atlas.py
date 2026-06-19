import logging
from fastapi import APIRouter, Query
from sqlalchemy import select
from app.models.db import AsyncSessionLocal, AtlasNode, AtlasEdge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard/atlas", tags=["atlas"])

@router.get("/graph")
async def get_atlas_graph(limit: int = Query(80, ge=1, le=200)):
	nodes = []
	edges = []

	try:
		async with AsyncSessionLocal() as session:
			# Fetch latest nodes from Postgres
			node_result = await session.execute(
				select(AtlasNode).order_by(AtlasNode.created_at.desc()).limit(limit)
			)
			db_nodes = node_result.scalars().all()
			
			if db_nodes:
				node_ids = [n.id for n in db_nodes]
				
				# Fetch edges connecting these nodes
				edge_result = await session.execute(
					select(AtlasEdge).where(
						AtlasEdge.source_node_id.in_(node_ids) & 
						AtlasEdge.target_node_id.in_(node_ids)
					)
				)
				db_edges = edge_result.scalars().all()

				for n in db_nodes:
					nodes.append({
						"id": str(n.id),
						"label": n.label,
						"type": n.type,
						"confidence": n.confidence
					})

				for e in db_edges:
					edges.append({
						"source": str(e.source_node_id),
						"target": str(e.target_node_id),
						"weight": e.weight,
						"kind": e.kind
					})

	except Exception as e:
		logger.error("Failed to build dynamic openZero atlas graph: %s", e)

	return {"nodes": nodes, "edges": edges}

