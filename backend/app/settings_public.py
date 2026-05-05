from __future__ import annotations

from app.storage.models import PublicSettings, Settings


def mask_webhook(url: str) -> str:
    if not url:
        return ""
    tail = url[-4:] if len(url) >= 4 else "****"
    prefix = "https://discord.com/api/webhooks/"
    if url.startswith(prefix):
        return f"{prefix}***{tail}"
    return f"***{tail}"


def public_settings(settings: Settings) -> PublicSettings:
    masked = mask_webhook(settings.discord_webhook_url)
    return PublicSettings(
        auto_refresh=settings.auto_refresh,
        scan_interval_minutes=settings.scan_interval_minutes,
        topic_min_net_yi=settings.topic_min_net_yi,
        topic_min_delta_yi=settings.topic_min_delta_yi,
        repeat_delta_yi=settings.repeat_delta_yi,
        stock_min_value_yi=settings.stock_min_value_yi,
        stock_min_delta_yi=settings.stock_min_delta_yi,
        min_value_delta_yi=settings.min_value_delta_yi,
        stale_seconds=settings.stale_seconds,
        net_near_zero_ratio=settings.net_near_zero_ratio,
        only_official_full=settings.only_official_full,
        show_cache_warning=settings.show_cache_warning,
        push_enabled=settings.push_enabled,
        stock_signal_enabled=settings.stock_signal_enabled,
        discord_webhook_configured=bool(settings.discord_webhook_url),
        discord_webhook_masked=masked,
        masked_webhook_url=masked,
    )
