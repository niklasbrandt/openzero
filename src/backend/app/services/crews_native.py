import logging
import json
import httpx
from typing import Optional
from app.config import settings
from app.services.crews import crew_registry, SYSTEM_TEMPLATE
from app.services.personal_context import get_personal_context_for_prompt, refresh_personal_context
from app.services.agent_context import get_agent_skills_for_prompt, refresh_agent_context
from app.services.llm import ACTION_TAG_DOCS

logger = logging.getLogger(__name__)


async def _write_crew_memory(crew_id: str, user_input: str, crew_response: str) -> None:
	"""Fire-and-forget: append this exchange to the crew's Planka conversation card."""
	try:
		from app.services.crew_memory import append_crew_exchange
		await append_crew_exchange(crew_id, user_input, crew_response)
	except Exception as e:
		logger.warning("crew_memory write failed (non-fatal): %s", e)

# Local model is now 1.7B with 32k context — use the same full template as cloud.

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

		is_local = not settings.cloud_configured

		# 1. Base Instructions and Protocol
		instructions = SYSTEM_TEMPLATE.format(instructions=config.instructions or "Tactical Steward.")

		# 2. Semantic Priming: Character Roles
		if config.characters:
			char_block = "\nCREW COMPOSITION & ROLES:\n"
			for char in config.characters:
				char_block += f"- {char.get('name', 'Expert')}: {char.get('role', 'Contributing logic')}\n"
			instructions += f"\n{char_block}"

		# 3. Context Injection
		# Local: personal context only (agent_context is large and not needed for most crew tasks)
		# Cloud: full personal + agent context
		if is_local:
			p_ctx = get_personal_context_for_prompt()
			if not p_ctx:
				try:
					await refresh_personal_context()
					p_ctx = get_personal_context_for_prompt()
				except Exception as e:
					logger.debug("Native Engine: Failed to refresh personal context: %s", e)
			if p_ctx:
				instructions += f"\n\n{p_ctx}"
		else:
			context_block = await self._get_crew_context()
			if context_block:
				instructions += f"\n\n{context_block}"

		# 3b. Crew conversation memory context (this crew's past conversations)
		try:
			from app.services.crew_memory import get_crew_memory_context
			mem_ctx = await get_crew_memory_context(crew_id)
			if mem_ctx:
				instructions += f"\n\n{mem_ctx}"
		except Exception as e:
			logger.debug("Native Engine: Failed to load crew memory context: %s", e)

		# 4. Action tag vocabulary — always included (1.7B+ has 32k ctx)
		instructions += f"\n\n{ACTION_TAG_DOCS}"

		# 5. Recent user messages from conversation history so the crew can reference
		# what the user shared (e.g. recipes, plans). Z's own prior responses are
		# excluded — they add noise and cause the crew to echo stale output.
		from app.models.db import get_global_history
		history_messages = []
		try:
			recent = await get_global_history(limit=20)
			for m in recent:
				if m["role"] != "user":
					continue
				history_messages.append({"role": "user", "content": m["content"]})
		except Exception as e:
			logger.debug("Native Engine: Could not fetch conversation history: %s", e)

		# Keep history small for local model (CTX_SIZE=4096 — prompt alone can be 2k+ tokens)
		max_history = 5 if not settings.cloud_configured else 20

		messages = [{"role": "system", "content": instructions}]
		if history_messages:
			# Summarise scope so the crew knows these are prior user messages
			messages.append({
				"role": "system",
				"content": "PRIOR USER MESSAGES (conversation history — use only as reference to find content the user shared, do not echo or repeat them):"
			})
			messages.extend(history_messages[-max_history:])
		messages.append({"role": "user", "content": user_input})

		# Local model: CTX_SIZE=4096, so cap max_tokens to leave room for the prompt
		max_tokens = 4000 if settings.cloud_configured else 1500

		payload = {
			"model": settings.LLM_MODEL_CLOUD if settings.cloud_configured else "local",
			"messages": messages,
			"temperature": 0.7,
			"max_tokens": max_tokens,
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
					collected_chunks: list[str] = []
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
								collected_chunks.append(content)
								yield content
						except Exception as je:
							logger.debug("Stream Chunk Parse Error (non-fatal): %s", je)
					# Write crew memory after stream completes
					full_response = "".join(collected_chunks)
					if full_response.strip():
						await _write_crew_memory(crew_id, user_input, full_response)
			except Exception as e:
				logger.error("Native Engine Streaming Failure: %s", e)
				raise


native_crew_engine = NativeCrewEngine()
