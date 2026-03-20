import os
import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, List, Any
import httpx
import yaml
from pydantic import BaseModel
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)

class CrewConfig(BaseModel):
    id: str
    name: str
    type: str  # "workflow" | "agent"
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


class DifyClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key

    def _headers(self, include_json: bool = True) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if include_json:
            headers["Content-Type"] = "application/json"
        return headers

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/info", headers=self._headers())
                return res.status_code in (200, 401, 403, 404)
        except Exception as e:
            logger.warning(f"Dify cluster unreachable: {e}")
            return False

    async def import_dsl(self, file_path: Path) -> str:
        """Uploads a YAML DSL payload to Dify and returns the new App UUID."""
        if not file_path.exists():
            raise FileNotFoundError(f"DSL file missing: {file_path}")
            
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Based on standard Dify app import specs
                with open(file_path, "rb") as f:
                    file_payload = {"file": (file_path.name, f, "application/x-yaml")}
                    res = await client.post(
                        f"{self.base_url}/apps/import",
                        headers=self._headers(include_json=False),
                        files=file_payload
                    )
                res.raise_for_status()
                data = res.json()
                return data.get("app_id") or data.get("id")
        except Exception as e:
            logger.error(f"Failed to import Dify DSL {file_path.name}: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=2, max=10), 
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException))
    )
    async def run_workflow(self, app_id: str, inputs: dict) -> dict:
        """Executes a blocking workflow on Dify."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "inputs": inputs,
                "response_mode": "blocking",
                "user": "zero-system"
            }
            # Note: Dify execution endpoint is typically /workflows/run
            res = await client.post(
                f"{self.base_url}/workflows/run", 
                headers=self._headers(),
                json=payload
            )
            res.raise_for_status()
            return res.json()

    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=2, max=10), 
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException))
    )
    async def run_agent(self, app_id: str, query: str, conversation_id: Optional[str] = None, inputs: Optional[dict] = None) -> dict:
        """Executes a Chat/Agent invocation on Dify."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "inputs": inputs or {},
                "query": query,
                "response_mode": "blocking",
                "user": "zero-system"
            }
            if conversation_id:
                payload["conversation_id"] = conversation_id
                
            res = await client.post(
                f"{self.base_url}/chat-messages", 
                headers=self._headers(),
                json=payload
            )
            res.raise_for_status()
            return res.json()

    async def get_active_runs(self, cadence: str = None) -> bool:
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
            logger.warning(f"crews.yaml not found at {self.crews_yaml_path}")
            return

        try:
            with open(self.crews_yaml_path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to parse crews.yaml: {e}")
            return

        if not raw_data:
            return

        crews_list = raw_data.get("crews") or raw_data.get("dify_crews")
        if not crews_list:
            return
        for crew_data in crews_list:
            if not crew_data.get("enabled", True):
                continue
            
            # Map YAML definition into internal config
            config = CrewConfig(**crew_data)
            self._crews[config.id] = config
            
        logger.info(f"CrewRegistry loaded {len(self._crews)} active crews from configuration.")

    async def provision(self) -> None:
        """Idempotent auto-provisioning engine matching local DSLs to Dify Cloud App IDs."""
        if not self.client.api_key or "require_me" in self.client.api_key:
            logger.warning("Dify API key missing or default. Skipping auto-provisioning.")
            return

        # Load known mappings
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    self._manifest = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read manifest {self.manifest_path}: {e}")

        updates_made = False

        for crew_id, config in self._crews.items():
            mapped_uuid = self._manifest.get(crew_id)
            if not mapped_uuid:
                logger.info(f"Crew '{crew_id}' lacks Dify mapping. Triggering Auto-Provisioning...")
                dsl_path = self.agent_dir / "dify" / config.dify_dsl_file
                try:
                    new_id = await self.client.import_dsl(dsl_path)
                    if new_id:
                        self._manifest[crew_id] = new_id
                        config.dify_app_id = new_id
                        updates_made = True
                        logger.info(f"Successfully provisioned Crew '{crew_id}' with App UUID {new_id}")
                except Exception as e:
                    logger.error(f"Failed to provision {crew_id}: {e}")
            else:
                config.dify_app_id = mapped_uuid

        # Persist new UUIDs to disk
        if updates_made:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(self._manifest, f, indent=4)
                logger.info("Persisted updated .dify_app_ids.json manifest to disk.")

    def get(self, crew_id: str) -> Optional[CrewConfig]:
        """O(1) retrieval of a Crew Config."""
        return self._crews.get(crew_id)

    def list_active(self) -> List[CrewConfig]:
        """Returns ordered active crews."""
        return list(self._crews.values())

from app.config import settings

dify_client = DifyClient(base_url=settings.DIFY_API_URL, api_key=settings.DIFY_API_KEY)
agent_dir = Path(__file__).parent.parent.parent.parent / "agent"
crew_registry = CrewRegistry(agent_dir=str(agent_dir), client=dify_client)


