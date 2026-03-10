from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

# Centralized scheduler instance to break circular import cycles between 
# task modules (which the scheduler needs to import to schedule them) 
# and service modules (which need the scheduler to add dynamic jobs).
scheduler = AsyncIOScheduler(timezone=pytz.utc)
