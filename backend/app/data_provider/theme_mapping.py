from __future__ import annotations

from app.storage.models import StockSnapshot


UNCLASSIFIED = {"", "Unclassified", "未分類"}


THEME_MAP: dict[str, list[str]] = {
    "1727": ["化學工業", "半導體材料", "車用化學"],
    "1802": ["玻璃陶瓷", "玻璃", "建材"],
    "2308": ["電子零組件業", "電源", "AI伺服器", "車用電子"],
    "2317": ["其他電子業", "AI伺服器", "GB200", "車用電子", "低軌衛星"],
    "2327": ["電子零組件業", "被動元件", "車用電子"],
    "2330": ["半導體業", "晶圓代工", "CoWoS", "AI晶片"],
    "2344": ["半導體業", "DRAM", "HBM記憶體"],
    "2345": ["通信網路業", "低軌衛星", "網通"],
    "2356": ["電腦及週邊設備業", "AI伺服器"],
    "2382": ["電腦及週邊設備業", "AI伺服器", "GB200"],
    "2408": ["半導體業", "DRAM", "HBM記憶體"],
    "2454": ["半導體業", "IC設計", "AI晶片", "車用晶片"],
    "2464": ["其他電子業", "電子材料", "航太"],
    "2481": ["半導體業", "分離式元件", "車用電子"],
    "2603": ["航運業", "貨櫃航運"],
    "2887": ["金融保險業", "金控"],
    "2891": ["金融保險業", "金控"],
    "2892": ["金融保險業", "金控"],
    "3006": ["半導體業", "IC設計", "記憶體"],
    "3008": ["光電業", "鏡頭"],
    "3035": ["半導體業", "IC設計", "車用晶片", "ASIC"],
    "3081": ["通信網路業", "光通訊", "矽光子"],
    "3167": ["電機機械", "PCB設備", "設備股"],
    "3231": ["電腦及週邊設備業", "AI伺服器", "GB200"],
    "3661": ["半導體業", "ASIC", "AI晶片"],
    "3701": ["電腦及週邊設備業", "AI伺服器", "GB200"],
    "4938": ["電腦及週邊設備業", "伺服器"],
    "5351": ["半導體業", "DRAM", "IC設計"],
    "6223": ["半導體業", "探針卡", "先進封裝"],
    "6239": ["半導體業", "封測", "HBM記憶體"],
    "6510": ["半導體業", "測試介面", "先進封裝"],
    "6531": ["半導體業", "IC設計", "記憶體"],
    "6658": ["電子零組件業", "PCB", "AI伺服器"],
    "6683": ["半導體業", "測試介面", "IC測試"],
    "8046": ["電子零組件業", "ABF載板", "AI伺服器"],
    "8064": ["半導體業", "設備股", "面板設備"],
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
    "Financial": "金融保險業",
    "Shipping": "航運業",
}


def localize_industry(industry: str | None) -> str:
    value = str(industry or "").strip()
    return INDUSTRY_ALIAS.get(value, value or "未分類")


def _clean_theme(theme: str | None) -> str:
    value = localize_industry(theme)
    return "" if value in UNCLASSIFIED else value


def apply_theme_mapping(snapshot: StockSnapshot) -> StockSnapshot:
    official_industry = localize_industry(snapshot.official_industry or snapshot.industry)
    mapped = THEME_MAP.get(snapshot.code, [])
    primary_theme = mapped[0] if mapped else (snapshot.primary_theme or None)
    existing = [_clean_theme(theme) for theme in snapshot.themes]
    themes = list(dict.fromkeys([*(mapped or []), *[theme for theme in existing if theme]]))
    display_name = official_industry if official_industry not in UNCLASSIFIED else "未分類"
    return snapshot.model_copy(
        update={
            "industry": official_industry,
            "official_industry": official_industry,
            "primary_theme": primary_theme,
            "industry_display_name": display_name,
            "themes": themes,
        }
    )


def apply_theme_mappings(snapshots: list[StockSnapshot]) -> list[StockSnapshot]:
    return [apply_theme_mapping(snapshot) for snapshot in snapshots]
