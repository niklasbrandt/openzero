import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional, Dict, List
import httpx
import yaml # type: ignore
from pydantic import BaseModel
import asyncio

logger = logging.getLogger(__name__)

# System Instructions Template
SYSTEM_TEMPLATE = """
{instructions}

SYSTEM_PROTOCOL:
1. You are an autonomous Crew within the openZero ecosystem.
2. Execute the mission with extreme precision.
3. Your results will be integrated into the Operator's universal context.
"""

class CrewConfig(BaseModel):
	id: str
	name: str
	type: str
	group: str
	description: str
	enabled: bool = True
	dify_app_id: Optional[str] = None
	dify_api_token: Optional[str] = None
	instructions: Optional[str] = None

class DifyClient:
	def __init__(self, base_url: str, api_key: str):
		self.base_url = base_url.rstrip('/')
		self.api_key = api_key

	def _headers(self, key: str = None) -> Dict[str, str]:
		headers = {"Authorization": f"Bearer {key or self.api_key}", "Content-Type": "application/json"}
		return headers

	async def run_agent(self, app_id: str, user_input: str, user_id: str = "operator", inputs: dict = None, api_key: str = None) -> dict:
		headers = self._headers(api_key)
		payload = {"inputs": inputs or {}, "query": user_input, "response_mode": "blocking", "user": user_id}
		async with httpx.AsyncClient(timeout=600.0) as client:
			res = await client.post(f"{self.base_url}/chat-messages", headers=headers, json=payload)
			if res.status_code != 200:
				logger.error("Dify API Failure (%d): %s", res.status_code, res.text)
			res.raise_for_status()
			return res.json()

class CrewRegistry:
	def __init__(self, agent_dir: str, client: DifyClient):
		self.agent_dir = Path(agent_dir)
		self.crews_yaml_path = self.agent_dir / "crews.yaml"
		self.manifest_path = self.agent_dir / ".dify_app_ids.json"
		self.client = client
		self._crews: Dict[str, CrewConfig] = {}
		self._manifest: Dict[str, dict] = {}

	async def load(self) -> None:
		if not self.crews_yaml_path.exists(): return
		with open(self.crews_yaml_path, "r", encoding="utf-8") as f:
			raw_data = yaml.safe_load(f)
		crews_list = raw_data.get("crews") or raw_data.get("dify_crews") or []
		for c in crews_list:
			if not isinstance(c, dict) or not c.get("enabled", True): continue
			config = CrewConfig(**c)
			self._crews[config.id] = config

	async def provision(self) -> None:
		from app.config import settings
		logger.info("Registry: Provisioning crews via Direct SQL Peering (v13)...")
		
		async def _get_conn():
			import asyncpg
			user = getattr(settings, "DB_USER", "zero")
			pw = getattr(settings, "DB_PASSWORD", "zero")
			dsn = f"postgresql://{user}:{pw}@postgres:5432/dify"
			return await asyncpg.connect(dsn)

		try:
			conn = await _get_conn()
			try:
				tenant_id = await conn.fetchval("SELECT id FROM tenants LIMIT 1")
				if not tenant_id: return

				updates_made = False
				for cid, config in self._crews.items():
					# 1. App Record
					db_app = await conn.fetchrow("SELECT id::text FROM apps WHERE name = $1", cid)
					if db_app: app_id = db_app['id']
					else:
						app_id = str(uuid.uuid4())
						await conn.execute("""
							INSERT INTO apps (id, tenant_id, name, mode, status, description, enable_site, enable_api, created_at, updated_at)
							VALUES ($1, $2, $3, 'chat', 'normal', $4, true, true, now(), now())
						""", app_id, tenant_id, cid, config.description)

					# 2. Model Config (v13 - Direct Schematic Mirror)
					instructions = SYSTEM_TEMPLATE.format(instructions=config.instructions or "Tactical Steward.")
					
					# Hybrid mapping discovered in production DB
					m_id_hybrid = "Qwen3-8B-Q3_K_M.gguf"
					m_name_hybrid = "Qwen3-8B-Q3"
					
					model_payload = {
						"mode": "chat",
						"name": m_name_hybrid,
						"model": m_name_hybrid,
						"provider": "openai",
						"completion_params": {"max_tokens": 4096, "temperature": 0.7}
					}
					configs_payload = {
						"prompt_type": "simple",
						"model": {"provider": "openai", "model": m_name_hybrid, "mode": "chat", "name": m_name_hybrid}
					}
					
					model_json = json.dumps(model_payload)
					configs_json = json.dumps(configs_payload)
					
					cfg_row = await conn.fetchrow("SELECT id::text FROM app_model_configs WHERE app_id = $1 LIMIT 1", app_id)
					if cfg_row:
						cfg_id = cfg_row['id']
						await conn.execute("""
							UPDATE app_model_configs SET model_id = $1, model = $2, configs = $3, pre_prompt = $4, updated_at = now()
							WHERE id = $5
						""", m_id_hybrid, model_json, configs_json, instructions, cfg_id)
					else:
						cfg_id = str(uuid.uuid4())
						await conn.execute("""
							INSERT INTO app_model_configs (id, app_id, provider, model_id, model, configs, pre_prompt, created_at, updated_at)
							VALUES ($1, $2, 'openai', $3, $4, $5, $6, now(), now())
						""", cfg_id, app_id, m_id_hybrid, model_json, configs_json, instructions)
					
					await conn.execute("UPDATE apps SET app_model_config_id = $1 WHERE id = $2", cfg_id, app_id)

					# 3. Dedicated Token
					token = await conn.fetchval("SELECT token FROM api_tokens WHERE app_id = $1 LIMIT 1", app_id)
					if not token:
						token = f"app-{uuid.uuid4().hex}"
						await conn.execute("""
							INSERT INTO api_tokens (id, app_id, type, token, created_at, tenant_id)
							VALUES (gen_random_uuid(), $1, 'app', $2, now(), $3)
						""", app_id, token, tenant_id)

					self._manifest[cid] = {"app_id": app_id, "api_token": token}
					self._crews[cid].dify_app_id = app_id
					self._crews[cid].dify_api_token = token
					updates_made = True

				if updates_made:
					try:
						with open(self.manifest_path, "w", encoding="utf-8") as f:
							json.dump(self._manifest, f, indent=4)
					except Exception: pass
					logger.info("✓ Direct SQL Assembly complete (%d crews).", len(self._crews))

			finally:
				await conn.close()
		except Exception as e:
			logger.error("Registry: SQL Seeding failed: %s", e)

	def get(self, crew_id: str) -> Optional[CrewConfig]:
		return self._crews.get(crew_id)

	def list_active(self) -> List[CrewConfig]:
		return list(self._crews.values())

from app.config import settings
dify_client = DifyClient(base_url=settings.DIFY_API_URL, api_key=settings.DIFY_API_KEY)
AGENT_FOLDER_PATH = Path("/app/agent") if Path("/app/agent").exists() else Path(__file__).parents[4] / "agent"
crew_registry = CrewRegistry(agent_dir=str(AGENT_FOLDER_PATH), client=dify_client)
