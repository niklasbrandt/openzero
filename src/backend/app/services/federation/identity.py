"""Tailscale peer identity verification."""
import ipaddress
import hmac
import hashlib
from fastapi import Request, HTTPException

TAILSCALE_CGNAT = ipaddress.ip_network("100.64.0.0/10")

def verify_tailscale_origin(request: Request) -> None:
	"""Raises 403 if the request did not originate from the Tailscale network."""
	client_ip = request.client.host if request.client else None
	if not client_ip:
		raise HTTPException(status_code=403, detail="No client IP")
	try:
		ip = ipaddress.ip_address(client_ip)
	except ValueError:
		raise HTTPException(status_code=403, detail="Invalid client IP") from None
	if ip not in TAILSCALE_CGNAT:
		raise HTTPException(status_code=403, detail="Not a Tailscale peer")

def verify_bearer_token(provided_token: str, stored_hash: str) -> bool:
	"""Constant-time bearer token verification."""
	provided_hash = hashlib.sha256(provided_token.encode()).hexdigest()
	return hmac.compare_digest(provided_hash, stored_hash)
