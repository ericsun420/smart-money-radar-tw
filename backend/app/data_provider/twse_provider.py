from __future__ import annotations

from datetime import datetime

import httpx

from app.storage.models import StockSnapshot
from app.time_utils import ensure_taipei, market_date


TWSE_STOCK_DAY_ALL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"


def parse_number(value) -> float:
    text = str(value or "0").replace(",", "").replace("--", "0").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_change(value) -> float:
    text = str(value or "0").replace(",", "").strip()
    text = text.replace("+", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


async def fetch_twse_daily_all(timeout: float = 12) -> list[dict]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(TWSE_STOCK_DAY_ALL)
        response.raise_for_status()
        return response.json()


def normalize_twse_row(row: dict, *, now: datetime) -> StockSnapshot | None:
    now = ensure_taipei(now)
    code = str(row.get("Code") or row.get("證券代號") or "").strip()
    name = str(row.get("Name") or row.get("證券名稱") or "").strip()
    if not code or not name:
        return None
    price = parse_number(row.get("ClosingPrice") or row.get("收盤價"))
    change = parse_change(row.get("Change") or row.get("漲跌價差"))
    previous_close = price - change if price else 0
    trade_value = parse_number(row.get("TradeValue") or row.get("成交金額"))
    volume = int(parse_number(row.get("TradeVolume") or row.get("成交股數")))
    industry = str(row.get("Industry") or row.get("產業別") or "Unclassified").strip() or "Unclassified"
    bucket = "official_partial"
    return StockSnapshot(
        code=code,
        name=name,
        market="TSE",
        industry=industry,
        themes=[industry],
        price=price,
        previous_close=previous_close,
        open=parse_number(row.get("OpeningPrice") or row.get("開盤價")) or price,
        high=parse_number(row.get("HighestPrice") or row.get("最高價")) or price,
        low=parse_number(row.get("LowestPrice") or row.get("最低價")) or price,
        change_pct=(change / previous_close * 100) if previous_close else 0,
        volume=volume,
        trade_value=trade_value,
        trade_value_yi=round(trade_value / 100_000_000, 2),
        timestamp=now,
        source_ts=now,
        generated_at=now,
        market_date=market_date(now),
        data_quality_bucket=bucket,
        formal_grade=False,
        formal_grade_label="estimated",
        provider_type=bucket,
        source_status="official",
        blocked_reason="twse_stock_day_all_is_not_intraday_full",
        vwap_twd=(trade_value / volume) if volume else None,
        units_normalized=True,
    )
