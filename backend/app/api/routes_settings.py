from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.notifier.discord import send_discord, validate_webhook_url
from app.notifier.notification_service import format_notification_message
from app.scheduler import reschedule_scan_job
from app.settings_public import public_settings
from app.storage.models import Settings
from app.storage.repository import repo

router = APIRouter(prefix="/api", tags=["settings"])
FORMAL_SOURCE_STATUSES = {"official_full", "official_intraday"}


@router.get("/settings")
def get_settings():
    return public_settings(repo.settings)


@router.post("/settings")
def update_settings(settings: Settings):
    if settings.discord_webhook_url and settings.discord_webhook_url != "__KEEP_EXISTING__":
        error = validate_webhook_url(settings.discord_webhook_url)
        if error:
            raise HTTPException(status_code=400, detail=error)
    old_interval = repo.settings.scan_interval_minutes
    updated = repo.update_settings(settings)
    if updated.scan_interval_minutes != old_interval:
        reschedule_scan_job(updated.scan_interval_minutes, repo.scan)
    return {
        "settings": public_settings(updated),
        "effective_scan_interval_minutes": updated.scan_interval_minutes,
    }


@router.post("/discord/test")
async def discord_test():
    webhook_url = repo.settings.discord_webhook_url
    if not webhook_url:
        raise HTTPException(status_code=400, detail="Discord webhook URL is not configured")
    error = validate_webhook_url(webhook_url)
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not repo.signals:
        repo.scan()
    signal = next((s for s in repo.signals if s.is_formal_push_allowed), None)
    if not signal:
        raise HTTPException(status_code=400, detail="No formal signal is available for Discord test")
    can_send, blocked_reason = repo.can_send_discord(signal)
    if not can_send:
        raise HTTPException(status_code=409, detail=blocked_reason)
    topic = repo.topic_flows.get(signal.target_id)
    content = format_notification_message(signal, topic)
    try:
        await send_discord(webhook_url, content)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Discord webhook request failed: {type(exc).__name__}") from exc
    repo.mark_discord_sent(signal)
    return {"ok": True, "content": content}


@router.post("/discord/flush")
async def discord_flush():
    debug = repo.latest_scan_debug()
    if debug and debug.source_status not in FORMAL_SOURCE_STATUSES:
        raise HTTPException(status_code=409, detail="data_source_not_official_full")
    webhook_url = repo.settings.discord_webhook_url
    if not webhook_url:
        raise HTTPException(status_code=400, detail="Discord webhook URL is not configured")
    error = validate_webhook_url(webhook_url)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return await repo.notifications.flush_discord(webhook_url, repo.mark_discord_sent, lambda target_id: repo.topic_flows.get(target_id))


@router.get("/discord/queue")
def discord_queue_status():
    return {
        "stats": repo.discord_queue_stats(),
        "items": repo.discord_queue_items(limit=50),
    }
