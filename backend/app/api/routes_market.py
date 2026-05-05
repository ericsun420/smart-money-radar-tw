from fastapi import APIRouter

from app.storage.repository import repo

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/flow")
def market_flow():
    return repo.market_flow()
