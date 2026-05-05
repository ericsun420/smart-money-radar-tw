from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter

from app.storage.models import AlertRule
from app.storage.repository import repo
from app.time_utils import taipei_now

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alert-rules")
def list_alert_rules():
    return repo.store.list_alert_rules()


@router.post("/alert-rules")
def save_alert_rule(rule: AlertRule):
    now = taipei_now()
    if not rule.id:
        rule = rule.model_copy(update={"id": uuid4().hex, "created_at": now})
    return repo.store.save_alert_rule(rule.model_copy(update={"updated_at": now}))
