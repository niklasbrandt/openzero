"""
Backup Service — openZero schema_version 3
-------------------------------------------
Full-content export/import for all operator data.
Encryption: pynacl SecretBox + Argon2id passphrase.

Exports: Planka, Calendar, Qdrant personal_memory, Atlas curation,
         preferences, custom_tasks, tracking_sessions, email_triage_rules,
         walkthroughs, share_contracts, Redis keys, agent/ + personal/ files.

Hard exclusions: tokens/, .env secrets, chat history, caches.
"""

import hashlib
import io
import json
import logging
import os
import re
import socket
import zipfile
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic import ConfigDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCHEMA_VERSION = 3
MAX_NAME = 256
MAX_DESC = 16384
MAX_SUMMARY = 1024
MAX_RRULE = 1024
MAX_UID = 256
MAX_EVENTS = 10000
MAX_CARDS = 50000

_YEAR_100 = timedelta(days=365 * 100)

# High-entropy secret scanner — Trufflehog-style patterns
_SECRET_PATTERNS = re.compile(
	r'(?:'
	r'(?:api[_-]?key|secret|password|passwd|token|bearer|auth)["\s:=]+["\']?[A-Za-z0-9+/\-_]{16,}'
	r'|sk-[A-Za-z0-9]{20,}'
	r'|ghp_[A-Za-z0-9]{36}'
	r'|xoxb-[0-9]+-[A-Za-z0-9]+'
	r'|[A-Za-z0-9+/]{40,}={0,2}'  # high-entropy base64 blobs
	r')',
	re.IGNORECASE,
)

# Control characters to strip from all text fields
_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def _strip_ctrl(s: Any) -> str:
	if not isinstance(s, str):
		s = str(s) if s is not None else ""
	return _CTRL_RE.sub("", s)


def _instance_slug() -> str:
	try:
		h = socket.gethostname()[:32]
		h = re.sub(r'[^a-zA-Z0-9]', '', h)
		if h:
			return h[:16]
	except Exception:  # noqa: S110
		pass
	return hashlib.sha256(socket.gethostname().encode()).hexdigest()[:4]


def _utcnow() -> datetime:
	return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class TaskNode(BaseModel):
	model_config = ConfigDict(str_strip_whitespace=True)
	name: str = Field(max_length=MAX_NAME)
	is_completed: bool = False

	@field_validator("name", mode="before")
	@classmethod
	def strip_ctrl_name(cls, v: Any) -> str:
		return _strip_ctrl(v)[:MAX_NAME]


class CardNode(BaseModel):
	model_config = ConfigDict(str_strip_whitespace=True)
	name: str = Field(max_length=MAX_NAME)
	description: Optional[str] = Field(None, max_length=MAX_DESC)
	tasks: list[TaskNode] = Field(default_factory=list)

	@field_validator("name", mode="before")
	@classmethod
	def strip_ctrl_name(cls, v: Any) -> str:
		if v is None:
			return ""
		return _strip_ctrl(str(v))[:MAX_NAME]

	@field_validator("description", mode="before")
	@classmethod
	def strip_ctrl_desc(cls, v: Any) -> Any:
		if v is None:
			return v
		return _strip_ctrl(str(v))[:MAX_DESC]


class ListNode(BaseModel):
	model_config = ConfigDict(str_strip_whitespace=True)
	name: str = Field(max_length=MAX_NAME)
	cards: list[CardNode] = Field(default_factory=list)

	@field_validator("name", mode="before")
	@classmethod
	def strip_ctrl_name(cls, v: Any) -> str:
		return _strip_ctrl(v)[:MAX_NAME]


class BoardNode(BaseModel):
	model_config = ConfigDict(str_strip_whitespace=True)
	name: str = Field(max_length=MAX_NAME)
	lists: list[ListNode] = Field(default_factory=list)

	@field_validator("name", mode="before")
	@classmethod
	def strip_ctrl_name(cls, v: Any) -> str:
		return _strip_ctrl(v)[:MAX_NAME]


class ProjectNode(BaseModel):
	model_config = ConfigDict(str_strip_whitespace=True)
	name: str = Field(max_length=MAX_NAME)
	boards: list[BoardNode] = Field(default_factory=list)

	@field_validator("name", mode="before")
	@classmethod
	def strip_ctrl_name(cls, v: Any) -> str:
		return _strip_ctrl(v)[:MAX_NAME]


class PlankaExportV3(BaseModel):
	projects: list[ProjectNode] = Field(default_factory=list)


class EventNode(BaseModel):
	model_config = ConfigDict(str_strip_whitespace=True)
	uid: str = Field(max_length=MAX_UID)
	summary: str = Field(max_length=MAX_SUMMARY)
	dtstart: str  # ISO 8601
	dtend: Optional[str] = None
	rrule: Optional[str] = Field(None, max_length=MAX_RRULE)
	tzid: Optional[str] = Field(None, max_length=64)
	description: Optional[str] = Field(None, max_length=MAX_DESC)
	origin: Optional[str] = Field(None, max_length=64)  # "google" | "caldav" | "local"

	@field_validator("summary", "description", "uid", "rrule", "tzid", "origin", mode="before")
	@classmethod
	def strip_ctrl_fields(cls, v: Any) -> Any:
		if v is None:
			return v
		return _strip_ctrl(str(v))

	@field_validator("dtstart", mode="after")
	@classmethod
	def check_dtstart_not_far_future(cls, v: str) -> str:
		try:
			dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
			if dt.replace(tzinfo=None) > _utcnow().replace(tzinfo=None) + _YEAR_100:
				raise ValueError("dtstart > 100 years out")
		except ValueError as exc:
			raise exc
		return v


class CalendarNode(BaseModel):
	events: list[EventNode] = Field(default_factory=list)


class CalendarBundle(BaseModel):
	caldav: CalendarNode = Field(default_factory=CalendarNode)
	google: CalendarNode = Field(default_factory=CalendarNode)
	local: CalendarNode = Field(default_factory=CalendarNode)


class MemoryPointNode(BaseModel):
	model_config = ConfigDict(str_strip_whitespace=True)
	id: str
	text: str = Field(max_length=MAX_DESC)
	payload: dict[str, Any] = Field(default_factory=dict)

	@field_validator("text", mode="before")
	@classmethod
	def strip_ctrl_text(cls, v: Any) -> str:
		return _strip_ctrl(str(v))[:MAX_DESC]


class AtlasNodeExport(BaseModel):
	id: int
	type: str = Field(max_length=64)
	label: str = Field(max_length=MAX_NAME)
	payload: dict[str, Any] = Field(default_factory=dict)
	confidence: float = 0.5


class AtlasEdgeExport(BaseModel):
	source_node_id: int
	target_node_id: int
	kind: str = Field(max_length=64)
	weight: float = 1.0
	payload: dict[str, Any] = Field(default_factory=dict)


class AtlasSpineExport(BaseModel):
	id: int
	label: str = Field(max_length=MAX_NAME)
	confidence: float = 0.5
	payload: dict[str, Any] = Field(default_factory=dict)
	derived: bool = True
	locked: bool = False
	summary: Optional[str] = Field(None, max_length=MAX_DESC)
	member_node_ids: list[int] = Field(default_factory=list)


class AtlasDecisionExport(BaseModel):
	node_id: Optional[int] = None
	title: Optional[str] = Field(None, max_length=MAX_NAME)
	rationale: Optional[str] = Field(None, max_length=MAX_DESC)
	context: Optional[str] = Field(None, max_length=MAX_DESC)
	outcome: Optional[str] = Field(None, max_length=MAX_DESC)
	status: str = "open"


class AtlasContradictionExport(BaseModel):
	primary_node_id: Optional[int] = None
	opposing_node_id: Optional[int] = None
	status: str = "open"


class AtlasCurationExport(BaseModel):
	nodes: list[AtlasNodeExport] = Field(default_factory=list)
	edges: list[AtlasEdgeExport] = Field(default_factory=list)
	spines: list[AtlasSpineExport] = Field(default_factory=list)
	decisions: list[AtlasDecisionExport] = Field(default_factory=list)
	contradictions: list[AtlasContradictionExport] = Field(default_factory=list)


class PreferencesExport(BaseModel):
	rows: list[dict[str, str]] = Field(default_factory=list)


