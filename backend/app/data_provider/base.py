from __future__ import annotations

from abc import ABC, abstractmethod

from app.storage.models import StockSnapshot


class MarketDataProvider(ABC):
    @abstractmethod
    async def fetch_snapshots(self) -> list[StockSnapshot]:
        raise NotImplementedError

