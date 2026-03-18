import logging
import re
from app.services.memory import store_memory

logger = logging.getLogger(__name__)

async def extract_and_store_facts(user_message: str):
	"""
	Post-processing memory extraction.
	Runs a fast fast-tier LLM call to extract learnable facts from user messages,
	then stores each fact via store_memory(). This is the primary learning mechanism.
	"""
	if not user_message or len(user_message.strip()) < 20:
		return

	# Skip trivial messages (greetings, confirmations, commands)
	from app.common.strings import TRIVIAL_PATTERNS
	msg_lower = user_message.lower().strip().rstrip('!?.,')
	if msg_lower in TRIVIAL_PATTERNS:
		return

	# Skip messages that are purely commands
	if user_message.strip().startswith('/'):
		return

	# Skip internal framing injected by coalescing
	clean_input = user_message
	if clean_input.startswith('[Follow-up'):
		clean_input = re.sub(r'^\[Follow-up[^\]]*\]\s*', '', clean_input)
	if clean_input.startswith('[Replying to'):
		clean_input = re.sub(r'^\[Replying to[^\]]*\]\s*', '', clean_input)

	try:
		from app.services.llm import chat
		extraction_prompt = (
			"Extract any personal facts, preferences, health information, skills, "
			"goals, relationships, or life updates from the following message. "
			"Return ONE fact per line, distilled into a clean permanent statement. "
			"Rules:\n"
			"- Only extract MEANINGFUL, PERMANENT facts worth remembering forever.\n"
			"- Skip greetings, questions, commands, and transient status updates.\n"
			"- DO NOT extract transient plans, isolated events, or short-term intentions (e.g. 'going to dinner tonight', 'ordered a present today', 'job application sent').\n"
			"- DO NOT extract system errors, technical issues, or agent self-references (e.g. 'I am having trouble reaching the local model').\n"
			"- No 'User likes...' or 'The user...' — just state the fact directly.\n"
			"- If there are NO learnable facts, reply ONLY with: NONE\n\n"
			f"Message: {clean_input}"
		)

		result = await chat(extraction_prompt, tier="fast")
		result = result.strip()

		# Parse result
		if not result or 'NONE' in result.upper():
			logger.debug("Memory extraction: no facts found in message")
			return

		# Store each extracted fact
		lines = [line.strip().lstrip('- ').lstrip('* ').strip() for line in result.split('\n')]
		stored_count = 0
		for fact in lines:
			# Skip empty, meta-commentary, or too-short lines
			if not fact or len(fact) < 10:
				continue
			if any(skip in fact.upper() for skip in ['NONE', 'NO LEARNABLE', 'NO FACTS', 'NO PERSONAL']):
				continue
			await store_memory(fact)
			stored_count += 1

		if stored_count > 0:
			logger.info("Memory extraction: stored %d fact(s)", stored_count)

	except Exception as e:
		logger.warning("Memory extraction failed (non-blocking): %s", e)
