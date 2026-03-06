from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.models.db import engine, Base, AsyncSessionLocal, Person
from sqlalchemy import select
from app.services.memory import ensure_collection
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.api.telegram import start_telegram_bot, stop_telegram_bot
import os
import asyncio
from sqlalchemy import text

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

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

        logging.info("✓ Postgres tables initialized and migrated.")
    except Exception as e:
        logging.warning(f"⚠ Warning: Could not connect to Postgres: {e}")
    
    # 2. Initialize Qdrant collection
    if settings.IS_DOCKER and not settings.QDRANT_API_KEY:
        raise RuntimeError(
            "QDRANT_API_KEY must be set in .env when running in Docker."
        )
    try:
        await ensure_collection()
        from app.services.memory import get_memory_stats
        stats = await get_memory_stats()
        if stats['status'] == 'error':
            raise Exception("Stats check failed")
        logging.info(f"✓ Qdrant collection ready ({stats['points']} points).")
    except Exception as e:
        logging.warning(f"⚠ Warning: Could not connect to Qdrant: {e}")
    
    # 3. Start background tasks & bot
    try:
        logging.info("Starting scheduler...")
        await start_scheduler()
        logging.info("Starting Telegram bot...")
        await start_telegram_bot()
        logging.info("Background tasks & bot started.")
        
        # 5-8. Background Startup Sequence (Non-blocking)
        async def run_background_startup():
            try:
                # 1. Warm up intelligence engine (Priority: Load models first)
                logging.info("⚡ Warming up intelligence engine...")
                from app.services.memory import get_embedder
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, get_embedder)
                logging.info("✓ AI models loaded in memory.")

                # Identity Record and Operator Sync moved here for stability
                # ...
                
                # 3. Ensure Identity Record
                async with AsyncSessionLocal() as session:
                    res = await session.execute(select(Person).where(Person.circle_type == "identity"))
                    if not res.scalar_one_or_none():
                        session.add(Person(
                            name="User", relationship="Self", circle_type="identity",
                            context="Z is beginning to understand your core parameters."
                        ))
                        await session.commit()
                        logging.info("✓ Identity record initialized.")
                # 3b. Load user settings (timezone, location) from DB into cache
                from app.services.timezone import refresh_user_settings
                await refresh_user_settings()
                logging.info("\u2713 User settings loaded from identity record.")
                # 4. Initial Operator Board Sync
                from app.services.operator_board import operator_service
                sync_res = await operator_service.sync_operator_tasks()
                logging.info(f"✓ {sync_res}")
            except Exception as e:
                logging.warning(f"⚠ Warning: Background startup tasks failed: {e}")

        asyncio.create_task(run_background_startup())

    except Exception as e:
        logging.warning(f"⚠ Warning: Core startup failed: {e}")
        
    yield
    # --- SHUTDOWN ---
    await stop_telegram_bot()
    await stop_scheduler()

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.api.dashboard import router as dashboard_router, auth_router
from app.api.health import router as health_router
from app.config import settings

app = FastAPI(title="Personal AI OS", lifespan=lifespan)


class CacheHeaderMiddleware(BaseHTTPMiddleware):
    """Set immutable cache headers for content-hashed dashboard assets.

    Files under /dashboard-assets/ have content hashes in their names
    (e.g. index-CyFrH-zg.css), making them safe for aggressive caching.
    The root HTML is served with no-cache so reloads always get fresh
    asset references.
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/dashboard-assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path in ("/home", "/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


# Add CORS for the dashboard — restrict to the configured base URL (not wildcard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.BASE_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(CacheHeaderMiddleware)

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(health_router)

@app.get("/calendar", include_in_schema=False)
async def calendar_redirect():
    return RedirectResponse(url="/home?open=calendar")

@app.get("/boards", include_in_schema=False)
async def boards_redirect():
    return RedirectResponse(url="/api/dashboard/planka-redirect")

@app.get("/projects", include_in_schema=False)
async def projects_redirect():
    return RedirectResponse(url="/api/dashboard/planka-redirect")

# Serve the Dashboard
@app.get("/home", include_in_schema=False)
async def serve_dashboard():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"detail": "Dashboard not found"}

@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/home")

if os.path.exists("static/dashboard-assets"):
    app.mount("/dashboard-assets", StaticFiles(directory="static/dashboard-assets"), name="dashboard-assets")
if os.path.exists("static"):
    # Also mount the rest of static without html=True fallback
    app.mount("/static", StaticFiles(directory="static"), name="static")
