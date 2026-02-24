from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.config import settings
from app.api import tenders, search, chat, cron, notifications, meetings, export, analytics


scheduler = BackgroundScheduler(timezone="UTC")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start scheduler on app startup
    from app.api.cron import run_scrape_task
    scheduler.add_job(
        run_scrape_task,
        CronTrigger(day_of_week="sun", hour=6, minute=0),  # Every Sunday 6am UTC = 9am Kuwait
        id="weekly_scrape",
        replace_existing=True,
    )
    scheduler.start()
    print("✅ Weekly scrape scheduler started (every Sunday 9am Kuwait time)")
    yield
    # Shutdown scheduler on app shutdown
    scheduler.shutdown(wait=False)
    print("🛑 Scheduler stopped")


class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    """Force HTTPS scheme from proxy headers - fixes Render HTTPS redirect issue"""
    async def dispatch(self, request: Request, call_next):
        # Trust X-Forwarded-Proto from Render proxy
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        if forwarded_proto == "https":
            # Override the scheme to https
            request.scope["scheme"] = "https"
        response = await call_next(request)
        return response


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# Add proxy headers middleware FIRST (before CORS)
app.add_middleware(ProxyHeadersMiddleware)

# CORS - Allow frontend from Vercel and localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for now (can restrict later)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(tenders.router, prefix="/api/tenders", tags=["tenders"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(cron.router, prefix="/api", tags=["cron"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(meetings.router, prefix="/api/meetings", tags=["meetings"])
app.include_router(export.router, prefix="/api", tags=["export"])
app.include_router(analytics.router, prefix="/api", tags=["analytics"])


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "operational"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
