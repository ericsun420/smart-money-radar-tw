from __future__ import annotations

from .utils import yi
from app.storage.models import Direction, StockFlow, StockSnapshot


def intraday_vwap(snapshot: StockSnapshot) -> float | None:
    if snapshot.vwap_twd is not None:
        return snapshot.vwap_twd
    if not snapshot.units_normalized or snapshot.volume <= 0:
        return None
    return snapshot.trade_value / max(snapshot.volume, 1)


def infer_direction(
    current: StockSnapshot,
    previous: StockSnapshot | None,
    previous_flow: StockFlow | None,
    *,
    min_value_delta_yi: float,
) -> StockFlow:
    prev_price = previous.price if previous else current.previous_close
    prev_value = previous.trade_value_yi if previous else 0
    prev_volume = previous.volume if previous else 0
    price_delta = current.price - prev_price
    value_delta_yi = max(current.trade_value_yi - prev_value, 0)
    volume_delta = current.volume - prev_volume
    short_return_pct = (price_delta / prev_price * 100) if prev_price else 0
    direction: Direction = "NEUTRAL"
    reason = "insufficient_delta"

    if value_delta_yi > min_value_delta_yi and price_delta > 0:
        direction, reason = "INFLOW", "price_up_with_value_delta"
    elif value_delta_yi > min_value_delta_yi and price_delta < 0:
        direction, reason = "OUTFLOW", "price_down_with_value_delta"
    elif price_delta == 0:
        vwap = intraday_vwap(current)
        if vwap and current.price > vwap and current.change_pct > 0:
            direction, reason = "INFLOW", "flat_price_above_vwap_positive_day"
        elif vwap and current.price < vwap and current.high > current.price:
            direction, reason = "OUTFLOW", "flat_price_below_vwap_pullback"
        elif previous_flow:
            direction, reason = previous_flow.direction, "carry_forward_due_to_flat_price"

    if current.blocked_reason and direction == "NEUTRAL":
        reason = current.blocked_reason

    display_signed = current.trade_value_yi if direction == "INFLOW" else -current.trade_value_yi if direction == "OUTFLOW" else 0
    delta_signed = value_delta_yi if direction == "INFLOW" else -value_delta_yi if direction == "OUTFLOW" else 0
    return StockFlow(
        code=current.code,
        name=current.name,
        price=current.price,
        change_pct=current.change_pct,
        trade_value_yi=yi(current.trade_value_yi),
        direction=direction,
        signed_flow_yi=yi(display_signed),
        display_signed_flow_yi=yi(display_signed),
        delta_signed_flow_yi=yi(delta_signed),
        direction_reason=reason,
        prev_price=prev_price,
        price_delta=yi(price_delta),
        short_return_pct=yi(short_return_pct),
        volume_delta=volume_delta,
        value_delta_yi=yi(value_delta_yi),
        timestamp=current.timestamp,
        themes=current.themes,
        industry=current.industry,
        official_industry=current.official_industry or current.industry,
        primary_theme=current.primary_theme,
        industry_display_name=current.industry_display_name or current.official_industry or current.industry,
        data_quality_bucket=current.data_quality_bucket,
        formal_grade=current.formal_grade,
        blocked_reason=current.blocked_reason,
        trade_date=current.market_date,
        quote_time=current.market_data_time or current.source_ts or current.timestamp,
        last_price=current.price,
        change=yi(current.price - current.previous_close),
        turnover=yi(current.trade_value_yi),
        flow_direction=direction,
        flow_amount=yi(display_signed),
        data_source=current.realtime_provider or current.provider_type,
    )
