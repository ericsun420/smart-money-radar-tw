from __future__ import annotations

from typing import Callable

from app.notifier.discord import format_discord_message
from app.notifier.discord_queue import flush_sqlite_queue
from app.storage.models import SignalEvent, TopicFlow
from app.storage.sqlite_store import SQLiteStore


class NotificationService:
    """Notification channel coordinator.

    Discord remains the first MVP channel, but enqueue/flush decisions are no
    longer modeled as a standalone sender.
    """

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def enqueue_signal(self, signal: SignalEvent, *, can_send: bool, blocked_reason: str | None = None) -> None:
        status = "pending" if can_send else "skipped_non_formal"
        self.store.enqueue_discord(signal, status=status, last_error=blocked_reason)

    async def flush_discord(
        self,
        webhook_url: str,
        mark_sent: Callable[[SignalEvent], SignalEvent],
        topic_lookup: Callable[[str], TopicFlow | None],
    ) -> dict:
        return await flush_sqlite_queue(self.store, webhook_url, mark_sent, topic_lookup)


def format_notification_message(signal: SignalEvent, topic: TopicFlow | None = None) -> str:
    return format_discord_message(signal, topic)
