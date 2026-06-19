#!/usr/bin/env python3
"""
Re-grade existing tenders under the current trust-gate rules WITHOUT calling any
model (free, deterministic). Recomputes extraction_quality_status / needs_review /
extraction_warnings from already-stored fields, then runs the duplicate-number
pass. Use after changing gate policy (e.g. relaxing missing-deadline / weak-match)
so previously-stored rows reflect the new rules.

    docker compose run --rm tender-api python scripts/regrade_quality.py
"""
import os
import sys


def _infer_strength(warnings):
    w = set(warnings or [])
    if "listing_match_none" in w:
        return "none"
    if "listing_match_weak" in w:
        return "weak"
    return "strong"


def main() -> int:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from app.db.session import SessionLocal
    from app.models.tender import Tender
    from app.services import extraction_quality as eq

    db = SessionLocal()
    try:
        rows = db.query(Tender).order_by(Tender.id).all()
        before = {}
        after = {}
        for t in rows:
            before[t.extraction_quality_status or "none"] = before.get(t.extraction_quality_status or "none", 0) + 1

            has_body = bool((t.body or "").strip())
            strength = _infer_strength(t.extraction_warnings)
            # Drop previously status-derived warnings so the recompute is clean;
            # keep intrinsic ones (block warnings, json_leak_fixed, multi_tender_page).
            _derived = {
                "missing_deadline", "ambiguous_tender_number", "weak_match_low_confidence",
                "low_overall_confidence", "duplicate_tender_number", "no_body_extracted",
                "listing_match_none",
            }
            base_warnings = [w for w in (t.extraction_warnings or []) if w not in _derived]

            status = eq.compute_quality_status(
                has_body=has_body,
                tender_number_conf=t.tender_number_confidence,
                deadline_missing_reason=t.deadline_missing_reason,
                announcement_type=t.announcement_type,
                overall_confidence=t.ai_confidence,
                warnings=base_warnings,
                match_strength=strength,
            )
            t.extraction_quality_status = status["status"]
            t.needs_review = status["needs_review"]
            t.extraction_warnings = status["warnings"]
        db.commit()

        dupes = eq.flag_duplicate_numbers(db)

        for t in db.query(Tender).all():
            after[t.extraction_quality_status or "none"] = after.get(t.extraction_quality_status or "none", 0) + 1

        print(f"✅ re-graded {len(rows)} rows; duplicates_flagged={dupes}")
        print(f"   before: {before}")
        print(f"   after : {after}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
