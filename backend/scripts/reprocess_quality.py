#!/usr/bin/env python3
"""
Phase 2 — targeted extraction-quality reprocess (NON-destructive).

What it does, for a small targeted set of EXISTING tender rows:
  1. group the rows by their source page (edition id + page number from the URL)
  2. render each page ONCE with free local Playwright (Browserless only if PW fails)
  3. run ONE page-level multi-tender extraction per page (app.ai.page_extractor)
  4. match each extracted block back to its listing row (deterministic)
  5. validate every field with rules (app.services.extraction_quality)
  6. UPDATE the row in place with clean fields + quality signals

Safety:
  - Never deletes rows, never wipes the DB, never runs a scrape.
  - Only touches the rows you pass in (--ids) or the auto-selected sample.
  - --dry-run prints the before/after without writing.
  - Cost ≈ ONE Claude call per UNIQUE page (not per row), plus free screenshots.

Usage (inside the api container):
  python scripts/reprocess_quality.py --auto            # pick a balanced 8-12 sample
  python scripts/reprocess_quality.py --ids 12,15,18    # specific rows
  python scripts/reprocess_quality.py --ids 12,15 --dry-run
  python scripts/reprocess_quality.py --report-only     # just print the quality report
"""
import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse, parse_qs


def _bootstrap():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _edition_page(url: str):
    """Return (edition_id, page_number) parsed from a stored flip URL, or (None, None)."""
    try:
        q = parse_qs(urlparse(url).query)
        edition = (q.get("id") or [None])[0]
        page = (q.get("no") or [None])[0]
        return edition, int(page) if page is not None else None
    except Exception:
        return None, None


_FISCAL = re.compile(r"^\s*\d{4}\s*/\s*\d{4}(\s*/\s*\d+)?\s*$")


def _auto_select(db, Tender, limit=12):
    """Pick a balanced sample covering the known failure modes."""
    rows = db.query(Tender).order_by(Tender.id.desc()).limit(300).all()
    picked, seen = [], set()

    def take(pred, n):
        c = 0
        for t in rows:
            if c >= n:
                break
            if t.id in seen:
                continue
            if pred(t):
                picked.append(t); seen.add(t.id); c += 1

    # multi-tender: rows sharing the same edition+page
    from collections import defaultdict
    by_page = defaultdict(list)
    for t in rows:
        e, p = _edition_page(t.url or "")
        if e and p:
            by_page[(e, p)].append(t)
    multi = [t for grp in by_page.values() if len(grp) > 1 for t in grp[:2]]
    for t in multi[:2]:
        if t.id not in seen:
            picked.append(t); seen.add(t.id)

    take(lambda t: bool(t.tender_number) and _FISCAL.match(str(t.tender_number)), 2)  # bad numbers
    take(lambda t: t.deadline is None, 1)                                             # missing deadline
    take(lambda t: bool(t.body) and t.body.lstrip().startswith("{"), 1)              # json leak
    tech = re.compile(r"(IT|software|نظام|شبكة|telecom|اتصالات|data|سيبراني|تقني)", re.IGNORECASE)
    take(lambda t: bool(t.body and tech.search(t.body)) or bool(t.title and tech.search(t.title)), 2)
    take(lambda t: bool(t.tender_number) and not _FISCAL.match(str(t.tender_number)) and t.deadline is not None, 2)
    take(lambda t: True, limit)  # top up
    return picked[:limit]


def _snapshot(t):
    return {
        "id": t.id,
        "tender_number": t.tender_number,
        "title": (t.title or "")[:60],
        "deadline": t.deadline.isoformat() if t.deadline else None,
        "sectors": list(t.ai_sectors or []),
        "status": t.extraction_quality_status,
        "body_head": (t.body or "")[:40].replace("\n", " "),
    }


