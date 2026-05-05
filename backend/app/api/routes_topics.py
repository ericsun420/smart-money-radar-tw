from fastapi import APIRouter, HTTPException

from app.storage.repository import repo

router = APIRouter(prefix="/api/topics", tags=["topics"])


@router.get("/{topic_name}")
def get_topic(topic_name: str):
    detail = repo.topic_detail(topic_name)
    if not detail:
        raise HTTPException(status_code=404, detail="topic not found")
    return detail

