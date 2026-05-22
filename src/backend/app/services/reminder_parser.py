"""Recurring reminder parser and CRUD service.

Supported syntax:
  /remind daily HH:MM <text>
  /remind weekly mon|tue|wed|thu|fri|sat|sun HH:MM <text>
  /remind delete <id>
  /remind list
"""
import logging
import re
from typing import Optional

from sqlalchemy import select

logger = logging.getLogger(__name__)

_DAILY_RE = re.compile(r'^daily[ \t]+(\d{1,2}):(\d{2})[ \t]+([^\n]+)$', re.IGNORECASE)
_WEEKLY_RE = re.compile(r'^weekly[ \t]+(mon|tue|wed|thu|fri|sat|sun)[ \t]+(\d{1,2}):(\d{2})[ \t]+([^\n]+)$', re.IGNORECASE)
_DELETE_RE = re.compile(r'^delete\s+(\d+)$', re.IGNORECASE)
_LIST_RE = re.compile(r'^list$', re.IGNORECASE)

_USAGE = (
	"Usage:\n"
	"  /remind daily HH:MM <text>  — fires every day at HH:MM\n"
	"  /remind weekly mon|tue|...|sun HH:MM <text>  — fires weekly on that day\n"
	"  /remind delete <id>  — remove a reminder by ID\n"
	"  /remind list  — show all active reminders"
)


async def handle_remind_command(args: str, channel: str) -> str:
	"""Parse a /remind command and execute the appropriate CRUD operation.

	Returns a human-readable confirmation string.
	"""
	args = args.strip()
	if not args:
		return _USAGE

	m = _DAILY_RE.match(args)
	if m:
		hour, minute, text = int(m.group(1)), int(m.group(2)), m.group(3).strip()
		if hour > 23 or minute > 59:
			return "Invalid time. Use HH:MM format, e.g. 08:30."
		rid = await _create_reminder(channel=channel, cadence="daily", day_of_week=None, hour=hour, minute=minute, text=text)
		return f"Reminder #{rid} set: every day at {hour:02d}:{minute:02d} — {text}"

	m = _WEEKLY_RE.match(args)
	if m:
		dow, hour, minute, text = m.group(1).lower(), int(m.group(2)), int(m.group(3)), m.group(4).strip()
		if hour > 23 or minute > 59:
			return "Invalid time. Use HH:MM format, e.g. 19:00."
		rid = await _create_reminder(channel=channel, cadence="weekly", day_of_week=dow, hour=hour, minute=minute, text=text)
		return f"Reminder #{rid} set: every {dow} at {hour:02d}:{minute:02d} — {text}"

	m = _DELETE_RE.match(args)
	if m:
		rid = int(m.group(1))
		deleted = await _delete_reminder(rid)
		if deleted:
			return f"Reminder #{rid} deleted."
		return f"No reminder found with ID #{rid}."

	if _LIST_RE.match(args):
		return await _list_reminders()

	return _USAGE


async def _create_reminder(channel: str, cadence: str, day_of_week: Optional[str], hour: int, minute: int, text: str) -> int:
	from app.models.db import AsyncSessionLocal, RecurringReminder
	async with AsyncSessionLocal() as session:
		r = RecurringReminder(
			channel=channel,
			cadence=cadence,
			day_of_week=day_of_week,
			hour=hour,
			minute=minute,
			text=text,
		)
		session.add(r)
		await session.commit()
		await session.refresh(r)
		return r.id


async def _delete_reminder(reminder_id: int) -> bool:
	from app.models.db import AsyncSessionLocal, RecurringReminder
	async with AsyncSessionLocal() as session:
		result = await session.execute(select(RecurringReminder).where(RecurringReminder.id == reminder_id))
		r = result.scalar_one_or_none()
		if r is None:
			return False
		await session.delete(r)
		await session.commit()
		return True


async def _list_reminders() -> str:
	from app.models.db import AsyncSessionLocal, RecurringReminder
	async with AsyncSessionLocal() as session:
		result = await session.execute(
			select(RecurringReminder).where(RecurringReminder.enabled == True).order_by(RecurringReminder.id)  # noqa: E712
		)
		reminders = list(result.scalars().all())
	if not reminders:
		return "No active reminders."
	lines = ["Active reminders:"]
	for r in reminders:
		if r.cadence == "daily":
			schedule = f"daily {r.hour:02d}:{r.minute:02d}"
		else:
			schedule = f"weekly {r.day_of_week} {r.hour:02d}:{r.minute:02d}"
		lines.append(f"  #{r.id} [{r.channel}] {schedule} — {r.text}")
	return "\n".join(lines)