class CustomTaskExport(BaseModel):
	name: str = Field(max_length=MAX_NAME)
	message: str = Field(max_length=MAX_DESC)
	job_type: str = Field(default="cron", max_length=32)
	spec: str = Field(max_length=256)
	is_active: bool = True


class TrackingSessionExport(BaseModel):
	tasks: str = Field(max_length=MAX_DESC)
	milestones_json: Optional[str] = None
	end_time: str  # ISO
	is_active: bool = False  # forced false on import


class EmailRuleExport(BaseModel):
	sender_pattern: str = Field(max_length=MAX_NAME)
	subject_pattern: Optional[str] = Field(None, max_length=MAX_NAME)
	action: str = Field(default="urgent", max_length=32)
	badge: Optional[str] = Field(None, max_length=64)


class WalkthroughStopExport(BaseModel):
	stop_order: int
	node_ref: Optional[int] = None  # original node_id, resolved on import
	spine_ref: Optional[int] = None
	narration: Optional[str] = Field(None, max_length=MAX_DESC)
	payload: dict[str, Any] = Field(default_factory=dict)


class WalkthroughExport(BaseModel):
	title: str = Field(max_length=MAX_NAME)
	stops: list[WalkthroughStopExport] = Field(default_factory=list)


class ShareContractExport(BaseModel):
	producer_node: str = Field(max_length=MAX_NAME)
	consumer_node: str = Field(max_length=MAX_NAME)
	resource: str = Field(max_length=MAX_NAME)
	scope_predicate: dict[str, Any] = Field(default_factory=dict)
	redactions: list[Any] = Field(default_factory=list)
	read_only: bool = True
	status: str = "inactive"  # always inactive on import


class RedisExport(BaseModel):
	planka_privacy_override: Optional[str] = None
	ambient_capture_authorship: Optional[str] = None


class FileEntry(BaseModel):
	path: str = Field(max_length=512)  # relative to repo root
	content: str  # raw text content


class FilesExport(BaseModel):
	files: list[FileEntry] = Field(default_factory=list)


class ImportError(BaseModel):
	path: str
	kind: str
	reason: str


class ImportReport(BaseModel):
	created: dict[str, int] = Field(default_factory=dict)
	skipped: dict[str, int] = Field(default_factory=dict)
	errors: list[ImportError] = Field(default_factory=list)
	dry_run: bool = False
	conflict: str = "skip"
	duration_ms: int = 0


class BackupManifest(BaseModel):
	schema_version: int = SCHEMA_VERSION
	created_at: str
	instance_slug: str
	source_commit: str = "unknown"
	sections: list[str] = Field(default_factory=list)
	sha256: dict[str, str] = Field(default_factory=dict)
	exclusion_log: list[str] = Field(default_factory=list)


class BackupBundleV3(BaseModel):
	manifest: BackupManifest
	planka: Optional[PlankaExportV3] = None
	calendar: Optional[CalendarBundle] = None
	memory: Optional[list[MemoryPointNode]] = None
	atlas: Optional[AtlasCurationExport] = None
	preferences: Optional[PreferencesExport] = None
	custom_tasks: Optional[list[CustomTaskExport]] = None
	tracking_sessions: Optional[list[TrackingSessionExport]] = None
	email_rules: Optional[list[EmailRuleExport]] = None
	walkthroughs: Optional[list[WalkthroughExport]] = None
	share_contracts: Optional[list[ShareContractExport]] = None
	redis: Optional[RedisExport] = None
	files: Optional[FilesExport] = None


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

def _derive_key(passphrase: bytes, salt: bytes) -> bytes:
	from nacl.pwhash import argon2id
	return argon2id.kdf(
		32,
		passphrase,
		salt,
		opslimit=argon2id.OPSLIMIT_INTERACTIVE,
		memlimit=argon2id.MEMLIMIT_INTERACTIVE,
	)


def encrypt_bundle(data: bytes, passphrase: str) -> bytes:
	from nacl.secret import SecretBox
	from nacl.utils import random as nacl_random
	from nacl.pwhash import argon2id
	salt = nacl_random(argon2id.SALTBYTES)
	key = _derive_key(passphrase.encode("utf-8"), salt)
	box = SecretBox(key)
	encrypted = box.encrypt(data)
	return salt + encrypted


def decrypt_bundle(data: bytes, passphrase: str) -> bytes:
	from nacl.secret import SecretBox
	from nacl.pwhash import argon2id
	salt_len = argon2id.SALTBYTES
	salt = data[:salt_len]
	encrypted = data[salt_len:]
	key = _derive_key(passphrase.encode("utf-8"), salt)
	box = SecretBox(key)
	return box.decrypt(encrypted)


def passphrase_strength(passphrase: str) -> dict[str, Any]:
	try:
		import zxcvbn as _zxcvbn
		result = _zxcvbn.zxcvbn(passphrase)
		score = result.get("score", 0)
		warning = result.get("feedback", {}).get("warning", "")
		return {"score": score, "warning": warning, "ok": len(passphrase) >= 12}
	except Exception:
		return {"score": 0, "warning": "zxcvbn unavailable", "ok": len(passphrase) >= 12}


def scan_for_secrets(text: str) -> list[str]:
	return [m.group(0)[:40] + "..." for m in _SECRET_PATTERNS.finditer(text)]


# ---------------------------------------------------------------------------
# SHA-256 helper
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
	return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

async def _export_planka() -> tuple[PlankaExportV3, list[str]]:
	exclusions: list[str] = []
	try:
		from app.services.planka_common import get_planka_auth_token
		from app.config import settings
		import httpx
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}
		import asyncio
		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=30.0, headers=headers) as client:
			resp = await client.get("/api/projects")
			resp.raise_for_status()
			projects_raw = resp.json().get("items", [])

			project_tasks = [client.get(f"/api/projects/{p['id']}") for p in projects_raw]
			project_resps = await asyncio.gather(*project_tasks, return_exceptions=True)

			out_projects: list[ProjectNode] = []
			for i, p_resp in enumerate(project_resps):
				if isinstance(p_resp, Exception):
					exclusions.append(f"planka/project/{projects_raw[i].get('name', i)}: fetch failed")
					continue
				p_resp.raise_for_status()  # type: ignore[union-attr]
				detail = p_resp.json()
				boards_raw = detail.get("included", {}).get("boards", [])
				proj_name = projects_raw[i]["name"]

				out_boards: list[BoardNode] = []
				board_tasks = [client.get(f"/api/boards/{b['id']}", params={"included": "lists,cards,cardLabels,cardMemberships,tasks"}) for b in boards_raw]
				board_resps = await asyncio.gather(*board_tasks, return_exceptions=True)

				for j, b_resp in enumerate(board_resps):
					if isinstance(b_resp, Exception):
						exclusions.append(f"planka/{proj_name}/{boards_raw[j].get('name', j)}: fetch failed")
						continue
					b_resp.raise_for_status()  # type: ignore[union-attr]
					b_detail = b_resp.json()
					board_name = boards_raw[j]["name"]
					lists_raw = b_detail.get("included", {}).get("lists", [])
					cards_raw = b_detail.get("included", {}).get("cards", [])
					tasks_raw = b_detail.get("included", {}).get("tasks", [])

					cards_by_list: dict[str, list[CardNode]] = {}
					total_cards = 0
					for card in cards_raw:
						if total_cards >= MAX_CARDS:
							exclusions.append(f"planka/{proj_name}/{board_name}: card limit {MAX_CARDS} reached")
							break
						lid = card.get("listId", "")
						card_tasks = [
							TaskNode(name=t.get("name", ""), is_completed=t.get("isCompleted", False))
							for t in tasks_raw if t.get("cardId") == card.get("id")
						]
						desc = card.get("description") or None
						if desc:
							hits = scan_for_secrets(desc)
							if hits:
								exclusions.append(f"planka/{proj_name}/{board_name}/{card.get('name', '')}: description excluded (possible secret)")
								desc = None
						cn = CardNode(
							name=card.get("name", ""),
							description=desc,
							tasks=card_tasks,
						)
						cards_by_list.setdefault(lid, []).append(cn)
						total_cards += 1

					out_lists: list[ListNode] = []
					for lst in lists_raw:
						out_lists.append(ListNode(
							name=lst.get("name", ""),
							cards=cards_by_list.get(lst.get("id", ""), []),
						))
					out_boards.append(BoardNode(name=board_name, lists=out_lists))

				out_projects.append(ProjectNode(name=proj_name, boards=out_boards))

		return PlankaExportV3(projects=out_projects), exclusions
	except Exception as exc:
		logger.warning("Planka export failed: %s", exc)
		return PlankaExportV3(), [f"planka: export failed ({exc})"]


