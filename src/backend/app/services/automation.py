from app.services.calendar import fetch_calendar_events
from app.services.planka import create_task
from app.models.db import Person
import datetime

PRIORITY_KEYWORDS = ["birthday", "deadline", "due", "important", "exam", "test", "appointment"]

async def run_contextual_automation(people: list[Person]):
    """
    Scans circle calendars for priority events and creates Planka tasks.
    Returns a list of actions taken for the briefing.
    """
    actions = []
    
    # Fetch primary events once ahead of time for efficiency
    try:
        primary_events = await fetch_calendar_events(calendar_id="primary", days_ahead=7)
    except Exception as ce:
        print(f"DEBUG: Automation calendar scan skipped: {ce}")
        primary_events = []

    for person in people:
        prefix = f"{person.name}:"
        events_to_process = [
            (e, person) for e in primary_events 
            if e["summary"].startswith(prefix)
        ]
        
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
                    if display_summary.startswith(f"{person.name}:"):
                        display_summary = display_summary[len(f"{person.name}:"):].strip()

                    task_title = f"Alert: {person.name}'s {display_summary} ({start_date})"
                    
                    success = await create_task(board_name="Family", list_name="Inbox", title=task_title)
                    
                    if success:
                        actions.append(f"Created priority task for {person.name}: {display_summary} (in {days_until} days)")
                    else:
                        actions.append(f"Priority detected for {person.name}: {display_summary} (in {days_until} days)")
    
    return actions
