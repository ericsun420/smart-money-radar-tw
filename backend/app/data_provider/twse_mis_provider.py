from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from app.data_provider.twse_provider import parse_number
from app.storage.models import StockSnapshot
from app.time_utils import TAIPEI_TZ, ensure_taipei, market_date, taipei_now


TWSE_MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
DEFAULT_CHUNK_SIZE = 80


def _chunked(items: list[StockSnapshot], size: int) -> list[list[StockSnapshot]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _parse_mis_time(item: dict, *, fallback_now: datetime) -> datetime | None:
    date_text = str(item.get("d") or "").strip()
    time_text = str(item.get("t") or "").strip()
    if len(date_text) != 8 or not time_text or time_text == "-":
        return None
    try:
        naive = datetime.strptime(f"{date_text} {time_text}", "%Y%m%d %H:%M:%S")
    except ValueError:
        return None
    return naive.replace(tzinfo=TAIPEI_TZ)


def _change_pct(price: float, previous_close: float) -> float:
    if previous_close <= 0:
        return 0
    return (price - previous_close) / previous_close * 100


def normalize_mis_item(item: dict, base_snapshot: StockSnapshot, *, now: datetime) -> StockSnapshot | None:
    """Overlay a TWSE MIS quote onto an official daily snapshot.

    MIS gives realtime quote and cumulative volume, but not a reliable official
    cumulative trade value field across all rows. We therefore compute trade
    value as a proxy from latest price * cumulative lots * 1000 and keep the UI
    language as estimated/proxy money flow.
    """

    now = ensure_taipei(now)
    code = str(item.get("c") or "").strip()
    if code != base_snapshot.code:
        return None

    price = parse_number(item.get("z"))
    if price <= 0:
        price = parse_number(item.get("y")) or base_snapshot.price
    if price <= 0:
        return None

    previous_close = parse_number(item.get("y")) or base_snapshot.previous_close or price
    open_price = parse_number(item.get("o")) or base_snapshot.open or price
    high = parse_number(item.get("h")) or max(price, open_price)
    low = parse_number(item.get("l")) or min(price, open_price)
    volume_lots = int(parse_number(item.get("v")))
    volume_shares = max(volume_lots, 0) * 1000
    trade_value = price * volume_shares
    market_time = _parse_mis_time(item, fallback_now=now)
    source_ts = market_time or now
    latency = max(int((now - source_ts).total_seconds()), 0)
    market = "OTC" if item.get("ex") == "otc" else "TSE"

    return base_snapshot.model_copy(
        update={
            "name": str(item.get("n") or base_snapshot.name).strip() or base_snapshot.name,
            "market": market,
            "price": price,
            "previous_close": previous_close,
            "open": open_price,
            "high": high,
            "low": low,
            "change_pct": _change_pct(price, previous_close),
            "volume": volume_shares,
            "trade_value": trade_value,
            "trade_value_yi": round(trade_value / 100_000_000, 2),
            "timestamp": now,
            "source_ts": source_ts,
            "generated_at": now,
            "market_date": market_date(source_ts),
            "market_data_time": source_ts,
            "data_latency_seconds": latency,
            "is_realtime": True,
            "is_intraday": True,
            "realtime_provider": "twse_mis",
            "data_quality_bucket": "official_intraday",
            "formal_grade": True,
            "formal_grade_label": "formal",
            "provider_type": "official_intraday",
            "source_status": "official_intraday",
            "blocked_reason": None,
            "vwap_twd": (trade_value / volume_shares) if volume_shares else None,
            "units_normalized": True,
        }
    )


async def fetch_mis_quotes_for_snapshots(
    base_snapshots: list[StockSnapshot],
    *,
    now: datetime | None = None,
    timeout: float = 8,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> tuple[list[StockSnapshot], list[str]]:
    now = ensure_taipei(now or taipei_now())
    by_code = {snapshot.code: snapshot for snapshot in base_snapshots}
    merged: dict[str, StockSnapshot] = {}
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        for chunk in _chunked(base_snapshots, chunk_size):
            ex_ch = "|".join(
                f"{'otc' if snapshot.market == 'OTC' else 'tse'}_{snapshot.code}.tw"
                for snapshot in chunk
            )
            try:
                response = await client.get(TWSE_MIS_URL, params={"ex_ch": ex_ch, "json": 1, "delay": 0})
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                errors.append(f"mis_chunk:{type(exc).__name__}")
                continue

            for item in payload.get("msgArray", []) if isinstance(payload, dict) else []:
                code = str(item.get("c") or "").strip()
                base = by_code.get(code)
                if not base:
                    continue
                normalized = normalize_mis_item(item, base, now=now)
                if normalized:
                    merged[code] = normalized

            await asyncio.sleep(0.05)

    return list(merged.values()), errors
