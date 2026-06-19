"""
Phase 2 — page-level multi-tender extractor (provider-dispatching).

ONE extraction call per rendered page. The model segments the page into logical
tender blocks and returns a strict JSON array — it must NOT force a multi-tender
page into a single row. Deterministic validation happens afterwards in
`app.services.extraction_quality` (the model proposes, rules verify).

Backends (see settings.PAGE_EXTRACTOR_PROVIDER):
  * "anthropic" → Claude Vision (one messages.create call). Production default.
  * "openai"    → OpenAI vision (gpt-5.4-mini), one image/page chat call.
                   Falls back to Claude on error.
  * "mistral"   → Mistral OCR 3 (mistral-ocr-2512), one OCR+document_annotation
                   call (~$0.003/page). Falls back to Claude on error.
                   NOTE: fails on Kuwait Al-Yawm flipbook pages (reads furniture,
                   hallucinates) — not safe as primary for this content.

This replaces the old per-listing flow that made 4 Claude calls per listing and
re-OCR'd the whole two-page spread each time (the contamination + cost bug).
"""
from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.ai.claude_service import claude_service


_PAGE_PROMPT = """أنت خبير في تحليل صفحات الجريدة الرسمية الكويتية (كويت اليوم).
الصورة قد تحتوي على صفحة واحدة أو على صفحتين متجاورتين (spread)، وقد تحتوي على
أكثر من إعلان مناقصة/ممارسة/مزاد على نفس الصفحة.

You are extracting Kuwait Official Gazette (Kuwait Al-Yawm) tender notices from a
page image that MAY contain a two-page spread and MULTIPLE separate tenders.

## CRITICAL RULES
1. SEGMENT the page into separate tender blocks. Each distinct notice (each
   "مناقصة رقم / ممارسة رقم / مزاد رقم / عطاء رقم / RFQ / RFP / CA/.. / CB/.. / CPC")
   is ITS OWN block. Do NOT merge two tenders into one block.
2. If the page truly has only one tender, return one block.
3. For each block, extract its OWN number, title, entity, deadline and body —
   do not let text from a neighbouring tender bleed into another block.
4. tender_number: copy the EXACT printed number next to an explicit label
   (مناقصة رقم / RFQ / CB/CPC/.. etc). Put any other plausible numbers you see in
   tender_number_candidates. Do NOT invent a number. A fiscal-year string like
   "2027/2026/14" is NOT a tender number unless it is literally labelled as one.
5. deadline: only from explicit anchors — "آخر موعد لتقديم العطاءات/العروض",
   "تاريخ الإقفال", "closing date", "submission deadline". Format YYYY-MM-DD.
   If there is no deadline on the page for that block, return null (do not guess).
6. body_text: PLAIN TEXT only (the readable Arabic/English notice text). NEVER put
   JSON inside body_text.
7. sectors: be CONSERVATIVE. Only include a sector if the text clearly supports it,
   and give a short reason. False positives are harmful.

## OUTPUT — return STRICT JSON ONLY, no prose, no markdown fences:
{
  "page_contains_multiple_tenders": true,
  "tenders": [
    {
      "block_index": 1,
      "tender_number": "string or null",
      "tender_number_candidates": ["..."],
      "title_ar": "العنوان/الموضوع الحقيقي للمناقصة",
      "title_en": "real English title if derivable, else null",
      "entity": "الجهة المعلنة (الوزارة/الشركة/الهيئة)",
      "deadline": "YYYY-MM-DD or null",
      "publication_date": "YYYY-MM-DD or null",
      "announcement_type": "NewTender|Awarding|Cancellation|Postponement|OpeningEnvelopes|null",
      "body_text": "plain text of THIS tender only",
      "summary_ar": "ملخص سطرين",
      "summary_en": "2-line summary",
      "sectors": [{"name": "telecom", "confidence": 0.0, "reason": "why"}],
      "confidence": 0.0,
      "warnings": []
    }
  ]
}

Valid sector names ONLY: telecom, datacenter, callcenter, network, smartcity,
software, construction, medical, oil_gas, education, security, transport, finance,
food, facilities, environment, energy, legal.

أرجع JSON فقط الآن:"""


