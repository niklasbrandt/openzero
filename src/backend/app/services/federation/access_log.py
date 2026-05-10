"""Federation audit log writes."""
import hashlib
import hmac
import hmac
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings

def _hmac_query(query: str) -> str:
	"""HMAC-SHA-256 of query against per-instance KEK (defeats rainbow-table on short queries)."""
	key = settings.FEDERATION_KEK.encode() if settings.FEDERATION_KEK else b"openzero-audit"
	return hmac.new(key, query.encode(), hashlib.sha256).hexdigest()

def _bucket(n: int) -> str:
	if n == 0:
		return "0"
	if n <= 5:
		return "1-5"
	return "6-20"

async def log_access(db: AsyncSession, *, direction: str, contract_id: str, peer_node: str,
	resource: str, query: str, result_count: int, status: str, latency_ms: int) -> None:
	try:
		await db.execute(text("""INSERT INTO federation_audit
			(direction, contract_id, peer_node, resource, query_hash, result_count_bucket, status, latency_ms)
			VALUES (:dir, :cid::uuid, :peer, :res, :qh, :rcb, :st, :lat)"""),
			{"dir": direction, "cid": contract_id, "peer": peer_node, "res": resource,
			 "qh": _hmac_query(query), "rcb": _bucket(result_count), "st": status, "lat": latency_ms})
	except Exception:  # noqa: BLE001
		pass  # audit failure must not block the actual response
