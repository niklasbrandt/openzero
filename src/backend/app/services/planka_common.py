import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)

_tree_cache: dict[str, tuple[float, str]] = {} # cache_key -> (timestamp, data)

async def get_planka_auth_token() -> str:
	"""Authenticates with Planka and returns an access token. Handles ToS acceptance."""
	login_url = f"{settings.PLANKA_BASE_URL}/api/access-tokens"
	payload = {
		"emailOrUsername": settings.PLANKA_ADMIN_EMAIL,
		"password": settings.PLANKA_ADMIN_PASSWORD
	}
	logger.debug("Attempting Planka auth at %s", login_url)
	async with httpx.AsyncClient(timeout=10.0) as client:
		try:
			resp = await client.post(login_url, json=payload)
			
			# Handle pending ToS acceptance (common on first login)
			if resp.status_code == 403:
				data = resp.json()
				pending_token = data.get("pendingToken")
				if pending_token:
					logger.debug("Planka requires ToS acceptance (pendingToken found). Accepting...")
					accept_url = f"{settings.PLANKA_BASE_URL}/api/access-tokens/{pending_token}/actions/accept"
					accept_resp = await client.post(accept_url)
					accept_resp.raise_for_status()
					# After accepting, retry the login to get the real token
					resp = await client.post(login_url, json=payload)
				else:
					resp.raise_for_status()  # 403 without pendingToken is a real error

			resp.raise_for_status()
			token = resp.json().get("item")
			if token:
				logger.debug("Planka auth successful.")
			else:
				raise ValueError("Auth token is empty — check Planka credentials.")
			return token
		except Exception as e:
			logger.debug("Planka auth exception: %s", e)
			raise

def clear_tree_cache():
	"""Invalidate the project tree cache."""
	_tree_cache.clear()
	logger.debug("Planka tree cache cleared")
