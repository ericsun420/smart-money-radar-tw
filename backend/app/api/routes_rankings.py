from fastapi import APIRouter

from app.storage.repository import repo

router = APIRouter(prefix="/api", tags=["rankings"])


@router.get("/rankings/latest")
def latest_rankings(official_full_only: bool = False):
    return repo.rankings(official_full_only=official_full_only)
