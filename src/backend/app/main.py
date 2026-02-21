from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.models.db import engine, Base
from app.services.memory import ensure_collection
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.api.telegram import start_telegram_bot, stop_telegram_bot

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown logic."""
    # --- STARTUP ---
    # 1. Initialize Postgres tables
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Ensure new columns are added if the table already existed
            from sqlalchemy import text
            try:
                await conn.execute(text("ALTER TABLE people ADD COLUMN IF NOT EXISTS use_my_calendar BOOLEAN DEFAULT FALSE"))
            except:
                pass # Already exists or sqlite/etc
        print("✓ Postgres tables initialized.")
    except Exception as e:
        print(f"⚠ Warning: Could not connect to Postgres: {e}")
    
    # 2. Initialize Qdrant collection
    try:
        await ensure_collection()
        print("✓ Qdrant collection ready.")
    except Exception as e:
        print(f"⚠ Warning: Could not connect to Qdrant: {e}")
    
    # 3. Start background tasks & bot
    try:
        await start_scheduler()
        await start_telegram_bot()
    except Exception as e:
        print(f"⚠ Warning: Background tasks failed to start: {e}")
        
    yield
    # --- SHUTDOWN ---
    await stop_telegram_bot()
    await stop_scheduler()

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.dashboard import router as dashboard_router
import os

app = FastAPI(title="Personal AI OS", lifespan=lifespan)

# Add CORS for the dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router)

# Serve the Dashboard
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.get("/health")
async def health():
    return {"status": "ok"}
