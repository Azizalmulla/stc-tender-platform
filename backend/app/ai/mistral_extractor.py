"""
Phase 2 — Mistral OCR 3 page-level multi-tender extractor.

ONE `client.ocr.process` call per rendered page using Mistral OCR 3
(mistral-ocr-2512). The page image is OCR'd AND, in the same call, annotated
into a strict JSON object via `document_annotation_format` — an array of tender
blocks. This mirrors the Claude page-extractor's output shape exactly so the
rest of the pipeline (extraction_pipeline, extraction_quality, the cron v2
scrape, reprocess_quality) is unchanged.

Why Mistral here:
  * ~$0.003 / page (OCR + annotation) vs ~$0.07 / page for Claude Vision.
  * strict JSON-schema mode → no JSON-in-body leaks at the source.

Deterministic validation still happens afterwards in
`app.services.extraction_quality` (model proposes, rules verify).
"""
from __future__ import annotations

import base64
import json
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.config import settings


# ── Structured-output schema (what we ask Mistral to fill) ──────────────────
class SectorTag(BaseModel):
    name: str = Field(description="One of the allowed sector names")
    confidence: float = Field(description="0.0–1.0 confidence this sector applies")
    reason: str = Field(description="Short reason from the text")


class TenderBlock(BaseModel):
    block_index: int = Field(description="1-based index of this tender on the page")
    tender_number: Optional[str] = Field(description="EXACT printed number next to an explicit label, else null")
    tender_number_candidates: List[str] = Field(description="Other plausible numbers seen in THIS block")
    title_ar: Optional[str] = Field(description="Real Arabic subject/title of the tender")
    title_en: Optional[str] = Field(description="Real English title if derivable, else null")
    entity: Optional[str] = Field(description="Announcing entity (ministry/company/authority)")
    deadline: Optional[str] = Field(description="YYYY-MM-DD from an explicit deadline anchor, else null")
    publication_date: Optional[str] = Field(description="YYYY-MM-DD if present, else null")
    announcement_type: Optional[str] = Field(description="NewTender|Awarding|Cancellation|Postponement|OpeningEnvelopes|null")
    body_text: Optional[str] = Field(description="Plain text of THIS tender only. NEVER JSON.")
    summary_ar: Optional[str] = Field(description="2-line Arabic summary")
    summary_en: Optional[str] = Field(description="2-line English summary")
    sectors: List[SectorTag] = Field(description="Conservative sector tags only")
    confidence: float = Field(description="0.0–1.0 overall confidence in this block")
    warnings: List[str] = Field(description="Any issues, e.g. ambiguous_tender_number")


class PageExtraction(BaseModel):
    page_contains_multiple_tenders: bool
    tenders: List[TenderBlock]


_ANNOTATION_PROMPT = """أنت خبير في تحليل صفحات الجريدة الرسمية الكويتية (كويت اليوم).
الصورة قد تحتوي على صفحة واحدة أو صفحتين متجاورتين (spread)، وقد تحتوي على أكثر من
إعلان مناقصة/ممارسة/مزاد على نفس الصفحة.

You are extracting Kuwait Official Gazette (Kuwait Al-Yawm) tender notices from a
page that MAY contain a two-page spread and MULTIPLE separate tenders.

RULES:
1. SEGMENT the page into separate tender blocks. Each distinct notice
   (مناقصة رقم / ممارسة رقم / مزاد رقم / عطاء رقم / RFQ / RFP / CA/.. / CB/.. / CPC)
   is ITS OWN block. Do NOT merge two tenders into one block. If the page truly has
   one tender, return one block.
2. For each block extract its OWN number, title, entity, deadline and body — do not
   let text from a neighbouring tender bleed into another block.
3. tender_number: copy the EXACT printed number next to an explicit label. Put other
   plausible numbers in tender_number_candidates. Do NOT invent a number. A
   fiscal-year string like "2027/2026/14" is NOT a tender number unless literally
   labelled as one. Reject OCR-garbage numbers > 12 digits and random budget numbers.
4. deadline: ONLY from explicit anchors — "آخر موعد لتقديم العطاءات/العروض",
   "تاريخ الإقفال", "closing date", "submission deadline". Format YYYY-MM-DD. If no
   deadline for that block, return null (do not guess).
5. body_text: PLAIN TEXT only. NEVER put JSON inside body_text.
6. sectors: be CONSERVATIVE — include a sector only if the text clearly supports it,
   with a short reason. False positives are harmful. Valid sector names ONLY:
   telecom, datacenter, callcenter, network, smartcity, software, construction,
   medical, oil_gas, education, security, transport, finance, food, facilities,
   environment, energy, legal.
"""


