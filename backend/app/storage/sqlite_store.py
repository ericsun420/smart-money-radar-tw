from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from app.storage.models import AlertRule, DeviceRegistration, DiscordQueueItem, ScanDebugSummary, Settings, SignalEvent, TopicState, UserPreferences
from app.time_utils import ensure_taipei, taipei_now


class SQLiteStore:
    def __init__(self, path: str = "smart_money_radar.sqlite3") -> None:
        self.path = Path(path)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS topic_state (
                    topic_name TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discord_sent (
                    fingerprint TEXT PRIMARY KEY,
                    sent_at TEXT NOT NULL,
                    sent_count INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_debug (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discord_queue (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retry_count INTEGER NOT NULL,
                    next_retry_at TEXT,
                    discord_response_code INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    last_error TEXT
                )
                """
            )
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_discord_queue_fingerprint ON discord_queue(fingerprint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_discord_queue_status ON discord_queue(status, next_retry_at)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

    def load_settings(self) -> Settings | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM settings_state WHERE id = 1").fetchone()
        return Settings.model_validate_json(row[0]) if row else None

    def save_settings(self, settings: Settings) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO settings_state(id, payload) VALUES(1, ?)", (settings.model_dump_json(),))

    def list_alert_rules(self) -> list[AlertRule]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM alert_rules ORDER BY id").fetchall()
        return [AlertRule.model_validate_json(row[0]) for row in rows]

    def save_alert_rule(self, rule: AlertRule) -> AlertRule:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO alert_rules(id, payload) VALUES(?, ?)", (rule.id, rule.model_dump_json()))
        return rule

    def load_user_preferences(self) -> UserPreferences | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM user_preferences WHERE id = 'local'").fetchone()
        return UserPreferences.model_validate_json(row[0]) if row else None

    def save_user_preferences(self, preferences: UserPreferences) -> UserPreferences:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO user_preferences(id, payload) VALUES(?, ?)", (preferences.id, preferences.model_dump_json()))
        return preferences

    def list_devices(self) -> list[DeviceRegistration]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM devices ORDER BY rowid DESC").fetchall()
        return [DeviceRegistration.model_validate_json(row[0]) for row in rows]

    def save_device(self, device: DeviceRegistration) -> DeviceRegistration:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO devices(id, payload) VALUES(?, ?)", (device.id, device.model_dump_json()))
        return device

    def load_topic_states(self) -> dict[str, TopicState]:
        with self._connect() as conn:
            rows = conn.execute("SELECT topic_name, payload FROM topic_state").fetchall()
        return {name: TopicState.model_validate_json(payload) for name, payload in rows}

    def save_topic_states(self, states: dict[str, TopicState]) -> None:
        with self._connect() as conn:
            for name, state in states.items():
                conn.execute(
                    "INSERT OR REPLACE INTO topic_state(topic_name, payload) VALUES(?, ?)",
                    (name, state.model_dump_json()),
                )

    def append_signal(self, signal: SignalEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO signals(id, timestamp, target_type, target_id, payload) VALUES(?, ?, ?, ?, ?)",
                (signal.id, signal.timestamp.isoformat(), signal.target_type, signal.target_id, signal.model_dump_json()),
            )

    def mark_discord_sent(self, signal: SignalEvent) -> SignalEvent:
        with self._connect() as conn:
            existing = conn.execute("SELECT sent_count FROM discord_sent WHERE fingerprint = ?", (signal.fingerprint,)).fetchone()
            sent_count = (existing[0] + 1) if existing else 1
            sent_at = signal.timestamp.isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO discord_sent(fingerprint, sent_at, sent_count) VALUES(?, ?, ?)",
                (signal.fingerprint, sent_at, sent_count),
            )
            row = conn.execute("SELECT payload FROM discord_queue WHERE fingerprint = ?", (signal.fingerprint,)).fetchone()
            if row:
                item = DiscordQueueItem.model_validate_json(row[0])
                updated = item.model_copy(update={"status": "sent", "updated_at": taipei_now(), "last_error": None})
                conn.execute(
                    """
                    UPDATE discord_queue
                    SET status = ?, updated_at = ?, payload = ?, last_error = ?
                    WHERE fingerprint = ?
                    """,
                    (updated.status, updated.updated_at.isoformat(), updated.model_dump_json(), None, signal.fingerprint),
                )
        return signal.model_copy(update={"sent_count": sent_count, "discord_sent_at": signal.timestamp})

    def was_discord_sent(self, fingerprint: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM discord_sent WHERE fingerprint = ?", (fingerprint,)).fetchone()
        return row is not None

    def load_signals(self, limit: int = 200) -> list[SignalEvent]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM signals ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        return [SignalEvent.model_validate_json(row[0]) for row in rows]

    def save_latest_scan(self, summary: ScanDebugSummary) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO scan_debug(id, payload) VALUES(1, ?)", (summary.model_dump_json(),))

    def load_latest_scan(self) -> ScanDebugSummary | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM scan_debug WHERE id = 1").fetchone()
        return ScanDebugSummary.model_validate_json(row[0]) if row else None

    def enqueue_discord(self, signal: SignalEvent, *, status: str = "pending", last_error: str | None = None) -> DiscordQueueItem:
        now = taipei_now()
        with self._connect() as conn:
            existing = conn.execute("SELECT payload FROM discord_queue WHERE fingerprint = ?", (signal.fingerprint,)).fetchone()
            if existing:
                return DiscordQueueItem.model_validate_json(existing[0])
            item = DiscordQueueItem(
                id=uuid4().hex,
                fingerprint=signal.fingerprint,
                signal_id=signal.id,
                target_id=signal.target_id,
                status=status,  # type: ignore[arg-type]
                payload=signal,
                last_error=last_error,
                created_at=now,
                updated_at=now,
            )
            conn.execute(
                """
                INSERT INTO discord_queue(
                    id, fingerprint, signal_id, target_id, status, retry_count, next_retry_at,
                    discord_response_code, created_at, updated_at, payload, last_error
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.fingerprint,
                    item.signal_id,
                    item.target_id,
                    item.status,
                    item.retry_count,
                    item.next_retry_at.isoformat() if item.next_retry_at else None,
                    item.discord_response_code,
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                    item.model_dump_json(),
                    item.last_error,
                ),
            )
        return item

    def list_discord_queue(self, *, statuses: set[str] | None = None, limit: int = 100) -> list[DiscordQueueItem]:
        with self._connect() as conn:
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                rows = conn.execute(
                    f"SELECT payload FROM discord_queue WHERE status IN ({placeholders}) ORDER BY created_at ASC LIMIT ?",
                    (*sorted(statuses), limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT payload FROM discord_queue ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [DiscordQueueItem.model_validate_json(row[0]) for row in rows]

    def list_due_discord_queue(self, *, limit: int = 100) -> list[DiscordQueueItem]:
        now = taipei_now().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM discord_queue
                WHERE status = 'pending'
                   OR (status = 'failed' AND (next_retry_at IS NULL OR next_retry_at <= ?))
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        return [DiscordQueueItem.model_validate_json(row[0]) for row in rows]

    def retry_due_discord_items(self) -> int:
        now = taipei_now()
        due = self.list_due_discord_queue(limit=1000)
        count = 0
        for item in due:
            if item.status == "failed" and (item.next_retry_at is None or ensure_taipei(item.next_retry_at) <= now):
                self.update_discord_queue_item(item.id, status="pending", retry_count=item.retry_count, next_retry_at=None, last_error=None)
                count += 1
        return count

    def update_discord_queue_item(
        self,
        item_id: str,
        *,
        status: str,
        retry_count: int | None = None,
        next_retry_at=None,
        discord_response_code: int | None = None,
        last_error: str | None = None,
    ) -> DiscordQueueItem | None:
        now = taipei_now()
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM discord_queue WHERE id = ?", (item_id,)).fetchone()
            if not row:
                return None
            item = DiscordQueueItem.model_validate_json(row[0])
            updated = item.model_copy(
                update={
                    "status": status,
                    "retry_count": item.retry_count if retry_count is None else retry_count,
                    "next_retry_at": next_retry_at,
                    "discord_response_code": discord_response_code,
                    "last_error": last_error,
                    "updated_at": now,
                }
            )
            conn.execute(
                """
                UPDATE discord_queue
                SET status = ?, retry_count = ?, next_retry_at = ?, discord_response_code = ?,
                    updated_at = ?, payload = ?, last_error = ?
                WHERE id = ?
                """,
                (
                    updated.status,
                    updated.retry_count,
                    updated.next_retry_at.isoformat() if updated.next_retry_at else None,
                    updated.discord_response_code,
                    updated.updated_at.isoformat(),
                    updated.model_dump_json(),
                    updated.last_error,
                    item_id,
                ),
            )
        return updated

    def discord_queue_stats(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) FROM discord_queue GROUP BY status").fetchall()
        return {status: count for status, count in rows}
