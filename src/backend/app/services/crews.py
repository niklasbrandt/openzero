import json as _json
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
Every crew MUST save its output to Planka using ONLY the [ACTION: ...] tag format below.
Emit ALL tags on separate lines after all prose — never inside text, never mid-response.

SCOPE DECISION — choose the minimal structure that fits the output:

A) DEFAULT — routine output, a single new topic, or a short list of items:
   Add a new list to the crew's existing dedicated board. No new project needed.
   [ACTION: CREATE_PROJECT | NAME: Crews | DESCRIPTION: Crew outputs]   ← idempotent
   [ACTION: CREATE_BOARD | PROJECT: Crews | NAME: <crew name, e.g. Fitness>]   ← idempotent
   [ACTION: CREATE_LIST | BOARD: <crew board> | NAME: <topic / phase>]
   [ACTION: CREATE_TASK | BOARD: <crew board> | LIST: <list name> | TITLE: <item>]  ← one per item

B) MAJOR NEW INITIATIVE — only if the topic genuinely warrants its own project space:
   i.e. it requires multiple boards AND/OR multiple lists with many tasks AND represents a
   sustained long-term domain (e.g. a full multi-phase training plan, a business roadmap,
   a multi-week protocol). In that case, create a dedicated project:
   [ACTION: CREATE_PROJECT | NAME: <initiative name> | DESCRIPTION: <description>]
   [ACTION: CREATE_BOARD | PROJECT: <initiative> | NAME: <board name>]
   [ACTION: CREATE_LIST | BOARD: <board name> | NAME: <column>]  ← repeat per phase/column
   [ACTION: CREATE_TASK | BOARD: <board name> | LIST: <column> | TITLE: <item>]

Rule of thumb: if the output fits in one or a few columns → use A (list in crew board).
Only escalate to B when the scope is truly multi-board or a brand new long-term domain.

