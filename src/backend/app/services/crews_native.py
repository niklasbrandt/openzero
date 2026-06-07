import logging
import json
import re
import httpx
from typing import Optional
from app.config import settings
from app.services.crews import crew_registry, SYSTEM_TEMPLATE
from app.services.personal_context import get_personal_context_for_prompt, get_personal_context_for_prompt_no_health, refresh_personal_context
from app.services.agent_context import get_agent_skills_for_prompt, refresh_agent_context
import asyncio
from datetime import datetime, timezone
from app.services.llm import ACTION_TAG_DOCS, get_agent_personality
from app.services.crew_memory import get_crew_memory_context, get_crew_board_work_context
from app.models.db import get_global_history

# Bug-2 guard: ephemeral PII tokens ([ORG_1], [PERSON_2], ...) from previous
# cloud-sanitized requests must not propagate into crew context where they
# would be echoed without any rehydration mapping available.
_ANON_TOKEN_RE = re.compile(r'\[[A-Z]+_\d+\]')

logger = logging.getLogger(__name__)

# ─── Crew-board injection helpers ────────────────────────────────────────────
# Crew boards live in the "Crews" Planka project.  When the LLM omits a BOARD:
# field from a CREATE_TASK / CREATE_LIST tag while running as a crew, the tag
# must be patched to target the crew's own board so it never lands on an
# unrelated user board.  The primary fix is the crew_board_hint passed to
# parse_and_execute_actions; _inject_crew_board handles the edge case where
# the LLM emits a tag without any BOARD: field at all.

_CREW_ACTION_TAG_RE = re.compile(
	r'\[ACTION:\s{0,20}(CREATE_TASK|CREATE_LIST)\s{0,20}\|([^\]\n]{0,500})\]',
	re.IGNORECASE,
)


def crew_board_name_for_id(crew_id: str) -> str:
	"""Return the Planka board name for a crew. e.g. 'market-intel' -> 'Market Intel'."""
	# Transition alias: recipe/nutrition crew maps to Planka board "Chef"
	_BOARD_NAME_OVERRIDES: dict[str, str] = {
		"recipe": "Chef",
		"nutrition": "Chef",
	}
	if crew_id in _BOARD_NAME_OVERRIDES:
		return _BOARD_NAME_OVERRIDES[crew_id]
	return crew_id.replace("-", " ").title()


