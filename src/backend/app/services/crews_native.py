import logging
import json
import httpx
from typing import Optional
from app.config import settings
from app.services.crews import crew_registry, SYSTEM_TEMPLATE
from app.services.personal_context import get_personal_context_for_prompt, refresh_personal_context
from app.services.agent_context import get_agent_skills_for_prompt, refresh_agent_context

logger = logging.getLogger(__name__)

class NativeCrewEngine:
	def __init__(self, llm_url: Optional[str] = None):
		default_url = settings.LLM_CLOUD_BASE_URL if settings.cloud_configured else settings.LLM_LOCAL_URL
		self.llm_url = (llm_url or default_url).rstrip('/')
		if not self.llm_url.endswith("/v1"):
			self.llm_url += "/v1"

	async def _get_crew_context(self) -> str:
		"""Fetch personal and agent context for crew injection."""
		# 1. Personal context (Allergies, Profile, Behavioral Rules)
		p_ctx = get_personal_context_for_prompt()
		if not p_ctx:
			try:
				await refresh_personal_context()
				p_ctx = get_personal_context_for_prompt()
			except Exception as e:
				logger.debug("Native Engine: Failed to refresh personal context: %s", e)
		
		# 2. Agent Skills (Operational Knowledge, Methodologies)
		a_ctx = get_agent_skills_for_prompt()
		if not a_ctx:
			try:
				await refresh_agent_context()
				a_ctx = get_agent_skills_for_prompt()
			except Exception as e:
				logger.debug("Native Engine: Failed to refresh agent context: %s", e)
		
		blocks = []
		if p_ctx: blocks.append(p_ctx)
		if a_ctx: blocks.append(a_ctx)
		return "\n\n".join(blocks) if blocks else ""

	async def run_crew(self, crew_id: str, user_input: str) -> str:
		"""Executes a crew mission directly via the local LLM engine."""
		full_res = ""
		async for chunk in self.run_crew_stream(crew_id, user_input):
			full_res += chunk
		return full_res

	async def run_crew_stream(self, crew_id: str, user_input: str):
		"""Executes a crew mission and yields tokens in real-time."""
		config = crew_registry.get(crew_id)
		if not config:
			raise ValueError(f"Crew '{crew_id}' is not defined in registry.")

		# 1. Base Instructions and Protocol
		instructions = SYSTEM_TEMPLATE.format(instructions=config.instructions or "Tactical Steward.")
		
		# 2. Semantic Priming: Character Roles
		if config.characters:
			char_block = "\nCREW COMPOSITION & ROLES:\n"
			for char in config.characters:
				char_block += f"- {char.get('name', 'Expert')}: {char.get('role', 'Contributing logic')}\n"
			instructions += f"\n{char_block}"

		# 3. Personal & Agent Context Injection
		context_block = await self._get_crew_context()
		if context_block:
			instructions += f"\n\n{context_block}"

		payload = {
			"model": settings.LLM_MODEL_CLOUD if settings.cloud_configured else "local",
			"messages": [
				{"role": "system", "content": instructions},
				# /no_think suppresses CoT for local Qwen3; ignored harmlessly by cloud APIs.
				{"role": "user", "content": user_input + "\n/no_think"}
			],
			"temperature": 0.7,
			"max_tokens": 6000,
			"stream": True
		}

		# Sanitize crew_id for logging to prevent CRLF injection (CodeQL)
		safe_crew_id = crew_id.replace("\n", "\\n").replace("\r", "\\r")
		logger.info("Native Engine: Executing streaming mission for '%s'...", safe_crew_id)

		req_headers = {}
		if settings.cloud_configured:
			req_headers["Authorization"] = f"Bearer {settings.LLM_CLOUD_API_KEY}"

		async with httpx.AsyncClient(timeout=3600.0) as client:
			try:
				async with client.stream("POST", f"{self.llm_url}/chat/completions", headers=req_headers, json=payload) as response:
					response.raise_for_status()
					async for line in response.aiter_lines():
						if not line or not line.startswith("data: "):
							continue
						
						data_str = line[6:].strip()
						if data_str == "[DONE]":
							break
							
						try:
							chunk_data = json.loads(data_str)
							delta = chunk_data.get("choices", [{}])[0].get("delta", {})
							content = delta.get("content", "")
							if content:
								yield content
						except Exception as je:
							logger.debug("Stream Chunk Parse Error (non-fatal): %s", je)
			except Exception as e:
				logger.error("Native Engine Streaming Failure: %s", e)
				raise


native_crew_engine = NativeCrewEngine()
