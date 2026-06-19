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
    
    # OpenAI — legacy embeddings deprecated; also used as a page-extractor backend
    # (vision) for benchmarking via PAGE_EXTRACTOR_PROVIDER=openai.
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_VISION_MODEL: str = "gpt-5.4-mini"  # page-level vision extraction (benchmark)
    
    # Anthropic Claude (for OCR, summarization, and structured extraction)
    ANTHROPIC_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-sonnet-4-6"  # Latest Claude Sonnet 4.6
    
    # Voyage AI (for embeddings - voyage-law-2 optimized for legal documents)
    VOYAGE_API_KEY: Optional[str] = None
    
    # Mistral AI — Mistral OCR 3 (mistral-ocr-2512) for page-level document
    # extraction. Cheaper (~$0.003/page) than Claude Vision and covered by
    # existing Mistral credits. See PAGE_EXTRACTOR_PROVIDER below.
    MISTRAL_API_KEY: Optional[str] = None
    MISTRAL_OCR_MODEL: str = "mistral-ocr-2512"  # Mistral OCR 3 (alias: mistral-ocr-latest)
    
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
    EMBEDDING_DIMENSION: int = 1024  # Voyage AI voyage-law-2 (legal document optimization)
    
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

    # ── Quality gating / admin visibility ───────────────────────────────────
    # Token that unlocks internal/admin views (clean + needs_review + failed,
    # with a ?view= toggle). Falls back to CRON_SECRET when unset. Public /
    # customer-facing reads ALWAYS see `clean` only, regardless of this token.
    ADMIN_TOKEN: Optional[str] = None

    # Trust-gate policy. Defaults relaxed so a tender that is otherwise strong is
    # not forced into needs_review purely because the gazette page omitted the
    # deadline (very common) or because the block↔listing linkage was "weak"
    # (the displayed fields come from the block itself, which is validated).
    # Set true to restore the strict behaviour.
    QUALITY_MISSING_DEADLINE_BLOCKS: bool = False
    QUALITY_WEAK_MATCH_BLOCKS: bool = False

    # ── Phase 0 cost-control flags ──────────────────────────────────────────
    # Legacy Celery daily scrape (OpenAI pipeline). OFF by default.
    ENABLE_CELERY_BEAT: bool = False
    # Legacy OpenAIService scrape/processing path. OFF by default.
    ENABLE_LEGACY_OPENAI_PIPELINE: bool = False
    # Write per-call provider usage rows to the usage_logs table.
    ENABLE_USAGE_LOGGING: bool = True
    # Hard ceiling on how many tenders a single scrape run will OCR/AI-process.
    # Protects against an accidental full-table reprocess blowing up cost.
    MAX_TENDERS_PER_RUN: int = 120

    # ── Phase 2 extraction-quality flag ─────────────────────────────────────
    # Use the page-level multi-tender extractor (ONE Claude Vision call per page,
    # returns an array of tender blocks, matched back to listing rows) instead of
    # the legacy per-listing flow (4 Claude calls per listing, re-OCR'd the whole
    # spread → contamination). ON by default. Set false to fall back to legacy.
    ENABLE_PAGE_EXTRACTOR: bool = True

    # Which backend powers the page-level extractor:
    #   "anthropic" → Claude Vision (default — reads the rendered page holistically)
    #   "openai"    → OpenAI vision (gpt-5.4-mini), image-native page extraction
    #   "mistral"   → Mistral OCR 3 one-call OCR+document_annotation
    #
    # NOTE: mistral-ocr-2512 was tested on Kuwait Al-Yawm flipbook screenshots and
    # FAILED badly — its OCR locks onto page furniture (page-number strip, masthead)
    # and misses the image-embedded Arabic tender body, after which the annotation
    # step HALLUCINATES tenders from the page numbers. It is unsafe as the primary
    # extractor for this content. Kept selectable for clean-PDF inputs / future use.
    # The Mistral→Claude fallback only triggers on ERRORS, not on bad-but-valid
    # output, so it does NOT catch the hallucination case.
    PAGE_EXTRACTOR_PROVIDER: str = "anthropic"
    PAGE_EXTRACTOR_FALLBACK: bool = True  # fall back to Claude if Mistral errors
    
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
