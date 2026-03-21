import json
import logging
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
        name: gpt-4o
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
        async with httpx.AsyncClient(timeout=90.0) as client:
            res = await client.post(f"{self.base_url}/chat-messages", headers=headers, json=payload)
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
        async with httpx.AsyncClient(timeout=90.0) as client:
            res = await client.post(f"{self.base_url}/workflows/run", headers=headers, json=payload)
            res.raise_for_status()
            return res.json()

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
                    rows = await conn.fetch("""
                        SELECT a.name, a.id::text as app_id, t.token as api_token
                        FROM apps a
                        JOIN api_tokens t ON a.id = t.app_id
                        WHERE t.type = 'app'
                    """)
                    if rows:
                        for row in rows:
                            cid = row['name']
                            self._manifest[cid] = {"app_id": row['app_id'], "api_token": row['api_token']}
                            if cid in self._crews:
                                self._crews[cid].dify_app_id = row['app_id']
                                self._crews[cid].dify_api_token = row['api_token']
                        updates_made = True
                        logger.info("✓ Recovered %d crew mappings via direct Postgres peering.", len(rows))
                finally:
                    await conn.close()
            except Exception as peering_err:
                logger.warning("Postgres peering recovery skipped: %s", peering_err)

        updates_made = False
        
        # --- Rule 14: Autonomous Bridge Assembly ---
        # Only perform deep seed if DB peering also returned nothing
        if len(self._manifest) == 0:
            logger.info("Dify instance empty. Performing Autonomous Bridge Assembly...")
                 # Strategy: Autonomous Remote Operation (Bridge Assembly)
            # We deploy a self-contained seeding script into the dify-api container's filesystem
            # and then execute it via python3 directly using a monkeypatched app context.
            seeder_py = """
import os, sys, datetime, secrets, json
import base64
import flask
import flask.sansio.blueprints
# Definitive monkeypatch for both standard and sansio blueprint registration checks in Dify/Flask
flask.blueprints.Blueprint._check_setup_finished = lambda self, f_name: None
flask.sansio.blueprints.Blueprint._check_setup_finished = lambda self, f_name: None

from app import create_app
from extensions.ext_database import db

app = create_app()
with app.app_context():
    from models.account import Account, Tenant, TenantAccountJoin, TenantAccountJoinRole
    from models.model import App, ApiToken
    from services.app_dsl_service import AppDslService
    from libs.password import hash_password

    try:
        email = "admin@openzero.ai"
        acc = Account.query.filter_by(email=email).first()
        if not acc:
            salt = secrets.token_bytes(16)
            hashed = hash_password("openZero2026!", salt)
            acc = Account(
                name="openZero-Z", email=email, status="active",
                password=base64.b64encode(hashed).decode('utf-8'),
                password_salt=base64.b64encode(salt).decode('utf-8'),
                initialized_at=datetime.datetime.now()
            )
            db.session.add(acc)
            db.session.commit()
        
        tenant = Tenant.query.filter_by(name="openZero-Core").first()
        if not tenant:
            tenant = Tenant(name="openZero-Core", status="normal")
            db.session.add(tenant)
            db.session.commit()
            
        join = TenantAccountJoin.query.filter_by(tenant_id=tenant.id, account_id=acc.id).first()
        if not join:
            join = TenantAccountJoin(tenant_id=tenant.id, account_id=acc.id, role=TenantAccountJoinRole.OWNER, current=True)
            db.session.add(join)
            db.session.commit()

        # Manually link current tenant to satisfy internal Dify checks in import_app
        acc._current_tenant = tenant

        agent_dir = "/app/agent/dify"
        mapping = {}
        if os.path.exists(agent_dir):
            dsl_svc = AppDslService(db.session)
            for fname in os.listdir(agent_dir):
                if not fname.endswith('.yml'): continue
                crew_id = fname.replace('.yml', '')
                existing = App.query.filter_by(tenant_id=tenant.id, name=crew_id).first()
                if not existing:
                    with open(os.path.join(agent_dir, fname), 'r', encoding='utf-8') as f:
                        content = f.read()
                        try:
                            # Import using content mode
                            app_obj = dsl_svc.import_app(account=acc, import_mode='yaml-content', yaml_content=content)
                            app_id = app_obj.id
                            token_str = f"app-{secrets.token_urlsafe(24)}"
                            token = ApiToken(tenant_id=tenant.id, app_id=app_id, type='app', token=token_str)
                            db.session.add(token)
                            db.session.commit()
                            mapping[crew_id] = {"app_id": str(app_id), "api_token": token_str}
                        except Exception as e:
                            db.session.rollback()
                            print(f"Error importing {crew_id}: {e}", file=sys.stderr)
                else:
                    token = ApiToken.query.filter_by(app_id=existing.id, type='app').first()
                    if not token:
                        token_str = f"app-{secrets.token_urlsafe(24)}"
                        token = ApiToken(tenant_id=tenant.id, app_id=existing.id, type='app', token=token_str)
                        db.session.add(token)
                        db.session.commit()
                        mapping[crew_id] = {"app_id": str(existing.id), "api_token": token_str}
                    else:
                        mapping[crew_id] = {"app_id": str(existing.id), "api_token": token.token}
                    
        print("AUTOSEED_START")
        print(json.dumps(mapping))
        print("AUTOSEED_END")

    except Exception as main_e:
        db.session.rollback()
        print(f"MAIN ERROR: {str(main_e)}", file=sys.stderr)
"""
            try:
                import subprocess
                # Deploy seeder script into container filesystem
                write_cmd = ["docker", "exec", "-i", "openzero-dify-api-1", "bash", "-c", "cat > /tmp/seeder.py"]
                subprocess.run(write_cmd, input=seeder_py, text=True, check=True)
                
                # Execute seeder via python3 directly (non-interactive, robust)
                # PYTHONPATH is required to locate Dify's app package
                run_cmd = ["docker", "exec", "openzero-dify-api-1", "bash", "-c", "export PYTHONPATH=/app/api && python3 /tmp/seeder.py"]
                res = subprocess.run(run_cmd, capture_output=True, text=True)
                
                if res.returncode == 0 and "AUTOSEED_START" in res.stdout:
                    # Extract JSON between markers
                    stdout_str = res.stdout
                    start_idx = stdout_str.find("AUTOSEED_START") + len("AUTOSEED_START")
                    end_idx = stdout_str.find("AUTOSEED_END")
                    json_str = stdout_str[start_idx:end_idx].strip()
                    
                    mapping = json.loads(json_str)
                    for crew_id, data in mapping.items():
                        self._manifest[crew_id] = data
                        if crew_id in self._crews:
                            self._crews[crew_id].dify_app_id = data["app_id"]
                            self._crews[crew_id].dify_api_token = data["api_token"]
                    updates_made = True
                    logger.info("✓ Autonomous Bridge Assembly complete: %d crews provisioned.", len(mapping))
                else:
                    logger.error("Autonomous seed assembly failed with RC %d. Marker found: %s", res.returncode, "AUTOSEED_START" in res.stdout)
                    if res.stderr: logger.error("Seeder Stderr: %s", res.stderr)
                    if res.stdout: logger.error("Seeder Stdout (first 1000ch): %s", res.stdout[:1000])
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