async def _export_calendar() -> tuple[CalendarBundle, list[str]]:
	exclusions: list[str] = []
	bundle = CalendarBundle()
	now_utc = _utcnow()
	try:
		from app.services.calendar import fetch_caldav_events
		import datetime as dt
		start = now_utc
		end = now_utc + dt.timedelta(days=365 * 3)
		raw = await fetch_caldav_events(start.replace(tzinfo=None), end.replace(tzinfo=None))
		events_out: list[EventNode] = []
		for ev in raw[:MAX_EVENTS]:
			try:
				rrule = ev.get("rrule")
				dtstart_raw = ev.get("start", "")
				uid = ev.get("uid", "") or ev.get("id", "")
				if not dtstart_raw:
					exclusions.append(f"calendar/caldav/{uid}: missing dtstart")
					continue
				node = EventNode(
					uid=_strip_ctrl(uid)[:MAX_UID] or hashlib.sha256(dtstart_raw.encode()).hexdigest()[:32],
					summary=_strip_ctrl(ev.get("summary", ""))[:MAX_SUMMARY],
					dtstart=dtstart_raw,
					dtend=ev.get("end"),
					rrule=rrule[:MAX_RRULE] if rrule else None,
					tzid=ev.get("tzid"),
					description=ev.get("description"),
					origin="caldav",
				)
				events_out.append(node)
			except Exception as e:
				_err = type(e).__name__
				exclusions.append(f"calendar/caldav/event: {_err}")
		bundle.caldav = CalendarNode(events=events_out)
	except Exception as exc:
		_err = type(exc).__name__
		exclusions.append(f"calendar/caldav: {_err}")

	try:
		from app.services.calendar import fetch_calendar_events
		import datetime as dt
		raw_g = await fetch_calendar_events(max_results=MAX_EVENTS, days_ahead=365 * 3)
		g_events: list[EventNode] = []
		for ev in raw_g:
			try:
				dtstart_raw = ev.get("start", "")
				if not dtstart_raw:
					continue
				uid = ev.get("id", "") or hashlib.sha256(dtstart_raw.encode()).hexdigest()[:32]
				node = EventNode(
					uid=_strip_ctrl(uid)[:MAX_UID],
					summary=_strip_ctrl(ev.get("summary", ""))[:MAX_SUMMARY],
					dtstart=dtstart_raw,
					dtend=ev.get("end"),
					origin="google",
				)
				g_events.append(node)
			except Exception as e:
				_err = type(e).__name__
				exclusions.append(f"calendar/google/event: {_err}")
		bundle.google = CalendarNode(events=g_events)
	except Exception as exc:
		_err = type(exc).__name__
		exclusions.append(f"calendar/google: {_err}")

	try:
		from app.models.db import AsyncSessionLocal, LocalEvent
		from sqlalchemy import select
		async with AsyncSessionLocal() as session:
			res = await session.execute(
				select(LocalEvent).where(
					LocalEvent.start_time >= now_utc.replace(tzinfo=None)
				)
			)
			local_evs = res.scalars().all()
			l_events: list[EventNode] = []
			for ev in local_evs:
				try:
					node = EventNode(
						uid=f"local-{ev.id}",
						summary=_strip_ctrl(ev.summary)[:MAX_SUMMARY],
						dtstart=ev.start_time.isoformat(),
						dtend=ev.end_time.isoformat() if ev.end_time else None,
						origin="local",
					)
					l_events.append(node)
				except Exception as e:
					_err = type(e).__name__
					exclusions.append(f"calendar/local/{ev.id}: {_err}")
			bundle.local = CalendarNode(events=l_events)
	except Exception as exc:
		_err = type(exc).__name__
		exclusions.append(f"calendar/local: {_err}")

	return bundle, exclusions


async def _export_memory() -> tuple[list[MemoryPointNode], list[str]]:
	exclusions: list[str] = []
	try:
		from app.services.memory import get_qdrant, COLLECTION_NAME
		client = get_qdrant()
		points = []
		offset = None
		while True:
			batch, next_offset = client.scroll(
				collection_name=COLLECTION_NAME,
				limit=256,
				offset=offset,
				with_payload=True,
				with_vectors=False,
			)
			points.extend(batch)
			if next_offset is None:
				break
			offset = next_offset

		out: list[MemoryPointNode] = []
		for p in points:
			text = (p.payload or {}).get("text", "")
			hits = scan_for_secrets(text)
			if hits:
				exclusions.append(f"memory/{p.id}: excluded (possible secret in text)")
				continue
			payload = {k: v for k, v in (p.payload or {}).items() if k != "text"}
			out.append(MemoryPointNode(id=str(p.id), text=_strip_ctrl(text), payload=payload))
		return out, exclusions
	except Exception as exc:
		return [], [f"memory: {exc}"]


async def _export_atlas() -> tuple[AtlasCurationExport, list[str]]:
	exclusions: list[str] = []
	try:
		from app.models.db import AsyncSessionLocal
		from sqlalchemy import text as sa_text
		async with AsyncSessionLocal() as session:
			nodes_raw = (await session.execute(sa_text("SELECT id, type, label, payload, confidence FROM atlas_nodes"))).fetchall()
			edges_raw = (await session.execute(sa_text("SELECT source_node_id, target_node_id, kind, weight, payload FROM atlas_edges"))).fetchall()
			spines_raw = (await session.execute(sa_text("SELECT id, label, confidence, payload, derived, locked FROM atlas_spines"))).fetchall()
			spine_members_raw = (await session.execute(sa_text("SELECT spine_id, node_id FROM atlas_spine_members"))).fetchall()
			spine_summaries_raw = (await session.execute(sa_text("SELECT spine_id, summary_text FROM atlas_spine_summaries ORDER BY generated_at DESC"))).fetchall()
			decisions_raw = (await session.execute(sa_text("SELECT node_id, title, rationale, context, outcome, status FROM atlas_decisions"))).fetchall()
			contradictions_raw = (await session.execute(sa_text("SELECT primary_node_id, opposing_node_id, status FROM atlas_contradictions"))).fetchall()

		node_ids = {r[0] for r in nodes_raw}
		nodes = [AtlasNodeExport(id=r[0], type=r[1], label=r[2], payload=r[3] or {}, confidence=r[4]) for r in nodes_raw]

		# Build edges — drop orphaned references
		edges: list[AtlasEdgeExport] = []
		for r in edges_raw:
			if r[0] not in node_ids or r[1] not in node_ids:
				exclusions.append(f"atlas/edge {r[0]}->{r[1]}: orphaned, excluded")
				continue
			edges.append(AtlasEdgeExport(source_node_id=r[0], target_node_id=r[1], kind=r[2], weight=r[3], payload=r[4] or {}))

		# Build spine summary index (latest per spine)
		spine_summary_map: dict[int, str] = {}
		for sr in spine_summaries_raw:
			if sr[0] not in spine_summary_map:
				spine_summary_map[sr[0]] = sr[1]

		# Build spine members index
		spine_members: dict[int, list[int]] = {}
		for sm in spine_members_raw:
			spine_members.setdefault(sm[0], []).append(sm[1])

		spines: list[AtlasSpineExport] = []
		for r in spines_raw:
			member_ids = spine_members.get(r[0], [])
			valid_members = [m for m in member_ids if m in node_ids]
			if len(valid_members) < len(member_ids):
				exclusions.append(f"atlas/spine/{r[0]}: {len(member_ids)-len(valid_members)} orphaned members excluded")
			spines.append(AtlasSpineExport(
				id=r[0], label=r[1], confidence=r[2], payload=r[3] or {},
				derived=r[4], locked=r[5],
				summary=spine_summary_map.get(r[0]),
				member_node_ids=valid_members,
			))

		decisions = [AtlasDecisionExport(node_id=r[0], title=r[1], rationale=r[2], context=r[3], outcome=r[4], status=r[5]) for r in decisions_raw]
		contradictions = [AtlasContradictionExport(primary_node_id=r[0], opposing_node_id=r[1], status=r[2]) for r in contradictions_raw]

		return AtlasCurationExport(nodes=nodes, edges=edges, spines=spines, decisions=decisions, contradictions=contradictions), exclusions
	except Exception as exc:
		return AtlasCurationExport(), [f"atlas: {exc}"]


