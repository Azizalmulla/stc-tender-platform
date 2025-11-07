# Kuwait Alyoum Tender Tracker - Setup Guide

## Prerequisites

- **Python 3.11+**
- **Node.js 18+**  
- **PostgreSQL** (Neon recommended)
- **Redis**
- **OpenAI API Key**
- **Google Cloud Vision API credentials**

---

## 🚀 Quick Start

### 1. Database Setup (Neon Postgres)

1. Create a Neon account at https://neon.tech
2. Create a new project
3. Enable pgvector extension (automatically enabled on Neon)
4. Copy the connection string

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Create .env file
cp .env.example .env
```

**Edit `.env`:**
```env
DATABASE_URL=postgresql://user:pass@ep-xxx-xxx.us-east-2.aws.neon.tech/stc_tenders?sslmode=require
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=sk-...
GOOGLE_CLOUD_VISION_CREDENTIALS=/path/to/credentials.json
```

```bash
# Run migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload --port 8000

# In another terminal, start Celery worker
celery -A app.worker worker --loglevel=info

# Optional: Start Celery Beat for scheduled scraping
celery -A app.worker beat --loglevel=info
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create .env.local
cp .env.local.example .env.local
```

**Edit `.env.local`:**
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

```bash
# Start development server
npm run dev
```

**Frontend will be available at http://localhost:3000**

---

## 🔧 Google Cloud Vision Setup

1. Go to https://console.cloud.google.com
2. Create a new project
3. Enable Cloud Vision API
4. Create service account credentials
5. Download JSON key file
6. Set path in backend `.env`

---

## 📊 Running Your First Scrape

### Manual Scrape (via Python)

```bash
cd backend
source venv/bin/activate

# Run scraper directly
python -c "from app.scraper.kuwait_alyoum import scrape_kuwait_alyoum; import asyncio; asyncio.run(scrape_kuwait_alyoum())"
```

### Via Celery Task

```bash
# Trigger scrape job
python -c "from app.worker import scrape_and_process_tenders; scrape_and_process_tenders.delay()"
```

---

## 🌐 Deployment

### Backend (Cloud Run / Fly.io)

#### Cloud Run
```bash
cd backend

# Build and deploy
gcloud run deploy stc-tender-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

#### Fly.io
```bash
cd backend

# Initialize
fly launch

# Deploy
fly deploy
```

### Frontend (Vercel)

```bash
cd frontend

# Install Vercel CLI
npm i -g vercel

# Deploy
vercel

# Set environment variables
vercel env add NEXT_PUBLIC_API_URL
```

**Or connect GitHub repo to Vercel dashboard for automatic deployments.**

---

## 🔐 Environment Variables Summary

### Backend
| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | Neon Postgres connection string | ✅ |
| `REDIS_URL` | Redis connection string | ✅ |
| `OPENAI_API_KEY` | OpenAI API key | ✅ |
| `GOOGLE_CLOUD_VISION_CREDENTIALS` | Path to GCP JSON key | ✅ |
| `DEBUG` | Enable debug mode | ❌ |
| `CORS_ORIGINS` | Allowed CORS origins | ❌ |

### Frontend
| Variable | Description | Required |
|----------|-------------|----------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | ✅ |

---

## 📝 API Endpoints

### Tenders
- `GET /api/tenders/` - List tenders with filters
- `GET /api/tenders/{id}` - Get tender details
- `GET /api/tenders/stats/summary` - Get statistics

### Search
- `GET /api/search/keyword?q=...` - Keyword search
- `GET /api/search/semantic?q=...` - Semantic search
- `GET /api/search/hybrid?q=...` - Hybrid search

### Chat
- `POST /api/chat/ask` - Ask AI question about tenders

**Full API docs:** http://localhost:8000/api/docs

---

## 🛠️ Troubleshooting

### Playwright Installation Issues
```bash
playwright install-deps
playwright install chromium
```

### Redis Connection Failed
```bash
# Install Redis (macOS)
brew install redis
brew services start redis

# Or use Docker
docker run -d -p 6379:6379 redis:alpine
```

### pgvector Extension Not Found
```sql
-- Run in your Postgres database
CREATE EXTENSION IF NOT EXISTS vector;
```

### Python Package Conflicts
```bash
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

---

## 📈 Monitoring

### Check Celery Tasks
```bash
# View active tasks
celery -A app.worker inspect active

# View registered tasks
celery -A app.worker inspect registered
```

### Database Stats
```bash
# Connect to database
psql $DATABASE_URL

# Check tender count
SELECT COUNT(*) FROM tenders;

# Check embeddings
SELECT COUNT(*) FROM tender_embeddings;
```

---

## 🎯 Next Steps

1. **Test the scraper** with a small batch
2. **Verify AI summarization** quality
3. **Check search relevance** (semantic vs keyword)
4. **Monitor API costs** (OpenAI + Google Cloud Vision)
5. **Set up monitoring** (Sentry recommended)
6. **Schedule daily scraping** (Celery Beat)

---

## 📞 Support

For issues or questions, refer to:
- FastAPI docs: https://fastapi.tiangolo.com
- Next.js docs: https://nextjs.org/docs
- OpenAI API: https://platform.openai.com/docs
- pgvector: https://github.com/pgvector/pgvector

---

**Built for STC Kuwait - Internal Use Only**
