from datetime import datetime, time
from math import ceil

from fastapi import APIRouter

from app.scheduler import scheduler_status
from app.storage.repository import repo
from app.time_utils import TAIPEI_TZ, ensure_taipei, market_date, taipei_now

router = APIRouter(prefix="/api", tags=["dashboard"])
FORMAL_SOURCE_STATUSES = {"official_full", "official_intraday"}
MANUAL_SCAN_COOLDOWN_SECONDS = 30
_last_manual_scan_at: datetime | None = None


def _needs_opening_rescan(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    opening = datetime.combine(now.date(), time(9, 0), tzinfo=TAIPEI_TZ)
    if now < opening:
        return False
    debug = repo.latest_scan_debug()
    if not debug or not debug.market_data_time:
        return True
    data_time = ensure_taipei(debug.market_data_time)
    return market_date(data_time) == market_date(now) and data_time < opening


@router.get("/dashboard/latest")
def latest_dashboard(official_full_only: bool = False):
    return repo.dashboard(official_full_only=official_full_only)


@router.post("/scan/run")
def run_scan():
    global _last_manual_scan_at
    now = taipei_now()
    forced_opening_scan = _needs_opening_rescan(now)
    if _last_manual_scan_at and not forced_opening_scan:
        elapsed = (now - ensure_taipei(_last_manual_scan_at)).total_seconds()
        if elapsed < MANUAL_SCAN_COOLDOWN_SECONDS:
            remaining = ceil(MANUAL_SCAN_COOLDOWN_SECONDS - elapsed)
            return {
                "ok": True,
                "scan_started": False,
                "reason": "manual_scan_cooldown",
                "cooldown_seconds": remaining,
                "updated_at": repo.last_scan_at,
                "scan_id": repo.current_scan_id(),
                "snapshot_id": repo.current_snapshot_id(),
                "batch_label": repo.current_batch_label(),
            }
    previous_scan_id = repo.current_scan_id()
    previous_snapshot_id = repo.current_snapshot_id()
    repo.scan()
    _last_manual_scan_at = now
    current_scan_id = repo.current_scan_id()
    current_snapshot_id = repo.current_snapshot_id()
    return {
        "ok": True,
        "scan_started": True,
        "forced_opening_scan": forced_opening_scan,
        "updated_at": repo.last_scan_at,
        "scan_id": current_scan_id,
        "previous_scan_id": previous_scan_id,
        "snapshot_id": current_snapshot_id,
        "previous_snapshot_id": previous_snapshot_id,
        "batch_changed": bool(current_snapshot_id and previous_snapshot_id and current_snapshot_id != previous_snapshot_id),
        "batch_label": repo.current_batch_label(),
    }


@router.get("/health")
def health():
    status = scheduler_status()
    debug = repo.latest_scan_debug()
    market_flow = repo.market_flow()
    market_status = repo.market_status(next_scan_at=status["next_run_time"])
    push_blocked_reason = market_flow.push_blocked_reason
    return {
        "ok": True,
        "data_source": debug.source_used if debug else "unknown",
        "data_source_status": debug.source_status if debug else "unknown",
        "is_realtime": debug.is_realtime if debug else False,
        "is_intraday": debug.is_intraday if debug else False,
        "realtime_provider": debug.realtime_provider if debug else None,
        "market_data_time": debug.market_data_time if debug else None,
        "data_latency_seconds": debug.data_latency_seconds if debug else None,
        "realtime_count": debug.realtime_count if debug else 0,
        "twse_count": debug.twse_count if debug else 0,
        "tpex_count": debug.tpex_count if debug else 0,
        "result_count": debug.result_count if debug else 0,
        "scan_id": repo.current_scan_id(),
        "snapshot_id": repo.current_snapshot_id(),
        "batch_label": repo.current_batch_label(),
        "is_empty": not bool(repo.stock_flows),
        "cache": "sqlite_wal_state_plus_memory_snapshots",
        "last_scan_at": repo.last_scan_at,
        "scan_interval_minutes": repo.settings.scan_interval_minutes,
        "active_scan_interval_minutes": status["scan_interval_minutes"],
        "scheduler_running": status["scheduler_running"],
        "scheduler_next_run_time": status["next_run_time"],
        "discord_queue_next_run_time": status["discord_queue_next_run_time"],
        "stock_signal_enabled": repo.settings.stock_signal_enabled,
        "observation_mode": not market_flow.formal_grade,
        "push_blocked_reason": push_blocked_reason,
        "market_status": market_status,
    }


@router.get("/debug/latest_scan")
def latest_scan_debug():
    return repo.latest_scan_debug()
