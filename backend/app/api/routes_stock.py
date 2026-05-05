from fastapi import APIRouter, HTTPException

from app.storage.repository import repo

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search/{query}")
def search_stock(query: str):
    detail = repo.stock_detail(query)
    if not detail:
        raise HTTPException(status_code=404, detail="查無此股票或今日尚無訊號")
    return detail


@router.get("/{code}")
def get_stock(code: str):
    detail = repo.stock_detail(code)
    if not detail:
        raise HTTPException(status_code=404, detail="查無此股票或今日尚無訊號")
    return detail
