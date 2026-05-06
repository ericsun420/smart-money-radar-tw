from __future__ import annotations

import json
import re
from datetime import datetime

import httpx

from app.storage.models import ProviderResult, StockSnapshot
from app.time_utils import TAIPEI_TZ, ensure_taipei, market_date, taipei_now


MCP_URL = "https://TW-Stock-MCP-Server.fastmcp.app/mcp"
QUOTE_LINE_RE = re.compile(
    r"^(?P<code>\d{4})\s+(?P<name>.+?)\s+\[(?P<market>上市|上櫃)\]\s+\|\s+"
    r"成交:\s+(?P<price>[\d.]+|-)\s+\|\s+開:\s+(?P<open>[\d.]+|-)\s+\|\s+"
    r"高:\s+(?P<high>[\d.]+|-)\s+\|\s+低:\s+(?P<low>[\d.]+|-)\s+\|\s+"
    r"昨收:\s+(?P<prev>[\d.]+|-)\s+\|\s+量:\s+(?P<volume>\d+|-)"
    r"張.*\|\s+(?P<date>\d{8})\s+(?P<time>\d{2}:\d{2}:\d{2})"
)


def _num(value: str | None) -> float:
    if not value or value == "-":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _parse_time(date_text: str, time_text: str) -> datetime:
    return datetime.strptime(f"{date_text} {time_text}", "%Y%m%d %H:%M:%S").replace(tzinfo=TAIPEI_TZ)


def _extract_sse_json(text: str) -> dict:
    lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
    if not lines:
        return {}
    return json.loads("\n".join(lines))


async def _mcp_post(client: httpx.AsyncClient, payload: dict, session_id: str | None = None) -> tuple[str | None, dict]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "User-Agent": "SmartMoneyRadar/1.0",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    response = await client.post(MCP_URL, json=payload, headers=headers)
    response.raise_for_status()
    return response.headers.get("mcp-session-id") or session_id, _extract_sse_json(response.text)


async def _mcp_session(client: httpx.AsyncClient) -> str:
    session_id, _ = await _mcp_post(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "smart-money-radar", "version": "1.0"},
            },
        },
    )
    if not session_id:
        raise RuntimeError("mcp_session_missing")
    await _mcp_post(client, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
    return session_id


def _chunked(items: list[StockSnapshot], size: int) -> list[list[StockSnapshot]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _merge_quote(line: str, base_by_code: dict[str, StockSnapshot], *, now: datetime) -> StockSnapshot | None:
    match = QUOTE_LINE_RE.match(line.strip())
    if not match:
        return None
    data = match.groupdict()
    code = data["code"]
    base = base_by_code.get(code)
    if not base:
        return None
    price = _num(data["price"])
    previous_close = _num(data["prev"]) or base.previous_close or price
    if price <= 0 or previous_close <= 0:
        return None
    volume_lots = int(_num(data["volume"]))
    volume_shares = volume_lots * 1000
    trade_value = price * volume_shares
    source_ts = _parse_time(data["date"], data["time"])
    latency = max(int((now - source_ts).total_seconds()), 0)
    return base.model_copy(
        update={
            "name": data["name"].strip() or base.name,
            "market": "TSE" if data["market"] == "上市" else "OTC",
            "price": price,
            "previous_close": previous_close,
            "open": _num(data["open"]) or price,
            "high": _num(data["high"]) or price,
            "low": _num(data["low"]) or price,
            "change_pct": (price - previous_close) / previous_close * 100,
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
            "realtime_provider": "twse_mcp_proxy",
            "data_quality_bucket": "official_partial",
            "formal_grade": False,
            "formal_grade_label": "estimated",
            "provider_type": "official_partial",
            "source_status": "official",
            "blocked_reason": "mcp_realtime_proxy_observation_mode",
            "vwap_twd": (trade_value / volume_shares) if volume_shares else None,
            "units_normalized": True,
        }
    )


async def fetch_mcp_realtime_quotes(base_snapshots: list[StockSnapshot], *, now: datetime | None = None, chunk_size: int = 80) -> ProviderResult:
    now = ensure_taipei(now or taipei_now())
    base_by_code = {snapshot.code: snapshot for snapshot in base_snapshots}
    merged: dict[str, StockSnapshot] = {}
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=45) as client:
        session_id = await _mcp_session(client)
        request_id = 10
        for chunk in _chunked(base_snapshots, chunk_size):
            request_id += 1
            try:
                _, payload = await _mcp_post(
                    client,
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {
                            "name": "get_realtime_quote",
                            "arguments": {"stock_nos": [snapshot.code for snapshot in chunk]},
                        },
                    },
                    session_id,
                )
                text = (
                    payload.get("result", {})
                    .get("structuredContent", {})
                    .get("result", "")
                )
                for line in text.splitlines():
                    snapshot = _merge_quote(line, base_by_code, now=now)
                    if snapshot:
                        merged[snapshot.code] = snapshot
            except Exception as exc:
                errors.append(f"mcp_quote_chunk:{type(exc).__name__}")

    snapshots = list(merged.values())
    market_data_time = max((s.market_data_time or s.source_ts or s.timestamp for s in snapshots), default=now)
    return ProviderResult(
        snapshots=snapshots,
        source_used="twse_mcp_realtime_proxy",
        source_status="official_partial",
        source_ts=market_data_time,
        market_data_time=market_data_time,
        data_latency_seconds=max(int((now - market_data_time).total_seconds()), 0),
        is_realtime=False,
        is_intraday=False,
        realtime_provider="twse_mcp_proxy",
        twse_count=sum(1 for s in snapshots if s.market == "TSE"),
        tpex_count=sum(1 for s in snapshots if s.market == "OTC"),
        realtime_count=len(snapshots),
        excluded_count=max(len(base_snapshots) - len(snapshots), 0),
        errors=errors,
    )
