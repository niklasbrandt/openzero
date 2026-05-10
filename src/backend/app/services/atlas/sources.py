"""MemorySource plugin contract for the Memory Atlas.

Every signal ingestion path (calendar, mail, chat, voice, vision, files)
implements this Protocol. Plugins are registered in the ingestion bus and
discovered at startup.

Static analysis only -- no dynamic imports in this module.
"""
from __future__ import annotations
import datetime
from typing import Any, AsyncIterator, Optional, Protocol, runtime_checkable


class RawSignal:
	"""Opaque container for a single raw signal from a MemorySource."""
	__slots__ = ("source_id", "signal_id", "kind", "payload", "captured_at", "cursor_value")

	def __init__(
		self,
		source_id: str,
		signal_id: str,
		kind: str,
		payload: dict[str, Any],
		captured_at: datetime.datetime,
		cursor_value: str = "",
	) -> None:
		self.source_id = source_id
		self.signal_id = signal_id
		self.kind = kind
		self.payload = payload
		self.captured_at = captured_at
		self.cursor_value = cursor_value


class AtlasIngest:
	"""Normalised signal ready for atlas_nodes/edges insertion."""
	__slots__ = ("node_type", "label", "payload", "confidence", "source_refs", "edges")

	def __init__(
		self,
		node_type: str,
		label: str,
		payload: dict[str, Any],
		confidence: float = 0.5,
		source_refs: Optional[list[dict[str, Any]]] = None,
		edges: Optional[list[dict[str, Any]]] = None,
	) -> None:
		self.node_type = node_type
		self.label = label
		self.payload = payload
		self.confidence = confidence
		self.source_refs = source_refs or []
		self.edges = edges or []


@runtime_checkable
class MemorySource(Protocol):
	"""Protocol every MemorySource plugin must satisfy.

	Plugins MUST sanitise untrusted content before yielding RawSignal instances.
	Text from any external channel is treated as untrusted-content origin.
	"""

	source_id: str

	async def discover(self) -> AsyncIterator[RawSignal]:
		"""Yield new RawSignal instances since the last cursor position."""
		...

	async def normalise(self, raw: RawSignal) -> list[AtlasIngest]:
		"""Convert a RawSignal into one or more AtlasIngest records."""
		...

	async def cursor(self) -> str:
		"""Return the current cursor position (opaque string)."""
		...

	async def advance_cursor(self, to: str) -> None:
		"""Advance the cursor to the given position after successful ingestion."""
		...
