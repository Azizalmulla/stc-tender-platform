from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api import tenders, search, chat, cron, notifications, meetings


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

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
