from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

from app.notifier.discord import format_discord_message, send_discord
from app.storage.models import SignalEvent, TopicFlow
from app.storage.sqlite_store import SQLiteStore
from app.time_utils import taipei_now


@dataclass
class DiscordQueue:
    min_interval_seconds: float = 1.2
    max_batch: int = 5
    queued: list[tuple[SignalEvent, TopicFlow | None]] = field(default_factory=list)
    last_sent_at: datetime | None = None

    def enqueue(self, signal: SignalEvent, topic: TopicFlow | None = None) -> None:
        if signal.is_formal_push_allowed:
            self.queued.append((signal, topic))

    async def flush(self, webhook_url: str, mark_sent) -> dict:
        sent = 0
        failed = 0
        errors: list[str] = []
        batch = self.queued[: self.max_batch]
        self.queued = self.queued[self.max_batch :]
        for signal, topic in batch:
            if self.last_sent_at:
                elapsed = (taipei_now() - self.last_sent_at).total_seconds()
                if elapsed < self.min_interval_seconds:
                    await asyncio.sleep(self.min_interval_seconds - elapsed)
            try:
                await send_discord(webhook_url, format_discord_message(signal, topic))
                mark_sent(signal)
                sent += 1
                self.last_sent_at = taipei_now()
            except Exception as exc:
                failed += 1
                errors.append(f"{signal.target_id}:{type(exc).__name__}")
        return {"sent": sent, "failed": failed, "errors": errors, "remaining": len(self.queued)}


discord_queue = DiscordQueue()


async def flush_sqlite_queue(
    store: SQLiteStore,
    webhook_url: str,
    mark_sent,
    topic_lookup,
    *,
    min_interval_seconds: float = 1.2,
    max_batch: int = 5,
) -> dict:
    sent = 0
    failed = 0
    errors: list[str] = []
    last_sent_at: datetime | None = None
    store.retry_due_discord_items()
    batch = store.list_due_discord_queue(limit=max_batch)
    for item in batch:
        if last_sent_at:
            elapsed = (taipei_now() - last_sent_at).total_seconds()
            if elapsed < min_interval_seconds:
                await asyncio.sleep(min_interval_seconds - elapsed)
        signal = item.payload
        topic = topic_lookup(signal.target_id)
        try:
            await send_discord(webhook_url, format_discord_message(signal, topic))
            mark_sent(signal)
            sent += 1
            last_sent_at = taipei_now()
        except Exception as exc:
            retry_count = item.retry_count + 1
            status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            retry_after = None
            if isinstance(exc, httpx.HTTPStatusError):
                retry_after = exc.response.headers.get("Retry-After")
            try:
                wait_seconds = float(retry_after) if retry_after else min(300, 30 * (2 ** min(retry_count, 4)))
            except ValueError:
                wait_seconds = min(300, 30 * (2 ** min(retry_count, 4)))
            store.update_discord_queue_item(
                item.id,
                status="failed",
                retry_count=retry_count,
                next_retry_at=taipei_now() + timedelta(seconds=wait_seconds),
                discord_response_code=status_code,
                last_error=f"{type(exc).__name__}:{status_code or 'no_status'}",
            )
            failed += 1
            errors.append(f"{signal.target_id}:{type(exc).__name__}")
    return {"sent": sent, "failed": failed, "errors": errors, "remaining": len(store.list_discord_queue(statuses={"pending"}, limit=1000))}
