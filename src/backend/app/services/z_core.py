"""Z-core: always-on faculties injected into every message context.

Absorbs the former workspace and signal_interpreter crews (removed in Phase 1).
These are not optional crew routes — they fire unconditionally on every message.
"""
from datetime import datetime
import zoneinfo

from app.config import settings


def build_z_core_context(user_text: str, session_context: dict | None = None) -> str:
	"""Return an always-on context string to prepend to the Z system prompt.

	Incorporates:
	- Workspace awareness (time, day, active context from session)
	- Signal interpretation (implicit intent signals from the user message)
	"""
	now = datetime.now(tz=zoneinfo.ZoneInfo(getattr(settings, "TIMEZONE", "UTC")))
	day_str = now.strftime("%A, %Y-%m-%d %H:%M")

	lines = [
		"[Z-CORE ALWAYS-ON FACULTIES]",
		f"Session moment: {day_str}. Ground every response to now — never report progress on a",
		"timeframe that has already passed according to the current time above.",
		"",
		"WORKSPACE FACULTY (absorbed from former workspace crew): When the user describes goals,",
		"workflows, or projects to be structured, translate high-level intent into the minimal",
		"concrete board/list topology needed. Apply the right methodology: Kanban WIP-limits for",
		"ongoing work, sprint structure for time-boxed initiatives, GTD capture-then-process for",
		"unstructured input. Always gate board/list creation with a one-sentence HITL proposal",
		"before emitting CREATE_BOARD or CREATE_LIST tags — one confirmation covers the full",
		"scaffold set. Blueprint first, execute second.",
		"",
		"SIGNAL INTERPRETATION FACULTY (absorbed from former signal_interpreter crew): Before",
		"composing any response, silently scan the incoming message for implicit signals:",
		"  - Urgency markers: deadlines, 'asap', 'today', 'by end of day', pressure language",
		"  - Emotional tone: frustration, excitement, uncertainty, overwhelm — match register",
		"  - Implicit requests behind explicit words ('I keep forgetting X' = suggest a reminder)",
		"  - Ambiguous intent: if the user's message has a plausible non-obvious reading, surface",
		"    it rather than guessing — ask one clarifying question at confidence < 0.4",
		"If the signal is clearly noise (greeting, ack, duplicate), respond normally without",
		"forcing an analysis overlay. One proposed action per message, never a list of guesses.",
	]

	return "\n".join(lines)
