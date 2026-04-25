"""Single-user / single-tenant operator scope guard.

Section 18 of the ambient capture plan: openZero is currently single-operator.
Every capture target must belong to the configured operator. Cross-user IDs
are rejected at the plugin scope-check stage.

If the operator user ID is not configured, ambient capture aborts startup
rather than defaulting open (S1 in the security test matrix).
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def get_operator_user_id() -> Optional[str]:
	"""Return the configured operator Planka user ID, or None if unset."""
	val = getattr(settings, "OPERATOR_USER_ID", "") or ""
	val = str(val).strip()
	return val or None


def require_operator_user_id() -> str:
	"""Return the operator user ID or raise — never default open.

	Engine startup calls this; failure is fatal by design.
	"""
	val = get_operator_user_id()
	if not val:
		raise RuntimeError(
			"OPERATOR_USER_ID is not configured. Ambient capture refuses to start "
			"without an explicit operator identity. Set OPERATOR_USER_ID in .env."
		)
	return val


def is_operator_owned_board(board: dict) -> bool:
	"""True if the given Planka board dict belongs to the configured operator.

	Single-user mode: in v1 we accept any board if no per-board user attribution
	is exposed by the local Planka API (single-tenant assumption). When the API
	does expose ownership (`createdBy`, `userId`, or membership lists), the
	check enforces it strictly.
	"""
	op = get_operator_user_id()
	if not op:
		# Defensive: refuse to authorise anything if startup guard was bypassed.
		logger.error("ambient_capture: operator user id not configured; rejecting board %s", board.get("id"))
		return False

	# Common attribution fields Planka may surface; first match wins.
	for field in ("createdBy", "createdByUserId", "userId", "ownerId"):
		owner = board.get(field)
		if owner is not None:
			return str(owner) == op

	# No attribution exposed -> single-tenant assumption holds.
	return True


def filter_operator_boards(boards: list[dict]) -> list[dict]:
	"""Drop any board not owned by the operator. Logs the count of drops."""
	kept = [b for b in boards if is_operator_owned_board(b)]
	dropped = len(boards) - len(kept)
	if dropped > 0:
		logger.warning("ambient_capture: filtered out %d non-operator boards", dropped)
	return kept
