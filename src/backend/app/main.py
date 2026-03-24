import logging
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.db import engine, Base, AsyncSessionLocal
from app.models.people import Person
from app.services.memory import ensure_collection
from app.services.automation import start_scheduler, stop_scheduler
from app.api.telegram_bot import start_telegram_bot, stop_telegram_bot

# Set up logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    \"\"\"
    Unified startup and shutdown lifecycle manager.
    Note: Heavy AI model warming and context loading are moved to non-blocking 
    background tasks to ensure the Telegram bot greets the operator instantly.
    \"\"\"
    # 1. Initialize Postgres tables
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Schema migrations for People table
            _people_work_cols = {
                "employer": "ALTER TABLE people ADD COLUMN employer VARCHAR;",
                "job_title": "ALTER TABLE people ADD COLUMN job_title VARCHAR;",
                "department": "ALTER TABLE people ADD COLUMN department VARCHAR;"
            }
            for col, alter_sql in _people_work_cols.items():
                res = await conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='people' AND column_name=:col"
                ), {"col": col})
                if not res.fetchone():
                    await conn.execute(text(alter_sql))
        logging.info("✓ Postgres tables initialized and migrated.")
    except Exception as e:
        logging.warning("⚠ Warning: Could not connect to Postgres: %s", e)
    
    # 2. Initialize Qdrant collection
    if settings.IS_DOCKER and not settings.QDRANT_API_KEY:
        raise RuntimeError("QDRANT_API_KEY must be set in .env when running in Docker.")
    try:
        await ensure_collection()
        from app.services.memory import get_memory_stats
        stats = await get_memory_stats()
        logging.info("✓ Qdrant collection ready (%s points).", stats.get('points', 0))
    except Exception as e:
        logging.warning("⚠ Warning: Could not connect to Qdrant: %s", e)
    
    # 3. Start background tasks & bot (Heartbeat priority)
    try:
        from app.services.timezone import refresh_user_settings
        await refresh_user_settings()

        logging.info("Starting scheduler...")
        await start_scheduler()

        logging.info("Starting Telegram bot...")
        await start_telegram_bot()
        logging.info("✓ Telegram bot online.")
        
        # 4. Background Startup Sequence (Non-blocking)
        async def run_delayed_init():
            try:
                logging.info("⚡ Background: Provisioning crews and context...")
                # Provision Dify Crews
                from app.services.dify import crew_registry
                await crew_registry.load()
                await crew_registry.provision()
                
                # Load personal/agent context (LLM compression)
                from app.services.personal_context import refresh_personal_context
                from app.services.agent_context import refresh_agent_context
                await refresh_personal_context()
                await refresh_agent_context()
                
                # Warm up local deep model VRAM
                from app.services.memory import get_embedder
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, get_embedder)
                
                logging.info("✓ Background heartbeat: All systems fully operational.")
            except Exception as _bg_err:
                logging.warning("⚠ Warning: Background init tasks failed: %s", _bg_err)

        asyncio.create_task(run_delayed_init())

    except Exception as e:
        logging.error("CRITICAL: Core startup failed: %s", e)
        
    yield
    
    # --- SHUTDOWN ---
    await stop_telegram_bot()
    await stop_scheduler()


app = FastAPI(
    title="openZero Native Dashboard Backend",
    description="Context-aware orchestration bridge for openZero agents.",
    version="1.0.0",
    lifespan=lifespan,
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.api.dashboard import router as dashboard_router, auth_router
from app.api.health import router as health_router

class SecurityHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

class CacheHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/dashboard-assets") or request.url.path.endswith(".js") or request.url.path.endswith(".css"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.BASE_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(CacheHeaderMiddleware)
app.add_middleware(SecurityHeaderMiddleware)

from app.api.external import router as external_router

app.include_router(external_router, prefix="/api")
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(health_router)

@app.get("/calendar", include_in_schema=False)
async def calendar_redirect():
    return RedirectResponse(url="/dashboard?open=calendar")

@app.get("/boards", include_in_schema=False)
async def boards_redirect():
    return RedirectResponse(url="/api/dashboard/planka-redirect")

@app.get("/projects", include_in_schema=False)
async def projects_redirect():
    return RedirectResponse(url="/api/dashboard/planka-redirect")

@app.get("/dashboard", include_in_schema=False)
async def serve_dashboard():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"detail": "Dashboard not found"}

@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/dashboard")

if os.path.exists("static/dashboard-assets"):
    app.mount("/dashboard-assets", StaticFiles(directory="static/dashboard-assets"), name="dashboard-assets")
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