Do NOT create top-level projects for routine crew output (no standalone "Fitness" project
for a session log, no "Nutrition" project for today's recipes — those are just new lists
inside the crew's board).
Do NOT use any other prefix — NEVER write [Crews: ...] or [Create Task |...] — only [ACTION: ...].

CREW-SAFE ACTION TAGS ONLY:
- Crews are strictly limited to: CREATE_PROJECT, CREATE_BOARD, CREATE_LIST, CREATE_TASK, MOVE_CARD, MARK_DONE.
- NEVER emit ADD_PERSON, LEARN, REMIND, SCHEDULE_CUSTOM, PROXIMITY_TRACK, or RUN_CREW tags.
  These are reserved for the user-facing agent only.
- Do NOT add users or operators to the circle of trust. Do NOT store memories.
- For CREATE_EVENT dates, ALWAYS use the current real-world date — never hardcode past years like 2023.
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
	keywords: Optional[List[str]] = None  # trigger words for auto-routing from free-text (English)
	keywords_i18n: Optional[Dict[str, List[str]]] = None  # per-language keyword overrides, e.g. {"de": [...], "fr": [...]}
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
				keywords_i18n=c.get("keywords_i18n"),
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

# ISO 639-1 code → human-readable language name for the translation prompt
_LANG_NAMES: dict[str, str] = {
	"de": "German", "fr": "French", "es": "Spanish", "it": "Italian",
	"pt": "Portuguese", "nl": "Dutch", "pl": "Polish", "ru": "Russian",
	"ja": "Japanese", "zh": "Chinese (Simplified)", "ko": "Korean",
	"hi": "Hindi", "ar": "Arabic", "sv": "Swedish", "no": "Norwegian",
	"da": "Danish", "fi": "Finnish", "tr": "Turkish",
}

# In-process cache: (crew_id, lang) -> translated keyword list.
# Populated lazily on first resolve; lives for the lifetime of the process.
_kw_translation_cache: dict[tuple, list] = {}


async def _translate_keywords_to_lang(crew_id: str, lang: str, keywords: list) -> list:
	"""Translate English crew trigger-keywords to `lang` via the fast local LLM.

	The result is cached in memory so translation happens at most once per
	crew/language pair per process lifetime.  Falls back to the original
	English keywords silently if the LLM is unavailable or returns bad JSON.
	"""
	cache_key = (crew_id, lang)
	if cache_key in _kw_translation_cache:
		return _kw_translation_cache[cache_key]

	lang_name = _LANG_NAMES.get(lang, lang)
	try:
		from app.services.llm import chat  # lazy import avoids circular deps
		prompt = (
			f"Translate each English keyword/phrase below to {lang_name}. "
			f"Return ONLY a valid JSON array of translated strings — no explanation, no markdown.\n"
			f"Input: {_json.dumps(keywords)}"
		)
		raw = await chat(
			prompt,
			system_override="You are a translation assistant. Reply with only a valid JSON array of strings.",
			tier="local",
			sanitize=False,
			_feature="crew_kw_translate",
		)
		# Strip markdown code fences if the model wraps the output
		raw = raw.strip()
		if raw.startswith("```"):
			lines = raw.split("\n")
			raw = "\n".join(lines[1:]).rsplit("```", 1)[0]
		translated = _json.loads(raw.strip())
		if isinstance(translated, list):
			result = [str(t).lower() for t in translated if t]
			_kw_translation_cache[cache_key] = result
			logger.debug("Crew '%s' keywords translated to %s: %s", crew_id, lang, result)
			return result
	except Exception as exc:
		logger.debug("Keyword translation failed for crew '%s' lang '%s': %s", crew_id, lang, exc)

	# Fallback: cache English list under this lang key so we don't retry indefinitely
	_kw_translation_cache[cache_key] = keywords
	return keywords

def _keyword_matches(keywords: list, text: str) -> bool:
	"""Return True if any keyword matches as a whole word (or phrase) in text.

	Uses word-boundary anchors so that short keywords like 'eat' don't false-fire
	on unrelated words such as 'weather' or 'create'.
	Multi-word phrases (e.g. 'shopping list') are matched as exact substrings with
	boundaries on the outer edges only.
	"""
	for kw in keywords:
		pattern = r'(?<![a-z0-9])' + re.escape(kw.lower()) + r'(?![a-z0-9])'
		if re.search(pattern, text):
			return True
	return False


async def _get_effective_keywords(crew: "CrewConfig", lang: str) -> list:
	"""Return the keyword list to use for `crew` in the given language.

	Priority:
	1. `keywords_i18n[lang]` — explicit manual override in YAML (fastest, no LLM call).
	2. Auto-translated via fast local LLM (lazy, cached per crew+lang in memory).
	3. English `keywords` fallback if LLM unavailable.
	"""
	base = list(crew.keywords or [])
	if not base:
		return []
	if lang == "en":
		return base
	# Manual override in YAML takes priority over auto-translation
	if crew.keywords_i18n:
		manual = crew.keywords_i18n.get(lang)
		if manual:
			return base + [k.lower() for k in manual]
	# Auto-translate English keywords to the user's configured language
	return await _translate_keywords_to_lang(crew.id, lang, base)


async def resolve_active_crew(history: list, user_text: str, lang: str = "en") -> Optional[str]:
	"""Return a crew_id if this message should be routed to a crew automatically.

	Algorithm (in order of priority):
	1. Direct keyword match in current message — strongest signal, route immediately.
	   For non-English sessions the English keywords are auto-translated to the
	   user's configured language via the fast local LLM (result cached in memory).
	2. Score the last ~8 history entries (user + Z) holistically:
	   - A Z reply with crew attribution footer scores +3 for that crew.
	   - A user message whose content matches a crew's keywords scores +1.
	   Highest-scoring crew wins if score >= 2.
	Returns crew_id string or None (let Z handle it normally).
	"""
	# 1. Immediate keyword match on current message.
	lower_text = user_text.lower()
	for crew in crew_registry.list_active():
		effective = await _get_effective_keywords(crew, lang)
		if effective and _keyword_matches(effective, lower_text):
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
				effective = await _get_effective_keywords(crew, lang)
				if effective and _keyword_matches(effective, lower_content):
					scores[crew.id] = scores.get(crew.id, 0) + 1

	if scores:
		best = max(scores, key=lambda k: scores[k])
		if scores[best] >= 2:
			return best

	return None