def _parse_json_array(text: str) -> Dict[str, Any]:
    """Robustly parse the model's JSON object (tolerates fences / leading prose)."""
    if not text:
        raise ValueError("empty response")
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if "```" in s[3:] else s
        s = s.lstrip("json").strip()
    start = s.find("{")
    end = s.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(s[start:end])


def extract_page(
    image_bytes: bytes,
    image_format: str = "png",
    source_page: Optional[str] = None,
) -> Dict[str, Any]:
    """Run ONE page-level extraction and return {page_contains_multiple_tenders, tenders:[...]}.

    Provider is chosen by settings.PAGE_EXTRACTOR_PROVIDER:
      * "mistral"   → Mistral OCR 3 (cheap, default). Falls back to Claude on
                       error when settings.PAGE_EXTRACTOR_FALLBACK is true.
      * "anthropic" → Claude Vision only.

    Never raises into the pipeline; returns a structured failure dict instead.
    """
    provider = (settings.PAGE_EXTRACTOR_PROVIDER or "anthropic").lower()

    if provider == "mistral":
        from app.ai.mistral_extractor import extract_page_mistral
        result = extract_page_mistral(image_bytes, image_format=image_format, source_page=source_page)
        if not result.get("error"):
            return result
        if settings.PAGE_EXTRACTOR_FALLBACK and claude_service is not None:
            print(f"↩️  falling back to Claude for {source_page} (mistral error: {result.get('error')})")
            return _extract_page_claude(image_bytes, image_format=image_format, source_page=source_page)
        return result

    if provider == "openai":
        from app.ai.openai_extractor import extract_page_openai
        result = extract_page_openai(image_bytes, image_format=image_format, source_page=source_page)
        if not result.get("error"):
            return result
        if settings.PAGE_EXTRACTOR_FALLBACK and claude_service is not None:
            print(f"↩️  falling back to Claude for {source_page} (openai error: {result.get('error')})")
            return _extract_page_claude(image_bytes, image_format=image_format, source_page=source_page)
        return result

    return _extract_page_claude(image_bytes, image_format=image_format, source_page=source_page)


def _extract_page_claude(
    image_bytes: bytes,
    image_format: str = "png",
    source_page: Optional[str] = None,
) -> Dict[str, Any]:
    """Run one Claude Vision call and return {page_contains_multiple_tenders, tenders:[...]}."""
    from app.core.usage_logger import log_usage, extract_anthropic_usage

    if claude_service is None:
        return {"page_contains_multiple_tenders": False, "tenders": [], "error": "claude_service unavailable"}

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64",
                                          "media_type": f"image/{image_format}",
                                          "data": image_b64}},
            {"type": "text", "text": _PAGE_PROMPT},
        ],
    }]

    try:
        # max_tokens generous: a spread can hold several tender blocks.
        response = claude_service.client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=8000,
            messages=messages,
        )
        try:
            _i, _o = extract_anthropic_usage(response)
            log_usage("anthropic", "page_extract", model=settings.CLAUDE_MODEL,
                      source_id=source_page, input_tokens=_i, output_tokens=_o)
        except Exception:
            pass

        data = _parse_json_array(response.content[0].text)
        tenders = data.get("tenders") or []
        if not isinstance(tenders, list):
            tenders = []
        # normalise block_index + source_page
        for idx, b in enumerate(tenders, 1):
            if isinstance(b, dict):
                b.setdefault("block_index", idx)
                if source_page:
                    b["source_page"] = source_page
        return {
            "page_contains_multiple_tenders": bool(data.get("page_contains_multiple_tenders", len(tenders) > 1)),
            "tenders": [b for b in tenders if isinstance(b, dict)],
        }
    except Exception as e:
        print(f"❌ page_extract failed for {source_page}: {e}")
        try:
            log_usage("anthropic", "page_extract", model=settings.CLAUDE_MODEL,
                      source_id=source_page, error=str(e))
        except Exception:
            pass
        return {"page_contains_multiple_tenders": False, "tenders": [], "error": str(e)}
