from fastapi import APIRouter

from app.scheduler import scheduler_status
from app.storage.repository import repo

router = APIRouter(prefix="/api", tags=["dashboard"])
FORMAL_SOURCE_STATUSES = {"official_full", "official_intraday"}


@router.get("/dashboard/latest")
def latest_dashboard(official_full_only: bool = False):
    return repo.dashboard(official_full_only=official_full_only)


@router.post("/scan/run")
def run_scan():
    repo.scan()
    return {"ok": True, "updated_at": repo.last_scan_at}


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
