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
    from collections import defaultdict

    # ── report-only ──────────────────────────────────────────────────────────
    if args.report_only:
        db = SessionLocal()
        try:
            ids = [int(x) for x in args.ids.split(",")] if args.ids else None
            print(json.dumps(build_quality_report(db, ids=ids), ensure_ascii=False, indent=2))
            return 0
        finally:
            db.close()

    if not settings.KUWAIT_ALYOM_USERNAME or not settings.KUWAIT_ALYOM_PASSWORD:
        print("❌ Scraper credentials not configured.", flush=True)
        return 2

    # ── PHASE 1: read targets, snapshot, then CLOSE the DB ───────────────────
    # We must NOT hold a Neon connection open during the slow render/AI phase —
    # the serverless pooler drops idle SSL connections (commit would then fail).
    db = SessionLocal()
    try:
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
        before_snaps = {t.id: _snapshot(t) for t in rows}
        # lightweight, detached copies of just what the slow phase needs
        meta = [{
            "id": t.id, "url": t.url, "tender_number": t.tender_number,
            "title": t.title, "published_at": t.published_at,
        } for t in rows]
        print(f"🎯 Reprocessing {len(meta)} rows: {target_ids}", flush=True)
        print("── BEFORE quality report (scoped) ──", flush=True)
        print(json.dumps(build_quality_report(db, ids=target_ids), ensure_ascii=False, indent=2), flush=True)
    finally:
        db.close()

    groups = defaultdict(list)
    for m in meta:
        e, p = _edition_page(m["url"] or "")
        groups[(e, p)].append(m)

    # ── PHASE 2: render + extract (NO DB connection held) ────────────────────
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

    updates: dict = {}   # id -> {fields..., _real_title, _old_title} | {"_no_match": True}
    page_calls = 0
    try:
        for (edition, page), grp in groups.items():
            if not edition or not page:
                for m in grp:
                    updates[m["id"]] = {"_error": "unparseable_url"}
                continue

            print(f"\n📄 Page edition={edition} no={page} ({len(grp)} listing rows)", flush=True)
            img = scraper._screenshot_page_with_playwright(edition, page)
            if not img:
                print("  ⚠️  Playwright failed; trying Browserless fallback", flush=True)
                img = scraper._screenshot_page_with_browserless(edition, page)
            if not img:
                for m in grp:
                    updates[m["id"]] = {"_error": "screenshot_failed"}
                continue

            page_calls += 1
            result = extract_page(img, "png", source_page=f"{edition}/{page}")
            blocks = result.get("tenders", [])
            page_multi = result.get("page_contains_multiple_tenders", len(blocks) > 1)
            page_text = "\n".join(str(b.get("body_text") or "") for b in blocks)
            print(f"  🧩 extracted {len(blocks)} block(s), multi={page_multi}", flush=True)

            listings = [{"id": m["id"], "tender_number": m["tender_number"], "title": m["title"]} for m in grp]
            assigned = eq.assign_blocks_to_listings(blocks, listings)
            for m in grp:
                a = assigned.get(m["id"], {"block": None, "strength": "none", "warnings": ["listing_match_weak"]})
                block = a["block"]
                if not block:
                    updates[m["id"]] = {"_no_match": True}
                    continue
                fields = apply_block_to_fields(
                    block,
                    listing_number=m["tender_number"],
                    listing_title=m["title"],
                    published_at=m["published_at"],
                    page_text=block.get("body_text"),
                    page_multi=page_multi,
                    match_strength=a["strength"],
                    match_warnings=a["warnings"],
                )
                fields.pop("_match_strength", None)
                fields["_strength"] = a["strength"]
                fields["_real_title"] = fields.get("title_ar") or fields.get("title_en")
                fields["_old_title"] = m["title"]
                updates[m["id"]] = fields
    finally:
        try:
            scraper.close_playwright()
        except Exception:
            pass

    # Run-level de-dup: a weak (title-only) match must NOT claim a tender number
    # already won by a strong (number-verified) match elsewhere — the two-page
    # spread overlap otherwise lets the same tender be claimed twice.
    strong_by_num = {}
    for tid, f in updates.items():
        if f.get("_strength") == "strong" and f.get("tender_number"):
            strong_by_num[eq.normalize_number(f["tender_number"])] = tid
    for tid, f in list(updates.items()):
        if f.get("_strength") != "strong" and f.get("tender_number"):
            k = eq.normalize_number(f["tender_number"])
            if k in strong_by_num and strong_by_num[k] != tid:
                updates[tid] = {"_no_match": True, "_dup_of": strong_by_num[k]}

    print(f"\n🧮 Claude page_extract calls this run: {page_calls}", flush=True)

    if args.dry_run:
        print("\n🧪 DRY RUN — no changes written.", flush=True)
        print("\n── PER-ROW BEFORE → (proposed) ──", flush=True)
        for tid, fields in updates.items():
            print(json.dumps({"id": tid, "before": before_snaps.get(tid),
                              "proposed_title": fields.get("_real_title"),
                              "proposed_number": fields.get("tender_number"),
                              "status": fields.get("extraction_quality_status"),
                              "flags": {k: v for k, v in fields.items() if k.startswith("_")}},
                             ensure_ascii=False), flush=True)
        return 0

    # ── PHASE 3: write on a FRESH session, commit per row ────────────────────
    from datetime import datetime as _dt, timezone as _tz
    after_snaps = {}
    db = SessionLocal()
    try:
        for tid, fields in updates.items():
            t = db.get(Tender, tid)
            if t is None:
                continue
            if fields.get("_error") or fields.get("_no_match"):
                t.extraction_quality_status = "needs_review"
                t.needs_review = True
                if fields.get("_dup_of"):
                    reason = "duplicate_block_claim"
                elif fields.get("_no_match"):
                    reason = "listing_match_weak"
                else:
                    reason = fields.get("_error")
                t.extraction_warnings = list(dict.fromkeys((t.extraction_warnings or []) + [reason]))
                t.ai_processed_at = _dt.now(_tz.utc)
                db.commit()
                after_snaps[tid] = _snapshot(t)
                continue

            real_title = fields.pop("_real_title", None)
            old_title = fields.pop("_old_title", None)
            if not t.source_label:
                t.source_label = old_title or t.title
            if real_title:
                t.title = real_title
            for k, v in fields.items():
                if k.startswith("_"):
                    continue
                setattr(t, k, v)
            try:
                db.commit()
                after_snaps[tid] = _snapshot(t)
            except Exception as e:
                db.rollback()
                print(f"  ❌ write failed for #{tid}: {e}", flush=True)

        print("\n💾 Committed updates (per-row).", flush=True)
        print("\n── PER-ROW BEFORE → AFTER ──", flush=True)
        for tid in updates:
            print(json.dumps({"id": tid, "before": before_snaps.get(tid),
                              "after": after_snaps.get(tid)}, ensure_ascii=False), flush=True)

        print("\n── AFTER quality report (scoped) ──", flush=True)
        print(json.dumps(build_quality_report(db, ids=list(updates.keys())),
                         ensure_ascii=False, indent=2), flush=True)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
