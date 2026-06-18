from typing import Protocol, Any, Dict, List, Optional
from dataclasses import dataclass
import datetime

@dataclass
class NormalisedSignal:
	source_id: str
	kind: str
	content: str
	confidence: float
	raw_payload: Dict[str, Any]
	timestamp: datetime.datetime

class MemorySource(Protocol):
	"""
	Scaffolding for MemorySource plugins that ingest signals into the unified ingestion bus.
	Satisfies Phase MA0 of the openZero Substrate master plan.
	"""
	async def discover(self) -> List[Dict[str, Any]]:
		"""Discover targets or configurations available for ingestion."""
		...

	async def normalise(self, raw_signal: Any) -> NormalisedSignal:
		"""Normalise a raw external source document into a structured NormalisedSignal."""
		...

	async def cursor(self) -> Dict[str, Any]:
		"""Get the current cursor / high-water mark for pagination or incremental sync."""
		...

	async def advance_cursor(self, new_cursor: Dict[str, Any]) -> None:
		"""Advance the ingestion cursor to prevent duplicate processing."""
		...
