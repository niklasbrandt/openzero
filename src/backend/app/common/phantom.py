"""Shared phantom-confirmation detection utilities.

Imported by message_bus.py, router.py, and phantom_detector.py.
Keep this module import-light (no app dependencies) so tests can use it standalone.
"""
import re

# Maximum reply length to scan (prevent ReDoS on huge responses)
_MAX_PHANTOM_SCAN = 10_000

# Phantom-confirmation guard — Z claimed success in prose without emitting a tag.
# Covers English, German, Spanish, French confirmation patterns.
# All patterns are linear (no backreferences, bounded quantifiers) — ReDoS-safe.
PHANTOM_RE = re.compile(
	r'\b(task added|board (added|created)|event (added|created)|card (added|created)'
	r'|added\s+(?:it\s+)?to\s+(?:your\s+)?(?:todo|list|board|today)'
	r'|done[\s\u2014\u2013-]+(?:i[\'’]?(?:ve)?|we[\'’]?(?:ve)?|i\s+have|we\s+have)?\s*(?:task|board|card|event|create|add|added|saved|new)'
	r'|done\s*[\u2014\u2013\-]+\s*(create|add|new)'
	# German phantom patterns
	r'|erledigt[\s\u2014\u2013\-]+(board|karte|aufgabe|liste)'
	r'|(?:board|karten?|listen?)\s+(?:wurde|wurden)?\s*(?:erfolgreich\s+)?(?:neu\s+strukturiert|reorganisiert|sortiert|umstrukturiert|erstellt|angelegt|verschoben|umbenannt)'
	r'|(?:habe|hab|ich\s+habe)\s+(?:das|die|den)?\s*(?:board|karte|liste|task)\s+(?:erstellt|angelegt|verschoben|gespeichert)'
	# System receipt spoofing (LLM fabricating server-generated receipts)
	r'|system\s+receipt\b'
	# Spanish / French
	r'|tablero\s+(?:ha\s+sido\s+)?(?:reorganizado|reestructurado)'
	r'|tableau\s+(?:a\s+\u00e9t\u00e9\s+)?(?:r\u00e9organis\u00e9|restructur\u00e9)'
	# German: save/store confirmations — "15 Keto-Rezepte gespeichert", "wurde gespeichert"
	r'|[a-z0-9\u00e4\u00f6\u00fc\u00df][\w\u00e4\u00f6\u00fc\u00df\-]*\s+(?:wurde|wurden)?\s*gespeichert'
	r'|erfolgreich\s+(?:gespeichert|erstellt|hinzugef\u00fcgt|angelegt)'
	r')\b',
	re.IGNORECASE,
)

# Modal verbs, inquiries, references to user actions, and negations that indicate
# intent, discussion, questions, or non-execution rather than a phantom confirmation.
NON_PHANTOM_MODAL_RE = re.compile(
	r'\b(?:soll(?:en|st|t)?|kann(?:st|t)?|k\u00f6nnte(?:n|st|t)?|m\u00f6chte(?:n|st|t)?|will(?:st)?|w\u00fcrde(?:n|st|t)?|wird|werden)\b'
	r'|\b(?:du\s+(?:erstellt|angelegt|gespeichert|verschoben)\s+hast|you\s+(?:created|added|saved|moved))\b'
	r'|\b(?:nicht|kein(?:e|en|er|es)?)\b',
	re.IGNORECASE,
)

# Placeholder stored in history instead of the phantom prose.
# Uses translation keys — router/bus replaces with localised string if available.
PHANTOM_HISTORY_PLACEHOLDER = (
	"[SYSTEM: phantom confirmation detected — no action tag was emitted. "
	"This reply was redacted from history to prevent hallucination propagation.]"
)


def is_phantom(reply: str, executed_cmds: list) -> bool:
	"""Return True when reply claims an action succeeded but no commands were executed."""
	if executed_cmds:
		return False
	clauses = re.split(r'[\n\r]+|[.!?]+\s*', reply[:_MAX_PHANTOM_SCAN])
	for clause in clauses:
		clause = clause.strip()
		if not clause:
			continue
		m = PHANTOM_RE.search(clause)
		if m:
			if NON_PHANTOM_MODAL_RE.search(clause):
				continue
			return True
	return False