async def _export_preferences() -> tuple[PreferencesExport, list[str]]:
	exclusions: list[str] = []
	try:
		from app.models.db import AsyncSessionLocal, Preference
		from sqlalchemy import select
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(Preference))
			prefs = res.scalars().all()
		rows: list[dict[str, str]] = []
		for p in prefs:
			hits = scan_for_secrets(p.value)
			if hits:
				exclusions.append(f"preferences/{p.key}: excluded (possible secret)")
				continue
			rows.append({"key": p.key, "value": p.value})
		return PreferencesExport(rows=rows), exclusions
	except Exception as exc:
		return PreferencesExport(), [f"preferences: {exc}"]


async def _export_custom_tasks() -> tuple[list[CustomTaskExport], list[str]]:
	exclusions: list[str] = []
	try:
		from app.models.db import AsyncSessionLocal, CustomTask
		from sqlalchemy import select
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(CustomTask))
			tasks = res.scalars().all()
		out: list[CustomTaskExport] = []
		for t in tasks:
			out.append(CustomTaskExport(
				name=_strip_ctrl(t.name)[:MAX_NAME],
				message=_strip_ctrl(t.message)[:MAX_DESC],
				job_type=t.job_type,
				spec=t.spec,
				is_active=t.is_active,
			))
		return out, exclusions
	except Exception as exc:
		return [], [f"custom_tasks: {exc}"]


async def _export_tracking_sessions() -> tuple[list[TrackingSessionExport], list[str]]:
	exclusions: list[str] = []
	try:
		from app.models.db import AsyncSessionLocal, TrackingSession
		from sqlalchemy import select
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(TrackingSession))
			sessions = res.scalars().all()
		out: list[TrackingSessionExport] = []
		for s in sessions:
			out.append(TrackingSessionExport(
				tasks=_strip_ctrl(s.tasks)[:MAX_DESC],
				milestones_json=s.milestones_json,
				end_time=s.end_time.isoformat() if s.end_time else _utcnow().isoformat(),
				is_active=False,  # forced false
			))
		return out, exclusions
	except Exception as exc:
		return [], [f"tracking_sessions: {exc}"]


async def _export_email_rules() -> tuple[list[EmailRuleExport], list[str]]:
	exclusions: list[str] = []
	try:
		from app.models.db import AsyncSessionLocal, EmailRule
		from sqlalchemy import select
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(EmailRule))
			rules = res.scalars().all()
		out: list[EmailRuleExport] = []
		for r in rules:
			out.append(EmailRuleExport(
				sender_pattern=_strip_ctrl(r.sender_pattern)[:MAX_NAME],
				subject_pattern=_strip_ctrl(r.subject_pattern)[:MAX_NAME] if r.subject_pattern else None,
				action=r.action,
				badge=r.badge,
			))
		return out, exclusions
	except Exception as exc:
		return [], [f"email_rules: {exc}"]


async def _export_walkthroughs() -> tuple[list[WalkthroughExport], list[str]]:
	exclusions: list[str] = []
	try:
		from app.models.db import AsyncSessionLocal
		from sqlalchemy import text as sa_text
		async with AsyncSessionLocal() as session:
			wts = (await session.execute(sa_text("SELECT id, title FROM walkthroughs"))).fetchall()
			stops = (await session.execute(sa_text("SELECT walkthrough_id, stop_order, node_id, spine_id, narration, payload FROM walkthrough_stops ORDER BY stop_order"))).fetchall()

		stops_by_wt: dict[int, list] = {}
		for s in stops:
			stops_by_wt.setdefault(s[0], []).append(s)

		out: list[WalkthroughExport] = []
		for wt in wts:
			stop_exports: list[WalkthroughStopExport] = []
			for s in stops_by_wt.get(wt[0], []):
				stop_exports.append(WalkthroughStopExport(
					stop_order=s[1],
					node_ref=s[2],
					spine_ref=s[3],
					narration=_strip_ctrl(s[4])[:MAX_DESC] if s[4] else None,
					payload=s[5] or {},
				))
			out.append(WalkthroughExport(title=_strip_ctrl(wt[1])[:MAX_NAME], stops=stop_exports))
		return out, exclusions
	except Exception as exc:
		return [], [f"walkthroughs: {exc}"]


async def _export_share_contracts() -> tuple[list[ShareContractExport], list[str]]:
	exclusions: list[str] = []
	try:
		from app.models.db import AsyncSessionLocal
		from sqlalchemy import text as sa_text
		async with AsyncSessionLocal() as session:
			rows = (await session.execute(sa_text(
				"SELECT producer_node, consumer_node, resource, scope_predicate, redactions, read_only FROM share_contracts"
			))).fetchall()
		out: list[ShareContractExport] = []
		for r in rows:
			out.append(ShareContractExport(
				producer_node=r[0], consumer_node=r[1], resource=r[2],
				scope_predicate=r[3] or {}, redactions=r[4] or [],
				read_only=r[5], status="inactive",
			))
		return out, exclusions
	except Exception as exc:
		return [], [f"share_contracts: {exc}"]


async def _export_redis() -> tuple[RedisExport, list[str]]:
	exclusions: list[str] = []
	try:
		import redis as _redis
		from app.config import settings
		r = _redis.Redis(
			host=settings.REDIS_HOST, port=settings.REDIS_PORT,
			password=settings.REDIS_PASSWORD or None,
			decode_responses=True, socket_timeout=3.0,
		)
		ppo = r.get("planka_privacy_override")
		aca = r.get("ambient_capture:authorship")
		return RedisExport(planka_privacy_override=ppo, ambient_capture_authorship=aca), exclusions
	except Exception as exc:
		return RedisExport(), [f"redis: {exc}"]


async def _export_files() -> tuple[FilesExport, list[str]]:
	exclusions: list[str] = []
	repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
	entries: list[FileEntry] = []
	skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "dist", "tokens", ".DS_Store"}

	for base_dir in ("agent", "personal"):
		base_path = os.path.join(repo_root, base_dir)
		if not os.path.isdir(base_path):
			exclusions.append(f"files/{base_dir}: directory not found")
			continue
		for dirpath, dirnames, filenames in os.walk(base_path):
			dirnames[:] = [d for d in dirnames if d not in skip_dirs]
			for fname in filenames:
				if fname.startswith("."):
					continue
				full = os.path.join(dirpath, fname)
				rel = os.path.relpath(full, repo_root)
				try:
					with open(full, "r", encoding="utf-8", errors="replace") as f:
						content = f.read()
					hits = scan_for_secrets(content)
					if hits:
						exclusions.append(f"files/{rel}: excluded (possible secret at position {hits[0][:20]})")
						continue
					entries.append(FileEntry(path=rel, content=content))
				except Exception as exc:
					_err = type(exc).__name__
					exclusions.append(f"files/{rel}: {_err}")

	return FilesExport(files=entries), exclusions


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------

