import logging
import re
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
4. Always respect the user's local unit system (Metric/Celsius for EU) and only enforce health constraints explicitly provided in their personal vault.

PLANKA PERSISTENCE (mandatory for all crews):
- Every crew MUST persist tangible output into Planka using the action tags provided.
- You are free to invent the most semantically appropriate project, board, column, and card
  structure for the task at hand. There is no required schema — use your judgment.
- If a project or board does not exist yet, create it first with CREATE_PROJECT / CREATE_BOARD.
- If a column does not exist, create it with CREATE_LIST before adding cards to it.
- One card per discrete item (recipe, plan, task, finding, entry). Put the full content in the card title or description.
- If the user asks to add a new column or restructure the board, comply immediately with CREATE_LIST / MOVE_CARD.
- NEVER place content from prior chat history (task names, project names, unrelated cards) into a domain-specific column (e.g. do not put a software task name into a Recipes column).
- ALWAYS write a clear human-readable summary of what you did FIRST (e.g. "Added 3 recipes to your Nutrition board"), then emit the action tags on new lines at the end. The user must see a confirmation — never produce action tags with no accompanying text.

CREW-SAFE ACTION TAGS ONLY:
- Crews are strictly limited to Planka scaffolding tags: CREATE_PROJECT, CREATE_BOARD, CREATE_LIST, CREATE_TASK, MOVE_CARD, MARK_DONE.
- NEVER emit ADD_PERSON, LEARN, REMIND, SCHEDULE_CUSTOM, SCHEDULE_CREW, PROXIMITY_TRACK, or RUN_CREW tags.
  ADD_PERSON and LEARN are reserved for the user-facing agent only — emitting them from a crew is a hallucination error.
- The people, facts, and names you see in persona or conversation context are provided for domain awareness only.
  Do NOT add users, operators, or anyone to the circle of trust. Do NOT store memories.
"""

class CrewConfig(BaseModel):
	id: str
	name: str
	type: str
	group: str
	description: str
	enabled: bool = True
	instructions: Optional[str] = None
	characters: Optional[List[Dict[str, str]]] = None
	keywords: Optional[List[str]] = None  # trigger words for auto-routing from free-text
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
				characters=c.get("characters"),
				keywords=c.get("keywords"),
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

# Regex that matches the crew attribution footer Z appends to every crew reply.
# Format: "Reasoning by crew <id>"
_CREW_ATTRIBUTION_RE = re.compile(r"Reasoning by crew ([a-zA-Z0-9_-]+)", re.IGNORECASE)

def resolve_active_crew(history: list, user_text: str) -> Optional[str]:
	"""Return a crew_id if this message should be routed to a crew automatically.

	Algorithm (in order of priority):
	1. Direct keyword match in current message — strongest signal, route immediately.
	2. Score the last ~8 history entries (user + Z) holistically:
	   - A Z reply with crew attribution footer scores +3 for that crew.
	   - A user message whose content matches a crew's keywords scores +1.
	   Highest-scoring crew wins if score >= 2. This lets a crew session
	   survive an unrelated message in between without needing an explicit command.
	Returns crew_id string or None (let Z handle it normally).
	"""
	# 1. Immediate keyword match on current message.
	lower_text = user_text.lower()
	for crew in crew_registry.list_active():
		if crew.keywords and any(kw.lower() in lower_text for kw in crew.keywords):
			return crew.id

	# 2. Holistic scoring over recent history.
	recent = history[-8:] if len(history) > 8 else history
	scores: dict[str, int] = {}
	for msg in recent:
		content = msg.get("content", "")
		role = msg.get("role", "")
		if role == "z":
			m = _CREW_ATTRIBUTION_RE.search(content)
			if m:
				crew_id = m.group(1).strip()
				if crew_registry.get(crew_id):
					scores[crew_id] = scores.get(crew_id, 0) + 3
		elif role == "user":
			lower_content = content.lower()
			for crew in crew_registry.list_active():
				if crew.keywords and any(kw.lower() in lower_content for kw in crew.keywords):
					scores[crew.id] = scores.get(crew.id, 0) + 1

	if scores:
		best = max(scores, key=lambda k: scores[k])
		if scores[best] >= 2:
			return best

	return None
