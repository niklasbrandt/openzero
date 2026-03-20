import httpx
import logging
from typing import Optional, Any, Dict, AsyncGenerator
from app.config import settings

logger = logging.getLogger(__name__)

class DifyClient:
	"""Client for interacting with Dify API (Chat, Workflow, Agent apps)."""

	def __init__(self, api_url: str = settings.DIFY_API_URL, api_key: Optional[str] = settings.DIFY_API_KEY):
		self.api_url = api_url.rstrip("/")
		self.api_key = api_key
		self.headers = {
			"Authorization": f"Bearer {self.api_key}",
			"Content-Type": "application/json"
		}

	async def run_workflow(self, inputs: Dict[str, Any], user: str = "openZero") -> Dict[str, Any]:
		"""Execute a Dify Workflow application."""
		if not self.api_key:
			return {"status": "error", "message": "Dify API key not configured."}

		async with httpx.AsyncClient(timeout=60.0) as client:
			try:
				response = await client.post(
					f"{self.api_url}/workflows/run",
					headers=self.headers,
					json={
						"inputs": inputs,
						"response_mode": "blocking",
						"user": user
					}
				)
				response.raise_for_status()
				return response.json()
			except Exception as e:
				logger.error("Dify workflow execution failed: %s", e)
				return {"status": "error", "message": str(e)}

	async def chat_message(self, query: str, conversation_id: Optional[str] = None, user: str = "openZero") -> Dict[str, Any]:
		"""Send a message to a Dify Chatbot or Agent application."""
		if not self.api_key:
			return {"status": "error", "message": "Dify API key not configured."}

		async with httpx.AsyncClient(timeout=60.0) as client:
			try:
				payload = {
					"inputs": {},
					"query": query,
					"response_mode": "blocking",
					"user": user
				}
				if conversation_id:
					payload["conversation_id"] = conversation_id

				response = await client.post(
					f"{self.api_url}/chat-messages",
					headers=self.headers,
					json=payload
				)
				response.raise_for_status()
				return response.json()
			except Exception as e:
				logger.error("Dify chat message failed: %s", e)
				return {"status": "error", "message": str(e)}

	async def check_health(self) -> bool:
		"""Verify connection to Dify API."""
		if not self.api_key:
			return False
		async with httpx.AsyncClient(timeout=5.0) as client:
			try:
				# Dify doesn't have a public ping, so we check the base URL or a common endpoint
				response = await client.get(f"{self.api_url}/parameters", headers=self.headers)
				return response.status_code == 200
			except Exception:
				return False

dify_service = DifyClient()