async def build_export_bundle(
	passphrase: str,
	include_preferences: bool = True,
	excluded_row_ids: Optional[dict[str, list[str]]] = None,
) -> tuple[bytes, BackupBundleV3]:
	exclusions: list[str] = []
	sections: list[str] = []

	from app.config import settings
	try:
		_vfile = os.path.join(os.path.dirname(__file__), "..", "VERSION")
		with open(_vfile) as _f:
			commit = _f.read().strip()
	except Exception:
		commit = "unknown"

	planka, ex = await _export_planka()
	exclusions.extend(ex)
	sections.append("planka")

	calendar, ex = await _export_calendar()
	exclusions.extend(ex)
	sections.append("calendar")

	memory, ex = await _export_memory()
	exclusions.extend(ex)
	sections.append("memory")

	atlas, ex = await _export_atlas()
	exclusions.extend(ex)
	sections.append("atlas")

	prefs: Optional[PreferencesExport] = None
	if include_preferences:
		prefs, ex = await _export_preferences()
		exclusions.extend(ex)
		sections.append("preferences")

	custom_tasks, ex = await _export_custom_tasks()
	exclusions.extend(ex)
	sections.append("custom_tasks")

	tracking, ex = await _export_tracking_sessions()
	exclusions.extend(ex)
	sections.append("tracking_sessions")

	email_rules: Optional[list[EmailRuleExport]] = None
	if getattr(settings, "EMAIL_ENABLED", False):
		email_rules, ex = await _export_email_rules()
		exclusions.extend(ex)
		sections.append("email_rules")

	walkthroughs, ex = await _export_walkthroughs()
	exclusions.extend(ex)
	sections.append("walkthroughs")

	share_contracts: Optional[list[ShareContractExport]] = None
	if getattr(settings, "FEDERATION_ENABLED", False):
		share_contracts, ex = await _export_share_contracts()
		exclusions.extend(ex)
		sections.append("share_contracts")

	redis_exp, ex = await _export_redis()
	exclusions.extend(ex)
	sections.append("redis")

	files_exp, ex = await _export_files()
	exclusions.extend(ex)
	sections.append("files")

	# Build JSON sections for SHA-256
	section_bytes: dict[str, bytes] = {}
	for name, obj in [
		("planka", planka),
		("calendar", calendar),
		("memory", memory),
		("atlas", atlas),
		("preferences", prefs),
		("custom_tasks", custom_tasks),
		("tracking_sessions", tracking),
		("email_rules", email_rules),
		("walkthroughs", walkthroughs),
		("share_contracts", share_contracts),
		("redis", redis_exp),
		("files", files_exp),
	]:
		if obj is not None:
			if hasattr(obj, "model_dump"):
				b = json.dumps(obj.model_dump(), default=str).encode("utf-8")
			else:
				b = json.dumps([x.model_dump() if hasattr(x, "model_dump") else x for x in obj], default=str).encode("utf-8")
			section_bytes[name] = b

	sha256_map = {k: _sha256(v) for k, v in section_bytes.items()}
	manifest = BackupManifest(
		schema_version=SCHEMA_VERSION,
		created_at=_utcnow().isoformat(),
		instance_slug=_instance_slug(),
		source_commit=commit,
		sections=sections,
		sha256=sha256_map,
		exclusion_log=exclusions,
	)

	bundle = BackupBundleV3(
		manifest=manifest,
		planka=planka,
		calendar=calendar,
		memory=memory,
		atlas=atlas,
		preferences=prefs,
		custom_tasks=custom_tasks,
		tracking_sessions=tracking,
		email_rules=email_rules,
		walkthroughs=walkthroughs,
		share_contracts=share_contracts,
		redis=redis_exp,
		files=files_exp,
	)

	# Pack into a zip in memory, then encrypt
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		manifest_bytes = json.dumps(manifest.model_dump(), default=str, indent=2).encode("utf-8")
		zf.writestr("manifest.json", manifest_bytes)
		for name, b in section_bytes.items():
			zf.writestr(f"{name}.json", b)

	zip_bytes = buf.getvalue()
	encrypted = encrypt_bundle(zip_bytes, passphrase)
	return encrypted, bundle


def backup_filename(slug: str) -> str:
	ts = _utcnow().strftime("%Y%m%d-%H%M%S")
	return f"openzero-backup-{slug}-{ts}-v3.ozbackup"


# ---------------------------------------------------------------------------
# Preview helper (paginated section scan, no encryption)
# ---------------------------------------------------------------------------

async def get_preview_section(section: str, cursor: int, page_size: int = 50) -> dict[str, Any]:
	"""Return a page of items from a section for the preview UI."""
	funcs = {
		"planka": _preview_planka,
		"memory": _preview_memory,
		"atlas": _preview_atlas,
		"custom_tasks": _preview_custom_tasks,
		"walkthroughs": _preview_walkthroughs,
	}
	fn = funcs.get(section)
	if fn is None:
		return {"items": [], "total": 0, "cursor": cursor, "done": True}
	return await fn(cursor, page_size)


async def _preview_planka(cursor: int, page_size: int) -> dict[str, Any]:
	try:
		planka, _ = await _export_planka()
		cards: list[dict] = []
		for proj in planka.projects:
			for board in proj.boards:
				for lst in board.lists:
					for card in lst.cards:
						cards.append({
							"path": f"{proj.name}/{board.name}/{lst.name}/{card.name}",
							"tasks": len(card.tasks),
						})
		page = cards[cursor:cursor + page_size]
		return {"items": page, "total": len(cards), "cursor": cursor + len(page), "done": cursor + len(page) >= len(cards)}
	except Exception as exc:
		return {"items": [], "total": 0, "cursor": 0, "done": True, "error": str(exc)}


async def _preview_memory(cursor: int, page_size: int) -> dict[str, Any]:
	try:
		mem, _ = await _export_memory()
		page = [{"id": m.id, "text": m.text[:120]} for m in mem[cursor:cursor + page_size]]
		return {"items": page, "total": len(mem), "cursor": cursor + len(page), "done": cursor + len(page) >= len(mem)}
	except Exception as exc:
		return {"items": [], "total": 0, "cursor": 0, "done": True, "error": str(exc)}


async def _preview_atlas(cursor: int, page_size: int) -> dict[str, Any]:
	try:
		atlas, _ = await _export_atlas()
		nodes = [{"id": n.id, "label": n.label, "type": n.type} for n in atlas.nodes]
		page = nodes[cursor:cursor + page_size]
		return {"items": page, "total": len(nodes), "cursor": cursor + len(page), "done": cursor + len(page) >= len(nodes)}
	except Exception as exc:
		return {"items": [], "total": 0, "cursor": 0, "done": True, "error": str(exc)}


async def _preview_custom_tasks(cursor: int, page_size: int) -> dict[str, Any]:
	try:
		tasks, _ = await _export_custom_tasks()
		page = [{"name": t.name, "spec": t.spec} for t in tasks[cursor:cursor + page_size]]
		return {"items": page, "total": len(tasks), "cursor": cursor + len(page), "done": cursor + len(page) >= len(tasks)}
	except Exception as exc:
		return {"items": [], "total": 0, "cursor": 0, "done": True, "error": str(exc)}


async def _preview_walkthroughs(cursor: int, page_size: int) -> dict[str, Any]:
	try:
		wts, _ = await _export_walkthroughs()
		page = [{"title": w.title, "stops": len(w.stops)} for w in wts[cursor:cursor + page_size]]
		return {"items": page, "total": len(wts), "cursor": cursor + len(page), "done": cursor + len(page) >= len(wts)}
	except Exception as exc:
		return {"items": [], "total": 0, "cursor": 0, "done": True, "error": str(exc)}


# ---------------------------------------------------------------------------
# Planka import helpers
# ---------------------------------------------------------------------------

async def _create_list(client: Any, board_id: str, list_name: str) -> Optional[str]:
	try:
		resp = await client.post(f"/api/boards/{board_id}/lists", json={"name": list_name, "position": 65535})
		resp.raise_for_status()
		return resp.json().get("item", {}).get("id")
	except Exception as exc:
		logger.warning("_create_list failed for %s/%s: %s", board_id, list_name, exc)
		return None


# ---------------------------------------------------------------------------
# Import function
# ---------------------------------------------------------------------------

