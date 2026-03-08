import re
import datetime
import logging
from app.services.operator_board import operator_service
from app.api.telegram import send_notification, _get_stats_footer
from app.services.llm import chat

logger = logging.getLogger(__name__)

# Urgency label → nudge interval in minutes
URGENCY_INTERVALS: dict[str, int] = {
    "urgent": 10,
    "medium": 60,
    "low": 180,
}

# card_id → (last_nudged_at, urgency_label, interval_minutes)
_nudge_state: dict[str, tuple[datetime.datetime, str, int]] = {}

# Lower-cased task-name fragment → interval override in minutes.
# Populated by the SET_NUDGE_INTERVAL Semantic Action Tag.
_nudge_overrides: dict[str, int] = {}


def set_nudge_override(task_fragment: str, minutes: int) -> None:
    """Store a user-requested custom nudge interval for a task name fragment."""
    _nudge_overrides[task_fragment.strip().lower()] = minutes


def _parse_custom_interval(text: str) -> int | None:
    """Extract an explicit nudge interval (in minutes) embedded in a task name.

    Recognised patterns (case-insensitive):
      [nudge:10m]  [10m]  [2h]
      every 15 minutes / every 2 hours
      nudge me in 30 min / nudge in 1 hour
      remind me in 45 minutes
    Returns minutes as int, or None if nothing found.
    """
    t = text.lower()
    # [nudge:10m] / [10m] / [2h]
    m = re.search(r'\[(?:nudge:)?(\d+)\s*(m|h|min|hr|hour|hours|minute|minutes)\]', t)
    if m:
        val, unit = int(m.group(1)), m.group(2)
        return val if unit.startswith('m') else val * 60
    # every N minutes/hours
    m = re.search(r'every\s+(\d+)\s*(m|h|min|hr|hour|hours|minute|minutes)', t)
    if m:
        val, unit = int(m.group(1)), m.group(2)
        return val if unit.startswith('m') else val * 60
    # nudge (me) in N
    m = re.search(r'nudge(?:\s+me)?\s+(?:in\s+)?(\d+)\s*(m|h|min|hr|hour|hours|minute|minutes)', t)
    if m:
        val, unit = int(m.group(1)), m.group(2)
        return val if unit.startswith('m') else val * 60
    # remind (me) in N
    m = re.search(r'remind(?:\s+me)?\s+(?:in\s+)?(\d+)\s*(m|h|min|hr|hour|hours|minute|minutes)', t)
    if m:
        val, unit = int(m.group(1)), m.group(2)
        return val if unit.startswith('m') else val * 60
    return None


def _keyword_urgency(text: str) -> str | None:
    """Fast keyword-based urgency estimate.

    Returns 'urgent', 'medium', or 'low', or None if the task needs LLM classification.
    """
    t = text.lower()
    urgent_kw = {
        "urgent", "asap", "critical", "deadline", "emergency",
        "hotfix", "outage", "down", "broken", "regression", "blocker",
    }
    low_kw = {
        "someday", "later", "maybe", "backlog", "idea", "wishlist",
        "low priority", "nice to have", "eventually", "icebox",
    }
    if any(k in t for k in urgent_kw) or t.count('!') >= 2:
        return "urgent"
    if any(k in t for k in low_kw):
        return "low"
    return None


async def _llm_classify_urgency(task_titles: list[str]) -> dict[str, str]:
    """Use the instant LLM tier to classify urgency for tasks not caught by keywords.

    Returns a dict mapping task title → 'urgent' | 'medium' | 'low'.
    Falls back to 'medium' for any title that cannot be matched.
    """
    if not task_titles:
        return {}
    items = "\n".join(f"- {t}" for t in task_titles)
    prompt = (
        "Classify each task's urgency as exactly one of: urgent, medium, or low.\n"
        "urgent = time-critical, must finish within the next hour\n"
        "medium = important but can wait 1-2 hours\n"
        "low = non-urgent, no immediate deadline today\n\n"
        f"Tasks:\n{items}\n\n"
        "Reply ONLY with lines in the format: <task name>: <urgency>\n"
        "No explanation, no preamble."
    )
    try:
        result = await chat(prompt, tier="instant")
        mapping: dict[str, str] = {}
        for line in result.strip().splitlines():
            if ':' not in line:
                continue
            name_part, urgency_part = line.rsplit(':', 1)
            urgency = urgency_part.strip().lower()
            if urgency not in URGENCY_INTERVALS:
                continue
            name_part = name_part.strip().lstrip('- ')
            for t in task_titles:
                if name_part in t or t in name_part:
                    mapping[t] = urgency
                    break
        return mapping
    except Exception as e:
        logger.warning("LLM urgency classification failed: %s", e)
        return {}


