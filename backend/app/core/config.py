from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Kuwait Alyoum Tender Tracker"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    
    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    
    # Anthropic Claude
    ANTHROPIC_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-sonnet-4.5-20250929"  # Latest Claude Sonnet 4.5
    
    # Google Cloud Document AI
    GOOGLE_CLOUD_DOCUMENTAI_CREDENTIALS: Optional[str] = None
    DOCUMENTAI_PROCESSOR_NAME: Optional[str] = None  # Format: projects/{project}/locations/{location}/processors/{processor}
    
    # Scraper
    SCRAPER_USER_AGENT: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    SCRAPER_TIMEOUT: int = 30000  # milliseconds
    SCRAPER_HEADLESS: bool = True
    
    # Kuwait Alyoum URLs
    BASE_URL: str = "https://kuwaitalyawm.media.gov.kw"
    TENDER_CATEGORIES: dict = {
        "tenders": 1,      # المناقصات
        "auctions": 2,     # المزايدات
        "practices": 18    # الممارسات
    }
    
    # Timezone
    TIMEZONE: str = "Asia/Kuwait"
    
    # AI Settings
    MAX_TOKENS_SUMMARY: int = 200
    MAX_TOKENS_QA: int = 500
    TEMPERATURE: float = 0.3
    
    # Embeddings
    EMBEDDING_DIMENSION: int = 1536  # text-embedding-3-small (Neon pgvector limit: 2000)
    
    # Search
    SIMILARITY_THRESHOLD: float = 0.7
    MAX_SEARCH_RESULTS: int = 50
    
    # CORS
    CORS_ORIGINS: list = [
        "http://localhost:3000",
        "https://frontend-ogdswxda6-azizalmulla16-gmailcoms-projects.vercel.app",
        "https://frontend-eight-xi-96.vercel.app",
        "https://*.vercel.app"
    ]
    
    # Cron Jobs
    CRON_SECRET: Optional[str] = None  # Secret token to protect cron endpoints
    
    # Google Cloud Document AI (for PDF OCR)
    GOOGLE_CLOUD_PROJECT: Optional[str] = None
    GOOGLE_DOC_AI_PROCESSOR_ID: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None  # Path to service account JSON
    
    # Kuwait Alyom (Official Gazette) Credentials
    KUWAIT_ALYOM_USERNAME: Optional[str] = None
    KUWAIT_ALYOM_PASSWORD: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