async def import_bundle(
	data: bytes,
	passphrase: str,
	dry_run: bool = False,
	conflict: str = "skip",
	include_preferences: bool = False,
	confirm_destructive: bool = False,
) -> ImportReport:
	import time as _time_mod
	start_ms = int(_time_mod.time() * 1000)
	report = ImportReport(dry_run=dry_run, conflict=conflict)

	if conflict == "replace" and not confirm_destructive:
		report.errors.append(ImportError(path="import", kind="config", reason="replace mode requires X-Confirm-Destructive: yes header"))
		return report

	try:
		zip_bytes = decrypt_bundle(data, passphrase)
	except Exception as exc:
		report.errors.append(ImportError(path="decrypt", kind="auth", reason=str(exc)))
		report.duration_ms = int(_time_mod.time() * 1000) - start_ms
		return report

	try:
		with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
			names = set(zf.namelist())
			manifest_raw = zf.read("manifest.json")
			manifest = BackupManifest(**json.loads(manifest_raw))

			def _read_section(name: str) -> Optional[Any]:
				fname = f"{name}.json"
				if fname in names:
					return json.loads(zf.read(fname))
				return None

			# Version compatibility
			if manifest.schema_version < 1:
				report.errors.append(ImportError(path="manifest", kind="version", reason=f"unsupported schema_version {manifest.schema_version}"))
				return report

			planka_raw = _read_section("planka")
			calendar_raw = _read_section("calendar")
			memory_raw = _read_section("memory")
			atlas_raw = _read_section("atlas")
			prefs_raw = _read_section("preferences")
			custom_tasks_raw = _read_section("custom_tasks")
			tracking_raw = _read_section("tracking_sessions")
			email_rules_raw = _read_section("email_rules")
			walkthroughs_raw = _read_section("walkthroughs")
			share_contracts_raw = _read_section("share_contracts")
			redis_raw = _read_section("redis")
			files_raw = _read_section("files")

	except Exception as exc:
		report.errors.append(ImportError(path="unpack", kind="parse", reason=str(exc)))
		report.duration_ms = int(_time_mod.time() * 1000) - start_ms
		return report

	# v1/v2 compatibility: only import planka + calendar sections
	if manifest.schema_version < 3:
		report.errors.append(ImportError(path="manifest", kind="version", reason=f"schema_version {manifest.schema_version} — only planka+calendar sections imported; other sections skipped"))
		memory_raw = atlas_raw = prefs_raw = custom_tasks_raw = tracking_raw = email_rules_raw = walkthroughs_raw = share_contracts_raw = redis_raw = files_raw = None

	if not dry_run:
		await _import_planka(planka_raw, conflict, report)
		await _import_calendar(calendar_raw, conflict, report)
		await _import_memory(memory_raw, conflict, report)
		await _import_atlas(atlas_raw, conflict, report)
		if include_preferences and prefs_raw:
			await _import_preferences(prefs_raw, conflict, report)
		await _import_custom_tasks(custom_tasks_raw, conflict, report)
		await _import_tracking_sessions(tracking_raw, conflict, report)
		await _import_email_rules(email_rules_raw, conflict, report)
		await _import_walkthroughs(walkthroughs_raw, conflict, report)
		await _import_share_contracts(share_contracts_raw, conflict, report)
		await _import_redis(redis_raw, conflict, report)
		await _import_files(files_raw, conflict, report)
	else:
		# Dry run: count items without writing
		if planka_raw:
			try:
				p = PlankaExportV3(**planka_raw)
				total = sum(len(lst.cards) for proj in p.projects for b in proj.boards for lst in b.lists)
				report.created["planka_cards_dry"] = total
			except Exception as exc:
				report.errors.append(ImportError(path="planka", kind="parse", reason=str(exc)))
		if memory_raw:
			report.created["memory_points_dry"] = len(memory_raw) if isinstance(memory_raw, list) else 0

	report.duration_ms = int(_time_mod.time() * 1000) - start_ms
	return report


async def _import_planka(planka_raw: Optional[dict], conflict: str, report: ImportReport) -> None:
	if not planka_raw:
		return
	try:
		from app.services.planka_common import get_planka_auth_token
		from app.config import settings
		import httpx
		p = PlankaExportV3(**planka_raw)
		token = await get_planka_auth_token()
		headers = {"Authorization": f"Bearer {token}"}
		created = skipped = 0

		async with httpx.AsyncClient(base_url=settings.PLANKA_BASE_URL, timeout=30.0, headers=headers) as client:
			# Fetch existing projects
			resp = await client.get("/api/projects")
			resp.raise_for_status()
			existing_projects = {p2["name"]: p2 for p2 in resp.json().get("items", [])}

			for proj in p.projects:
				if proj.name in existing_projects:
					if conflict == "skip":
						skipped += 1
						continue
					proj_id = existing_projects[proj.name]["id"]
				else:
					r = await client.post("/api/projects", json={"name": proj.name})
					r.raise_for_status()
					proj_id = r.json().get("item", {}).get("id")
					created += 1

				# Get boards for this project
				r2 = await client.get(f"/api/projects/{proj_id}")
				r2.raise_for_status()
				existing_boards = {b["name"]: b for b in r2.json().get("included", {}).get("boards", [])}

				for board in proj.boards:
					if board.name in existing_boards:
						if conflict == "skip":
							skipped += 1
							continue
						board_id = existing_boards[board.name]["id"]
					else:
						r3 = await client.post(f"/api/projects/{proj_id}/boards", json={"name": board.name, "position": 65535})
						r3.raise_for_status()
						board_id = r3.json().get("item", {}).get("id")
						created += 1

					# Get lists for board
					r4 = await client.get(f"/api/boards/{board_id}", params={"included": "lists,cards"})
					r4.raise_for_status()
					existing_lists = {l2["name"]: l2 for l2 in r4.json().get("included", {}).get("lists", [])}
					existing_cards_by_list: dict[str, set[str]] = {}
					for c in r4.json().get("included", {}).get("cards", []):
						existing_cards_by_list.setdefault(c["listId"], set()).add(c["name"])

					for lst in board.lists:
						if lst.name in existing_lists:
							if conflict == "skip":
								skipped += 1
								continue
							list_id = existing_lists[lst.name]["id"]
						else:
							list_id = await _create_list(client, board_id, lst.name)
							if not list_id:
								report.errors.append(ImportError(path=f"planka/{proj.name}/{board.name}/{lst.name}", kind="create", reason="list creation failed"))
								continue
							created += 1

						existing_card_names = existing_cards_by_list.get(list_id, set())
						for card in lst.cards:
							if card.name in existing_card_names:
								if conflict == "skip":
									skipped += 1
									continue
							r5 = await client.post(f"/api/lists/{list_id}/cards", json={
								"name": card.name,
								"description": card.description or "",
								"position": 65535,
							})
							if r5.is_success:
								card_id = r5.json().get("item", {}).get("id")
								# Add provenance label via description suffix
								for task in card.tasks:
									await client.post(f"/api/cards/{card_id}/tasks", json={"name": task.name, "isCompleted": task.is_completed})
								created += 1
							else:
								skipped += 1

		report.created["planka"] = created
		report.skipped["planka"] = skipped
	except Exception as exc:
		report.errors.append(ImportError(path="planka", kind="import", reason=str(exc)))


async def _import_calendar(calendar_raw: Optional[dict], conflict: str, report: ImportReport) -> None:
	if not calendar_raw:
		return
	try:
		bundle = CalendarBundle(**calendar_raw)
		created = skipped = 0

		# Local events
		from app.models.db import AsyncSessionLocal, LocalEvent
		from sqlalchemy import select
		async with AsyncSessionLocal() as session:
			existing = (await session.execute(select(LocalEvent.summary))).scalars().all()
			existing_set = set(existing)
			for ev in bundle.local.events:
				if ev.summary in existing_set and conflict == "skip":
					skipped += 1
					continue
				try:
					dtstart = datetime.fromisoformat(ev.dtstart.replace("Z", "+00:00")).replace(tzinfo=None)
					dtend = datetime.fromisoformat(ev.dtend.replace("Z", "+00:00")).replace(tzinfo=None) if ev.dtend else None
					local_ev = LocalEvent(
						summary=ev.summary,
						start_time=dtstart,
						end_time=dtend,
					)
					session.add(local_ev)
					created += 1
				except Exception as exc:
					report.errors.append(ImportError(path=f"calendar/local/{ev.uid}", kind="import", reason=str(exc)))
			await session.commit()

		# CalDAV events — reject Google-origin events to Google target
		for ev in bundle.caldav.events:
			if ev.origin == "google":
				report.errors.append(ImportError(path=f"calendar/caldav/{ev.uid}", kind="event", reason="google_write_unsupported"))
				skipped += 1
				continue
			try:
				from app.config import settings
				if not settings.CALDAV_URL:
					break
				# Write via CalDAV PUT
				import httpx
				ical = _build_ical(ev)
				auth = (settings.CALDAV_USERNAME, settings.CALDAV_PASSWORD)
				url = f"{settings.CALDAV_URL.rstrip('/')}/{ev.uid}.ics"
				async with httpx.AsyncClient(timeout=10.0) as c:
					existing_resp = await c.request("GET", url, auth=auth)
					if existing_resp.status_code == 200 and conflict == "skip":
						skipped += 1
						continue
					r = await c.put(url, content=ical.encode("utf-8"), headers={"Content-Type": "text/calendar"}, auth=auth)
					if r.is_success:
						created += 1
					else:
						skipped += 1
			except Exception as exc:
				report.errors.append(ImportError(path=f"calendar/caldav/{ev.uid}", kind="import", reason=str(exc)))

		report.created["calendar"] = created
		report.skipped["calendar"] = skipped
	except Exception as exc:
		report.errors.append(ImportError(path="calendar", kind="import", reason=str(exc)))


