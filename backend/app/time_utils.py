from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def taipei_now() -> datetime:
    return datetime.now(TAIPEI_TZ)


def ensure_taipei(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TAIPEI_TZ)
    return dt.astimezone(TAIPEI_TZ)


def market_date(dt: datetime) -> str:
    return ensure_taipei(dt).date().isoformat()


def is_regular_tw_session(dt: datetime) -> bool:
    local = ensure_taipei(dt)
    if local.weekday() >= 5:
        return False
    return time(9, 0) <= local.time() <= time(13, 35)
