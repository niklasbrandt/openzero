from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.models.db import engine, Base, AsyncSessionLocal, Person
from sqlalchemy import select
from app.services.memory import ensure_collection
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.api.telegram import start_telegram_bot, stop_telegram_bot
from sqlalchemy import text

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown logic."""
    # --- STARTUP ---
    # 1. Initialize Postgres tables
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
            # --- Migrations ---
            # 1. Add 'badge' column to 'email_rules' if not exists
            res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='email_rules' AND column_name='badge'"))
            if not res.fetchone():
                await conn.execute(text("ALTER TABLE email_rules ADD COLUMN badge VARCHAR"))
            
            # 2. Add 'badge' column to 'email_summaries' if not exists
            res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='email_summaries' AND column_name='badge'"))
            if not res.fetchone():
                await conn.execute(text("ALTER TABLE email_summaries ADD COLUMN badge VARCHAR"))

        print("✓ Postgres tables initialized and migrated.")
    except Exception as e:
        print(f"⚠ Warning: Could not connect to Postgres: {e}")
    
    # 2. Initialize Qdrant collection
    try:
        await ensure_collection()
        from app.services.memory import get_memory_stats
        stats = await get_memory_stats()
        if stats['status'] == 'error':
            raise Exception("Stats check failed")
        print(f"✓ Qdrant collection ready ({stats['points']} points).")
    except Exception as e:
        print(f"⚠ Warning: Could not connect to Qdrant: {e}")
    
    # 3. Start background tasks & bot
    try:
        print("Starting scheduler...")
        await start_scheduler()
        print("Starting Telegram bot...")
        await start_telegram_bot()
        print("Background tasks & bot started.")
        
        # 4. Warm up intelligence engine
        print("⚡ Warming up intelligence engine...")
        from app.services.memory import get_embedder
        import asyncio
        # Pre-load embedder in a thread to not block startup too much, 
        # though lifespan is async anyway.
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, get_embedder)
        print("✓ AI models loaded in memory.")
        
        # 5. Ensure Identity Record
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Person).where(Person.circle_type == "identity"))
            if not res.scalar_one_or_none():
                session.add(Person(
                    name="User", 
                    relationship="Self", 
                    circle_type="identity",
                    context="Z is beginning to understand your core parameters."
                ))
                await session.commit()
                print("✓ Identity record initialized.")

        # Initial Operator Board Sync
        from app.services.operator_board import operator_service
        sync_res = await operator_service.sync_operator_tasks()
        print(f"✓ {sync_res}")
    except Exception as e:
        print(f"⚠ Warning: Background startup failed: {e}")
        
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

@app.get("/calendar", include_in_schema=False)
async def calendar_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/?open=calendar")

@app.get("/boards", include_in_schema=False)
async def boards_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/api/dashboard/planka-redirect")

# Serve the Dashboard
@app.get("/", include_in_schema=False)
async def serve_dashboard():
    from fastapi.responses import FileResponse
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"detail": "Dashboard not found"}

if os.path.exists("static"):
    app.mount("/dashboard-assets", StaticFiles(directory="static/dashboard-assets"), name="dashboard-assets")
    # Also mount the rest of static without html=True fallback
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/health")
async def health():
    return {"status": "ok"}