def _build_ical(ev: EventNode) -> str:
	lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//openZero//backup//EN", "BEGIN:VEVENT"]
	lines.append(f"UID:{ev.uid}")
	lines.append(f"SUMMARY:{ev.summary}")
	# Emit DTSTART with TZID if available (not floating UTC)
	if ev.tzid:
		lines.append(f"DTSTART;TZID={ev.tzid}:{ev.dtstart}")
	else:
		ts = ev.dtstart.replace("+00:00", "Z")
		lines.append(f"DTSTART:{ts}")
	if ev.dtend:
		if ev.tzid:
			lines.append(f"DTEND;TZID={ev.tzid}:{ev.dtend}")
		else:
			lines.append(f"DTEND:{ev.dtend.replace('+00:00', 'Z')}")
	if ev.rrule:
		lines.append(f"RRULE:{ev.rrule}")
	if ev.description:
		lines.append(f"DESCRIPTION:{ev.description[:MAX_DESC]}")
	lines.extend(["END:VEVENT", "END:VCALENDAR"])
	return "\r\n".join(lines) + "\r\n"


async def _import_memory(memory_raw: Optional[list], conflict: str, report: ImportReport) -> None:
	if not memory_raw:
		return
	try:
		from app.services.memory import get_qdrant, COLLECTION_NAME, get_embedder
		import asyncio
		client = get_qdrant()
		from qdrant_client.models import PointStruct

		points, _ = client.scroll(collection_name=COLLECTION_NAME, limit=10000, with_payload=True, with_vectors=False)
		existing_texts = {(p.payload or {}).get("text", ""): True for p in points}

		created = skipped = 0
		loop = asyncio.get_event_loop()

		for raw_pt in memory_raw:
			pt = MemoryPointNode(**raw_pt)
			if pt.text in existing_texts and conflict == "skip":
				skipped += 1
				continue
			vec = await loop.run_in_executor(None, lambda t=pt.text: get_embedder().encode(t).tolist())
			payload = {**pt.payload, "text": pt.text, "imported_from_backup": True}
			client.upsert(collection_name=COLLECTION_NAME, points=[
				PointStruct(id=pt.id, vector=vec, payload=payload)
			])
			created += 1

		report.created["memory"] = created
		report.skipped["memory"] = skipped
	except Exception as exc:
		report.errors.append(ImportError(path="memory", kind="import", reason=str(exc)))


async def _import_atlas(atlas_raw: Optional[dict], conflict: str, report: ImportReport) -> None:
	if not atlas_raw:
		return
	try:
		atlas = AtlasCurationExport(**atlas_raw)
		from app.models.db import AsyncSessionLocal
		from sqlalchemy import text as sa_text

		node_id_map: dict[int, int] = {}  # old_id -> new_id
		spine_id_map: dict[int, int] = {}

		async with AsyncSessionLocal() as session:
			# FK closure: collect valid node IDs in export
			export_node_ids = {n.id for n in atlas.nodes}

			# Import nodes
			created_n = 0
			for node in atlas.nodes:
				r = await session.execute(sa_text(
					"INSERT INTO atlas_nodes (type, label, payload, confidence, imported_from_backup) "
					"VALUES (:type, :label, :payload, :confidence, true) "
					"ON CONFLICT DO NOTHING RETURNING id"
				), {"type": node.type, "label": node.label, "payload": json.dumps(node.payload), "confidence": node.confidence})
				row = r.fetchone()
				if row:
					node_id_map[node.id] = row[0]
					created_n += 1
				else:
					# Find existing by label
					ex = (await session.execute(sa_text("SELECT id FROM atlas_nodes WHERE label=:l"), {"l": node.label})).fetchone()
					if ex:
						node_id_map[node.id] = ex[0]

			# Import edges — FK closure validation
			created_e = 0
			for edge in atlas.edges:
				if edge.source_node_id not in export_node_ids or edge.target_node_id not in export_node_ids:
					report.errors.append(ImportError(path=f"atlas/edge/{edge.source_node_id}->{edge.target_node_id}", kind="fk", reason="orphaned edge excluded"))
					continue
				src = node_id_map.get(edge.source_node_id)
				tgt = node_id_map.get(edge.target_node_id)
				if not src or not tgt:
					report.errors.append(ImportError(path=f"atlas/edge/{edge.source_node_id}->{edge.target_node_id}", kind="fk", reason="node not imported"))
					continue
				await session.execute(sa_text(
					"INSERT INTO atlas_edges (source_node_id, target_node_id, kind, weight, payload) "
					"VALUES (:s, :t, :k, :w, :p) ON CONFLICT DO NOTHING"
				), {"s": src, "t": tgt, "k": edge.kind, "w": edge.weight, "p": json.dumps(edge.payload)})
				created_e += 1

			# Import spines
			created_s = 0
			for spine in atlas.spines:
				r = await session.execute(sa_text(
					"INSERT INTO atlas_spines (label, confidence, payload, derived, locked) "
					"VALUES (:l, :c, :p, :d, :lk) RETURNING id"
				), {"l": spine.label, "c": spine.confidence, "p": json.dumps(spine.payload), "d": spine.derived, "lk": spine.locked})
				row = r.fetchone()
				if row:
					new_sid = row[0]
					spine_id_map[spine.id] = new_sid
					created_s += 1
					# Spine members — FK closure
					for nid in spine.member_node_ids:
						if nid not in export_node_ids:
							report.errors.append(ImportError(path=f"atlas/spine/{spine.id}/member/{nid}", kind="fk", reason="orphaned member excluded"))
							continue
						mapped = node_id_map.get(nid)
						if mapped:
							await session.execute(sa_text(
								"INSERT INTO atlas_spine_members (spine_id, node_id, weight) VALUES (:s, :n, 1.0) ON CONFLICT DO NOTHING"
							), {"s": new_sid, "n": mapped})
					if spine.summary:
						await session.execute(sa_text(
							"INSERT INTO atlas_spine_summaries (spine_id, summary_text) VALUES (:s, :t)"
						), {"s": new_sid, "t": spine.summary})

			await session.commit()

		report.created["atlas_nodes"] = created_n
		report.created["atlas_edges"] = created_e
		report.created["atlas_spines"] = created_s
	except Exception as exc:
		report.errors.append(ImportError(path="atlas", kind="import", reason=str(exc)))


async def _import_preferences(prefs_raw: Optional[dict], conflict: str, report: ImportReport) -> None:
	if not prefs_raw:
		return
	try:
		prefs = PreferencesExport(**prefs_raw)
		from app.models.db import AsyncSessionLocal, Preference
		from sqlalchemy import select
		created = skipped = 0
		async with AsyncSessionLocal() as session:
			for row in prefs.rows:
				res = await session.execute(select(Preference).where(Preference.key == row["key"]))
				existing = res.scalar_one_or_none()
				if existing and conflict == "skip":
					skipped += 1
					continue
				if existing:
					existing.value = row["value"]
				else:
					session.add(Preference(key=row["key"], value=row["value"]))
				created += 1
			await session.commit()
		report.created["preferences"] = created
		report.skipped["preferences"] = skipped
	except Exception as exc:
		report.errors.append(ImportError(path="preferences", kind="import", reason=str(exc)))


async def _import_custom_tasks(tasks_raw: Optional[list], conflict: str, report: ImportReport) -> None:
	if not tasks_raw:
		return
	try:
		from app.models.db import AsyncSessionLocal, CustomTask
		from sqlalchemy import select
		created = skipped = 0
		async with AsyncSessionLocal() as session:
			existing_names = {t.name for t in (await session.execute(select(CustomTask.name))).scalars().all()}
			for raw in tasks_raw:
				t = CustomTaskExport(**raw)
				if t.name in existing_names and conflict == "skip":
					skipped += 1
					continue
				task = CustomTask(
					name=t.name, message=t.message, job_type=t.job_type,
					spec=t.spec, is_active=t.is_active,
				)
				session.add(task)
				created += 1
			await session.commit()
		report.created["custom_tasks"] = created
		report.skipped["custom_tasks"] = skipped
	except Exception as exc:
		report.errors.append(ImportError(path="custom_tasks", kind="import", reason=str(exc)))


