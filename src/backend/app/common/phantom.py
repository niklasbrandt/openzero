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
	r'|added to (your )?(todo|list|board|today)'
	r'|done[\s\u2014\u2013-]+(task|board|card|event|create|add)'
	r'|done\s*[\u2014\u2013\-]+\s*(create|add|new)'
	# German phantom patterns
	r'|erledigt[\s\u2014\u2013\-]+(board|karte|aufgabe|liste)'
	r'|board[^.]{0,80}(neu\s+strukturiert|reorganisiert|sortiert|umstrukturiert)'
	r'|karten?[^.]{0,80}(verschoben|sortiert|erstellt)'
	r'|listen?[^.]{0,80}(erstellt|angelegt|umbenannt)'
	# Spanish / French
	r'|tablero[^.]{0,80}(reorganizado|reestructurado)'
	r'|tableau[^.]{0,80}(réorganisé|restructuré)'
	# German: save/store confirmations — "15 Keto-Rezepte gespeichert", "wurde gespeichert"
	r'|[a-z0-9\u00e4\u00f6\u00fc\u00df][\w\u00e4\u00f6\u00fc\u00df\-]*\s+gespeichert'
	r'|wurden?\s+gespeichert'
	r'|erfolgreich\s+(gespeichert|erstellt|hinzugef\u00fcgt|angelegt)'
	r')\b',
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
	return bool(PHANTOM_RE.search(reply[:_MAX_PHANTOM_SCAN]))
