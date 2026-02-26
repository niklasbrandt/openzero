import httpx
import logging
from app.services.operator_board import operator_service
from app.api.telegram import send_notification, _get_stats_footer
from app.services.llm import chat
from app.config import settings

logger = logging.getLogger(__name__)

async def run_proactive_follow_up():
    """
    Scans the Operator Board's 'Today' list for uncompleted tasks 
    and sends a proactive nudge to the user via Telegram.
    """
    try:
        logger.info("Proactive Follow-up: Checking mission status...")
        async with await operator_service._get_client() as client:
            # 1. Ensure board is initialized
            project_id, board_id = await operator_service.initialize_board(client)
            
            # 2. Fetch Board Details with Lists and Cards
            # Note: We need to see which cards are in which lists.
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
            
            # 3. Filter cards in 'Today'
            today_cards = [c for c in cards if c["listId"] == today_list["id"]]
            
            if not today_cards:
                logger.info("Follow-up: No active tasks in 'Today'.")
                return

            # 4. Generate Proactive Nudge using LLM
            task_titles = [c["name"] for c in today_cards[:3]] # Keep it brief
            prompt = (
                f"The user has these items on their 'Today' list: {', '.join(task_titles)}. "
                "Ask them warmly and directly for a progress update on these specific missions. "
                "Keep it concise (1-2 sentences). No filler like 'I noticed' or 'I am checking'. Just the mission check."
            )
            
            nudge = await chat(prompt)
            footer = await _get_stats_footer()
            
            # 5. Send Notification
            await send_notification(f"🎯 *Mission Check:*\n\n{nudge}{footer}")
            logger.info(f"Follow-up: Sent nudge for {len(today_cards)} tasks.")

    except Exception as e:
        logger.error(f"Proactive Follow-up failed: {e}")

async def check_active_tracking_sessions():
    """
    Monitors active TrackingSessions and delivers granular, 
    item-specific progress nudges as requested.
    """
    from app.models.db import TrackingSession, AsyncSessionLocal
    import datetime, json
    from sqlalchemy import select
    
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(TrackingSession).where(TrackingSession.is_active == True))
            sessions = result.scalars().all()
            
            now = datetime.datetime.now()
            
            for session in sessions:
                modified = False
                milestones = json.loads(session.milestones_json) if session.milestones_json else []
                
                # 1. Process Individual Milestones (In-Progress)
                for m in milestones:
                    due_dt = datetime.datetime.fromisoformat(m["due_at"])
                    if now >= due_dt and not m.get("sent"):
                        logger.info(f"Proximity: Milestone check for '{m['task']}' (Session {session.id})")
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
                    logger.info(f"Proximity: Final check for Session {session.id}")
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
        logger.error(f"Tracking Session Check failed: {e}")
