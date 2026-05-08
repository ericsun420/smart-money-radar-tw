from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from app.storage.models import Settings, SignalEvent, StockFlow, TopicFlow, TopicState
from app.time_utils import ensure_taipei, market_date


def signal_fingerprint(*, target_id: str, signal_level: str, formal_grade: bool, market_date_value: str | None, event_type: str, source_ts) -> str:
    source = source_ts.isoformat() if source_ts else "unknown_source_ts"
    return f"{target_id}|{signal_level}|formal={formal_grade}|date={market_date_value or 'unknown_date'}|event={event_type}|source_ts={source}"


def topic_blocked_reason(topic: TopicFlow) -> str | None:
    if not topic.formal_grade:
        return topic.blocked_reason or f"topic_not_formal:{topic.data_quality_bucket}"
    if topic.data_quality_bucket not in {"official_full", "official_intraday"}:
        return f"topic_data_quality_not_formal:{topic.data_quality_bucket}"
    return None


def should_emit_topic_signal(topic: TopicFlow, previous_state: TopicState | None, recent: SignalEvent | None, settings: Settings) -> tuple[bool, str | None]:
    blocked = topic_blocked_reason(topic)
    if blocked:
        return False, blocked
    if abs(topic.net_yi) < settings.topic_min_net_yi:
        return False, "below_topic_min_net_yi"
    reversal = previous_state is not None and previous_state.last_direction not in {"NEUTRAL", topic.direction} and topic.direction != "NEUTRAL"
    if recent and recent.direction == topic.direction:
        within_cooldown = ensure_taipei(topic.timestamp) - ensure_taipei(recent.timestamp) <= timedelta(minutes=10)
        if within_cooldown and abs(topic.delta_net_yi) < settings.repeat_delta_yi:
            return False, "cooldown_repeat_delta_not_met"
    if not reversal and abs(topic.delta_net_yi) < settings.topic_min_delta_yi:
        return False, "below_topic_min_delta_yi"
    return True, None


def build_topic_signal(topic: TopicFlow, previous_state: TopicState | None, *, blocked_reason: str | None = None) -> SignalEvent:
    prev_net = previous_state.last_net_yi if previous_state else 0
    delta = topic.delta_net_yi
    verb = "inflow" if topic.direction == "INFLOW" else "outflow" if topic.direction == "OUTFLOW" else "neutral"
    formal = blocked_reason is None and topic.formal_grade
    event_type = "topic_reversal" if previous_state and previous_state.last_direction not in {"NEUTRAL", topic.direction} else "topic_flow"
    market_date_value = market_date(topic.timestamp)
    source_ts = max((impact.quote_time for impact in topic.top_impacts if impact.quote_time), default=topic.timestamp)
    fingerprint = signal_fingerprint(
        target_id=topic.topic_name,
        signal_level=topic.signal_level,
        formal_grade=formal,
        market_date_value=market_date_value,
        event_type=event_type,
        source_ts=source_ts,
    )
    return SignalEvent(
        id=str(uuid4()),
        timestamp=topic.timestamp,
        target_type="topic",
        target_id=topic.topic_name,
        event_type=event_type,
        fingerprint=fingerprint,
        market_date=market_date_value,
        source_ts=source_ts,
        topic_name=topic.topic_name,
        direction=topic.direction,
        amount_yi=abs(topic.net_yi),
        net_yi=topic.net_yi,
        previous_net_yi=prev_net,
        delta_from_previous_yi=delta,
        score=topic.signal_score,
        signal_level=topic.signal_level,
        message=f"{topic.signal_level} topic {topic.topic_name} {verb} score={topic.signal_score}",
        related_stocks=topic.top_impacts,
        top_impacts_snapshot=topic.top_impacts,
        topic_net_yi_at_emit=topic.net_yi,
        topic_delta_net_yi_at_emit=topic.delta_net_yi,
        topic_inflow_yi_at_emit=topic.inflow_yi,
        topic_outflow_yi_at_emit=topic.outflow_yi,
        data_quality_bucket_at_emit=topic.data_quality_bucket,
        formal_grade_at_emit=formal,
        blocked_reason_at_emit=blocked_reason,
        data_quality_bucket=topic.data_quality_bucket,
        formal_grade=formal,
        blocked_reason=blocked_reason,
        is_formal_push_allowed=formal,
        explain_flags=[flag for flag in [blocked_reason, "net_near_zero" if topic.net_near_zero else None] if flag],
    )


def should_emit_stock_signal(flow: StockFlow, top_impact_codes: set[str], recent: SignalEvent | None, settings: Settings) -> tuple[bool, str | None]:
    if not settings.stock_signal_enabled:
        return False, "stock_signal_disabled"
    if not flow.formal_grade or flow.data_quality_bucket not in {"official_full", "official_intraday"}:
        return False, flow.blocked_reason or f"stock_data_quality_not_formal:{flow.data_quality_bucket}"
    if flow.direction == "NEUTRAL":
        return False, "neutral_direction"
    if recent and recent.direction == flow.direction and ensure_taipei(flow.timestamp) - ensure_taipei(recent.timestamp) <= timedelta(minutes=10):
        if abs(flow.delta_signed_flow_yi) < settings.stock_min_delta_yi:
            return False, "stock_cooldown_delta_not_met"
    if flow.code in top_impact_codes:
        return True, None
    if flow.trade_value_yi >= settings.stock_min_value_yi and abs(flow.delta_signed_flow_yi) >= settings.stock_min_delta_yi:
        return True, None
    return False, "below_stock_signal_threshold"


def build_stock_signal(flow: StockFlow, *, blocked_reason: str | None = None) -> SignalEvent:
    formal = blocked_reason is None and flow.formal_grade
    verb = "inflow" if flow.direction == "INFLOW" else "outflow" if flow.direction == "OUTFLOW" else "neutral"
    event_type = "stock_flow"
    market_date_value = market_date(flow.timestamp)
    source_ts = flow.quote_time or flow.timestamp
    fingerprint = signal_fingerprint(
        target_id=flow.code,
        signal_level="normal",
        formal_grade=formal,
        market_date_value=market_date_value,
        event_type=event_type,
        source_ts=source_ts,
    )
    return SignalEvent(
        id=str(uuid4()),
        timestamp=flow.timestamp,
        target_type="stock",
        target_id=flow.code,
        event_type=event_type,
        fingerprint=fingerprint,
        market_date=market_date_value,
        source_ts=source_ts,
        direction=flow.direction,
        amount_yi=abs(flow.display_signed_flow_yi),
        net_yi=flow.display_signed_flow_yi,
        previous_net_yi=flow.display_signed_flow_yi - flow.delta_signed_flow_yi,
        delta_from_previous_yi=flow.delta_signed_flow_yi,
        price=flow.price,
        change_pct=flow.change_pct,
        score=5,
        signal_level="normal",
        message=f"stock {flow.code} {flow.name} {verb}",
        related_stocks=[],
        stock_price_at_emit=flow.price,
        stock_change_pct_at_emit=flow.change_pct,
        stock_amount_yi_at_emit=abs(flow.display_signed_flow_yi),
        data_quality_bucket_at_emit=flow.data_quality_bucket,
        formal_grade_at_emit=formal,
        blocked_reason_at_emit=blocked_reason,
        data_quality_bucket=flow.data_quality_bucket,
        formal_grade=formal,
        blocked_reason=blocked_reason,
        direction_reason=flow.direction_reason,
        is_formal_push_allowed=formal,
        explain_flags=[flag for flag in [blocked_reason, flow.direction_reason] if flag],
    )
