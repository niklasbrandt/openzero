import logging
import json
import httpx
from typing import Optional, Dict, List
from app.services.dify import crew_registry, SYSTEM_TEMPLATE

logger = logging.getLogger(__name__)

class NativeCrewEngine:
	def __init__(self, llm_url: str = "http://openzero-llm-deep:8000/v1"):
		self.llm_url = llm_url.rstrip('/')

	async def run_crew(self, crew_id: str, user_input: str) -> str:
		"""Executes a crew mission directly via the local LLM engine."""
		config = crew_registry.get(crew_id)
		if not config:
			raise ValueError(f"Crew '{crew_id}' is not defined in registry.")

		instructions = SYSTEM_TEMPLATE.format(instructions=config.instructions or "Tactical Steward.")
		
		payload = {
			"model": "Qwen3-8B-Q3",
			"messages": [
				{"role": "system", "content": instructions},
				{"role": "user", "content": user_input}
			],
			"temperature": 0.7,
			"max_tokens": 4096
		}

		logger.info(f"Native Engine: Executing mission for '{crew_id}'...")
		
		async with httpx.AsyncClient(timeout=300.0) as client:
			try:
				res = await client.post(f"{self.llm_url}/chat/completions", json=payload)
				res.raise_for_status()
				data = res.json()
				return data['choices'][0]['message']['content']
			except Exception as e:
				logger.error(f"Native Engine Failure: {e}")
				raise

native_crew_engine = NativeCrewEngine()
