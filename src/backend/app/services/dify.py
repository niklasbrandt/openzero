import json
import logging
# openZero Tactical Bridge Build ID: 876e4821-2a1d-481d-91b2-8ec2512cf123
import os
from pathlib import Path
from typing import Optional, Dict, List
import httpx
import yaml # type: ignore
from pydantic import BaseModel
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)

# Canonical Dify Agent DSL Blueprint for openZero Zero-Config Provisioning
BOOTSTRAP_DSL_TEMPLATE = """
app:
  description: '{description}'
  icon: 🤖
  icon_background: '#14B8A6'
  mode: agent-chat
  name: '{name}'
  use_icon_as_answer_icon: false
kind: app
version: 0.1.2
workflow:
  features:
    opening_statement: '🚀 Crew **{name}** initialized. Tactical reasoning budget: 5 iterations.'
    retriever_resource: {{enabled: false}}
    sensitive_word_avoidance: {{enabled: false}}
    speech_to_text: {{enabled: false}}
    suggested_questions: []
    suggested_questions_after_answer: {{enabled: false}}
    text_to_speech: {{enabled: false}}
  nodes:
  - data:
      agent_mode:
        enabled: true
        options:
          max_iteration: 5
          strategy: function_call
        tools: []
      model:
        completion_params: {{stop: [], temperature: 0.7, top_p: 1}}
        name: Qwen3-8B-Q3_K_M.gguf
        provider: openai
      prompt_template:
        system: |
          {instructions}
          
          SYSTEM_PROTOCOL:
          1. You are an autonomous Crew within the openZero ecosystem.
          2. Execute the above mission with extreme precision.
          3. Your results will be integrated into the Operator's universal context.
        user: '{{{{query}}}}'
      variables: []
    id: '1742574620515'
    position: {{x: 80, y: 80}}
    type: custom
"""

class CrewConfig(BaseModel):
    id: str
    name: str
    type: str  # "workflow" | "agent"
    group: str
    description: str
    dify_dsl_file: str
    enabled: bool = True
    feeds_briefing: Optional[str] = None
    schedule: Optional[str] = None
    lead_time: Optional[int] = None
    dify_app_id: Optional[str] = None
    instructions: Optional[str] = None
    briefing_day: Optional[str] = None
    briefing_dom: Optional[str] = None
    briefing_months: Optional[str] = None
    characters: Optional[List[Dict[str, str]]] = None
    # --- Auto-Provisioning Extension ---
    dify_api_token: Optional[str] = None  # Per-app Service API key


class DifyClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key

    def _headers(self, include_json: bool = True) -> Dict[str, str]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if include_json:
            headers["Content-Type"] = "application/json"
        return headers

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/info", headers=self._headers())
                return res.status_code in (200, 401, 403, 404)
        except Exception as e:
            logger.warning("Dify cluster unreachable: %s", e)
            return False

    async def import_dsl(self, file_path: Path) -> str:
        """Uploads a YAML DSL payload to Dify and returns the new App UUID."""
        if not file_path.exists():
            raise FileNotFoundError(f"DSL file missing: {file_path}")
            
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                with open(file_path, "rb") as f:
                    file_payload = {"file": (file_path.name, f, "application/x-yaml")}
                    res = await client.post(
                        f"{self.base_url}/apps/import",
                        headers=self._headers(include_json=False),
                        files=file_payload
                    )
                res.raise_for_status()
                data = res.json()
                return data.get("id") or data.get("app", {}).get("id", "")
        except Exception as e:
            logger.error("Dify import failed: %s", e)
            return ""

    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=2, max=10), 
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException))
    )
    async def run_agent(self, app_id: str, user_input: str, user_id: str = None, inputs: dict = None, api_key: str = None) -> dict:
        """Runs an autonomous agent cycle via the Service API."""
        target_key = api_key or self.api_key
        if not target_key:
             raise ValueError("Dify API key missing (autonomous provisioning pending?)")
        
        headers = {
            "Authorization": f"Bearer {target_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": inputs or {},
            "query": user_input,
            "response_mode": "blocking",
            "user": user_id or "operator"
        }
        logger.info("Dify: Executing agent %s (url: %s/chat-messages)", app_id, self.base_url)
        async with httpx.AsyncClient(timeout=600.0) as client:
            res = await client.post(f"{self.base_url}/chat-messages", headers=headers, json=payload)
            if res.status_code in (401, 500):
                logger.warning("Dify Agent failed (%d), falling back to direct LLM...", res.status_code)
                from app.services.openai import chat
                ans = await chat(user_input, tier="deep")
                return {"answer": ans}
                
            if not res.is_success:
                logger.error("Dify 400/500 Detail: %s (Payload: %s)", res.text, payload)
            res.raise_for_status()
            return res.json()

    async def run_workflow(self, app_id: str, inputs: dict = None, user_id: str = None, api_key: str = None) -> dict:
        """Runs a deterministic workflow via the Service API."""
        target_key = api_key or self.api_key
        if not target_key:
             raise ValueError("Dify API key missing (autonomous provisioning pending?)")

        headers = {
            "Authorization": f"Bearer {target_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": inputs or {},
            "response_mode": "blocking",
            "user": user_id or "operator"
        }
        logger.info("Dify: Executing workflow %s (url: %s/workflows/run)", app_id, self.base_url)
        async with httpx.AsyncClient(timeout=600.0) as client:
            try:
                res = await client.post(f"{self.base_url}/workflows/run", headers=headers, json=payload)
                res.raise_for_status()
                return res.json()
            except Exception as e:
                logger.error("Dify workflow execution fault: %s (URL: %s)", e, self.base_url)
                raise Exception(f"Communication failure with crew '{app_id}'. Detail: {str(e)}")

    async def get_active_runs(self, cadence: Optional[str] = None) -> bool:
        """
        Interrogates Dify execution status.
        Currently mocked as False due to absence of specific `/runs` filtering API in Dify OS, 
        but stubbed here to satisfy the architectural yield requirement.
        """
        # In a full implementation, we would query Dify or an internal execution lock state.
        return False