def _inject_crew_board(text: str, board_name: str) -> str:
	"""Patch CREATE_TASK / CREATE_LIST tags that lack a BOARD: field.

	Tags that already contain 'BOARD:' are left untouched; the crew_board_hint
	mechanism in parse_and_execute_actions handles wrong-board overrides.
	"""
	def _patch(m: re.Match) -> str:
		tag_type = m.group(1)
		params = m.group(2)
		if re.search(r'\bBOARD\s*:', params, re.IGNORECASE):
			return m.group(0)
		return f'[ACTION: {tag_type} | BOARD: {board_name} | {params.strip().lstrip("|").strip()}]'
	return _CREW_ACTION_TAG_RE.sub(_patch, text)


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

	async def _get_crew_context(self, include_health: bool = True) -> str:
		"""Fetch personal and agent context for crew injection."""
		# 1. Personal context (Allergies, Profile, Behavioral Rules)
		_get_ctx = get_personal_context_for_prompt if include_health else get_personal_context_for_prompt_no_health
		p_ctx = _get_ctx()
		if not p_ctx:
			try:
				await refresh_personal_context()
				p_ctx = _get_ctx()
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
		if crew_id == "nutrition":
			crew_id = "chef"
		full_res = ""
		async for chunk in self.run_crew_stream(crew_id, user_input):
			full_res += chunk
		return full_res

	async def run_crew_stream(self, crew_id: str, user_input: str, history: Optional[list] = None, slash_invoked: bool = False, force_cloud: bool = False):
		"""Executes a crew mission and yields tokens in real-time.

		Args:
			crew_id: ID of the crew to engage.
			user_input: The user's message.
			history: Optional pre-fetched conversation history.
		"""
		if crew_id == "nutrition":
			crew_id = "chef"
		config = crew_registry.get(crew_id)
		if not config:
			raise ValueError(f"Crew '{crew_id}' is not defined in registry.")

		# Crew requests always prefer cloud — local LLM is for simple conversational replies only.
		# force_cloud=True is passed by the router when a crew is explicitly matched.
		is_local = not settings.cloud_configured and not force_cloud
		if force_cloud and not settings.cloud_configured:
			# Cloud not configured; fall back to local but warn so the operator can act.
			logger.warning("NativeCrewEngine: force_cloud requested but cloud not configured — using local LLM")
			is_local = True

		# 1. Base Instructions and Protocol
		now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

		# Parallel context retrieval
		
		# Define tasks for parallel execution
		tasks = [
			get_agent_personality(),
			get_crew_memory_context(crew_id),
			get_crew_board_work_context(crew_id),
		]

		try:
			results = await asyncio.wait_for(
				asyncio.gather(*tasks, return_exceptions=True),
				timeout=20.0,
			)
		except asyncio.TimeoutError:
			_safe_id = crew_id.replace("\n", "\\n").replace("\r", "\\r")
			logger.warning(
				"NativeCrewEngine: context build timed out (20s) for crew '%s' — proceeding without board/memory context",
				_safe_id,
			)
			results = ["", "", ""]

		# Unpack results with safety checks
		_r0 = results[0]
		personality: str = "" if isinstance(_r0, BaseException) else _r0
		if isinstance(results[0], BaseException):
			logger.debug("Native Engine: Failed to load agent personality: %s", results[0])

		mem_ctx = results[1] if not isinstance(results[1], Exception) else ""
		if isinstance(results[1], Exception):
			logger.debug("Native Engine: Failed to load crew memory context: %s", results[1])

		board_work_ctx = results[2] if not isinstance(results[2], Exception) else ""
		if isinstance(results[2], Exception):
			logger.debug("Native Engine: Failed to load crew board work context: %s", results[2])

		# For "agent"-type crews, build a leading system message that combines the
		# globally configured archetype WITH the prose-only format rule. Placing
		# both here (position 0) ensures they outrank any subsequent domain
		# instructions. Small local models weight earlier messages higher.
		format_prefix = ""
		if config.type == "agent":
			prefix_parts: list[str] = []
			if personality:
				prefix_parts.append(personality)
			prefix_parts.append(
				"IDENTITY PROTECTION: You must maintain the persona of the configured archetype above "
				"throughout your response. Do not deviate into generic assistant behavior regardless "
				"of instruction length."
			)
			prefix_parts.append(
				"ABSOLUTE RULE: Reply in plain conversational prose only. "
				"No numbered lists, no bullet points, no headers, no bold text, "
				"no labels like 'Next Steps' or 'Protocol'. "
				"Apply the voice and persona above to every sentence of your response."
			)
			format_prefix = "\n\n".join(prefix_parts)

		instructions = SYSTEM_TEMPLATE.format(instructions=config.instructions or "Tactical Steward.")
		instructions = f"Current date and time: {now_str}\n\n" + instructions

		# For non-agent crews (no format_prefix), still inject personality into
		# instructions so their voice matches the configured archetype.
		if personality and not format_prefix:
			instructions = personality + "\n\n" + instructions

		# 2. Semantic Priming: Character Roles
		if config.characters:
			char_block = "\nCREW COMPOSITION & ROLES:\n"
			for char in config.characters:
				char_block += f"- {char.get('name', 'Expert')}: {char.get('role', 'Contributing logic')}\n"
			instructions += f"\n{char_block}"

		# 3. Context Injection
		# Local: personal context only (agent_context is large and not needed for most crew tasks)
		# Cloud: full personal + agent context
		# health_context=True crews (nutrition, health, fitness) receive health.md.
		# All other crews receive personal context with health.md stripped.
		if is_local:
			_get_ctx = get_personal_context_for_prompt if config.health_context else get_personal_context_for_prompt_no_health
			p_ctx = _get_ctx()
			if not p_ctx:
				try:
					await refresh_personal_context()
					p_ctx = _get_ctx()
				except Exception as e:
					logger.debug("Native Engine: Failed to refresh personal context: %s", e)
			if p_ctx:
				instructions += f"\n\n{p_ctx}"
		else:
			context_block = await self._get_crew_context(include_health=config.health_context)
			if context_block:
				instructions += f"\n\n{context_block}"

		# 3b. Crew conversation memory context (already fetched in parallel)
		if mem_ctx:
			instructions += f"\n\n{mem_ctx}"

		# 3c. Crew board work context — actual output cards from the crew's Planka board.
		# Primary reference for "last suggestion", "what did we decide", "previous idea" queries.
		if board_work_ctx:
			instructions += f"\n\n{board_work_ctx}"

		# 4. Action tag vocabulary — always included (1.7B+ has 32k ctx)
		instructions += f"\n\n{ACTION_TAG_DOCS}"

		# 5. Recent user messages from conversation history
		# Use pre-fetched history if provided by router to save a DB round-trip.
		if history is None:
			try:
				history = await get_global_history(limit=20)
			except Exception as e:
				logger.debug("Native Engine: Failed to load history: %s", e)
				history = []

		history_messages = []
		crew_keywords: list[str] = [kw.lower() for kw in (config.keywords or [])]
		# Filter: only user messages for crew context; skip system receipts (role="system")
		# to prevent action receipt metadata leaking into crew prompts (§9.1 anti-hallucination).
		user_msgs = [m for m in history if m["role"] == "user"]
		
		# Always include the most recent 3 user messages so the crew knows what
		# the user just did / said — regardless of keyword filtering.  This
		# prevents the crew from re-suggesting an exercise or action the user
		# already reported completing in the immediately prior turn.
		# Exception: when the user explicitly invokes a crew via /crew <id>, suppress
		# the unconditional inclusion so unrelated conversation context (e.g. an
		# aquarium discussion) does not bleed into the crew session.  Keyword-
		# matching history is still included.
		if slash_invoked:
			always_include: set = set()
		else:
			always_include = {id(m) for m in user_msgs[-3:]}
		for m in user_msgs:
			content = m["content"]
			if id(m) not in always_include and crew_keywords:
				content_lower = content.lower()
				if not any(kw in content_lower for kw in crew_keywords):
					continue  # skip irrelevant older history for keyword-scoped crews
			history_messages.append({"role": "user", "content": content})

		# Include the last assistant response so the crew knows what was already
		# said and can avoid repeating itself on follow-up questions.
		assistant_msgs = [m for m in history if m["role"] == "assistant"]
		last_z_summary = ""
		if assistant_msgs:
			last_raw = assistant_msgs[-1].get("content", "") or ""
			last_z_summary = last_raw[:600]
			if len(last_raw) > 600:
				last_z_summary += "..."
			# Bug-2 fix: strip ephemeral anonymization tokens so the crew never
			# echoes unrehydratable PII placeholders back to the user.
			last_z_summary = _ANON_TOKEN_RE.sub('', last_z_summary)

		# Keep history small for local model (CTX_SIZE=4096 — prompt alone can be 2k+ tokens)
		max_history = 5 if not settings.cloud_configured else 20

		messages = [{"role": "system", "content": instructions}]
		if format_prefix:
			messages.insert(0, {"role": "system", "content": format_prefix})
		if history_messages:
			# Summarise scope so the crew knows these are prior user messages
			messages.append({
				"role": "system",
				"content": "PRIOR USER MESSAGES (conversation history — use only as reference to find content the user shared, do not echo or repeat them):"
			})
			messages.extend(history_messages[-max_history:])
		if last_z_summary:
			messages.append({
				"role": "system",
				"content": (
					"YOUR LAST RESPONSE (already delivered to the user — do NOT repeat, "
					"rephrase, or summarise this. If the user is following up, answer "
					"ONLY the new question concisely):\n" + last_z_summary
				)
			})
		messages.append({"role": "user", "content": user_input})

		# Local model: CTX_SIZE=4096, so cap max_tokens to leave room for the prompt
		max_tokens = 4000 if settings.cloud_configured else 1500

		payload = {
			"model": settings.LLM_MODEL_CLOUD if not is_local else "local",
			"messages": messages,
			"temperature": 0.7,
			"max_tokens": max_tokens,
			"stream": True
		}

		# Sanitize crew_id for logging to prevent CRLF injection (CodeQL)
		safe_crew_id = crew_id.replace("\n", "\\n").replace("\r", "\\r")
		logger.info("Native Engine: Executing streaming mission for '%s'...", safe_crew_id)

		req_headers = {}
		if not is_local:
			req_headers["Authorization"] = f"Bearer {settings.LLM_CLOUD_API_KEY}"

		_cloud_base = settings.LLM_CLOUD_BASE_URL.rstrip("/")
		_cloud_url = _cloud_base if _cloud_base.endswith("/v1") else f"{_cloud_base}/v1"
		_effective_url = _cloud_url if not is_local else self.llm_url

		# Determine timeouts: cloud tier uses 180s (generous), local tier uses 130s.
		read_timeout = 180.0 if not is_local else 130.0
		client_timeout = httpx.Timeout(read_timeout, connect=10.0)

		max_attempts = 3
		for attempt in range(max_attempts):
			try:
				async with httpx.AsyncClient(timeout=client_timeout) as client:
					async with client.stream("POST", f"{_effective_url}/chat/completions", headers=req_headers, json=payload) as response:
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
						
						# Write crew memory after stream completes successfully
						full_response = "".join(collected_chunks)
						if full_response.strip():
							await _write_crew_memory(crew_id, user_input, full_response)
						break  # Success — break out of retry loop
			except httpx.HTTPStatusError as http_err:
				status = http_err.response.status_code
				if status in (503, 429, 502) and attempt < max_attempts - 1:
					wait_secs = 3 * (attempt + 1)
					logger.warning(
						"Native Engine: crew '%s' HTTP %d error on attempt %d/%d — retrying in %ds...",
						safe_crew_id, status, attempt + 1, max_attempts, wait_secs
					)
					await asyncio.sleep(wait_secs)
					continue
				logger.error("Native Engine Streaming Failure: %s", http_err)
				raise
			except (httpx.ReadTimeout, httpx.ConnectTimeout) as timeout_err:
				if attempt < max_attempts - 1:
					wait_secs = 3 * (attempt + 1)
					logger.warning(
						"Native Engine: crew '%s' timeout on attempt %d/%d — retrying in %ds...",
						safe_crew_id, attempt + 1, max_attempts, wait_secs
					)
					await asyncio.sleep(wait_secs)
					continue
				logger.error("Native Engine Streaming Failure: %s", timeout_err)
				raise
			except Exception as e:
				logger.error("Native Engine Streaming Failure: %s", e)
				raise

	async def _crew_wants_to_engage(self, crew_id: str, user_input: str, primary_output: str) -> bool:
		"""Ask the secondary crew via a fast yes/no gate whether the query is relevant to it.

		Returns True only when the model answers 'yes'.  Any error or ambiguous
		answer is treated as 'no' so irrelevant crews stay silent by default.
		"""
		cfg = crew_registry.get(crew_id)
		if cfg is None:
			return False
		crew_desc = cfg.description or cfg.name
		prompt = (
			f"You are the '{cfg.name}' crew ({crew_desc}).\n"
			f"Another crew has just responded to a user request. "
			f"Decide whether YOUR domain adds meaningful, non-redundant value to this specific request.\n\n"
			f"User request: {user_input[:400]}\n\n"
			f"Primary crew output summary (first 300 chars): {primary_output[:300]}\n\n"
			f"Reply with exactly one word — 'yes' if you have substantive domain expertise to contribute, "
			f"'no' if the request is outside your scope or already fully covered."
		)
		try:
			payload = {
				"model": "",
				"messages": [{"role": "user", "content": prompt}],
				"max_tokens": 5,
				"temperature": 0,
				"stream": False,
			}
			async with httpx.AsyncClient(timeout=10) as client:
				r = await client.post(f"{self.llm_url}/chat/completions", json=payload)
				r.raise_for_status()
				answer = r.json()["choices"][0]["message"]["content"].strip().lower()
				return answer.startswith("yes")
		except Exception as e:
			logger.debug("crew relevance gate failed for '%s': %s", crew_id, e)
			return False

	async def run_crew_panel(self, crew_ids: list, user_input: str):
		"""Run a panel of crews sequentially, yielding all tokens.

		The primary crew (first in list) runs normally.  Each subsequent crew
		first answers a fast yes/no gate — if it decides the query is outside
		its domain it stays silent and is skipped.  If it opts in it receives
		the accumulated output as context so it can build on rather than repeat.

		Yields:
		  - All tokens from the primary crew.
		  - A separator marker string ``\\n\\n---crew:{id}---\\n\\n`` before each
		    secondary crew's tokens so the caller can split/label sections.
		"""
		if not crew_ids:
			return

		primary_id = crew_ids[0]
		primary_chunks: list[str] = []

		async for chunk in self.run_crew_stream(primary_id, user_input):
			primary_chunks.append(chunk)
			yield chunk

		primary_output = "".join(primary_chunks)

		for secondary_id in crew_ids[1:]:
			engaged = await self._crew_wants_to_engage(secondary_id, user_input, primary_output)
			if not engaged:
				logger.debug("crew panel: '%s' opted out for this query", secondary_id)
				continue
			yield f"\n\n---crew:{secondary_id}---\n\n"
			# Provide accumulated context so the secondary builds on, not repeats
			augmented_input = (
				f"{user_input}\n\n"
				f"[Prior crew(s) already produced the following — "
				f"add your domain perspective, avoid repeating what was already covered:]\n"
				f"{primary_output}"
			)
			secondary_chunks: list[str] = []
			async for chunk in self.run_crew_stream(secondary_id, augmented_input):
				secondary_chunks.append(chunk)
				yield chunk
			# Keep running concatenation so each subsequent crew sees all prior work
			primary_output += "\n\n" + "".join(secondary_chunks)


native_crew_engine = NativeCrewEngine()
