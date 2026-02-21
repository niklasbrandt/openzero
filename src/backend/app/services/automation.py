from app.services.calendar import fetch_calendar_events
from app.services.planka import create_task, get_planka_client
from app.models.db import Person
import datetime

PRIORITY_KEYWORDS = ["birthday", "deadline", "due", "important", "exam", "test", "appointment"]

async def run_contextual_automation(people: list[Person]):
    """
    Scans circle calendars for priority events and creates Planka tasks.
    Returns a list of actions taken for the briefing.
    """
    actions = []
    
    for person in people:
        # 1. Check person's dedicated calendar
        if person.calendar_id and not person.use_my_calendar:
            dedicated_events = await fetch_calendar_events(calendar_id=person.calendar_id, days_ahead=7)
            events_to_process = [(e, person) for e in dedicated_events]
        # 2. Check primary calendar for prefixed events
        elif person.use_my_calendar:
            primary_events = await fetch_calendar_events(calendar_id="primary", days_ahead=7)
            prefix = f"{person.name}:"
            events_to_process = [
                (e, person) for e in primary_events 
                if e["summary"].startswith(prefix)
            ]
        else:
            continue
            
        for event, person in events_to_process:
            summary = event["summary"].lower()
            is_priority = any(kw in summary for kw in PRIORITY_KEYWORDS)
            
            if is_priority:
                # Check if it's coming up in next 3 days specifically for the "alert"
                start_date = event["start"].split("T")[0]
                event_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                days_until = (event_date - datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).days
                
                if 0 <= days_until <= 3:
                    # Clean the name from summary if it's prefixed
                    display_summary = event["summary"]
                    if person.use_my_calendar and display_summary.startswith(f"{person.name}:"):
                        display_summary = display_summary[len(f"{person.name}:"):].strip()

                    task_title = f"Alert: {person.name}'s {display_summary} ({start_date})"
                    
                    success = create_task(board_name="Family", list_name="Inbox", title=task_title)
                    
                    if success:
                        actions.append(f"Created priority task for {person.name}: {display_summary} (in {days_until} days)")
                    else:
                        actions.append(f"Priority detected for {person.name}: {display_summary} (in {days_until} days)")
    
    return actions
