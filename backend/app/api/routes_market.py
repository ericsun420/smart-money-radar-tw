from fastapi import APIRouter

from app.scheduler import scheduler_status
from app.storage.repository import repo

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/flow")
def market_flow():
    return repo.market_flow()


@router.get("/status")
def market_status():
    status = scheduler_status()
    return repo.market_status(next_scan_at=status["next_run_time"])