def main() -> int:
    _bootstrap()
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="comma-separated tender ids")
    ap.add_argument("--auto", action="store_true", help="auto-select a balanced sample")
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    from app.db.session import SessionLocal
    from app.models.tender import Tender
    from app.core.config import settings
    from app.services.quality_report import build_quality_report

    db = SessionLocal()
    try:
        if args.report_only:
            ids = [int(x) for x in args.ids.split(",")] if args.ids else None
            print(json.dumps(build_quality_report(db, ids=ids), ensure_ascii=False, indent=2))
            return 0

        # resolve target rows
        if args.ids:
            ids = [int(x) for x in args.ids.split(",") if x.strip()]
            rows = db.query(Tender).filter(Tender.id.in_(ids)).all()
        elif args.auto:
            rows = _auto_select(db, Tender, args.limit)
        else:
            print("Pass --ids, --auto, or --report-only", flush=True)
            return 2

        if not rows:
            print("No rows matched.", flush=True)
            return 2

        target_ids = [t.id for t in rows]
        print(f"🎯 Reprocessing {len(rows)} rows: {target_ids}", flush=True)
        print("── BEFORE quality report (scoped) ──", flush=True)
        print(json.dumps(build_quality_report(db, ids=target_ids), ensure_ascii=False, indent=2), flush=True)

        # group by page
        from collections import defaultdict
        groups = defaultdict(list)
        for t in rows:
            e, p = _edition_page(t.url or "")
            groups[(e, p)].append(t)

        if not settings.KUWAIT_ALYOM_USERNAME or not settings.KUWAIT_ALYOM_PASSWORD:
            print("❌ Scraper credentials not configured.", flush=True)
            return 2

        from app.scraper.kuwaitalyom_scraper import KuwaitAlyomScraper
        from app.ai.page_extractor import extract_page
        from app.services.extraction_pipeline import apply_block_to_fields
        from app.services import extraction_quality as eq

        scraper = KuwaitAlyomScraper(
            username=settings.KUWAIT_ALYOM_USERNAME,
            password=settings.KUWAIT_ALYOM_PASSWORD,
        )
        if not scraper.login():
            print("❌ Login failed.", flush=True)
            return 1

        changes = []
        page_calls = 0
        try:
            for (edition, page), grp in groups.items():
                if not edition or not page:
                    for t in grp:
                        changes.append((t, _snapshot(t), {"error": "unparseable_url"}))
                    continue

                print(f"\n📄 Page edition={edition} no={page} ({len(grp)} listing rows)", flush=True)
                # Render the page ONCE (free local Playwright) → bytes for the page extractor.
                img = scraper._screenshot_page_with_playwright(edition, page)
                if not img:
                    print("  ⚠️  Playwright failed; trying Browserless fallback", flush=True)
                    img = scraper._screenshot_page_with_browserless(edition, page)
                if not img:
                    for t in grp:
                        changes.append((t, _snapshot(t), {"error": "screenshot_failed"}))
                    continue

                page_calls += 1
                result = extract_page(img, "png", source_page=f"{edition}/{page}")
                blocks = result.get("tenders", [])
                page_multi = result.get("page_contains_multiple_tenders", len(blocks) > 1)
                page_text = "\n".join(str(b.get("body_text") or "") for b in blocks)
                print(f"  🧩 extracted {len(blocks)} block(s), multi={page_multi}", flush=True)

                for t in grp:
                    before = _snapshot(t)
                    match = eq.match_block_to_listing(blocks, t.tender_number, t.title)
                    block = match["block"]
                    if not block:
                        t.extraction_quality_status = "needs_review"
                        t.needs_review = True
                        t.extraction_warnings = list(
                            dict.fromkeys((t.extraction_warnings or []) + ["listing_match_weak"])
                        )
                        changes.append((t, before, {"matched": False, **_snapshot(t)}))
                        continue

                    fields = apply_block_to_fields(
                        block,
                        listing_number=t.tender_number,
                        listing_title=t.title,
                        published_at=t.published_at,
                        page_text=page_text,
                        page_multi=page_multi,
                        match_strength=match["strength"],
                        match_warnings=match["warnings"],
                    )
                    fields.pop("_match_strength", None)

                    # preserve old synthetic title as source_label, promote real title
                    if not t.source_label:
                        t.source_label = t.title
                    real_title = fields.get("title_ar") or fields.get("title_en")
                    if real_title:
                        t.title = real_title

                    for k, v in fields.items():
                        setattr(t, k, v)

                    changes.append((t, before, _snapshot(t)))
        finally:
            try:
                scraper.close_playwright()
            except Exception:
                pass

        if args.dry_run:
            db.rollback()
            print("\n🧪 DRY RUN — no changes written.", flush=True)
        else:
            db.commit()
            print("\n💾 Committed updates.", flush=True)

        # before/after table
        print("\n── PER-ROW BEFORE → AFTER ──", flush=True)
        for t, before, after in changes:
            print(json.dumps({"before": before, "after": after}, ensure_ascii=False), flush=True)

        print(f"\n🧮 Claude page_extract calls this run: {page_calls}", flush=True)
        print("\n── AFTER quality report (scoped) ──", flush=True)
        if not args.dry_run:
            print(json.dumps(build_quality_report(db, ids=target_ids), ensure_ascii=False, indent=2), flush=True)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
