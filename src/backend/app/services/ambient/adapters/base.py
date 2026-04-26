"""StateAdapter protocol.

Each concrete adapter implements snapshot() and exposes source_id / poll_interval_s.
The engine calls snapshot() each cycle and stores the result in StateStore.

See docs/artifacts/ambient_intelligence.md §3.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StateAdapter(Protocol):
	source_id: str        # unique identifier, e.g. "planka"
	poll_interval_s: int  # desired snapshot interval (engine may override globally)

	async def snapshot(self) -> dict:
		"""Return a JSON-serialisable snapshot of the current state."""
		...
