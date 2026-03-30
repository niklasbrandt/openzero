import logging
from pathlib import Path
from typing import Optional, Dict, List
import yaml # type: ignore
from pydantic import BaseModel

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
	instructions: Optional[str] = None
	feeds_briefing: Optional[str] = None
	schedule: Optional[str] = None
	briefing_day: Optional[str] = None
	briefing_dom: Optional[str] = None
	briefing_months: Optional[str] = None
	lead_time: Optional[int] = None

class CrewRegistry:
	def __init__(self, agent_dir: str):
		self.agent_dir = Path(agent_dir)
		self.crews_yaml_path = self.agent_dir / "crews.yaml"
		self._crews: Dict[str, CrewConfig] = {}

	async def load(self) -> None:
		logger.info("Registry: Loading crews from %s", self.crews_yaml_path)
		if not self.crews_yaml_path.exists():
			logger.warning("Registry: %s NOT FOUND", self.crews_yaml_path)
			return
		with open(self.crews_yaml_path, "r", encoding="utf-8") as f:
			raw_data = yaml.safe_load(f)
		
		# Native Registry Manifest
		crews_list = raw_data.get("crews", [])
		logger.info("Registry: Found %d potential crews in YAML", len(crews_list))
		for c in crews_list:
			if not isinstance(c, dict) or not c.get("enabled", True): continue
			# Create config, ignoring any leftover Dify fields
			config = CrewConfig(
				id=c.get("id"),
				name=c.get("name"),
				type=c.get("type"),
				group=c.get("group"),
				description=c.get("description"),
				enabled=c.get("enabled", True),
				instructions=c.get("instructions"),
				feeds_briefing=c.get("feeds_briefing"),
				schedule=c.get("schedule"),
				briefing_day=c.get("briefing_day"),
				briefing_dom=c.get("briefing_dom"),
				briefing_months=c.get("briefing_months"),
				lead_time=c.get("lead_time")
			)
			self._crews[config.id] = config
		logger.info("Registry: Successfully loaded %d active crews.", len(self._crews))

	def get(self, crew_id: str) -> Optional[CrewConfig]:
		return self._crews.get(crew_id)

	def list_active(self) -> List[CrewConfig]:
		return list(self._crews.values())

AGENT_FOLDER_PATH = Path("/app/agent") if Path("/app/agent").exists() else Path(__file__).parents[4] / "agent"
crew_registry = CrewRegistry(agent_dir=str(AGENT_FOLDER_PATH))
