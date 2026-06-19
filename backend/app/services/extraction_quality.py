"""
Phase 2 — deterministic extraction-quality validators.

These are PURE, rule-based functions that run AFTER the model returns its
structured JSON. The model proposes; these functions verify. They never call an
API, so they are free, fast, and unit-testable. Responsibilities:

- tender-number cleaning (anchor-based, rejects fiscal-year / OCR-garbage)
- deadline validation (parse + sanity + explicit missing-reason)
- body sanitation (no JSON leaking into the plain-text body)
- conservative sector tagging (drop low-confidence / unreasoned tags)
- matching an extracted page block back to a listing row
- rolling everything up into clean | needs_review | failed
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ── Tender number ───────────────────────────────────────────────────────────

# Explicit Arabic anchors: مناقصة/ممارسة/مزاد/عطاء [عامة|محدودة|مجمعة] رقم <X>
_AR_NUM_ANCHOR = re.compile(
    r"(?:مناقصة|ممارسة|مزاد|عطاء)\s*(?:عامة|محدودة|مجمعة|مركزية)?\s*رقم\s*[:\-]?\s*"
    r"([0-9\u0660-\u0669][0-9\u0660-\u0669A-Za-z/\-\.]*)"
)
# English RFQ/RFP anchors
_EN_RFQ_ANCHOR = re.compile(r"\b(RFQ|RFP)\s*[#:/\-]?\s*([0-9][0-9A-Za-z\-/]*)", re.IGNORECASE)
# KOC/KNPC style codes: CA/CPC/0985, CB/CPC/2551, IT/CPC/4766, GSD/CMS/3102, CZ HSE 126
_CODE_ANCHOR = re.compile(r"\b([A-Z]{2,4}\s*/?\s*(?:CPC|CMS|HSE|CNSE)\s*/?\s*[0-9]{2,6})\b")

# Reject patterns
_FISCAL_YEAR = re.compile(r"^\s*\d{4}\s*/\s*\d{4}(\s*/\s*\d+)?\s*$")  # 2027/2026/14
_LONG_DIGITS = re.compile(r"^\D*\d{13,}\D*$")  # OCR garbage like 241410118888263

_ARABIC_DIGITS = {ord(a): ord(e) for a, e in zip("٠١٢٣٤٥٦٧٨٩", "0123456789")}


def _norm(s: Optional[str]) -> str:
    return (s or "").translate(_ARABIC_DIGITS).strip()


def normalize_number(s: Optional[str]) -> str:
    """Canonical form for comparing two tender numbers (drop spaces/separators)."""
    return re.sub(r"[\s/\\\-_.]", "", _norm(s)).upper()


def _is_garbage_number(s: str) -> bool:
    s = _norm(s)
    if not s:
        return True
    if _LONG_DIGITS.match(s):
        return True
    if _FISCAL_YEAR.match(s):
        return True
    return False


def _looks_like_real_number(s: str) -> bool:
    s = _norm(s)
    if _is_garbage_number(s):
        return False
    if _EN_RFQ_ANCHOR.search(s) or _CODE_ANCHOR.search(s.upper()):
        return True
    # short alphanumeric with a separator and not a fiscal year (e.g. 2418-1, 2448)
    if re.match(r"^[0-9A-Za-z][0-9A-Za-z/\-]{1,18}$", s):
        return True
    return False


_BARE_SHORT = re.compile(r"^\d{1,2}$")


def clean_tender_number(
    primary: Optional[str],
    candidates: Optional[List[str]],
    block_text: Optional[str],
    listing_number: Optional[str] = None,
) -> Dict[str, Any]:
    """Return {number, confidence, candidates, warnings}.

    IMPORTANT: `block_text` must be THIS block's own text only — never the whole
    page — otherwise numbers from neighbouring tenders leak in.

    Trust order: a candidate that equals the listing's own number (strong external
    signal) > the model's per-block primary number > an anchor found in the block's
    own text > other model candidates. Fiscal-year, >12-digit OCR strings, and bare
    1–2 digit "numbers" are rejected/down-ranked.
    """
    warnings: List[str] = []
    pool: List[Tuple[str, float, str]] = []  # (number, confidence, source)
    text = _norm(block_text)
    ln = normalize_number(listing_number)

    # model's per-block primary number — most trusted intrinsic signal
    p = _norm(primary)
    if p and not _is_garbage_number(p):
        pool.append((p, 0.5 if _BARE_SHORT.match(p) else 0.9, "model_primary"))
    elif p:
        warnings.append("rejected_garbage_number")

    # other model candidates
    for c in (candidates or []):
        c = _norm(c)
        if not c:
            continue
        if _is_garbage_number(c):
            warnings.append("rejected_garbage_number")
            continue
        pool.append((c, 0.45 if _BARE_SHORT.match(c) else 0.65, "candidate"))

    # anchors found in THIS block's own text (not the whole page)
    for m in _AR_NUM_ANCHOR.finditer(text):
        val = _norm(m.group(1)).rstrip(".,؛)")
        if not _is_garbage_number(val):
            pool.append((val, 0.8, "ar_anchor"))
    for m in _EN_RFQ_ANCHOR.finditer(text):
        pool.append((f"{m.group(1).upper()}/{_norm(m.group(2))}", 0.78, "rfq_anchor"))
    for m in _CODE_ANCHOR.finditer(text.upper()):
        pool.append((re.sub(r"\s+", "", m.group(1)), 0.78, "code_anchor"))

    # boost whichever candidate equals the listing number (authoritative match)
    if ln:
        for i, (num, conf, src) in enumerate(pool):
            if normalize_number(num) == ln:
                pool[i] = (num, max(conf, 0.95), src + "+listing")

    if not pool:
        warnings.append("ambiguous_tender_number")
        proposed = [c for c in ([primary] + list(candidates or [])) if c]
        return {"number": None, "confidence": 0.2, "candidates": proposed, "warnings": warnings}

    # de-dupe keeping highest confidence per normalized number
    best_by_norm: Dict[str, Tuple[str, float, str]] = {}
    for num, conf, src in pool:
        key = normalize_number(num)
        if not key:
            continue
        if key not in best_by_norm or conf > best_by_norm[key][1]:
            best_by_norm[key] = (num, conf, src)

    ranked = sorted(best_by_norm.values(), key=lambda x: x[1], reverse=True)
    cand_list = [r[0] for r in ranked]
    best_num, best_conf, _ = ranked[0]

    # a bare 1–2 digit "number" (e.g. "مناقصة رقم 3") is too weak to trust unless
    # it is exactly the listing's own number — down-rank so it goes to review.
    if _BARE_SHORT.match(normalize_number(best_num)) and (not ln or normalize_number(best_num) != ln):
        best_conf = min(best_conf, 0.5)
        if "ambiguous_tender_number" not in warnings:
            warnings.append("ambiguous_tender_number")

    # only flag ambiguity when several DISTINCT high-confidence numbers compete
    strong = [r for r in ranked if r[1] >= 0.85]
    if len(strong) > 1 and len({normalize_number(s[0]) for s in strong}) > 1:
        best_conf = min(best_conf, 0.6)
        warnings.append("multiple_tender_number_candidates")
    if best_conf < 0.65:
        warnings.append("ambiguous_tender_number")

    return {"number": best_num, "confidence": round(best_conf, 2),
            "candidates": cand_list, "warnings": list(dict.fromkeys(warnings))}


# ── Deadline ────────────────────────────────────────────────────────────────

_NO_DEADLINE_TYPES = {"Awarding", "Cancellation", "OpeningEnvelopes", "Complaint"}


def parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = _norm(str(value))
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def clean_deadline(
    raw_deadline: Any,
    published_at: Any,
    announcement_type: Optional[str],
    model_confidence: Optional[float] = None,
) -> Dict[str, Any]:
    """Return {deadline, confidence, missing_reason}. Never silently null."""
    dt = parse_date(raw_deadline)
    pub = parse_date(published_at)

    if dt is None:
        if announcement_type in _NO_DEADLINE_TYPES:
            return {"deadline": None, "confidence": None,
                    "missing_reason": f"not_applicable_for_{announcement_type}"}
        return {"deadline": None, "confidence": None,
                "missing_reason": "no_deadline_found_on_page"}

    conf = float(model_confidence) if model_confidence is not None else 0.8
    # sanity: deadline should not predate publication
    if pub and dt < pub:
        return {"deadline": dt, "confidence": min(conf, 0.4),
                "missing_reason": "deadline_before_publication"}
    return {"deadline": dt, "confidence": round(conf, 2), "missing_reason": None}


# ── Body sanitation (no JSON leaks) ─────────────────────────────────────────

def sanitize_body(text: Optional[str]) -> Tuple[Optional[str], bool]:
    """Ensure body is plain OCR text. If a JSON/code-fence payload leaked in, try
    to recover the real body_text/body field; otherwise strip fences. Returns
    (clean_text, json_leak_fixed)."""
    if not text:
        return text, False
    stripped = text.strip()
    leaked = stripped.startswith("```json") or stripped.startswith("{") or stripped.startswith("[") \
        or ('"ministry"' in stripped[:200]) or ('"body"' in stripped[:200])
    if not leaked:
        return text, False

    # strip code fences
    cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
    cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    # try to pull a textual body field out of the JSON
    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        obj = json.loads(cleaned[start:end])
        if isinstance(obj, list) and obj:
            obj = obj[0]
        if isinstance(obj, dict):
            for key in ("body_text", "body", "text"):
                if obj.get(key):
                    return str(obj[key]).strip(), True
    except Exception:
        pass
    # last resort: keep the de-fenced text but flag it was repaired
    return cleaned, True


# ── Conservative sector tagging ─────────────────────────────────────────────

_VALID_SECTORS = {
    "telecom", "datacenter", "callcenter", "network", "smartcity", "software",
    "construction", "medical", "oil_gas", "education", "security", "transport",
    "finance", "food", "facilities", "environment", "energy", "legal",
}
_SECTOR_MIN_CONF = 0.6


def conservative_sectors(raw_sectors: Any) -> Dict[str, Any]:
    """Keep only sectors with confidence >= 0.6 AND a non-empty reason.

    Accepts either a list of strings or a list of {name, confidence, reason}.
    Returns {sectors: [names], details: [{name,confidence,reason}], warnings}.
    """
    warnings: List[str] = []
    details: List[Dict[str, Any]] = []

    if not raw_sectors:
        return {"sectors": [], "details": [], "warnings": warnings}

    for item in raw_sectors:
        if isinstance(item, str):
            name, conf, reason = item, 0.5, ""
        elif isinstance(item, dict):
            name = item.get("name") or item.get("sector")
            conf = item.get("confidence", 0.5)
            reason = item.get("reason") or item.get("match_reason") or ""
        else:
            continue
        if not name or name not in _VALID_SECTORS:
            continue
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.5
        if conf >= _SECTOR_MIN_CONF and reason.strip():
            details.append({"name": name, "confidence": round(conf, 2), "reason": reason.strip()[:200]})
        else:
            warnings.append("low_confidence_sector")

    # de-dupe by name keeping highest confidence
    by_name: Dict[str, Dict[str, Any]] = {}
    for d in details:
        if d["name"] not in by_name or d["confidence"] > by_name[d["name"]]["confidence"]:
            by_name[d["name"]] = d
    final = sorted(by_name.values(), key=lambda x: x["confidence"], reverse=True)
    return {"sectors": [d["name"] for d in final], "details": final,
            "warnings": list(dict.fromkeys(warnings))}


# ── Block ↔ listing matching ────────────────────────────────────────────────

def _title_tokens(s: Optional[str]) -> set:
    s = _norm(s).lower()
    return set(re.findall(r"[a-z\u0600-\u06ff0-9]{3,}", s))


def match_block_to_listing(
    blocks: List[Dict[str, Any]],
    listing_number: Optional[str],
    listing_title: Optional[str],
) -> Dict[str, Any]:
    """Pick the page block that best matches a listing row.

    Returns {block, strength: strong|weak|none, warnings}. Strong = tender-number
    match; weak = title-token overlap only; none = no usable match (caller should
    mark needs_review with listing_match_weak).
    """
    warnings: List[str] = []
    if not blocks:
        return {"block": None, "strength": "none", "warnings": ["listing_match_weak"]}

    ln = normalize_number(listing_number)
    if ln:
        for b in blocks:
            cands = [b.get("tender_number")] + list(b.get("tender_number_candidates") or [])
            if any(normalize_number(c) == ln for c in cands if c):
                return {"block": b, "strength": "strong", "warnings": []}

    # fall back to title-token overlap
    lt = _title_tokens(listing_title)
    best, best_score = None, 0.0
    for b in blocks:
        bt = _title_tokens(b.get("title_ar")) | _title_tokens(b.get("title_en")) | _title_tokens(b.get("body_text"))
        if not lt or not bt:
            continue
        score = len(lt & bt) / max(1, len(lt))
        if score > best_score:
            best, best_score = b, score

    if best is not None and best_score >= 0.4:
        return {"block": best, "strength": "weak", "warnings": ["listing_match_weak"]}

    # single-block page → assume it's the one
    if len(blocks) == 1:
        return {"block": blocks[0], "strength": "weak", "warnings": ["listing_match_weak"]}

    return {"block": None, "strength": "none", "warnings": ["listing_match_weak"]}


def assign_blocks_to_listings(
    blocks: List[Dict[str, Any]],
    listings: List[Dict[str, Any]],
) -> Dict[Any, Dict[str, Any]]:
    """Greedy UNIQUE assignment of page blocks to listing rows.

    Prevents two listings from grabbing the same block (the duplicate-number bug).
    `listings` items need {id, tender_number, title}. Returns
    {listing_id: {block, strength, warnings}}.

    Pass 1: match by tender number (authoritative) — each block used at most once.
    Pass 2: remaining listings matched by title-token overlap to remaining blocks.
    Pass 3: if exactly one listing and one block remain, pair them (weak).
    """
    result: Dict[Any, Dict[str, Any]] = {}
    pool = list(range(len(blocks)))

    # Pass 1 — strong, by number
    for L in listings:
        ln = normalize_number(L.get("tender_number"))
        if not ln:
            continue
        for bi in list(pool):
            b = blocks[bi]
            cands = [b.get("tender_number")] + list(b.get("tender_number_candidates") or [])
            if any(normalize_number(c) == ln for c in cands if c):
                result[L["id"]] = {"block": b, "strength": "strong", "warnings": []}
                pool.remove(bi)
                break

    # Pass 2 — weak, by title overlap (unique)
    for L in listings:
        if L["id"] in result:
            continue
        lt = _title_tokens(L.get("title"))
        best_bi, best_score = None, 0.0
        for bi in pool:
            b = blocks[bi]
            bt = _title_tokens(b.get("title_ar")) | _title_tokens(b.get("title_en")) | _title_tokens(b.get("body_text"))
            if not lt or not bt:
                continue
            score = len(lt & bt) / max(1, len(lt))
            if score > best_score:
                best_bi, best_score = bi, score
        if best_bi is not None and best_score >= 0.4:
            result[L["id"]] = {"block": blocks[best_bi], "strength": "weak", "warnings": ["listing_match_weak"]}
            pool.remove(best_bi)

    # Pass 3 — last 1:1
    remaining = [L for L in listings if L["id"] not in result]
    if len(remaining) == 1 and len(pool) == 1:
        result[remaining[0]["id"]] = {"block": blocks[pool[0]], "strength": "weak", "warnings": ["listing_match_weak"]}
        pool.clear()

    for L in listings:
        result.setdefault(L["id"], {"block": None, "strength": "none", "warnings": ["listing_match_weak"]})
    return result


# ── Roll-up status ──────────────────────────────────────────────────────────

_BLOCKING_WARNINGS = {"ambiguous_tender_number", "listing_match_weak", "json_leak_unrecovered"}


def compute_quality_status(
    *,
    has_body: bool,
    tender_number_conf: Optional[float],
    deadline_missing_reason: Optional[str],
    announcement_type: Optional[str],
    overall_confidence: Optional[float],
    warnings: List[str],
) -> Dict[str, Any]:
    """Roll warnings + confidences into clean | needs_review | failed."""
    w = list(dict.fromkeys(warnings))

    if not has_body:
        return {"status": "failed", "needs_review": True, "warnings": w + ["no_body_extracted"]}

    needs = False
    if (overall_confidence is not None and overall_confidence < 0.5):
        needs = True
    if tender_number_conf is not None and tender_number_conf < 0.65:
        needs = True
        if "ambiguous_tender_number" not in w:
            w.append("ambiguous_tender_number")
    if deadline_missing_reason == "no_deadline_found_on_page" and announcement_type in (None, "NewTender"):
        needs = True
        if "missing_deadline" not in w:
            w.append("missing_deadline")
    if deadline_missing_reason == "deadline_before_publication":
        needs = True
    if any(bw in w for bw in _BLOCKING_WARNINGS):
        needs = True

    return {"status": "needs_review" if needs else "clean", "needs_review": needs, "warnings": w}
