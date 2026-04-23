import asyncio
import json as _json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, List
import yaml
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

A) DEFAULT — routine output that belongs to THIS crew's ongoing domain:
   Add a new list to this crew's own dedicated board. The board name MUST be exactly the
   crew's own name (e.g. "Fitness" for the Fitness crew, "Dependents" for the Dependents
   crew). NEVER use a custom event or topic name as the board name under Crews.
   [ACTION: CREATE_PROJECT | NAME: Crews | DESCRIPTION: Crew outputs]   ← idempotent
   [ACTION: CREATE_BOARD | PROJECT: Crews | NAME: <exact crew name>]   ← idempotent
   [ACTION: CREATE_LIST | BOARD: <exact crew name> | NAME: <topic / phase>]
   [ACTION: CREATE_TASK | BOARD: <exact crew name> | LIST: <list name> | TITLE: <item> | DESCRIPTION: <full content>]  ← one per item; use DESCRIPTION for recipe text, multi-step instructions, or any detailed body content

B) NAMED INITIATIVE — ONLY for a one-off external event, project, or initiative that has
   a unique proper name tied to a specific occasion or goal (e.g. "Birthday 2026",
   "Marathon Training", "Q3 Roadmap", "Portugal Trip"). These are things that exist
   *independently* of any crew, have a clear start/end, and would make sense as a
   standalone project for a person who doesn't know which crew produced them.
   Create a dedicated project using that initiative name — NOT "Crews".
   [ACTION: CREATE_PROJECT | NAME: <initiative name> | DESCRIPTION: <description>]
   [ACTION: CREATE_BOARD | PROJECT: <initiative name> | NAME: <board name>]
   [ACTION: CREATE_LIST | BOARD: <board name> | NAME: <column>]  ← repeat per phase/column
   [ACTION: CREATE_TASK | BOARD: <board name> | LIST: <column> | TITLE: <item>]

Rule of thumb — when in doubt, use A:
- Routine crew output → A. Examples: meal plans, workout logs, recipe collections,
  weekly check-ins, shopping lists, health summaries, financial reports. These always
  belong on the crew's own board, even if the list has a descriptive name like
  "New Recipes", "High-Protein Meals", or "Weekly Log Apr 2026".
- One-off external initiative with a proper name → B. Testing question: could this
  stand alone as a project a non-crew person would manage? If yes → B. If it's just
  this crew's domain output with a label → A.

CRITICAL: The "Crews" project must only ever contain boards named exactly as crew IDs.
Never add a board to "Crews" with a custom name. Use option B instead.
Do NOT use any other prefix — NEVER write [Crews: ...] or [Create Task |...] — only [ACTION: ...].

CREW-SAFE ACTION TAGS ONLY:
- Crews are strictly limited to: CREATE_PROJECT, CREATE_BOARD, CREATE_LIST, CREATE_TASK, MOVE_CARD, MARK_DONE.
- NEVER emit ADD_PERSON, LEARN, REMIND, SCHEDULE_CUSTOM, PROXIMITY_TRACK, or RUN_CREW tags.
  These are reserved for the user-facing agent only.
