from __future__ import annotations

from datetime import datetime

import httpx

from app.storage.models import StockSnapshot
from app.time_utils import ensure_taipei, market_date
from .twse_provider import parse_change, parse_number


TPEX_OPENAPI_CANDIDATES = [
    "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
]


async def fetch_tpex_daily_all(timeout: float = 12) -> list[dict]:
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for url in TPEX_OPENAPI_CANDIDATES:
            try:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, list):
                    return data
            except Exception as exc:
                errors.append(f"{url}:{type(exc).__name__}")
    raise RuntimeError(";".join(errors) or "No TPEx candidate endpoint returned list JSON")


def normalize_tpex_row(row: dict, *, now: datetime) -> StockSnapshot | None:
    now = ensure_taipei(now)
    code = str(row.get("SecuritiesCompanyCode") or row.get("Code") or row.get("代號") or row.get("股票代號") or "").strip()
    name = str(row.get("CompanyName") or row.get("Name") or row.get("名稱") or row.get("股票名稱") or "").strip()
    if not code or not name:
        return None
    price = parse_number(row.get("Close") or row.get("ClosingPrice") or row.get("收盤") or row.get("收盤價"))
    change = parse_change(row.get("Change") or row.get("漲跌") or row.get("漲跌價差"))
    previous_close = price - change if price else 0
    trade_value = parse_number(
        row.get("TransactionAmount")
        or row.get("TradingAmount")
        or row.get("TradeValue")
        or row.get("成交金額")
    )
    volume = int(parse_number(row.get("TradingShares") or row.get("TradeVolume") or row.get("成交股數")))
    if price <= 0 or trade_value <= 0:
        return None
    industry = str(row.get("Industry") or row.get("產業別") or "Unclassified").strip() or "Unclassified"
    bucket = "official_partial"
    return StockSnapshot(
        code=code,
        name=name,
        market="OTC",
        industry=industry,
        themes=[industry],
        price=price,
        previous_close=previous_close,
        open=parse_number(row.get("Open") or row.get("OpeningPrice") or row.get("開盤")) or price,
        high=parse_number(row.get("High") or row.get("HighestPrice") or row.get("最高")) or price,
        low=parse_number(row.get("Low") or row.get("LowestPrice") or row.get("最低")) or price,
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
        blocked_reason="tpex_daily_quote_is_not_intraday_full",
        vwap_twd=(trade_value / volume) if volume else None,
        units_normalized=True,
    )
