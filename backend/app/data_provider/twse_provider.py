from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO

import httpx

from app.storage.models import StockSnapshot
from app.time_utils import ensure_taipei, market_date


TWSE_STOCK_DAY_ALL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TWSE_STOCK_DAY_ALL_JSON_CANDIDATES = [
    "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json",
    "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json",
]
TWSE_STOCK_DAY_ALL_CSV_CANDIDATES = [
    "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=open_data",
]
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 SmartMoneyRadar/1.0",
    "Accept": "application/json,text/csv,text/plain,*/*",
    "Referer": "https://www.twse.com.tw/",
}


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


def _normalize_twse_csv_row(row: dict) -> dict:
    return {
        "Code": row.get("證券代號"),
        "Name": row.get("證券名稱"),
        "TradeVolume": row.get("成交股數"),
        "TradeValue": row.get("成交金額"),
        "OpeningPrice": row.get("開盤價"),
        "HighestPrice": row.get("最高價"),
        "LowestPrice": row.get("最低價"),
        "ClosingPrice": row.get("收盤價"),
        "Change": row.get("漲跌價差"),
        "Industry": "Unclassified",
    }


def _normalize_twse_json_record(fields: list[str], values: list) -> dict:
    row = dict(zip(fields, values))
    return _normalize_twse_csv_row(row)


def _http_error_label(prefix: str, exc: Exception) -> str:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code:
        return f"{prefix}:HTTPStatusError:{status_code}"
    return f"{prefix}:{type(exc).__name__}"


async def fetch_twse_daily_all(timeout: float = 12) -> list[dict]:
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(TWSE_STOCK_DAY_ALL, headers=HTTP_HEADERS)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            errors.append("openapi_not_list")
        except Exception as exc:
            errors.append(_http_error_label("openapi", exc))

        for url in TWSE_STOCK_DAY_ALL_JSON_CANDIDATES:
            try:
                response = await client.get(url, headers=HTTP_HEADERS)
                response.raise_for_status()
                payload = response.json()
                fields = payload.get("fields") if isinstance(payload, dict) else None
                records = payload.get("data") if isinstance(payload, dict) else None
                if fields and isinstance(records, list):
                    return [_normalize_twse_json_record(fields, values) for values in records]
                errors.append(f"json_unexpected_shape:{url}")
            except Exception as exc:
                errors.append(_http_error_label(f"json:{url}", exc))

        for url in TWSE_STOCK_DAY_ALL_CSV_CANDIDATES:
            try:
                response = await client.get(url, headers=HTTP_HEADERS)
                response.raise_for_status()
                rows = list(csv.DictReader(StringIO(response.text)))
                if rows:
                    return [_normalize_twse_csv_row(row) for row in rows]
                errors.append(f"csv_empty:{url}")
            except Exception as exc:
                errors.append(_http_error_label(f"csv:{url}", exc))

    raise RuntimeError(";".join(errors) or "twse_daily_all_unavailable")


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
