"""ShareContract CRUD — stores in share_contracts table."""
import hashlib
import secrets
import json
from datetime import datetime
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

async def create_contract(db: AsyncSession, *, producer_node: str, consumer_node: str, resource: str,
	scope_predicate: dict, redactions: list, expires_at: datetime | None = None) -> dict[str, Any]:
	"""Creates a new share contract and generates a bearer token."""
	bearer_token = secrets.token_urlsafe(32)
	token_hash = hashlib.sha256(bearer_token.encode()).hexdigest()
	result = await db.execute(
		text("""INSERT INTO share_contracts
			(producer_node, consumer_node, resource, scope_predicate, redactions, expires_at, bearer_token_hash)
			VALUES (:pn, :cn, :res, :sp::jsonb, :red::jsonb, :exp, :th) RETURNING id, created_at"""),
		{"pn": producer_node, "cn": consumer_node, "res": resource,
		 "sp": json.dumps(scope_predicate), "red": json.dumps(redactions),
		 "exp": expires_at, "th": token_hash}
	)
	row = result.fetchone()
	return {"id": str(row.id), "bearer_token": bearer_token, "created_at": row.created_at.isoformat()}

async def get_contract(db: AsyncSession, contract_id: str) -> dict[str, Any] | None:
	result = await db.execute(
		text("SELECT * FROM share_contracts WHERE id = :id AND revoked_at IS NULL"),
		{"id": contract_id}
	)
	row = result.fetchone()
	return dict(row._mapping) if row else None

async def revoke_contract(db: AsyncSession, contract_id: str) -> bool:
	result = await db.execute(
		text("UPDATE share_contracts SET revoked_at = now() WHERE id = :id AND revoked_at IS NULL RETURNING id"),
		{"id": contract_id}
	)
	return result.fetchone() is not None

async def list_contracts(db: AsyncSession, node: str) -> list[dict]:
	result = await db.execute(
		text("SELECT id, producer_node, consumer_node, resource, scope_predicate, read_only, expires_at, created_at, revoked_at FROM share_contracts WHERE producer_node = :n OR consumer_node = :n ORDER BY created_at DESC"),
		{"n": node}
	)
	return [dict(row._mapping) for row in result.fetchall()]
