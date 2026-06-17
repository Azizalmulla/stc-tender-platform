"""
Usage / cost observability logger (Phase 0).

Records one row per external paid call (Claude, Voyage, Browserless, OpenAI)
into the `usage_logs` table so weekly spend can be measured per run_type.

Design rules:
- BEST EFFORT: any failure here is swallowed — it must never break the pipeline.
- DECOUPLED: opens its own short-lived DB session so it never interferes with
  the caller's transaction.
- CHEAP: a single INSERT per logged call.
"""
import logging
from decimal import Decimal
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


# Approximate public list prices (USD per 1M tokens). Used only for rough
# estimates in the cost report — not billing-accurate. Update as prices change.
_PRICING_PER_MTOK = {
    # provider/model: (input_usd_per_mtok, output_usd_per_mtok)
    "anthropic:claude-sonnet-4-6": (3.0, 15.0),
    "anthropic:default": (3.0, 15.0),
    "openai:gpt-4o": (2.5, 10.0),
    "openai:gpt-4o-mini": (0.15, 0.6),
    "voyage:voyage-law-2": (0.12, 0.0),  # embeddings: input-only
    "voyage:default": (0.12, 0.0),
}

# Flat per-unit cost for non-token services (USD per call). Browserless is
# billed per unit/second; this is a rough placeholder for visibility only.
_FLAT_COST = {
    "browserless:screenshot": 0.0015,
}


def estimate_cost(
    provider: str,
    model: Optional[str],
    input_tokens: Optional[int],
    output_tokens: Optional[int],
) -> Optional[Decimal]:
    """Best-effort cost estimate in USD. Returns None if not estimable."""
    try:
        key = f"{provider}:{model}" if model else f"{provider}:default"
        if key not in _PRICING_PER_MTOK:
            key = f"{provider}:default"
        if key not in _PRICING_PER_MTOK:
            return None
        in_rate, out_rate = _PRICING_PER_MTOK[key]
        cost = 0.0
        if input_tokens:
            cost += (input_tokens / 1_000_000) * in_rate
        if output_tokens:
            cost += (output_tokens / 1_000_000) * out_rate
        return Decimal(str(round(cost, 6)))
    except Exception:
        return None


def log_usage(
    provider: str,
    run_type: str,
    *,
    model: Optional[str] = None,
    tender_id: Optional[int] = None,
    source_id: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    estimated_cost_usd: Optional[Decimal] = None,
    cache_hit: bool = False,
    retry_count: int = 0,
    error: Optional[str] = None,
) -> None:
    """Insert a usage row. Never raises."""
    if not settings.ENABLE_USAGE_LOGGING:
        return

    # Flat-cost services (e.g. browserless screenshot)
    if estimated_cost_usd is None:
        flat = _FLAT_COST.get(f"{provider}:{run_type}")
        if flat is not None:
            estimated_cost_usd = Decimal(str(flat))
        else:
            estimated_cost_usd = estimate_cost(provider, model, input_tokens, output_tokens)

    db = None
    try:
        from app.db.session import SessionLocal
        from app.models.tender import UsageLog

        db = SessionLocal()
        db.add(UsageLog(
            provider=provider,
            model=model,
            run_type=run_type,
            tender_id=tender_id,
            source_id=source_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd,
            cache_hit=cache_hit,
            retry_count=retry_count,
            error=(error[:1000] if error else None),
        ))
        db.commit()
    except Exception as e:  # pragma: no cover - observability must not break flow
        logger.debug(f"usage_logger: failed to write usage row: {e}")
        try:
            if db is not None:
                db.rollback()
        except Exception:
            pass
    finally:
        try:
            if db is not None:
                db.close()
        except Exception:
            pass


def extract_anthropic_usage(response) -> tuple[Optional[int], Optional[int]]:
    """Pull (input_tokens, output_tokens) from an Anthropic message response."""
    try:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None, None
        return getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)
    except Exception:
        return None, None
