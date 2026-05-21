from __future__ import annotations

import asyncio
import json
from datetime import datetime

import httpx

from app.data_provider.static_universe_provider import load_static_universe
from app.data_provider.twse_provider import parse_number
from app.storage.models import StockSnapshot
from app.time_utils import TAIPEI_TZ, ensure_taipei, market_date, taipei_now


TWSE_MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
DEFAULT_CHUNK_SIZE = 20
MIN_SPLIT_CHUNK_SIZE = 5
MAX_SPLIT_DEPTH = 2
MIS_HEADERS = {
    "User-Agent": "Mozilla/5.0 SmartMoneyRadar/1.0",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://mis.twse.com.tw/stock/index.jsp",
}
STATIC_NAME_BY_CODE: dict[str, str] | None = None
KNOWN_NAME_OVERRIDES = {"2327": "國巨*"}


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


def _display_name(code: str, fallback: str) -> str:
    if code in KNOWN_NAME_OVERRIDES:
        return KNOWN_NAME_OVERRIDES[code]
    global STATIC_NAME_BY_CODE
    if STATIC_NAME_BY_CODE is None:
        STATIC_NAME_BY_CODE = {snapshot.code: snapshot.name for snapshot in load_static_universe()}
    return STATIC_NAME_BY_CODE.get(code) or fallback


def _first_book_price(value: object) -> float:
    text = str(value or "").strip()
    if not text or text == "-":
        return 0.0
    for part in text.split("_"):
        price = parse_number(part)
        if price > 0:
            return price
    return 0.0


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

    last_trade_price = parse_number(item.get("z"))
    best_ask = _first_book_price(item.get("a"))
    best_bid = _first_book_price(item.get("b"))
    limit_up = parse_number(item.get("u"))
    previous_close = parse_number(item.get("y")) or base_snapshot.previous_close or last_trade_price
    open_price = parse_number(item.get("o")) or base_snapshot.open or last_trade_price or previous_close
    high = parse_number(item.get("h")) or max(last_trade_price, open_price)
    low = parse_number(item.get("l")) or min(last_trade_price or open_price, open_price)
    price = last_trade_price
    if price <= 0 and high > 0 and limit_up > 0 and abs(high - limit_up) < 0.001:
        price = high
    if price <= 0:
        # Some active TWSE MIS rows publish the live book while z/tv are "-".
        # In that case the user-visible quote should follow the live best quote,
        # not the stale official daily/base row.
        price = best_bid or best_ask or base_snapshot.price
    if price <= 0:
        return None

    previous_close = previous_close or price
    open_price = open_price or price
    high = high or max(price, open_price)
    low = low or min(price, open_price)
    volume_lots = int(parse_number(item.get("v")))
    volume_shares = max(volume_lots, 0) * 1000
    trade_value = price * volume_shares
    market_time = _parse_mis_time(item, fallback_now=now)
    source_ts = market_time or now
    latency = max(int((now - source_ts).total_seconds()), 0)
    market = "OTC" if item.get("ex") == "otc" else "TSE"

    return base_snapshot.model_copy(
        update={
            "name": _display_name(code, base_snapshot.name),
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
    timeout: float = 5,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_concurrency: int = 4,
) -> tuple[list[StockSnapshot], list[str]]:
    now = ensure_taipei(now or taipei_now())
    by_code = {snapshot.code: snapshot for snapshot in base_snapshots}
    merged: dict[str, StockSnapshot] = {}
    errors: list[str] = []
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def fetch_chunk(
        client: httpx.AsyncClient,
        chunk: list[StockSnapshot],
        *,
        split_depth: int = 0,
    ) -> tuple[list[StockSnapshot], list[str]]:
        ex_ch = "|".join(
            f"{'otc' if snapshot.market == 'OTC' else 'tse'}_{snapshot.code}.tw"
            for snapshot in chunk
        )
        try:
            async with semaphore:
                response = await client.get(
                    TWSE_MIS_URL,
                    params={"ex_ch": ex_ch, "json": 1, "delay": 0},
                    headers=MIS_HEADERS,
                )
            response.raise_for_status()
            payload = response.json()
        except (json.JSONDecodeError, httpx.RemoteProtocolError) as exc:
            if len(chunk) > MIN_SPLIT_CHUNK_SIZE and split_depth < MAX_SPLIT_DEPTH:
                midpoint = len(chunk) // 2
                (left, left_errors), (right, right_errors) = await asyncio.gather(
                    fetch_chunk(client, chunk[:midpoint], split_depth=split_depth + 1),
                    fetch_chunk(client, chunk[midpoint:], split_depth=split_depth + 1),
                )
                return [*left, *right], [*left_errors, *right_errors, f"mis_chunk_split:{type(exc).__name__}:{len(chunk)}"]
            return [], [f"mis_chunk:{type(exc).__name__}:{chunk[0].code}"]
        except httpx.HTTPError as exc:
            # Network timeouts on Render should fail the chunk quickly. Splitting
            # every timed-out chunk down to single symbols can make startup scan
            # take minutes and leave the app empty.
            return [], [f"mis_chunk:{type(exc).__name__}:{len(chunk)}"]
        except Exception as exc:
            if len(chunk) > MIN_SPLIT_CHUNK_SIZE and split_depth < MAX_SPLIT_DEPTH:
                midpoint = len(chunk) // 2
                (left, left_errors), (right, right_errors) = await asyncio.gather(
                    fetch_chunk(client, chunk[:midpoint], split_depth=split_depth + 1),
                    fetch_chunk(client, chunk[midpoint:], split_depth=split_depth + 1),
                )
                return [*left, *right], [*left_errors, *right_errors, f"mis_chunk_split:{type(exc).__name__}:{len(chunk)}"]
            return [], [f"mis_chunk:{type(exc).__name__}:{chunk[0].code}"]

        snapshots: list[StockSnapshot] = []
        for item in payload.get("msgArray", []) if isinstance(payload, dict) else []:
            code = str(item.get("c") or "").strip()
            base = by_code.get(code)
            if not base:
                continue
            normalized = normalize_mis_item(item, base, now=now)
            if normalized:
                snapshots.append(normalized)
        return snapshots, []

    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [fetch_chunk(client, chunk) for chunk in _chunked(base_snapshots, chunk_size)]
        for chunk_snapshots, chunk_errors in await asyncio.gather(*tasks):
            errors.extend(chunk_errors)
            for normalized in chunk_snapshots:
                merged[normalized.code] = normalized

    return list(merged.values()), errors