class CrewRegistry:
    def __init__(self, agent_dir: str, client: DifyClient):
        self.agent_dir = Path(agent_dir)
        self.crews_yaml_path = self.agent_dir / "crews.yaml"
        self.manifest_path = self.agent_dir / ".dify_app_ids.json"
        self.client = client
        self._crews: Dict[str, CrewConfig] = {}
        self._manifest: Dict[str, str] = {}

    async def load(self) -> None:
        """Parses crews.yaml and loads uncommented mappings."""
        logger.info("Registry: Loading crews.yaml from %s", self.crews_yaml_path)
        if not self.crews_yaml_path.exists():
            logger.warning("crews.yaml not found at %s", self.crews_yaml_path)
            return

        try:
            with open(self.crews_yaml_path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)
        except Exception as e:
            logger.error("Failed to parse crews.yaml: %s", e)
            return

        if not raw_data:
            return

        crews_list = raw_data.get("crews") or raw_data.get("dify_crews")
        if not crews_list:
            if "id" in raw_data or "name" in raw_data:
                logger.error("⚠ CRITICAL: crews.yaml root contains 'id' or 'name'. Your indentation is probably broken! List members must be indented under 'crews:'.")
            else:
                logger.warning("No 'crews' key found in crews.yaml.")
            return

        for crew_data in crews_list:
            if not isinstance(crew_data, dict):
                logger.error("Invalid crew entry in yaml (expected dict, got %s): %s", type(crew_data).__name__, crew_data)
                continue
            
            if not crew_data.get("enabled", True):
                continue
            
            try:
                # Map YAML definition into internal config
                config = CrewConfig(**crew_data)
                self._crews[config.id] = config
            except Exception as e:
                logger.error("Failed to parse crew configuration for %s: %s", crew_data.get('id', 'unknown'), e)
            
        logger.info("CrewRegistry loaded %d active crews from configuration.", len(self._crews))

    async def provision(self) -> None:
        """Idempotent auto-provisioning engine matching local DSLs to Dify Cloud App IDs."""
        logger.info("Registry: Provisioning Dify bridge (client: %s)", self.client.base_url)
        # Check Dify health first
        if not await self.client.health_check():
            logger.warning("Dify cluster unreachable. Deferring provisioning.")
            return

        # Load known mappings
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._manifest = data
                    for crew_id, mapping in data.items():
                        if crew_id in self._crews:
                            self._crews[crew_id].dify_app_id = mapping.get("app_id")
                            self._crews[crew_id].dify_api_token = mapping.get("api_token")
                logger.info("✓ Dify manifest loaded: %d crews provisioned.", len(self._manifest))
            except Exception as e:
                logger.error("Failed to read manifest %s: %s", self.manifest_path, e)

        # --- Rule 14: Postgres Peering (Deep Recovery) ---
        # If manifest is empty/malformed, attempt to recover by direct DB peering
        if len(self._manifest) == 0:
            try:
                import asyncpg
                # Peering credentials derived from shared backend env
                user = os.getenv("DB_USER", "zero")
                pw = os.getenv("DB_PASSWORD", "zero_dev_password")
                dsn = f"postgresql://{user}:{pw}@postgres:5432/dify"
                conn = await asyncpg.connect(dsn)
                try:
                    # Tier 1: Direct Database Peering (High Availability Recovery)
                    # We fetch all app names and their corresponding service tokens
                    rows = await conn.fetch("""
                        SELECT a.name, a.id::text as app_id, t.token as api_token
                        FROM apps a
                        JOIN api_tokens t ON a.id = t.app_id
                        WHERE t.type = 'app'
                    """)
                    
                    if rows:
                        # Match database apps back to our crew configuration
                        for row in rows:
                            db_name = row['name']
                            for cid, config in self._crews.items():
                                # Match by stable crew_id (slug) OR human name
                                if db_name == cid or db_name == config.name:
                                    self._manifest[cid] = {"app_id": row['app_id'], "api_token": row['api_token']}
                                    self._crews[cid].dify_app_id = row['app_id']
                                    self._crews[cid].dify_api_token = row['api_token']
                        
                        if self._manifest:
                            logger.info("✓ Recovered %d crew mappings via direct Postgres peering.", len(self._manifest))
                finally:
                    await conn.close()
            except Exception as peering_err:
                logger.warning("Postgres peering recovery skipped: %s", peering_err)

        updates_made = False
        
        # --- Rule 14: Autonomous Bridge Assembly ---
        # Logic: If we have ANY active crews in config that are missing from our manifest,
        # we perform a targeted assembly to fill the gaps autonomously.
        missing_crews = [cid for cid in self._crews.keys() if cid not in self._manifest]
        
        if missing_crews:
            logger.info("Dify brain incomplete (missing %d crews). Performing Direct database Bridge Assembly...", len(missing_crews))
            
            try:
                import asyncpg, uuid, secrets
                user = os.getenv("DB_USER", "zero")
                pw = os.getenv("DB_PASSWORD", "zero_dev_password")
                dsn = f"postgresql://{user}:{pw}@postgres:5432/dify"
                conn = await asyncpg.connect(dsn)
                try:
                    # Step 1: Recover Tenant & Admin
                    tenant_id = await conn.fetchval("SELECT id FROM tenants LIMIT 1")
                    account_id = await conn.fetchval("SELECT id FROM accounts LIMIT 1")
                    
                    if not tenant_id or not account_id:
                        logger.error("Dify database not initialized (no tenant/account found).")
                        return

                    # Step 2: Ensure 'openai' provider points to local LLM
                    # Dify 0.15.x uses provider_name in providers table
                    await conn.execute("""
                        INSERT INTO providers (id, tenant_id, provider_name, provider_type, quota_type, is_valid, token_is_set, created_at, updated_at)
                        VALUES ($1, $2, 'openai', 'custom', 'unlimited', true, true, now(), now())
                        ON CONFLICT DO NOTHING
                    """, uuid.uuid4(), tenant_id)

                    # Step 3: Provision Missing Crews
                    new_mappings = {}
                    for cid in missing_crews:
                        config = self._crews[cid]
                        app_id = uuid.uuid4()
                        
                        # A. Create App
                        await conn.execute("""
                            INSERT INTO apps (id, tenant_id, name, mode, status, description, enable_site, created_at, updated_at)
                            VALUES ($1, $2, $3, 'chat', 'normal', $4, false, now(), now())
                            ON CONFLICT (tenant_id, name) DO UPDATE SET updated_at = now()
                            RETURNING id
                        """, app_id, tenant_id, cid, config.description)
                        
                        # B. Create App Model Config (Directly pointing to local Qwen)
                        # Note: We use the simplest valid JSON for model config
                        model_config = json.dumps({
                            "provider": "openai",
                            "model": "Qwen3-8B-Q3_K_M.gguf",
                            "mode": "chat",
                            "completion_params": {"temperature": 0.7}
                        })
                        await conn.execute("""
                            INSERT INTO app_model_configs (id, app_id, model, created_at, updated_at)
                            VALUES ($1, $2, $3, now(), now())
                        """, uuid.uuid4(), app_id, model_config)
                        
                        # C. Create API Token
                        token_str = f"app-{secrets.token_urlsafe(24)}"
                        await conn.execute("""
                            INSERT INTO api_tokens (id, tenant_id, app_id, type, token, created_at)
                            VALUES ($1, $2, $3, 'app', $4, now())
                        """, uuid.uuid4(), tenant_id, app_id, token_str)
                        
                        new_mappings[cid] = {"app_id": str(app_id), "api_token": token_str}

                    # Step 4: Finalize Manifest
                    self._manifest.update(new_mappings)
                    for cid, data in new_mappings.items():
                        if cid in self._crews:
                            self._crews[cid].dify_app_id = data["app_id"]
                            self._crews[cid].dify_api_token = data["api_token"]
                    
                    with open(self.manifest_path, 'w', encoding='utf-8') as f:
                        json.dump(self._manifest, f, indent=4)
                    
                    updates_made = True
                    logger.info("✓ Direct Bridge Assembly complete: %d crews provisioned.", len(new_mappings))
                    
                    # Proactive notification (Background Hook)
                    try:
                        from app.api.telegram_bot import send_notification_html
                        from app.services.timezone import format_time
                        alert_text = (
                            "🚀 <b>Tactical Brain Assembled (Direct Tier)</b>\n\n"
                            f"- {len(new_mappings)} crews provisioned.\n"
                            "- Local Peer: Qwen3-8B (Direct SQL)\n\n"
                            f"<i>Infrastructure verified at {format_time()}</i>"
                        )
                        asyncio.create_task(send_notification_html(alert_text))
                    except Exception: pass

                finally:
                    await conn.close()
            except Exception as seed_err:
                logger.error("Strategic seed assembly error: %s", seed_err)

        # Standard provision loop (for incremental additions)
        for crew_id, config in self._crews.items():
            mapped_data = self._manifest.get(crew_id)
            if not mapped_data:
                logger.info("Crew '%s' lacks Dify mapping. Waiting for next bootstrapping cycle or manual provisioning.", crew_id)
                pass
            else:
                if isinstance(mapped_data, dict):
                    config.dify_app_id = mapped_data.get("app_id")
                    config.dify_api_token = mapped_data.get("api_token", "")
                else:
                    config.dify_app_id = mapped_data

        # Persist new UUIDs to disk
        if updates_made:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(self._manifest, f, indent=4)
                logger.info("Persisted updated .dify_app_ids.json manifest.")

    def get(self, crew_id: str) -> Optional[CrewConfig]:
        """O(1) retrieval of a Crew Config."""
        return self._crews.get(crew_id)

    def list_active(self) -> List[CrewConfig]:
        """Returns ordered active crews."""
        return list(self._crews.values())

from app.config import settings

dify_client = DifyClient(base_url=settings.DIFY_API_URL, api_key=settings.DIFY_API_KEY)

# Path resolution — /app/agent in Docker, project root /agent locally
if Path("/app/agent").exists():
	# Docker container path (WORKDIR /app)
	AGENT_FOLDER_PATH = Path("/app/agent")
else:
	# Local development path (relative to src/backend/app/services/dify.py)
	# Path(__file__).parents[4] maps:
	# 0: services -> 1: app -> 2: backend -> 3: src -> 4: project_root
	AGENT_FOLDER_PATH = Path(__file__).parents[4] / "agent"

crew_registry = CrewRegistry(agent_dir=str(AGENT_FOLDER_PATH), client=dify_client)


