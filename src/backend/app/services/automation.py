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
        if not person.calendar_id:
            continue
            
        # Look ahead 7 days
        events = await fetch_calendar_events(calendar_id=person.calendar_id, days_ahead=7)
        
        for event in events:
            summary = event["summary"].lower()
            is_priority = any(kw in summary for kw in PRIORITY_KEYWORDS)
            
            if is_priority:
                # Check if it's coming up in next 3 days specifically for the "alert"
                start_date = event["start"].split("T")[0]
                event_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                days_until = (event_date - datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).days
                
                if 0 <= days_until <= 3:
                    task_title = f"Alert: {person.name}'s {event['summary']} ({start_date})"
                    
                    # Logic to prevent duplicates: Check if task exists (simplified)
                    # For now, we attempt to create it in the 'Family' board, 'Inbox' list
                    # These names should probably be configurable, but 'Family' is our standard
                    success = create_task(board_name="Family", list_name="Inbox", title=task_title)
                    
                    if success:
                        actions.append(f"Created priority task for {person.name}: {event['summary']} (in {days_until} days)")
                    else:
                        # If board/list not found, we still report it for the briefing
                        actions.append(f"Priority detected for {person.name}: {event['summary']} (in {days_until} days)")
    
    return actions
