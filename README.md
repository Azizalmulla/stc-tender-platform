# Kuwait Alyoum AI Tender Platform - STC Internal

Enterprise-grade AI platform for tracking and analyzing Kuwait government tenders.

## Architecture

- **Backend**: FastAPI (Python 3.11+) with Celery workers
- **Database**: Neon Postgres with pgvector extension
- **Frontend**: Next.js 14 (App Router) with TypeScript
- **AI**: OpenAI GPT-4o-mini + text-embedding-3-large
- **OCR**: Google Cloud Vision API with PyMuPDF fallback
- **Deployment**: Vercel (frontend) + Cloud Run/Fly.io (backend)

## Features

- ✅ Automated daily scraping of Kuwait Alyoum tenders
- ✅ Arabic/English bilingual support
- ✅ AI-powered summarization and Q&A (RAG)
- ✅ Semantic + keyword search with pgvector
- ✅ OCR for PDF tenders (95%+ accuracy)
- ✅ Real-time tracking with deadline alerts

## Quick Start

### 1. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` file:
```env
DATABASE_URL=postgresql://user:pass@host/dbname
OPENAI_API_KEY=sk-...
GOOGLE_CLOUD_VISION_CREDENTIALS=/path/to/credentials.json
REDIS_URL=redis://localhost:6379
```

Run migrations:
```bash
alembic upgrade head
```

Start server:
```bash
uvicorn app.main:app --reload
```

Start Celery worker:
```bash
celery -A app.worker worker --loglevel=info
```

### 2. Frontend Setup

```bash
cd frontend
npm install
```

Create `.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Run dev server:
```bash
npm run dev
```

## Project Structure

```
stc/
├── backend/
│   ├── app/
│   │   ├── api/              # REST endpoints
│   │   ├── scraper/          # Playwright scraper
│   │   ├── parser/           # PDF/HTML parsing + OCR
│   │   ├── ai/               # OpenAI integration
│   │   ├── models/           # SQLAlchemy models
│   │   ├── db/               # Database config
│   │   └── worker.py         # Celery tasks
│   └── requirements.txt
│
└── frontend/
    ├── app/
    │   ├── dashboard/        # Main tender list
    │   ├── chat/             # AI Q&A interface
    │   └── api/              # Next.js API routes
    └── components/           # Reusable components
```

## Target URLs

- **Tenders (المناقصات)**: https://kuwaitalyawm.media.gov.kw/online/AdsCategory/1
- **Auctions (المزايدات)**: https://kuwaitalyawm.media.gov.kw/online/AdsCategory/2
- **Practices (الممارسات)**: https://kuwaitalyawm.media.gov.kw/online/AdsCategory/18

## License

Proprietary - STC Kuwait Internal Use Only
