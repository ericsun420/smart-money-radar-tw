from __future__ import annotations

from datetime import datetime, timedelta

from app.storage.models import StockSnapshot
from app.time_utils import ensure_taipei, market_date, taipei_now


SEED_ROWS = [
    ("2317", "HonHai", "TSE", "OtherElectronics", ["AIServer", "GB200", "AutoElectronics"], 218.5, 207.7, 442.33, 5.21),
    ("2454", "MediaTek", "TSE", "Semiconductor", ["ICDesign", "AIChip"], 1455.0, 1325.0, 231.07, 9.81),
    ("3035", "Faraday", "TSE", "Semiconductor", ["ICDesign", "AutoChip"], 185.0, 168.5, 61.98, 9.79),
    ("2330", "TSMC", "TSE", "Semiconductor", ["CoWoS", "AIChip"], 986.0, 970.0, 398.72, 1.65),
    ("3661", "Alchip-KY", "TSE", "Semiconductor", ["ASIC", "AIChip"], 3660.0, 3510.0, 82.46, 4.27),
    ("3701", "FIC", "TSE", "ComputerPeripherals", ["AIServer", "GB200"], 68.4, 64.2, 28.41, 6.54),
    ("6658", "SynPower", "OTC", "ElectronicParts", ["Thermal", "AIServer"], 142.5, 130.0, 12.35, 9.62),
    ("1727", "ChinaChem", "TSE", "Chemical", ["SpecialtyChemical", "SemiMaterial"], 45.8, 47.1, 7.82, -2.76),
    ("8046", "NanyaPCB", "TSE", "ElectronicParts", ["ABF", "AIServer"], 181.5, 178.5, 99.64, 1.68),
    ("1802", "TGlass", "TSE", "GlassCeramic", ["Construction", "Glass"], 23.75, 24.75, 34.74, -4.04),
    ("2408", "NanyaTech", "TSE", "Semiconductor", ["DRAM", "HBM"], 58.2, 60.5, 72.11, -3.8),
    ("2344", "Winbond", "TSE", "Semiconductor", ["DRAM", "HBM"], 24.4, 25.1, 36.85, -2.79),
    ("6239", "PTI", "TSE", "Semiconductor", ["Packaging", "HBM"], 139.0, 136.0, 18.72, 2.21),
]


def build_seed_snapshots(now: datetime | None = None) -> tuple[list[StockSnapshot], list[StockSnapshot]]:
    now = ensure_taipei(now or taipei_now())
    previous: list[StockSnapshot] = []
    current: list[StockSnapshot] = []
    for idx, (code, name, market, industry, themes, price, prev_close, value_yi, change_pct) in enumerate(SEED_ROWS):
        prev_price = price - (1.2 + idx % 3) if code not in {"8046", "2408", "2344", "1802", "1727"} else price + (0.8 + idx % 2)
        prev_value = max(value_yi - (0.8 + idx * 0.17), 0.1)
        volume_shares = int(value_yi * 1_000_000)
        base = dict(
            code=code,
            name=name,
            market=market,
            industry=industry,
            themes=themes,
            previous_close=prev_close,
            open=prev_close * 1.002,
            high=max(price, prev_price) * 1.01,
            low=min(price, prev_price) * 0.99,
            volume=volume_shares,
            trade_value=value_yi * 100_000_000,
            provider_type="seed",
            source_status="seed",
            formal_grade=False,
            formal_grade_label="blocked",
            blocked_reason="seed_provider_not_formal",
            generated_at=now,
            source_ts=now,
            market_date=market_date(now),
            vwap_twd=(value_yi * 100_000_000 / volume_shares) if volume_shares else None,
            units_normalized=True,
        )
        previous.append(
            StockSnapshot(
                **base,
                price=round(prev_price, 2),
                change_pct=round((prev_price - prev_close) / prev_close * 100, 2),
                trade_value_yi=round(prev_value, 2),
                timestamp=now - timedelta(minutes=5),
                data_quality_bucket="seed",
            )
        )
        current.append(
            StockSnapshot(
                **{**base, "source_status": "cache" if code == "6658" else "seed", "blocked_reason": "cache_only_not_formal" if code == "6658" else "seed_provider_not_formal"},
                price=price,
                change_pct=change_pct,
                trade_value_yi=value_yi,
                timestamp=now,
                data_quality_bucket="cache_only" if code == "6658" else "seed",
            )
        )
    return previous, current