async def run_proactive_follow_up():
    """Scan the Operator Board's 'Today' list and send urgency-adapted nudges.

    Nudge cadence per urgency level:
      urgent  → every 10 minutes
      medium  → every 60 minutes
      low     → every 180 minutes (3 hours)
      custom  → interval parsed from the task name  OR set via SET_NUDGE_INTERVAL action

    The scheduler calls this every 10 minutes during work hours (09:00–21:50).
    State is kept in the module-level _nudge_state dict so cards are only nudged
    when their individual interval has elapsed.
    """
    try:
        logger.info("Proactive Follow-up: Checking mission status...")
        async with await operator_service._get_client() as client:
            project_id, board_id = await operator_service.initialize_board(client)

            board_resp = await client.get(f"/api/boards/{board_id}", params={"included": "lists,cards"})
            board_resp.raise_for_status()
            board_detail = board_resp.json()

            included = board_detail.get("included", {})
            lists = included.get("lists", [])
            cards = included.get("cards", [])

            today_list = next((l for l in lists if l["name"] == "Today"), None)
            if not today_list:
                logger.warning("Follow-up: 'Today' list not found on Operator Board.")
                return

            today_cards = [c for c in cards if c["listId"] == today_list["id"]]
            if not today_cards:
                logger.info("Follow-up: No active tasks in 'Today'.")
                return

            now = datetime.datetime.now()

            # --- Step 1: Determine urgency and interval for each card ---
            # Priority: override dict → inline name pattern → keyword → LLM
            card_intervals: dict[str, tuple[str, int]] = {}  # card_id → (label, minutes)
            needs_llm: list[dict] = []

            for card in today_cards:
                card_id = card["id"]
                name = card["name"]

                # a) User-set override via SET_NUDGE_INTERVAL action tag
                for fragment, minutes in _nudge_overrides.items():
                    if fragment in name.lower():
                        card_intervals[card_id] = ("custom", minutes)
                        break
                if card_id in card_intervals:
                    continue

                # b) Interval embedded in the task name itself
                custom = _parse_custom_interval(name)
                if custom is not None:
                    card_intervals[card_id] = ("custom", custom)
                    continue

                # c) Fast keyword check
                kw = _keyword_urgency(name)
                if kw:
                    card_intervals[card_id] = (kw, URGENCY_INTERVALS[kw])
                    continue

                # d) Defer to LLM for ambiguous tasks
                needs_llm.append(card)

            # e) LLM classification for any remaining cards
            if needs_llm:
                llm_result = await _llm_classify_urgency([c["name"] for c in needs_llm])
                for card in needs_llm:
                    urgency = llm_result.get(card["name"], "medium")
                    card_intervals[card["id"]] = (urgency, URGENCY_INTERVALS[urgency])

            # --- Step 2: Filter to cards whose interval has elapsed ---
            due_cards: list[tuple[dict, str, int]] = []
            for card in today_cards:
                card_id = card["id"]
                urgency, interval_min = card_intervals.get(card_id, ("medium", 60))
                state = _nudge_state.get(card_id)
                elapsed = (now - state[0]).total_seconds() / 60 if state else float('inf')
                if elapsed >= interval_min:
                    due_cards.append((card, urgency, interval_min))
                    _nudge_state[card_id] = (now, urgency, interval_min)

            if not due_cards:
                logger.info("Follow-up: No cards due for nudge yet.")
                return

            # --- Step 3: Generate and deliver nudge ---
            task_line = ", ".join(
                f"{c['name']} ({urgency})" for c, urgency, _ in due_cards[:5]
            )
            prompt = (
                f"The user has these mission items due for a check-in: {task_line}. "
                "Ask them warmly and directly for a progress update on these specific missions. "
                "Keep it concise (1-2 sentences). No filler. Just the mission check."
            )
            nudge = await chat(prompt)
            footer = await _get_stats_footer()
            await send_notification(f"🎯 *Mission Check:*\n\n{nudge}{footer}")
            logger.info("Follow-up: Sent nudge for %s tasks.", len(due_cards))

    except Exception as e:
        logger.error("Proactive Follow-up failed: %s", e)

async def check_active_tracking_sessions():
    """
    Monitors active TrackingSessions and delivers granular, 
    item-specific progress nudges as requested.
    """
    from app.models.db import TrackingSession, AsyncSessionLocal
    import datetime
    import json
    from sqlalchemy import select
    
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(TrackingSession).where(TrackingSession.is_active.is_(True)))
            sessions = result.scalars().all()
            
            now = datetime.datetime.now()
            
            for session in sessions:
                modified = False
                milestones = json.loads(session.milestones_json) if session.milestones_json else []
                
                # 1. Process Individual Milestones (In-Progress)
                for m in milestones:
                    due_dt = datetime.datetime.fromisoformat(m["due_at"])
                    if now >= due_dt and not m.get("sent"):
                        logger.info("Proximity: Milestone check for '%s' (Session %s)", m['task'], session.id)
                        prompt = (
                            f"Target Zero: The allocated duration for this mission item has passed: '{m['task']}'. "
                            "Do a technical progress check. Ask if this segment is complete or if unexpected friction occurred. "
                            "Keep it direct and professional."
                        )
                        nudge = await chat(prompt)
                        footer = await _get_stats_footer()
                        await send_notification(f"⚖️ *Segment Check:* \n\n{nudge}{footer}")
                        m["sent"] = True
                        modified = True
                
                # 2. Final Session Wrap-up
                if now >= session.end_time and not session.final_nudge_sent:
                    logger.info("Proximity: Final check for Session %s", session.id)
                    prompt = (
                        f"Target Zero: The full mission timeframe is complete for: {session.tasks}. "
                        "Ask for final confirmation on which blocks reached 100% completion. "
                        "Be direct. This is the final mission-wrap-up."
                    )
                    nudge = await chat(prompt)
                    footer = await _get_stats_footer()
                    await send_notification(f"🏁 *Final Mission Wrap-up:* \n\n{nudge}{footer}")
                    session.final_nudge_sent = True
                    session.is_active = False
                    modified = True

                if modified:
                    session.milestones_json = json.dumps(milestones)
                    await db.commit()
                    
    except Exception as e:
        logger.error("Tracking Session Check failed: %s", e)
