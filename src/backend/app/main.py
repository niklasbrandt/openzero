from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.models.db import engine, Base, AsyncSessionLocal, Person
from sqlalchemy import select
from app.services.memory import ensure_collection
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.api.telegram_bot import start_telegram_bot, stop_telegram_bot
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

            # 3. Add theme color columns to 'people' if not exists
            #    (added after initial release; UserCard writes these, personality endpoint reads them)
            _people_color_cols = {
                "color_primary":   "ALTER TABLE people ADD COLUMN color_primary VARCHAR",
                "color_secondary": "ALTER TABLE people ADD COLUMN color_secondary VARCHAR",
                "color_tertiary":  "ALTER TABLE people ADD COLUMN color_tertiary VARCHAR",
            }
            for col, alter_sql in _people_color_cols.items():
                res = await conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='people' AND column_name=:col"
                ), {"col": col})
                if not res.fetchone():
                    await conn.execute(text(alter_sql))

            # 4. Add 'model' column to 'global_messages' if not exists
            #    (records which LLM tier/model produced each Z response)
            res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='global_messages' AND column_name='model'"))
            if not res.fetchone():
                await conn.execute(text("ALTER TABLE global_messages ADD COLUMN model VARCHAR"))

            # 5. Add 'model' column to 'briefings' if not exists
            #    (records which LLM tier/model generated each briefing)
            res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='briefings' AND column_name='model'"))
            if not res.fetchone():
                await conn.execute(text("ALTER TABLE briefings ADD COLUMN model VARCHAR"))

            # 6. Add quiet hours columns to 'people' if not exists
            _people_quiet_cols = {
                "quiet_hours_enabled": "ALTER TABLE people ADD COLUMN quiet_hours_enabled BOOLEAN DEFAULT TRUE",
                "quiet_hours_start": "ALTER TABLE people ADD COLUMN quiet_hours_start VARCHAR DEFAULT '00:00'",
                "quiet_hours_end": "ALTER TABLE people ADD COLUMN quiet_hours_end VARCHAR DEFAULT '06:00'",
            }
            for col, alter_sql in _people_quiet_cols.items():
                res = await conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='people' AND column_name=:col"
                ), {"col": col})
                if not res.fetchone():
                    await conn.execute(text(alter_sql))

            # 7. Add work time columns to 'people' if not exists
            _people_work_cols = {
                "work_start": "ALTER TABLE people ADD COLUMN work_start VARCHAR DEFAULT '09:00'",
                "work_end":   "ALTER TABLE people ADD COLUMN work_end VARCHAR DEFAULT '17:00'",
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
        raise RuntimeError(
            "QDRANT_API_KEY must be set in .env when running in Docker."
        )
    try:
        await ensure_collection()
        from app.services.memory import get_memory_stats
        stats = await get_memory_stats()
        if stats['status'] == 'error':
            raise Exception("Stats check failed")
        logging.info("✓ Qdrant collection ready (%s points).", stats['points'])
    except Exception as e:
        logging.warning("⚠ Warning: Could not connect to Qdrant: %s", e)
    
    # 3. Start background tasks & bot
    try:
        # Load user timezone from DB BEFORE starting the scheduler so
        # get_current_timezone() returns the correct value (not the
        # hardcoded "Europe/Berlin" fallback) when CronTriggers are built.
        from app.services.timezone import refresh_user_settings
        await refresh_user_settings()

        logging.info("Starting scheduler...")
        await start_scheduler()

        # Load personal context before the bot starts polling so Z has full
        # context for any messages that arrive immediately after a restart.
        try:
            from app.services.personal_context import refresh_personal_context
            await refresh_personal_context()
            logging.info("✓ Personal context pre-loaded before bot start.")
        except Exception as _pc_err:
            logging.warning("⚠ Warning: Personal context pre-load failed: %s", _pc_err)

        try:
            from app.services.agent_context import refresh_agent_context
            await refresh_agent_context()
            logging.info("✓ Agent context pre-loaded before bot start.")
        except Exception as _ac_err:
            logging.warning("⚠ Warning: Agent context pre-load failed: %s", _ac_err)

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
                await refresh_user_settings()
                logging.info("\u2713 User settings loaded from identity record.")
                # 3c. Load personal context folder into system prompt
                await refresh_personal_context()
                logging.info("\u2713 Personal context loaded from /personal folder.")
                # 3d. Load agent context folder into system prompt
                await refresh_agent_context()
                logging.info("\u2713 Agent context loaded from /agent folder.")
                
                # 3e. Load and Provision Dify Crews
                try:
                    from app.services.dify import crew_registry
                    await crew_registry.load()
                    await crew_registry.provision()
                    logging.info("\u2713 Dify Crews initialized (%d active).", len(crew_registry.list_active()))
                except Exception as _crew_err:
                    logging.warning("⚠ Warning: Dify Crew Provisioning failed: %s", _crew_err)
                    
                # 4. Initial Operator Board Sync
                from app.services.operator_board import operator_service
                sync_res = await operator_service.sync_operator_tasks()
                logging.info("\u2713 %s", sync_res)
            except Exception as e:
                logging.warning("⚠ Warning: Background startup tasks failed: %s", e)

        asyncio.create_task(run_background_startup())

    except Exception as e:
        logging.warning("⚠ Warning: Core startup failed: %s", e)
        
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


from fastapi import Request as _Request
from fastapi.responses import JSONResponse as _JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(_request: _Request, exc: Exception):
    import logging as _logging
    _logging.getLogger(__name__).error("Unhandled exception: %s", exc, exc_info=True)
    return _JSONResponse(status_code=500, content={"detail": "Internal server error"})


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
        elif path in ("/dashboard", "/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


class SecurityHeaderMiddleware(BaseHTTPMiddleware):
    """Inject OWASP-recommended security headers on every response (A5/A8).

    - Content-Security-Policy: restricts resource origins; 'unsafe-inline'
      is required for Vite-built inline scripts/styles (A8)
    - X-Content-Type-Options: prevents MIME-sniffing attacks
    - X-Frame-Options: blocks clickjacking (SAMEORIGIN allows Planka iframes
      served from the same origin; change to DENY if iframes are removed)
    - Referrer-Policy: limits referrer leakage to same-origin upgrades
    - Permissions-Policy: opt out of sensitive browser capabilities
    - X-XSS-Protection: legacy header; belt-and-suspenders for older browsers
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "font-src 'self' data:; "
            "frame-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response


# Add CORS for the dashboard — restrict to the configured base URL (not wildcard)
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

# Serve the Dashboard
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
    # Also mount the rest of static without html=True fallback
    app.mount("/static", StaticFiles(directory="static"), name="static")
