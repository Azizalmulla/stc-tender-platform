"""
Phase 2 — shared "block → clean fields" builder.

Takes ONE extracted tender block (from app.ai.page_extractor) plus the listing
hints, runs every deterministic validator (app.services.extraction_quality), and
returns a dict of Tender column updates. Used by BOTH the targeted reprocess
script and the live page-grouped scrape so they can never diverge.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services import extraction_quality as eq


def _keywords_from(block: Dict[str, Any], sectors: List[str]) -> List[str]:
    """Cheap, deterministic keyword signal: sector names + salient English title tokens."""
    kws: List[str] = list(sectors)
    title_en = (block.get("title_en") or "")
    for tok in re.findall(r"[A-Za-z]{4,}", title_en):
        t = tok.lower()
        if t not in kws:
            kws.append(t)
    return kws[:10]


def apply_block_to_fields(
    block: Dict[str, Any],
    *,
    listing_number: Optional[str],
    listing_title: Optional[str],
    published_at: Any,
    page_text: Optional[str],
    page_multi: bool,
    match_strength: str = "strong",
    match_warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return a dict of Tender attribute updates for one matched block."""
    warnings: List[str] = list(block.get("warnings") or [])
    warnings += list(match_warnings or [])
    if page_multi:
        warnings.append("multi_tender_page")

    ann_type = block.get("announcement_type")

    # tender number — use THIS block's own text only (never the whole page) plus
    # the listing number as an authoritative external signal.
    num = eq.clean_tender_number(
        block.get("tender_number"),
        block.get("tender_number_candidates"),
        block.get("body_text"),
        listing_number=listing_number,
    )
    warnings += num["warnings"]

    # deadline (explicit, never silently null)
    dl = eq.clean_deadline(
        block.get("deadline"),
        published_at,
        ann_type,
        block.get("confidence"),
    )

    # body must be plain text
    body, leaked = eq.sanitize_body(block.get("body_text"))
    if leaked:
        warnings.append("json_leak_fixed")

    # conservative sectors
    sect = eq.conservative_sectors(block.get("sectors"))
    warnings += sect["warnings"]

    overall_conf = block.get("confidence")
    try:
        overall_conf = float(overall_conf) if overall_conf is not None else None
    except (TypeError, ValueError):
        overall_conf = None

    status = eq.compute_quality_status(
        has_body=bool(body and body.strip()),
        tender_number_conf=num["confidence"],
        deadline_missing_reason=dl["missing_reason"],
        announcement_type=ann_type,
        overall_confidence=overall_conf,
        warnings=warnings,
        match_strength=match_strength,
    )

    title_ar = (block.get("title_ar") or "").strip() or None
    title_en = (block.get("title_en") or "").strip() or None

    return {
        "title_ar": title_ar,
        "title_en": title_en,
        "ministry": (block.get("entity") or "").strip() or None,
        "tender_number": num["number"],
        "tender_number_confidence": num["confidence"],
        "tender_number_candidates": num["candidates"],
        "deadline": dl["deadline"],
        "deadline_confidence": dl["confidence"],
        "deadline_missing_reason": dl["missing_reason"],
        "body": body,
        "summary_ar": (block.get("summary_ar") or "").strip() or None,
        "summary_en": (block.get("summary_en") or "").strip() or None,
        "ai_sectors": sect["sectors"],
        "sector_details": sect["details"],
        "ai_confidence": overall_conf,
        "ai_keywords": _keywords_from(block, sect["sectors"]),
        "announcement_type": ann_type,
        "extraction_json": block,
        "extraction_quality_status": status["status"],
        "extraction_warnings": status["warnings"],
        "needs_review": status["needs_review"],
        "source_page_block_index": block.get("block_index"),
        "ai_processed_at": datetime.now(timezone.utc),
        "_match_strength": match_strength,  # private, for reporting; caller drops it
    }
