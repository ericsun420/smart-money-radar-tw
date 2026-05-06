from __future__ import annotations

import asyncio
import os

from app.data_provider.mcp_realtime_provider import fetch_mcp_realtime_quotes
from app.data_provider.seed_data import build_seed_snapshots
from app.data_provider.static_universe_provider import load_static_universe
from app.data_provider.stock_universe import filter_common_stocks
from app.data_provider.theme_mapping import apply_theme_mappings
from app.data_provider.tpex_provider import fetch_tpex_daily_all, normalize_tpex_row
from app.data_provider.twse_mis_provider import fetch_mis_quotes_for_snapshots
from app.data_provider.twse_provider import fetch_twse_daily_all, normalize_twse_row
from app.storage.models import ProviderResult, StockSnapshot
from app.time_utils import is_regular_tw_session, market_date, taipei_now


REALTIME_STALE_SECONDS = 600


async def fetch_official_snapshots_async() -> ProviderResult:
    now = taipei_now()
    errors: list[str] = []
    twse_snapshots: list[StockSnapshot] = []
    tpex_snapshots: list[StockSnapshot] = []

    try:
        twse_rows = await fetch_twse_daily_all()
        twse_snapshots = [s for row in twse_rows if (s := normalize_twse_row(row, now=now))]
    except Exception as exc:
        errors.append(f"twse:{type(exc).__name__}")

    try:
        tpex_rows = await fetch_tpex_daily_all()
        tpex_snapshots = [s for row in tpex_rows if (s := normalize_tpex_row(row, now=now))]
    except Exception as exc:
        errors.append(f"tpex:{type(exc).__name__}")

    daily_snapshots, excluded_count = filter_common_stocks([*twse_snapshots, *tpex_snapshots])
    daily_snapshots = apply_theme_mappings(daily_snapshots)
    realtime_snapshots: list[StockSnapshot] = []
    realtime_errors: list[str] = []
    if daily_snapshots:
        realtime_snapshots, realtime_errors = await fetch_mis_quotes_for_snapshots(daily_snapshots, now=now)
        errors.extend(realtime_errors)

    realtime_ratio = (len(realtime_snapshots) / len(daily_snapshots)) if daily_snapshots else 0
    realtime_market_time = max((s.market_data_time or s.source_ts or s.timestamp for s in realtime_snapshots), default=None)
    realtime_latency = max(int((now - realtime_market_time).total_seconds()), 0) if realtime_market_time else None
    realtime_is_same_trade_date = (
        realtime_market_time is not None
        and market_date(realtime_market_time) == market_date(now)
    )
    realtime_is_fresh = (
        realtime_market_time is not None
        and realtime_latency is not None
        and realtime_latency <= REALTIME_STALE_SECONDS
        and realtime_is_same_trade_date
        and is_regular_tw_session(now)
    )
    if realtime_snapshots and realtime_ratio >= 0.8 and realtime_is_fresh:
        official_snapshots = apply_theme_mappings(realtime_snapshots)
        source_status = "official_intraday"
        source_used = "twse_mis_realtime"
    elif realtime_snapshots and realtime_ratio >= 0.8 and realtime_is_same_trade_date:
        official_snapshots = apply_theme_mappings(
            [
                snapshot.model_copy(
                    update={
                        "is_realtime": False,
                        "is_intraday": False,
                        "data_quality_bucket": "official_partial",
                        "formal_grade": False,
                        "formal_grade_label": "estimated",
                        "provider_type": "official_partial",
                        "source_status": "official",
                        "blocked_reason": "twse_mis_today_quote_not_realtime",
                    }
                )
                for snapshot in realtime_snapshots
            ]
        )
        source_status = "official_partial"
        source_used = "twse_mis_today_quote"
        errors.append(f"mis_today_quote_not_realtime:latency={realtime_latency}s")
    else:
        official_snapshots = daily_snapshots
        source_status = "official_partial" if official_snapshots else "failed"
        source_used = "twse_tpex_official"
        if realtime_snapshots:
            if realtime_ratio < 0.8:
                errors.append(f"mis_realtime_coverage_below_threshold:{len(realtime_snapshots)}/{len(daily_snapshots)}")
            if realtime_ratio >= 0.8 and not realtime_is_fresh:
                errors.append(f"mis_realtime_not_fresh:latency={realtime_latency}s")

    market_data_time = max((s.market_data_time or s.source_ts or s.timestamp for s in official_snapshots), default=None)
    latency = max(int((now - market_data_time).total_seconds()), 0) if market_data_time else None
    return ProviderResult(
        snapshots=official_snapshots,
        source_used=source_used,
        source_status=source_status,
        source_ts=market_data_time or now,
        market_data_time=market_data_time,
        data_latency_seconds=latency,
        is_realtime=source_status == "official_intraday",
        is_intraday=source_status == "official_intraday",
        realtime_provider="twse_mis" if source_status == "official_intraday" else None,
        twse_count=len(twse_snapshots),
        tpex_count=len(tpex_snapshots),
        realtime_count=len(realtime_snapshots),
        excluded_count=excluded_count,
        errors=errors,
    )


