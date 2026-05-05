from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import median

from app.engine.quality import topic_quality
from app.storage.models import ImpactStock, StockFlow, TopicFlow, TopicState
from .score_engine import score_topic_signal, signal_level
from .utils import yi


def topic_direction(net_yi: float) -> str:
    if net_yi > 0:
        return "INFLOW"
    if net_yi < 0:
        return "OUTFLOW"
    return "NEUTRAL"


def next_topic_state(topic_name: str, direction: str, previous: TopicState | None, *, net_yi: float, abs_total_yi: float, formal_grade: bool, data_quality_bucket: str) -> TopicState:
    if direction == "NEUTRAL":
        count = previous.same_direction_count if previous else 0
    elif previous and previous.last_direction == direction:
        count = previous.same_direction_count + 1
    else:
        count = 1
    return TopicState(
        topic_name=topic_name,
        last_direction=direction,
        same_direction_count=count,
        last_net_yi=yi(net_yi),
        last_abs_total_yi=yi(abs_total_yi),
        last_emit_at=previous.last_emit_at if previous else None,
        last_formal_grade=formal_grade,
        last_data_quality_bucket=data_quality_bucket,
    )


def trimmed_sum(values: list[float], trim_ratio: float = 0.1) -> float:
    if len(values) < 5:
        return sum(values)
    ordered = sorted(values)
    trim_count = max(1, int(len(ordered) * trim_ratio))
    if trim_count * 2 >= len(ordered):
        return sum(ordered)
    return sum(ordered[trim_count:-trim_count])


def aggregate_topics(
    stock_flows: list[StockFlow],
    *,
    timestamp: datetime,
    topic_states: dict[str, TopicState] | None = None,
    net_near_zero_ratio: float = 0.08,
) -> tuple[list[TopicFlow], dict[str, TopicState]]:
    grouped: dict[str, list[tuple[str, StockFlow]]] = defaultdict(list)
    for flow in stock_flows:
        industry = flow.official_industry or flow.industry
        topics = ([] if industry in {"", "Unclassified", "未分類"} else [industry]) + list(flow.themes)
        for topic in dict.fromkeys([t for t in topics if t and t not in {"Unclassified", "未分類"}]):
            topic_type = "industry" if topic == industry else "theme"
            grouped[topic].append((topic_type, flow))

    results: list[TopicFlow] = []
    next_states: dict[str, TopicState] = dict(topic_states or {})
    for topic, rows in grouped.items():
        flows = [f for _, f in rows]
        inflow = sum(abs(f.display_signed_flow_yi) for f in flows if f.direction == "INFLOW")
        outflow = sum(abs(f.display_signed_flow_yi) for f in flows if f.direction == "OUTFLOW")
        delta_inflow = sum(abs(f.delta_signed_flow_yi) for f in flows if f.direction == "INFLOW")
        delta_outflow = sum(abs(f.delta_signed_flow_yi) for f in flows if f.direction == "OUTFLOW")
        net = inflow - outflow
        delta_net = delta_inflow - delta_outflow
        abs_total = inflow + outflow
        direction = topic_direction(net)
        previous_state = (topic_states or {}).get(topic)
        bucket, formal, blocked_reason = topic_quality(flows)
        net_near_zero = abs_total > 0 and abs(net) / abs_total < net_near_zero_ratio
        sorted_impacts = sorted((f for f in flows if f.direction != "NEUTRAL"), key=lambda f: abs(f.display_signed_flow_yi), reverse=True)
        top5 = sorted_impacts[:5]
        concentration = (sum(abs(f.display_signed_flow_yi) for f in top5) / abs_total * 100) if abs_total else 0
        top_stock_share = (abs(top5[0].display_signed_flow_yi) / abs(net) * 100) if top5 and net else 0
        top1_signed = sorted_impacts[0].display_signed_flow_yi if sorted_impacts else 0
        top1_contribution_pct = (abs(top1_signed) / abs(net) * 100) if net else 0
        top_stock_concentration = (abs(top1_signed) / abs_total * 100) if abs_total else 0
        ex_top1_net = net - top1_signed if sorted_impacts else net
        median_delta = median([f.delta_signed_flow_yi for f in sorted_impacts]) if sorted_impacts else 0
        signed_display_values = [f.display_signed_flow_yi for f in sorted_impacts]
        median_flow = median(signed_display_values) if signed_display_values else 0
        trimmed_net = trimmed_sum(signed_display_values)
        strong_count = sum(1 for f in flows if f.direction == "INFLOW")
        weak_count = sum(1 for f in flows if f.direction == "OUTFLOW")
        up_count = sum(1 for f in flows if f.change_pct > 0)
        down_count = sum(1 for f in flows if f.change_pct < 0)
        next_state = next_topic_state(
            topic,
            direction,
            previous_state,
            net_yi=net,
            abs_total_yi=abs_total,
            formal_grade=formal,
            data_quality_bucket=bucket,
        )
        next_states[topic] = next_state
        impacts = [
            ImpactStock(
                code=f.code,
                name=f.name,
                price=f.price,
                change_pct=f.change_pct,
                direction=f.direction,
                signed_flow_yi=f.display_signed_flow_yi,
                display_signed_flow_yi=f.display_signed_flow_yi,
                stock_flow_proxy_amount=f.display_signed_flow_yi,
                delta_signed_flow_yi=f.delta_signed_flow_yi,
                previous_delta_proxy_amount=f.delta_signed_flow_yi,
                value_delta_yi=f.value_delta_yi,
                impact_pct=yi(abs(f.display_signed_flow_yi) / abs(net) * 100) if net else 0,
                contribution_ratio=(abs(f.display_signed_flow_yi) / abs(net)) if net else 0,
            )
            for f in top5
        ]
        score = score_topic_signal(
            net_yi=net,
            delta_from_previous_yi=delta_net,
            same_direction_count=next_state.same_direction_count,
            affected_stock_count=len(sorted_impacts),
            concentration_pct=concentration,
            data_quality_bucket=bucket,
            top_stock_net_share_pct=top_stock_share,
            net_near_zero=net_near_zero,
        )
        results.append(
            TopicFlow(
                topic_name=topic,
                topic_type="industry" if rows[0][0] == "industry" else "theme",
                inflow_yi=yi(inflow),
                outflow_yi=yi(outflow),
                net_yi=yi(net),
                delta_inflow_yi=yi(delta_inflow),
                delta_outflow_yi=yi(delta_outflow),
                delta_net_yi=yi(delta_net),
                abs_total_yi=yi(abs_total),
                direction=direction,
                concentration_pct=yi(concentration),
                top_impacts=impacts,
                signal_score=score,
                signal_level=signal_level(score),
                timestamp=timestamp,
                data_quality_bucket=bucket,
                formal_grade=formal,
                blocked_reason=blocked_reason,
                affected_stock_count=len(sorted_impacts),
                same_direction_count=next_state.same_direction_count,
                net_near_zero=net_near_zero,
                strong_stock_count=strong_count,
                weak_stock_count=weak_count,
                top1_contribution_pct=yi(top1_contribution_pct),
                ex_top1_net_yi=yi(ex_top1_net),
                median_delta_flow_yi=yi(median_delta),
                up_count=up_count,
                down_count=down_count,
                median_flow_yi=yi(median_flow),
                trimmed_net_flow_yi=yi(trimmed_net),
                top_stock_concentration_pct=yi(top_stock_concentration),
            )
        )
    return results, next_states