- Do NOT add users or operators to the circle of trust. Do NOT store memories.
- For CREATE_EVENT dates, ALWAYS use the current real-world date — never hardcode past years like 2023.
"""

_STOP_WORDS = {
	"a", "an", "the", "of", "and", "or", "for", "to", "in", "on", "with",
	"at", "by", "from", "into", "is", "are", "its", "it", "that", "this",
	"be", "as", "all", "any", "per", "up", "do", "not", "no", "via", "new",
	"each", "your", "their", "has", "have", "will", "can", "they", "them",
	"but", "so", "if", "when", "then", "which", "who", "how",
}


def _crew_tokens(cfg: "CrewConfig") -> set:
	"""Return a bag-of-words for a crew using name + description + character roles."""
	parts = [cfg.name, cfg.description or ""]
	if cfg.characters:
		for ch in cfg.characters:
			parts.append(ch.get("name", ""))
			parts.append(ch.get("role", ""))
	text = " ".join(parts).lower()
	return {w for w in re.findall(r'[a-z]+', text) if w not in _STOP_WORDS and len(w) > 3}


def _jaccard(a: set, b: set) -> float:
	if not a or not b:
		return 0.0
	return len(a & b) / len(a | b)


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
	panel_exclude: Optional[List[str]] = None  # crew IDs explicitly blocked from co-running in panels
	feeds_briefing: Optional[str] = None
	schedule: Optional[str] = None
	briefing_day: Optional[str] = None
	briefing_dom: Optional[str] = None
	briefing_months: Optional[str] = None
	lead_time: Optional[int] = None
	health_context: bool = False  # If True, health.md is included in the injected personal context

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
				panel_exclude=c.get("panel_exclude"),
				feeds_briefing=c.get("feeds_briefing"),
				schedule=c.get("schedule"),
				briefing_day=c.get("briefing_day"),
				briefing_dom=c.get("briefing_dom"),
				briefing_months=c.get("briefing_months"),
				lead_time=c.get("lead_time"),
				health_context=c.get("health_context", False),
			)
			self._crews[config.id] = config
		logger.info("Registry: Successfully loaded %d active crews.", len(self._crews))
		self._compute_panel_candidates()
		await self._precache_keywords()

	async def _precache_keywords(self) -> None:
		"""Pre-calculate and cache keyword lists for all enabled languages.
		
		This avoids JIT translation/matching overhead during request resolution.
		Current priority is 'en' and 'de' as the primary deployment languages.
		"""
		languages = ["en", "de"]
		logger.info("Registry: Pre-caching keywords for %s", languages)
		
		tasks = []
		for lang in languages:
			for crew in self._crews.values():
				tasks.append(_get_effective_keywords(crew, lang))
		
		if tasks:
			await asyncio.gather(*tasks, return_exceptions=True)
		logger.info("Registry: Keyword pre-cache complete for %d crews across %s", len(self._crews), languages)

	def _compute_panel_candidates(self, top_n: int = 5, min_score: float = 0.15) -> None:
		"""Auto-compute domain-similar crew pairs via bag-of-words Jaccard on name + description + character roles.

		Run once after load(). Result cached in self._panel_candidates.
		"""
		crews = list(self._crews.values())
		vectors = {c.id: _crew_tokens(c) for c in crews}
		self._panel_candidates: Dict[str, List[str]] = {}
		for crew in crews:
			scores = [
				(other.id, _jaccard(vectors[crew.id], vectors[other.id]))
				for other in crews if other.id != crew.id
			]
			scores.sort(key=lambda x: -x[1])
			self._panel_candidates[crew.id] = [
				cid for cid, s in scores[:top_n] if s >= min_score
			]
		nonempty = {k: v for k, v in self._panel_candidates.items() if v}
		logger.info("Panel candidates (auto-computed): %s", nonempty)

	def get(self, crew_id: str) -> Optional[CrewConfig]:
		return self._crews.get(crew_id)

	def list_active(self) -> List[CrewConfig]:
		return list(self._crews.values())

AGENT_FOLDER_PATH = Path("/app/agent") if Path("/app/agent").exists() else Path(__file__).parents[4] / "agent"
crew_registry = CrewRegistry(agent_dir=str(AGENT_FOLDER_PATH))

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

# ---------------------------------------------------------------------------
# Crew Session Continuity
# ---------------------------------------------------------------------------
# Tracks the last crew that handled a message per channel, enabling follow-up
# messages to route back to the same crew within a time window even if they
# don't contain crew-specific keywords.
# Key: channel string (e.g. "telegram", "dashboard").
# Value: (crew_id, unix_timestamp).
_crew_sessions: dict[str, tuple[str, float]] = {}

_CREW_SESSION_MAX_AGE_S: float = 600  # 10 minutes


def record_crew_session(channel: str, crew_id: str) -> None:
	"""Store the active crew for a channel after a successful crew execution."""
	import time
	_crew_sessions[channel] = (crew_id, time.time())
	logger.debug("Crew session recorded: channel=%s crew=%s", channel, crew_id)


def get_active_crew_session(channel: str) -> Optional[str]:
	"""Return the crew_id if the last crew execution on this channel was
	within the session window, otherwise None."""
	import time
	entry = _crew_sessions.get(channel)
	if not entry:
		return None
	crew_id, ts = entry
	if time.time() - ts > _CREW_SESSION_MAX_AGE_S:
		return None
	return crew_id


def clear_crew_session(channel: str) -> None:
	"""Explicitly end a crew session (e.g. when a different crew is triggered)."""
	_crew_sessions.pop(channel, None)


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

# Structural Planka operations (move board, create task, delete card, etc.) are
# handled by Z's action processor and must NEVER be routed to a crew.
# Routing to a crew causes persona/dialect bleed in what should be a neutral
# one-line confirmation. Matches the current-message text only; safe patterns
# use explicit noun anchors so regex cannot backtrack on long input (CWE-1333).
_SYSTEM_ACTION_RE = re.compile(
	r'\b(?:'
	r'move\s+(?:board|card|task|list)\b'
	r'|create\s+(?:a\s+)?(?:board|card|task|list|project)\b'
	r'|delete\s+(?:a\s+)?(?:board|card|task|list|project)\b'
	r'|rename\s+(?:a\s+)?(?:board|card|task|list|project)\b'
	r'|archive\s+(?:a\s+)?(?:board|card|task|list|project)\b'
	r'|add\s+(?:a\s+)?(?:card|task)\s+to\s+(?:board|list)\b'
	r')',
	re.IGNORECASE,
)

# Messages that ask about the OUTCOME of a previous action ("did you do it?",
# "no feedback from you", "did it work?") should NEVER route to a crew — the
# crew has no context about what Z did and will respond with irrelevant domain
# content. These must always be handled by Z who has the full conversation history.
_OPERATIONAL_QUERY_RE = re.compile(
	r'\b(?:'
	r'did\s+you\s+do\s+(?:it|that)'
	r'|did\s+(?:you|it|that)\s+(?:work|go\s+through|save|add|create|happen)'
	r'|no\s+feedback\s+from\s+you'
	r'|any\s+(?:confirmation|feedback|result|update)\s+(?:from|on|about)'
	r'|confirm\s+(?:it|that|if)'
	r'|what\s+happened\s+(?:with|to)'
	r')\b',
	re.IGNORECASE,
)

# Referential words that strongly suggest the message is a follow-up refinement
# of the previous response rather than a new, unrelated request.
# "make it spicier" / "do that again" / "and now?" → continuation.
# "buy glasses" / "todo for next week" → no referential signal → no continuation.
_FOLLOWUP_SIGNALS: frozenset = frozenset([
	"it", "this", "that", "them", "those", "these",		# referential pronouns
	"again", "redo", "re-do", "once more",				# explicit redo
	"instead",											# replacement
	"now", "next", "then",								# temporal continuation ("and now?", "what next?")
	"continue", "proceed", "go on", "more",				# explicit continuation
	"ok", "okay", "sure", "fine", "great",				# acknowledgement → continue
])

# Matches the crew attribution footer added by _process_crew_stream.
_CREW_ATTRIBUTION_RE = re.compile(r'\(Reasoning by crew ([^)]+)\)', re.IGNORECASE)


def _last_attributed_crew(history: list) -> Optional[str]:
	"""Return the most recently active crew ID from the immediately preceding Z
	message, or None.

	Scans exactly 1 Z/assistant turn. If the most recent Z reply is not attributed
	to a crew (e.g. a recall response, a task confirmation, an unrelated Z answer),
	the continuation chain resets to None — preventing stale emotional-crew
	attribution from contaminating unrelated operational follow-ups like
	"did you do it?" or "no feedback from you?".

	The previous 3-turn scan was introduced to handle restart notifications but
	caused false positives: a 'life' crew reply earlier in the session would
	re-engage when the user asked a simple status question because the word "it"
	triggered _is_followup_text while the life attribution was still in range.
	Post-restart continuation is now handled by _infer_crew_from_user_history.
	"""
	for msg in reversed(history):
		if msg.get("role") not in ("z", "assistant"):
			continue
		m = _CREW_ATTRIBUTION_RE.search(msg.get("content", ""))
		# Return the crew id if found, None otherwise — stop after the first Z turn.
		return m.group(1).split(",")[0].strip() if m else None
	return None


def _is_followup_text(text: str) -> bool:
	"""Heuristic: does this message contain referential language pointing to the
	previous response?  Only short, clearly referential tokens qualify so that
	unrelated messages (e.g. 'buy glasses') are not mistakenly continued.

	Punctuation is stripped from each token so that "now?" matches "now",
	"it." matches "it", etc.
	"""
	# Strip leading/trailing punctuation from each token before comparing
	tokens = {re.sub(r'^[^\w]+|[^\w]+$', '', w) for w in text.lower().split()}
	tokens.discard("")
	return bool(tokens & _FOLLOWUP_SIGNALS)


def _keyword_matches(keywords: list, text: str) -> bool:
	"""Return True if any keyword matches as a whole word (or phrase) in text.

	Uses word-boundary anchors so that short keywords like 'eat' don't false-fire
	on unrelated words such as 'weather' or 'create'.
	Multi-word phrases (e.g. 'shopping list') are matched as exact substrings with
	boundaries on the outer edges only.
	"""
	# Cap input to prevent polynomial backtracking (CWE-1333) on adversarial strings.
	safe_text = text[:2000]
	for kw in keywords:
		pattern = r'(?<![a-z0-9])' + re.escape(kw.lower()) + r'(?![a-z0-9])'
		if re.search(pattern, safe_text):
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


async def _infer_crew_from_user_history(history: list, lang: str = "en", active_crews: Optional[List["CrewConfig"]] = None) -> Optional[str]:
	"""Scan recent user messages for crew keyword matches.

	Fallback for when _last_attributed_crew finds no attribution (e.g. legacy
	messages, post-restart session where attribution wasn't yet stored in DB).

	Strategy: scan older substantive messages first (the ones that established
	original intent), skipping follow-up signals like "and now?" that have no
	domain content of their own. Returns the crew whose keywords appear in the
	most-recent substantive user message.
	"""
	# Collect up to 6 recent user turns, oldest-first (so original intent wins
	# when we iterate), filtering out pure follow-up messages.
	raw = [m for m in reversed(history) if m.get("role") == "user"][:6]
	# Reverse again so we go oldest→newest; skip messages that are entirely
	# follow-up signals (no domain content to infer from).
	substantive = [
		m for m in reversed(raw)
		if not _is_followup_text(m.get("content", ""))
		   or len(m.get("content", "").split()) > 6  # long messages may carry both
	]
	if not substantive:
		return None

	if active_crews is None:
		active_crews = crew_registry.list_active()

	# Pre-fetch all effective keywords in parallel to minimize latency.
	kw_tasks = [_get_effective_keywords(crew, lang) for crew in active_crews]
	kw_lists = await asyncio.gather(*kw_tasks)
	crew_keywords = list(zip(active_crews, kw_lists))

	# For each substantive message (newest-first so most-recent context wins),
	# check which crew keywords it triggers.
	for msg in substantive:
		content_lower = msg.get("content", "").lower()
		for crew, effective in crew_keywords:
			if effective and _keyword_matches(effective, content_lower):
				return crew.id
	return None


async def resolve_active_crew(history: list, user_text: str, lang: str = "en") -> Optional[str]:
	"""Return a crew_id if this message should be routed to a crew automatically.

	Algorithm (in order of priority):
	-1. Operational query guard — questions about the result of a previous action
	    ("did you do it?", "no feedback from you", "did it work?") are never
	    routed to crews. The crew has no context about what Z did and would
	    respond with irrelevant domain content. Z handles these with full history.
	0. Crew ID direct match — if the user's message contains the exact crew id as
	   a standalone word (e.g. "hi dependents"), route there immediately.
	1. Keyword match in current message — base English keywords plus any
	   auto-translated keywords for the user's configured language.
	2. Single-turn continuation — if the immediately preceding Z reply was
	   attributed to a crew AND the current message contains referential language
	   (e.g. "it", "that", "again"), continue with that crew.
	   Unrelated messages without such signals (e.g. "buy glasses") return None.
	Returns crew_id string or None (let Z handle it normally).
	"""
	lower_text = user_text.lower()

	# -2. System action guard: structural Planka operations (move/create/delete board,
	# card, task, list, project) are handled by Z's action processor. Routing to any
	# crew causes persona/dialect bleed in what must be a plain, language-correct
	# confirmation. Bypass ALL crew routing — session continuity included.
	if _SYSTEM_ACTION_RE.search(user_text[:500]):
		logger.debug("Router: system action detected — bypassing crew routing")
		return None

	# -1. Operational query guard: status / confirmation questions skip all crew routing.
	if _OPERATIONAL_QUERY_RE.search(user_text[:2000]):
		logger.debug("Router: operational query detected — bypassing crew routing")
		return None

	# 0. Priority: explicit crew ID in message — beats keyword order entirely.
	active_crews = crew_registry.list_active()
	for crew in active_crews:
		pattern = r'(?<![a-z0-9])' + re.escape(crew.id.lower()) + r'(?![a-z0-9])'
		if re.search(pattern, lower_text):
			return crew.id

	# 1. Keyword match on current message.
	# Pre-fetch all effective keywords in parallel.
	kw_tasks = [_get_effective_keywords(crew, lang) for crew in active_crews]
	kw_lists = await asyncio.gather(*kw_tasks)
	for crew, effective in zip(active_crews, kw_lists):
		if effective and _keyword_matches(effective, lower_text):
			return crew.id

	# 1.5. Session continuity: if no keyword matched but the user interacted
	# with a crew recently (within 10 min), route the follow-up back to that
	# crew. This covers natural follow-ups like "but how to make them money?"
	# that lack specific crew keywords.
	# Single-user system: check all channels for a recent session.
	session_crew: Optional[str] = None
	for ch in ("telegram", "dashboard", "whatsapp"):
		session_crew = get_active_crew_session(ch)
		if session_crew:
			break
	if session_crew and crew_registry.get(session_crew):
		logger.info("Crew session continuity: routing to '%s' (no keyword match, within time window)", session_crew)
		return session_crew

	# 2. Attribution-based continuation: most recent Z reply attributed to a crew
	# + referential language in current message → continue with that crew.
	last_crew = _last_attributed_crew(history)
	if last_crew and _is_followup_text(lower_text):
		if crew_registry.get(last_crew):
			return last_crew

	# 3. Keyword-inferred continuation (fallback): no attribution in history (e.g.
	# legacy messages, post-restart) but recent USER messages contain crew keywords
	# AND current message is a follow-up signal. Handles "and now?" after
	# "i am feeling drained" even across restarts with no attribution in DB.
	if _is_followup_text(lower_text):
		inferred = await _infer_crew_from_user_history(history, lang, active_crews=active_crews)
		if inferred and crew_registry.get(inferred):
			return inferred

	return None


async def resolve_active_crews(history: list, user_text: str, lang: str = "en", max_crews: int = 5) -> list:
	"""Return an ordered list of up to `max_crews` crew IDs for this message.

	The first entry is the primary crew (same algorithm as resolve_active_crew).
	Subsequent entries are drawn from auto-computed domain-similarity candidates
	(see CrewRegistry._compute_panel_candidates). Any crew listed in the primary's
	`panel_exclude` config is skipped. Secondary crews MUST also keyword-match the
	current user message — purely semantic similarity is not sufficient. Only crews
	that exist in the registry are included.
	Returns an empty list if no crew matches.
	"""
	primary = await resolve_active_crew(history, user_text, lang=lang)
	if not primary:
		return []

	result = [primary]
	cfg = crew_registry.get(primary)
	exclude = set(cfg.panel_exclude or []) if cfg else set()
	candidates = crew_registry._panel_candidates.get(primary, [])
	lower_text = user_text.lower()
	
	candidate_configs = [crew_registry.get(sid) for sid in candidates if sid != primary and sid not in exclude]
	candidate_configs = [c for c in candidate_configs if c]
	
	if candidate_configs:
		kw_tasks = [_get_effective_keywords(cc, lang) for cc in candidate_configs]
		kw_lists = await asyncio.gather(*kw_tasks)
		for secondary_cfg, secondary_kws in zip(candidate_configs, kw_lists):
			if len(result) >= max_crews:
				break
			# Only include a secondary crew if it also keyword-matches the current message.
			# This prevents domain-similarity alone from pulling in unrelated crews.
			if secondary_kws and _keyword_matches(secondary_kws, lower_text):
				result.append(secondary_cfg.id)
	return result