def _import_mistral():
    """Import the Mistral client across SDK layouts (1.x top-level, 2.x .client)."""
    try:
        from mistralai import Mistral  # SDK 1.x
        return Mistral
    except Exception:
        from mistralai.client import Mistral  # SDK 2.x (namespace package)
        return Mistral


def _client():
    if not settings.MISTRAL_API_KEY:
        return None
    Mistral = _import_mistral()
    return Mistral(api_key=settings.MISTRAL_API_KEY)


def _annotation_format():
    """Build the document_annotation_format from the Pydantic schema.

    Uses the SDK helper when available; falls back to a hand-built json_schema.
    """
    try:
        try:
            from mistralai.extra import response_format_from_pydantic_model
        except Exception:
            from mistralai.client import response_format_from_pydantic_model  # type: ignore
        return response_format_from_pydantic_model(PageExtraction)
    except Exception:
        return {
            "type": "json_schema",
            "json_schema": {
                "schema": PageExtraction.model_json_schema(),
                "name": "page_extraction",
                "strict": True,
            },
        }


def extract_page_mistral(
    image_bytes: bytes,
    image_format: str = "png",
    source_page: Optional[str] = None,
) -> Dict[str, Any]:
    """One Mistral OCR 3 call → {page_contains_multiple_tenders, tenders:[...]}.

    Returns a dict with an "error" key on failure (so the caller can fall back
    to Claude). Never raises into the pipeline.
    """
    from app.core.usage_logger import log_usage

    client = _client()
    if client is None:
        return {"page_contains_multiple_tenders": False, "tenders": [], "error": "mistral_api_key_missing"}

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    document = {"type": "image_url", "image_url": f"data:image/{image_format};base64,{b64}"}

    try:
        resp = client.ocr.process(
            model=settings.MISTRAL_OCR_MODEL,
            document=document,
            document_annotation_format=_annotation_format(),
            document_annotation_prompt=_ANNOTATION_PROMPT,
            include_image_base64=False,
        )

        pages_processed = None
        try:
            pages_processed = getattr(getattr(resp, "usage_info", None), "pages_processed", None)
        except Exception:
            pass
        log_usage(
            "mistral", "page_extract", model=settings.MISTRAL_OCR_MODEL,
            source_id=source_page,
            estimated_cost_usd=(Decimal(str(round(0.003 * pages_processed, 6))) if pages_processed else None),
        )

        ann = getattr(resp, "document_annotation", None)
        if not ann:
            raise ValueError("empty document_annotation")
        data = json.loads(ann) if isinstance(ann, str) else ann

        tenders = data.get("tenders") or []
        if not isinstance(tenders, list):
            tenders = []
        for idx, b in enumerate(tenders, 1):
            if isinstance(b, dict):
                b.setdefault("block_index", idx)
                if source_page:
                    b["source_page"] = source_page
        return {
            "page_contains_multiple_tenders": bool(
                data.get("page_contains_multiple_tenders", len(tenders) > 1)
            ),
            "tenders": [b for b in tenders if isinstance(b, dict)],
        }
    except Exception as e:
        print(f"❌ mistral page_extract failed for {source_page}: {e}")
        try:
            log_usage("mistral", "page_extract", model=settings.MISTRAL_OCR_MODEL,
                      source_id=source_page, error=str(e))
        except Exception:
            pass
        return {"page_contains_multiple_tenders": False, "tenders": [], "error": str(e)}