def fetch_official_snapshots() -> ProviderResult:
    try:
        return asyncio.run(fetch_official_snapshots_async())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(fetch_official_snapshots_async())
        finally:
            loop.close()


def fetch_mcp_proxy_snapshots() -> ProviderResult:
    base = load_static_universe()
    if not base:
        return ProviderResult(
            snapshots=[],
            source_used="twse_mcp_realtime_proxy",
            source_status="failed",
            source_ts=taipei_now(),
            errors=["static_universe_empty"],
        )
    try:
        return asyncio.run(fetch_mcp_realtime_quotes(base))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(fetch_mcp_realtime_quotes(base))
        except Exception as exc:
            return ProviderResult(
                snapshots=[],
                source_used="twse_mcp_realtime_proxy",
                source_status="failed",
                source_ts=taipei_now(),
                errors=[f"mcp_proxy:{type(exc).__name__}"],
            )
        finally:
            loop.close()
    except Exception as exc:
        return ProviderResult(
            snapshots=[],
            source_used="twse_mcp_realtime_proxy",
            source_status="failed",
            source_ts=taipei_now(),
            errors=[f"mcp_proxy:{type(exc).__name__}"],
        )


def seed_provider_result() -> ProviderResult:
    _, current = build_seed_snapshots()
    current, excluded_count = filter_common_stocks(current)
    current = apply_theme_mappings(current)
    now = taipei_now()
    return ProviderResult(
        snapshots=current,
        source_used="seed_provider",
        source_status="seed",
        source_ts=now,
        twse_count=0,
        tpex_count=0,
        excluded_count=excluded_count,
        errors=["official_provider_failed_or_empty"],
    )


def fetch_market_snapshots(*, allow_seed_fallback: bool = False, min_official_count: int = 1500) -> ProviderResult:
    prefer_mcp = os.getenv("SMART_MONEY_PREFER_MCP_PROXY", "1").strip().lower() not in {"0", "false", "no"}
    mcp_enabled = os.getenv("SMART_MONEY_ENABLE_MCP_PROXY", "1").strip().lower() not in {"0", "false", "no"}
    if prefer_mcp and mcp_enabled:
        mcp = fetch_mcp_proxy_snapshots()
        if len(mcp.snapshots) >= min_official_count:
            return mcp

    official = fetch_official_snapshots()
    official_has_twse = official.twse_count > 0
    if len(official.snapshots) >= min_official_count and official_has_twse:
        return official
    if mcp_enabled:
        mcp = fetch_mcp_proxy_snapshots()
        if len(mcp.snapshots) >= min_official_count:
            mcp.errors = [
                *official.errors,
                *mcp.errors,
                f"official_direct_count_below_min:{len(official.snapshots)}",
                f"official_direct_twse_count:{official.twse_count}",
            ]
            return mcp
        official.errors = [
            *official.errors,
            *mcp.errors,
            f"mcp_proxy_count_below_min:{len(mcp.snapshots)}",
            f"mcp_proxy_status:{mcp.source_status}",
        ]
    if not allow_seed_fallback:
        return official
    seed = seed_provider_result()
    seed.errors = [*official.errors, f"official_count_below_min:{len(official.snapshots)}"]
    return seed
