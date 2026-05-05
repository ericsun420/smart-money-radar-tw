from __future__ import annotations

import re

from app.storage.models import StockSnapshot


EXCLUDED_NAME_KEYWORDS = (
    "ETF",
    "ETN",
    "FUND",
    "INDEX",
    "指數",
    "基金",
    "受益",
    "權證",
    "認購",
    "認售",
    "牛證",
    "熊證",
    "債",
    "特別股",
)

EXCLUDED_CODE_PREFIXES = (
    "00",  # listed ETFs/ETNs and other exchange traded products
    "02",  # ETN-like products in TWSE code space
)


def is_common_stock_code(code: str) -> bool:
    code = code.strip()
    if not re.fullmatch(r"\d{4}", code):
        return False
    return not code.startswith(EXCLUDED_CODE_PREFIXES)


def is_excluded_instrument(name: str, industry: str = "") -> bool:
    text = f"{name} {industry}".upper()
    return any(keyword.upper() in text for keyword in EXCLUDED_NAME_KEYWORDS)


def is_common_stock(snapshot: StockSnapshot) -> bool:
    return is_common_stock_code(snapshot.code) and not is_excluded_instrument(snapshot.name, snapshot.industry)


def filter_common_stocks(snapshots: list[StockSnapshot]) -> tuple[list[StockSnapshot], int]:
    kept = [s for s in snapshots if is_common_stock(s)]
    return kept, len(snapshots) - len(kept)
