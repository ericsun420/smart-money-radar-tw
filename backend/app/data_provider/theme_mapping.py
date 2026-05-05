from __future__ import annotations

from app.storage.models import StockSnapshot


THEME_MAP: dict[str, list[str]] = {
    "2317": ["其他電子業", "AI伺服器", "GB200", "車用電子", "低軌衛星"],
    "2454": ["半導體業", "IC設計", "AI晶片", "車用晶片"],
    "3035": ["半導體業", "IC設計", "車用晶片", "ASIC"],
    "2330": ["半導體業", "晶圓代工", "CoWoS", "AI晶片"],
    "3661": ["半導體業", "ASIC", "AI晶片"],
    "3701": ["電腦及週邊設備業", "AI伺服器", "GB200"],
    "6658": ["電子零組件業", "散熱", "AI伺服器"],
    "1727": ["化學工業", "半導體材料", "特用化學"],
    "8046": ["電子零組件業", "ABF載板", "AI伺服器"],
    "1802": ["玻璃陶瓷", "建材", "玻璃"],
    "2408": ["半導體業", "DRAM", "HBM記憶體"],
    "2344": ["半導體業", "DRAM", "HBM記憶體"],
    "6239": ["半導體業", "封測", "HBM記憶體"],
    "3008": ["光電業", "高價股"],
    "4938": ["電腦及週邊設備業", "品牌電腦"],
    "2308": ["電子零組件業", "電源", "AI伺服器", "電動車"],
    "2327": ["電子零組件業", "被動元件", "車用電子"],
    "2345": ["通信網路業", "低軌衛星", "網通"],
    "2382": ["電腦及週邊設備業", "AI伺服器", "GB200"],
    "3231": ["電腦及週邊設備業", "AI伺服器", "GB200"],
    "2356": ["電腦及週邊設備業", "品牌電腦"],
    "2464": ["其他電子業", "設備工程", "自動化"],
    "5351": ["半導體業", "DRAM", "IC設計"],
}


INDUSTRY_ALIAS = {
    "Semiconductor": "半導體業",
    "OtherElectronics": "其他電子業",
    "ComputerPeripherals": "電腦及週邊設備業",
    "ElectronicParts": "電子零組件業",
    "Chemical": "化學工業",
    "GlassCeramic": "玻璃陶瓷",
    "Optics": "光電業",
    "Semi": "半導體業",
}


def localize_industry(industry: str) -> str:
    return INDUSTRY_ALIAS.get(industry, industry or "未分類")


def apply_theme_mapping(snapshot: StockSnapshot) -> StockSnapshot:
    official_industry = localize_industry(snapshot.official_industry or snapshot.industry)
    mapped = THEME_MAP.get(snapshot.code, [])
    primary_theme = mapped[0] if mapped else (snapshot.primary_theme or None)
    existing = [localize_industry(theme) for theme in snapshot.themes]
    existing = [theme for theme in existing if theme not in {"Unclassified", "未分類", ""}]
    themes = list(dict.fromkeys([*(mapped or []), *existing]))
    return snapshot.model_copy(
        update={
            "industry": official_industry,
            "official_industry": official_industry,
            "primary_theme": primary_theme,
            "industry_display_name": official_industry if official_industry not in {"Unclassified", ""} else "未分類",
            "themes": themes,
        }
    )


def apply_theme_mappings(snapshots: list[StockSnapshot]) -> list[StockSnapshot]:
    return [apply_theme_mapping(snapshot) for snapshot in snapshots]
