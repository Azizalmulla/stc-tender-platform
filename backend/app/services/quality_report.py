"""
Phase 2 — data-quality report.

Pure read-only aggregation over the tenders table. Used by the
`/api/cron/quality-report` endpoint and the reprocess script so the numbers
always match. No external API calls.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.tender import Tender


def _count(q) -> int:
    return q.count()


def build_quality_report(db: Session, sample_size: int = 10, ids: Optional[List[int]] = None) -> Dict[str, Any]:
    base = db.query(Tender)
    if ids:
        base = base.filter(Tender.id.in_(ids))

    total = base.count()

    # status breakdown
    status_rows = (
        base.with_entities(Tender.extraction_quality_status, func.count())
        .group_by(Tender.extraction_quality_status)
        .all()
    )
    status_breakdown = {(s or "unprocessed"): c for s, c in status_rows}

    missing_titles = base.filter(
        Tender.title_ar.is_(None), Tender.title_en.is_(None)
    ).count()

    missing_deadlines = base.filter(Tender.deadline.is_(None)).count()
    missing_deadline_no_reason = base.filter(
        Tender.deadline.is_(None), Tender.deadline_missing_reason.is_(None)
    ).count()

    ambiguous_numbers = base.filter(
        or_(
            Tender.extraction_warnings.any("ambiguous_tender_number"),
            Tender.tender_number_confidence < 0.65,
        )
    ).count()

    multi_tender_rows = base.filter(
        Tender.extraction_warnings.any("multi_tender_page")
    ).count()

    json_leaks_fixed = base.filter(
        Tender.extraction_warnings.any("json_leak_fixed")
    ).count()

    # remaining (unfixed) JSON leaks — should be 0
    json_leaks_remaining = base.filter(
        or_(
            Tender.body.ilike("{%"),
            Tender.body.ilike("```json%"),
            Tender.body.ilike('%"ministry":%'),
        )
    ).count()

    needs_review = base.filter(Tender.needs_review.is_(True)).count()

    # duplicate tender numbers (within scope)
    dup_q = (
        base.with_entities(Tender.tender_number, func.count().label("c"))
        .filter(Tender.tender_number.isnot(None))
        .group_by(Tender.tender_number)
        .having(func.count() > 1)
        .all()
    )
    duplicate_numbers = [{"tender_number": n, "count": c} for n, c in dup_q]

    # sector confidence distribution (buckets) from sector_details JSONB
    sector_buckets = {"high(>=0.8)": 0, "med(0.6-0.8)": 0, "low(<0.6)": 0}
    sector_name_counts: Dict[str, int] = {}
    for (details,) in base.with_entities(Tender.sector_details).filter(
        Tender.sector_details.isnot(None)
    ).all():
        if not isinstance(details, list):
            continue
        for d in details:
            try:
                conf = float(d.get("confidence", 0))
            except (TypeError, ValueError, AttributeError):
                continue
            name = d.get("name") if isinstance(d, dict) else None
            if name:
                sector_name_counts[name] = sector_name_counts.get(name, 0) + 1
            if conf >= 0.8:
                sector_buckets["high(>=0.8)"] += 1
            elif conf >= 0.6:
                sector_buckets["med(0.6-0.8)"] += 1
            else:
                sector_buckets["low(<0.6)"] += 1

    # sample rows needing review
    sample = (
        base.filter(Tender.needs_review.is_(True))
        .order_by(Tender.id.desc())
        .limit(sample_size)
        .all()
    )
    sample_rows = [
        {
            "id": t.id,
            "tender_number": t.tender_number,
            "tender_number_confidence": t.tender_number_confidence,
            "title_ar": t.title_ar,
            "deadline": t.deadline.isoformat() if t.deadline else None,
            "deadline_missing_reason": t.deadline_missing_reason,
            "status": t.extraction_quality_status,
            "warnings": t.extraction_warnings or [],
        }
        for t in sample
    ]

    real_titles = total - missing_titles
    return {
        "scope": "ids" if ids else "all",
        "total_tenders": total,
        "status_breakdown": status_breakdown,
        "real_titles": real_titles,
        "real_titles_pct": round(100 * real_titles / total, 1) if total else 0.0,
        "missing_titles": missing_titles,
        "missing_deadlines": missing_deadlines,
        "missing_deadline_without_reason": missing_deadline_no_reason,
        "ambiguous_tender_numbers": ambiguous_numbers,
        "multi_tender_rows": multi_tender_rows,
        "json_leaks_fixed": json_leaks_fixed,
        "json_leaks_remaining": json_leaks_remaining,
        "needs_review": needs_review,
        "duplicate_tender_numbers": duplicate_numbers,
        "sector_confidence_distribution": sector_buckets,
        "sector_counts": sector_name_counts,
        "sample_rows_needing_review": sample_rows,
    }
