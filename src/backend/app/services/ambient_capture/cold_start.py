"""Cold-start co-creator mode (Epoch 3 / H2).

When the operator has fewer than 5 boards AND fewer than 20 cards (both
conditions — AND, not OR), the engine enters cold-start mode.

In cold-start mode:
- The TEACH lane fires regardless of confidence thresholds.
- Silent execution (EXECUTE lane) is disabled.
- HITL is mandatory for every capture.
- Rate limits apply (at most 3 boards / 10 lists / 30 cards per (user_id, hour)).

See Section 8 and Section 17.2 of docs/artifacts/ambient_capture_routing.md.

H2 mitigation: cold-start still runs through the Tier D sanitiser;
proposed board / list / card names are sanitised before display.
"""

from __future__ import annotations

_COLD_START_BOARD_THRESHOLD = 5
_COLD_START_CARD_THRESHOLD = 20

# Per-hour creation limits when in cold-start mode (H2 rate-limit).
COLD_START_MAX_BOARDS_PER_HOUR = 3
COLD_START_MAX_LISTS_PER_HOUR = 10
COLD_START_MAX_CARDS_PER_HOUR = 30


def is_cold_start(board_count: int, card_count: int) -> bool:
	"""Return True when BOTH board_count < 5 AND card_count < 20 (H2).

	AND semantics are intentional: a user with 6 boards but only 3 cards is
	not in cold-start; a user with 2 boards but 25 cards is not in cold-start.
	Both conditions must hold simultaneously.
	"""
	return board_count < _COLD_START_BOARD_THRESHOLD and card_count < _COLD_START_CARD_THRESHOLD


def cold_start_lane() -> str:
	"""Canonical lane for cold-start captures — always TEACH.

	Cold-start never silently executes (H2). A single TEACH confirm authorises
	exactly one board+list+card triad. Subsequent input restarts the flow.
	"""
	return "TEACH"
