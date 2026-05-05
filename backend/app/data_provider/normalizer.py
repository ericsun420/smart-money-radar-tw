from __future__ import annotations

from app.storage.models import NormalizedSnapshot


def normalize_snapshot(raw: dict) -> NormalizedSnapshot:
    try:
        price_twd = float(raw["price_twd"])
        volume_shares = int(raw["volume_shares"])
        trade_value_twd = float(raw["trade_value_twd"])
    except (KeyError, TypeError, ValueError) as exc:
        return NormalizedSnapshot(
            price_twd=0,
            volume_shares=0,
            volume_lots=0,
            trade_value_twd=0,
            trade_value_yi=0,
            vwap_twd=None,
            unit_ok=False,
            unit_error=f"missing_or_invalid_unit_field:{exc}",
        )

    if price_twd <= 0 or volume_shares < 0 or trade_value_twd < 0:
        return NormalizedSnapshot(
            price_twd=price_twd,
            volume_shares=volume_shares,
            volume_lots=volume_shares / 1000,
            trade_value_twd=trade_value_twd,
            trade_value_yi=trade_value_twd / 100_000_000,
            vwap_twd=None,
            unit_ok=False,
            unit_error="non_positive_or_negative_unit_value",
        )

    return NormalizedSnapshot(
        price_twd=price_twd,
        volume_shares=volume_shares,
        volume_lots=volume_shares / 1000,
        trade_value_twd=trade_value_twd,
        trade_value_yi=trade_value_twd / 100_000_000,
        vwap_twd=(trade_value_twd / volume_shares) if volume_shares else None,
        unit_ok=True,
    )
