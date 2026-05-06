from __future__ import annotations

import json
from pathlib import Path

from app.storage.models import StockSnapshot
from app.time_utils import taipei_now


STATIC_UNIVERSE_PATH = Path(__file__).with_name("static_universe.json")


def load_static_universe() -> list[StockSnapshot]:
    if not STATIC_UNIVERSE_PATH.exists():
        return []
    payload = json.loads(STATIC_UNIVERSE_PATH.read_text(encoding="utf-8"))
    now = taipei_now()
    snapshots: list[StockSnapshot] = []
    for row in payload.get("stocks", []):
        price = float(row.get("price") or row.get("previous_close") or 0)
        previous_close = float(row.get("previous_close") or price or 0)
        snapshots.append(
            StockSnapshot(
                code=str(row.get("code") or ""),
                name=str(row.get("name") or ""),
                market=str(row.get("market") or "TSE"),
                industry=str(row.get("industry") or "Unclassified"),
                official_industry=str(row.get("official_industry") or row.get("industry") or "Unclassified"),
                primary_theme=row.get("primary_theme"),
                industry_display_name=row.get("industry_display_name"),
                themes=list(row.get("themes") or []),
                price=price,
                previous_close=previous_close,
                open=float(row.get("open") or price or 0),
                high=float(row.get("high") or price or 0),
                low=float(row.get("low") or price or 0),
                change_pct=((price - previous_close) / previous_close * 100) if previous_close else 0,
                volume=int(row.get("volume") or 0),
                trade_value=float(row.get("trade_value") or 0),
                trade_value_yi=float(row.get("trade_value_yi") or 0),
                timestamp=now,
                source_ts=now,
                generated_at=now,
                market_date=None,
                data_quality_bucket="cache_only",
                formal_grade=False,
                formal_grade_label="cache",
                provider_type="cache_only",
                source_status="cache",
                blocked_reason="static_universe_for_mcp_proxy",
                units_normalized=True,
            )
        )
    return [snapshot for snapshot in snapshots if snapshot.code and snapshot.name]
