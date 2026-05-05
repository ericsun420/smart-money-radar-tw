def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def yi(value: float) -> float:
    return round(value, 2)


def concentration_label(pct: float) -> str:
    if pct < 40:
        return "low"
    if pct < 65:
        return "medium"
    if pct < 80:
        return "high"
    return "extreme_single_weight_risk"
