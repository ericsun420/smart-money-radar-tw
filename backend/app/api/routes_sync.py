from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter

from app.storage.models import AlertRule, DeviceRegistration, UserPreferences
from app.storage.repository import repo
from app.time_utils import taipei_now

router = APIRouter(prefix="/api", tags=["local-sync-ready"])


@router.get("/alert-rules")
def list_alert_rules():
    return repo.store.list_alert_rules()


@router.post("/alert-rules")
def save_alert_rule(rule: AlertRule):
    now = taipei_now()
    if not rule.id:
        rule = rule.model_copy(update={"id": uuid4().hex})
    return repo.store.save_alert_rule(rule.model_copy(update={"updated_at": now}))


@router.get("/user-preferences")
def get_user_preferences():
    preferences = repo.store.load_user_preferences()
    return preferences or UserPreferences(updated_at=taipei_now())


@router.post("/user-preferences")
def save_user_preferences(preferences: UserPreferences):
    return repo.store.save_user_preferences(preferences.model_copy(update={"updated_at": taipei_now()}))


@router.get("/devices")
def list_devices():
    return {
        "sync_mode": "local_only",
        "note": "local device schema is sync-ready; iOS/Android account sync is not enabled in this MVP",
        "devices": repo.store.list_devices(),
    }


@router.post("/devices")
def save_device(device: DeviceRegistration):
    return repo.store.save_device(device.model_copy(update={"updated_at": taipei_now()}))
