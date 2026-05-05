from __future__ import annotations

from .utils import clamp


def signal_level(score: int) -> str:
    if score <= 3:
        return "weak"
    if score <= 6:
        return "normal"
    if score <= 8:
        return "strong"
    return "very_strong"


def score_topic_signal(
    *,
    net_yi: float,
    delta_from_previous_yi: float,
    same_direction_count: int,
    affected_stock_count: int,
    concentration_pct: float,
    data_quality_bucket: str,
    top_stock_net_share_pct: float,
    net_near_zero: bool = False,
) -> int:
    score = 5.0
    abs_net = abs(net_yi)
    abs_delta = abs(delta_from_previous_yi)

    if abs_net >= 300:
        score += 2
    elif abs_net >= 100:
        score += 1.5
    elif abs_net >= 30:
        score += 1
    elif abs_net >= 10:
        score += 0.5

    if abs_delta >= 50:
        score += 1
    elif abs_delta >= 10:
        score += 0.5

    if same_direction_count >= 3:
        score += 1
    elif same_direction_count >= 2:
        score += 0.5

    if affected_stock_count >= 20:
        score += 1
    elif affected_stock_count >= 10:
        score += 0.5

    if 35 <= concentration_pct <= 65:
        score += 0.5
    elif concentration_pct > 80:
        score -= 0.5

    if data_quality_bucket not in {"official_full", "official_intraday"}:
        score -= 1
    if abs_net >= 30 and affected_stock_count < 3:
        score -= 1
    if top_stock_net_share_pct > 70:
        score -= 0.5
    if net_near_zero:
        score -= 0.5

    return round(clamp(score, 1, 10))
