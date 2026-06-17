#!/usr/bin/env python3
"""
Weekly scrape runner (VPS, Phase 1).

This is the LONG-TERM scheduled scrape entrypoint. It deliberately does NOT go
through FastAPI BackgroundTasks or the HTTP layer — it calls the incremental
scrape function directly in a dedicated one-shot process (systemd timer or
`docker compose --profile scrape run --rm scrape`).

Safety guarantees:
- Runs the SAFE INCREMENTAL scrape only (run_scrape_task).
- NEVER wipes the database and NEVER reprocesses existing tenders.
- Respects the per-run cost cap (settings.MAX_TENDERS_PER_RUN).

Exit codes:
    0 = success
    2 = missing required configuration (e.g. scraper credentials)
    1 = scrape raised an unexpected error
"""
import os
import sys
import traceback


def main() -> int:
    # Run from the app root so `import app.*` resolves (Docker WORKDIR=/app).
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from app.core.config import settings

    if not settings.KUWAIT_ALYOM_USERNAME or not settings.KUWAIT_ALYOM_PASSWORD:
        print("❌ KUWAIT_ALYOM_USERNAME / KUWAIT_ALYOM_PASSWORD not configured — aborting.", flush=True)
        return 2

    # days_back is configurable but defaults to the safe weekly window.
    try:
        days_back = int(os.getenv("SCRAPE_DAYS_BACK", "7"))
    except ValueError:
        days_back = 7

    from app.api.cron import run_scrape_task

    print(f"🗓️  Weekly scrape starting (days_back={days_back}, "
          f"max_per_run={getattr(settings, 'MAX_TENDERS_PER_RUN', 120)}, destructive=NEVER)", flush=True)

    try:
        result = run_scrape_task(days_back=days_back)
        print(f"✅ Weekly scrape finished: {result}", flush=True)
        print("ℹ️  Verify cost with: GET /api/cron/usage-report (Authorization: Bearer $CRON_SECRET)", flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001 — top-level runner: surface and exit non-zero
        print(f"❌ Weekly scrape failed: {exc}", flush=True)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