async def _import_tracking_sessions(tracking_raw: Optional[list], conflict: str, report: ImportReport) -> None:
	if not tracking_raw:
		return
	try:
		from app.models.db import AsyncSessionLocal, TrackingSession
		created = 0
		async with AsyncSessionLocal() as session:
			for raw in tracking_raw:
				ts = TrackingSessionExport(**raw)
				end_time = datetime.fromisoformat(ts.end_time.replace("Z", "+00:00")).replace(tzinfo=None)
				session.add(TrackingSession(
					tasks=ts.tasks,
					milestones_json=ts.milestones_json,
					end_time=end_time,
					is_active=False,  # forced false
					final_nudge_sent=True,
				))
				created += 1
			await session.commit()
		report.created["tracking_sessions"] = created
	except Exception as exc:
		report.errors.append(ImportError(path="tracking_sessions", kind="import", reason=str(exc)))


async def _import_email_rules(rules_raw: Optional[list], conflict: str, report: ImportReport) -> None:
	if not rules_raw:
		return
	try:
		from app.models.db import AsyncSessionLocal, EmailRule
		from sqlalchemy import select
		created = skipped = 0
		async with AsyncSessionLocal() as session:
			existing = {r.sender_pattern for r in (await session.execute(select(EmailRule))).scalars().all()}
			for raw in rules_raw:
				r = EmailRuleExport(**raw)
				if r.sender_pattern in existing and conflict == "skip":
					skipped += 1
					continue
				session.add(EmailRule(
					sender_pattern=r.sender_pattern,
					subject_pattern=r.subject_pattern,
					action=r.action,
					badge=r.badge,
				))
				created += 1
			await session.commit()
		report.created["email_rules"] = created
		report.skipped["email_rules"] = skipped
	except Exception as exc:
		report.errors.append(ImportError(path="email_rules", kind="import", reason=str(exc)))


async def _import_walkthroughs(walkthroughs_raw: Optional[list], conflict: str, report: ImportReport) -> None:
	if not walkthroughs_raw:
		return
	try:
		from app.models.db import AsyncSessionLocal
		from sqlalchemy import text as sa_text
		created = skipped = 0
		async with AsyncSessionLocal() as session:
			existing = {r[0] for r in (await session.execute(sa_text("SELECT title FROM walkthroughs"))).fetchall()}
			for raw in walkthroughs_raw:
				wt = WalkthroughExport(**raw)
				if wt.title in existing and conflict == "skip":
					skipped += 1
					continue
				r = await session.execute(sa_text("INSERT INTO walkthroughs (title) VALUES (:t) RETURNING id"), {"t": wt.title})
				wt_id = r.fetchone()[0]
				created += 1
				for stop in wt.stops:
					await session.execute(sa_text(
						"INSERT INTO walkthrough_stops (walkthrough_id, stop_order, narration, payload) VALUES (:w, :o, :n, :p)"
					), {"w": wt_id, "o": stop.stop_order, "n": stop.narration, "p": json.dumps(stop.payload)})
			await session.commit()
		report.created["walkthroughs"] = created
		report.skipped["walkthroughs"] = skipped
	except Exception as exc:
		report.errors.append(ImportError(path="walkthroughs", kind="import", reason=str(exc)))


async def _import_share_contracts(contracts_raw: Optional[list], conflict: str, report: ImportReport) -> None:
	if not contracts_raw:
		return
	try:
		from app.models.db import AsyncSessionLocal
		from sqlalchemy import text as sa_text
		from app.config import settings
		if not getattr(settings, "FEDERATION_ENABLED", False):
			report.skipped["share_contracts"] = len(contracts_raw)
			return
		created = 0
		async with AsyncSessionLocal() as session:
			for raw in contracts_raw:
				c = ShareContractExport(**raw)
				await session.execute(sa_text(
					"INSERT INTO share_contracts (producer_node, consumer_node, resource, scope_predicate, redactions, read_only) "
					"VALUES (:pn, :cn, :r, :sp, :rd, :ro)"
				), {
					"pn": c.producer_node, "cn": c.consumer_node, "r": c.resource,
					"sp": json.dumps(c.scope_predicate), "rd": json.dumps(c.redactions), "ro": c.read_only,
				})
				created += 1
			await session.commit()
		report.created["share_contracts"] = created
	except Exception as exc:
		report.errors.append(ImportError(path="share_contracts", kind="import", reason=str(exc)))


async def _import_redis(redis_raw: Optional[dict], conflict: str, report: ImportReport) -> None:
	if not redis_raw:
		return
	try:
		import redis as _redis
		from app.config import settings
		r = _redis.Redis(
			host=settings.REDIS_HOST, port=settings.REDIS_PORT,
			password=settings.REDIS_PASSWORD or None,
			decode_responses=True, socket_timeout=3.0,
		)
		redis_exp = RedisExport(**redis_raw)
		created = 0
		if redis_exp.planka_privacy_override:
			key = "planka_privacy_override"
			if not r.exists(key) or conflict != "skip":
				r.set(key, redis_exp.planka_privacy_override + ":imported_from_backup")
				created += 1
		if redis_exp.ambient_capture_authorship:
			key = "ambient_capture:authorship"
			if not r.exists(key) or conflict != "skip":
				r.set(key, redis_exp.ambient_capture_authorship + ":imported_from_backup")
				created += 1
		report.created["redis"] = created
	except Exception as exc:
		report.errors.append(ImportError(path="redis", kind="import", reason=str(exc)))


async def _import_files(files_raw: Optional[dict], conflict: str, report: ImportReport) -> None:
	if not files_raw:
		return
	try:
		files_exp = FilesExport(**files_raw)
		repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
		created = skipped = 0

		import difflib

		for entry in files_exp.files:
			rel = entry.path
			# Safety: only allow agent/ and personal/ directories
			if not (rel.startswith("agent/") or rel.startswith("personal/")):
				report.errors.append(ImportError(path=f"files/{rel}", kind="path", reason="path outside allowed directories"))
				continue
			full = os.path.join(repo_root, rel)
			# Prevent path traversal
			if not os.path.abspath(full).startswith(repo_root):
				report.errors.append(ImportError(path=f"files/{rel}", kind="path", reason="path traversal detected"))
				continue
			os.makedirs(os.path.dirname(full), exist_ok=True)

			# Special handling for domain.derived.yaml: default skip
			if rel.endswith("domain.derived.yaml"):
				if conflict == "skip" or conflict == "merge":
					if os.path.exists(full) and conflict == "merge":
						# Land as .imported.yaml for diff review
						imported_path = full.replace("domain.derived.yaml", "domain.derived.imported.yaml")
						with open(imported_path, "w", encoding="utf-8") as f:
							f.write(entry.content)
						report.errors.append(ImportError(path=f"files/{rel}", kind="merge", reason="domain.derived.yaml landed as domain.derived.imported.yaml — review and merge manually"))
					skipped += 1
					continue

			if os.path.exists(full):
				if conflict == "skip":
					skipped += 1
					continue
				if conflict == "merge":
					with open(full, "r", encoding="utf-8", errors="replace") as f:
						existing = f.read()
					if existing == entry.content:
						skipped += 1
						continue
					# Unified diff stored in report
					diff = "".join(difflib.unified_diff(
						existing.splitlines(keepends=True),
						entry.content.splitlines(keepends=True),
						fromfile=f"existing/{rel}",
						tofile=f"imported/{rel}",
					))
					report.errors.append(ImportError(path=f"files/{rel}", kind="diff", reason=diff[:2048]))
					skipped += 1
					continue

			with open(full, "w", encoding="utf-8") as f:
				f.write(entry.content)
			created += 1

		report.created["files"] = created
		report.skipped["files"] = skipped
	except Exception as exc:
		report.errors.append(ImportError(path="files", kind="import", reason=str(exc)))
