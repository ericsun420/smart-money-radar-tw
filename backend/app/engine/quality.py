from __future__ import annotations

from datetime import datetime

from app.storage.models import StockFlow, StockSnapshot
from app.time_utils import ensure_taipei, is_regular_tw_session, market_date


FORMAL_PROVIDER_TYPES = {"official_full", "official_intraday"}
FORMAL_BUCKETS = {"official_full", "official_intraday"}
BLOCKING_SOURCE_STATUSES = {"seed", "cache", "mock", "stale", "fallback", "unit_unknown"}


def quality_block_reason(snapshot: StockSnapshot, *, now: datetime, stale_seconds: int) -> str | None:
    now_local = ensure_taipei(now)
    source_ts = ensure_taipei(snapshot.source_ts or snapshot.timestamp)
    age_seconds = (now_local - source_ts).total_seconds()
    if snapshot.provider_type not in FORMAL_PROVIDER_TYPES:
        return f"provider_type_not_formal:{snapshot.provider_type}"
    if snapshot.data_quality_bucket not in FORMAL_BUCKETS:
        return f"data_quality_not_formal:{snapshot.data_quality_bucket}"
    if snapshot.source_status in BLOCKING_SOURCE_STATUSES:
        return f"source_status_blocked:{snapshot.source_status}"
    if age_seconds > stale_seconds:
        return f"stale_timestamp:{int(age_seconds)}s"
    if snapshot.market_date and snapshot.market_date != market_date(now_local):
        return f"market_date_mismatch:{snapshot.market_date}"
    if not is_regular_tw_session(now_local):
        return "outside_regular_tw_session"
    if not snapshot.units_normalized:
        return "unit_normalization_failed"
    return None


def apply_snapshot_quality(snapshot: StockSnapshot, *, now: datetime, stale_seconds: int) -> StockSnapshot:
    blocked = quality_block_reason(snapshot, now=now, stale_seconds=stale_seconds)
    if blocked:
        bucket = snapshot.data_quality_bucket
        if "stale" in blocked:
            bucket = "stale"
        if "unit" in blocked:
            bucket = "unit_unknown"
        return snapshot.model_copy(
            update={
                "formal_grade": False,
                "formal_grade_label": "blocked",
                "blocked_reason": blocked,
                "data_quality_bucket": bucket,
            }
        )
    return snapshot.model_copy(update={"formal_grade": True, "formal_grade_label": "formal", "blocked_reason": None})


def topic_quality(stock_flows: list[StockFlow]) -> tuple[str, bool, str | None]:
    if not stock_flows:
        return "official_partial", False, "no_constituent_stocks"
    non_formal = [f for f in stock_flows if not f.formal_grade or f.data_quality_bucket not in FORMAL_BUCKETS]
    if non_formal:
        reason = ";".join(f"{f.code}:{f.blocked_reason or f.data_quality_bucket}" for f in non_formal[:5])
        return "official_partial", False, f"topic_contains_non_formal_stock:{reason}"
    if any(f.data_quality_bucket == "official_intraday" for f in stock_flows):
        return "official_intraday", True, None
    return "official_full", True, None
