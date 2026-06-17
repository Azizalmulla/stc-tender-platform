# VPS Deployment — Kuwait Alyoum / STC Tender Platform

VPS-only deployment. **No Render / Fly / Railway.** Telegram/OpenClaw are added
later, after the backend is stable.

- **Target VPS:** `72.61.106.61`
- **Deploy dir:** `/opt/tender-platform`
- **Public entrypoint:** Caddy (ports 80/443) → `tender-api:8000`
- **Database (Phase 1 default):** existing managed Postgres (Neon) via `DATABASE_URL`.
  Self-hosted Postgres+pgvector is available behind the `localdb` profile.

---

## Architecture

```
            ┌─────────── VPS 72.61.106.61 ───────────┐
 Internet → │ Caddy :80/:443 ──→ tender-api:8000      │
            │                      │  └─ redis (cache) │
            │                      └─ DATABASE_URL ────┼─→ Neon (or localdb profile)
            │ systemd timer ──→ scrape (one-shot)      │
            └─────────────────────────────────────────┘
```

Services (`docker-compose.yml`):
- `tender-api` — FastAPI app (Claude OCR/extraction, Voyage embeddings, Playwright screenshots).
- `redis` — chat response cache (optional; app runs without it).
- `caddy` — reverse proxy / TLS.
- `postgres` *(profile `localdb`)* — pgvector Postgres for self-hosting later.
- `scrape` *(profile `scrape`)* — one-shot weekly scrape, run by the systemd timer.

---

## First-time setup

```bash
# 1. Clone into the deploy dir
git clone https://github.com/Azizalmulla/stc-tender-platform.git /opt/tender-platform
cd /opt/tender-platform
git checkout phase-1-vps-only-architecture

# 2. Create the real env file (NEVER commit it)
cp .env.example .env
nano .env        # fill ANTHROPIC_API_KEY, VOYAGE_API_KEY, DATABASE_URL,
                 # CRON_SECRET, KUWAIT_ALYOM_USERNAME/PASSWORD, (BROWSERLESS_API_KEY optional)

# 3. Free ports 80/443 for the Caddy container (host system-caddy owns them)
systemctl disable --now caddy   # the placeholder host Caddy from base prep

# 4. Deploy
./ops/deploy.sh
```

`deploy.sh` builds images, takes a DB backup, applies idempotent migrations,
starts the stack, and health-checks it.

---

## Weekly scrape (scheduled job, NOT FastAPI BackgroundTasks)

The long-term scrape runs as a dedicated **one-shot** process via systemd:

```bash
cp ops/systemd/tender-scrape.* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tender-scrape.timer
systemctl list-timers tender-scrape.timer     # confirm next run (Sun 06:00 Asia/Kuwait)
```

It runs `docker compose --profile scrape run --rm scrape`, which executes
`backend/scripts/run_weekly_scrape.py` → `run_scrape_task(days_back=7)`:
**safe incremental only, never destructive, never a full wipe**, and bounded by
`MAX_TENDERS_PER_RUN`.

Manual run / test:
```bash
docker compose --profile scrape run --rm scrape
```

---

## Database options

### Default (Phase 1): keep Neon
Set `DATABASE_URL` in `.env` to the managed connection string. Nothing else to do.
This is the recommended Phase-1 path — no data migration, no schema bootstrap risk.

### Later: self-host Postgres + pgvector
```bash
# set in .env:
#   DATABASE_URL=postgresql://tender:STRONG_PW@postgres:5432/tender
#   POSTGRES_USER=tender  POSTGRES_PASSWORD=STRONG_PW  POSTGRES_DB=tender
docker compose --profile localdb up -d postgres   # pgvector extension auto-created

# Bootstrap schema (the app has no create_all; alembic chain is broken):
docker compose run --rm tender-api python -c "from app.db.session import engine, Base; import app.models.tender; Base.metadata.create_all(engine)"
./ops/migrate.sh                                   # apply idempotent column/table migrations

# Migrate existing data from Neon (optional):
docker compose run --rm -T tender-api sh -c 'pg_dump "$OLD_NEON_URL"' | \
  docker compose run --rm -T tender-api sh -c 'psql "$DATABASE_URL"'
```

---

## Operations

| Action | Command |
|---|---|
| Deploy latest | `./ops/deploy.sh` |
| Deploy a ref | `./ops/deploy.sh <git-ref>` |
| Roll back | `./ops/rollback.sh` |
| Health check | `./ops/healthcheck.sh` |
| Backup DB | `./ops/backup.sh` |
| Migrate | `./ops/migrate.sh` |
| Logs | `docker compose logs --tail=100 -f tender-api` |
| Cost report | `curl -H "Authorization: Bearer $CRON_SECRET" http://localhost/api/cron/usage-report` |

---

## Going live with a domain

1. Point DNS A record at `72.61.106.61`.
2. Edit `caddy/Caddyfile.domain.template` (set `api.example.com`), copy to `caddy/Caddyfile`.
3. `docker compose up -d caddy` — Caddy auto-issues TLS.

---

## Cost-control invariants (Phase 0, carried forward)

- Destructive scrape requires `clear_first=true AND confirm_wipe=true`; the weekly job never sets them.
- `extract-tender-values` is idempotent (skips `value_extracted_at IS NOT NULL`).
- Browserless is **fallback-only**; local Playwright/Chromium is the free primary path.
- Legacy OpenAI + Celery beat are **OFF** unless explicitly enabled in `.env`.
- Every paid call is logged to `usage_logs` → `GET /api/cron/usage-report`.
