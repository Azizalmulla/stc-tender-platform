"""
Phase 2 — OpenAI vision page-level multi-tender extractor (benchmark backend).

ONE image/page call to an OpenAI vision model (default gpt-5.4-mini). Image-native
like Claude (it reads the whole rendered page, not OCR'd furniture), returns the
SAME strict multi-tender JSON shape, and feeds the SAME deterministic trust gate
in `app.services.extraction_quality`.

Selected via settings.PAGE_EXTRACTOR_PROVIDER == "openai". Anthropic stays the
production default unless OpenAI clearly beats it on the targeted sample.
"""
from __future__ import annotations

import base64
from typing import Any, Dict, Optional

from app.core.config import settings
# Reuse the exact Claude page prompt + robust JSON parser (same schema/shape).
# Safe import: page_extractor does NOT import this module at top level (only
# lazily inside its dispatcher), so there is no circular import at load time.
from app.ai.page_extractor import _PAGE_PROMPT, _parse_json_array


def _client():
    if not settings.OPENAI_API_KEY:
        return None
    from openai import OpenAI
    return OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=2, timeout=120.0)


def _create(client, model: str, messages: list):
    """Create a chat completion, tolerating GPT-5/o-series param differences.

    GPT-5/o-series require `max_completion_tokens`; older models use `max_tokens`.
    """
    base = dict(model=model, messages=messages, response_format={"type": "json_object"})
    try:
        return client.chat.completions.create(max_completion_tokens=8000, **base)
    except Exception as e:
        msg = str(e).lower()
        if "max_completion_tokens" in msg or "unsupported" in msg or "max_tokens" in msg:
            return client.chat.completions.create(max_tokens=8000, **base)
        raise


def extract_page_openai(
    image_bytes: bytes,
    image_format: str = "png",
    source_page: Optional[str] = None,
) -> Dict[str, Any]:
    """One OpenAI vision call → {page_contains_multiple_tenders, tenders:[...]}.

    Returns a dict with an "error" key on failure (so the caller can fall back).
    Never raises into the pipeline.
    """
    from app.core.usage_logger import log_usage

    client = _client()
    if client is None:
        return {"page_contains_multiple_tenders": False, "tenders": [], "error": "openai_api_key_missing"}

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": _PAGE_PROMPT},
            {"type": "image_url", "image_url": {
                "url": f"data:image/{image_format};base64,{b64}", "detail": "high"}},
        ],
    }]

    model = settings.OPENAI_VISION_MODEL
    try:
        response = _create(client, model, messages)

        try:
            usage = getattr(response, "usage", None)
            in_tok = getattr(usage, "prompt_tokens", None) if usage else None
            out_tok = getattr(usage, "completion_tokens", None) if usage else None
            log_usage("openai", "page_extract", model=model, source_id=source_page,
                      input_tokens=in_tok, output_tokens=out_tok)
        except Exception:
            pass

        text = response.choices[0].message.content or ""
        data = _parse_json_array(text)
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
        print(f"❌ openai page_extract failed for {source_page}: {e}")
        try:
            log_usage("openai", "page_extract", model=model, source_id=source_page, error=str(e))
        except Exception:
            pass
        return {"page_contains_multiple_tenders": False, "tenders": [], "error": str(e)}
