from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Direction = Literal["INFLOW", "OUTFLOW", "NEUTRAL"]
DataQualityBucket = Literal[
    "official_full",
    "official_intraday",
    "official_partial",
    "cache_only",
    "fallback",
    "seed",
    "mock",
    "stale",
    "unit_unknown",
]
SourceStatus = Literal["official", "official_intraday", "seed", "cache", "mock", "stale", "fallback", "unit_unknown"]


class Settings(BaseModel):
    auto_refresh: bool = True
    scan_interval_minutes: int = 5
    topic_min_net_yi: float = 5
    topic_min_delta_yi: float = 1
    repeat_delta_yi: float = 3
    stock_min_value_yi: float = 1
    stock_min_delta_yi: float = 0.3
    min_value_delta_yi: float = 0.05
    stale_seconds: int = 600
    net_near_zero_ratio: float = 0.08
    only_official_full: bool = False
    show_cache_warning: bool = True
    discord_webhook_url: str = ""
    push_enabled: bool = False
    stock_signal_enabled: bool = True


class PublicSettings(BaseModel):
    auto_refresh: bool
    scan_interval_minutes: int
    topic_min_net_yi: float
    topic_min_delta_yi: float
    repeat_delta_yi: float
    stock_min_value_yi: float
    stock_min_delta_yi: float
    min_value_delta_yi: float
    stale_seconds: int
    net_near_zero_ratio: float
    only_official_full: bool
    show_cache_warning: bool
    push_enabled: bool
    stock_signal_enabled: bool
    discord_webhook_configured: bool
    discord_webhook_masked: str = ""
    masked_webhook_url: str = ""


class NormalizedSnapshot(BaseModel):
    price_twd: float
    volume_shares: int
    volume_lots: float
    trade_value_twd: float
    trade_value_yi: float
    vwap_twd: float | None
    unit_ok: bool
    unit_error: str | None = None


class StockSnapshot(BaseModel):
    code: str
    name: str
    market: Literal["TSE", "OTC"]
    industry: str
    official_industry: str | None = None
    primary_theme: str | None = None
    industry_display_name: str | None = None
    themes: list[str] = Field(default_factory=list)
    price: float
    previous_close: float
    open: float
    high: float
    low: float
    change_pct: float
    volume: int
    trade_value: float
    trade_value_yi: float
    timestamp: datetime
    source_ts: datetime | None = None
    generated_at: datetime | None = None
    market_date: str | None = None
    market_data_time: datetime | None = None
    data_latency_seconds: int | None = None
    is_realtime: bool = False
    is_intraday: bool = False
    realtime_provider: str | None = None
    data_quality_bucket: DataQualityBucket = "official_full"
    formal_grade: bool = True
    formal_grade_label: Literal["formal", "estimated", "cache", "blocked"] = "formal"
    provider_type: str = "official_full"
    source_status: SourceStatus = "official"
    blocked_reason: str | None = None
    vwap_twd: float | None = None
    units_normalized: bool = True


class StockFlow(BaseModel):
    code: str
    name: str
    price: float
    change_pct: float
    trade_value_yi: float
    direction: Direction
    signed_flow_yi: float
    display_signed_flow_yi: float
    delta_signed_flow_yi: float
    direction_reason: str
    prev_price: float | None = None
    price_delta: float = 0
    short_return_pct: float = 0
    volume_delta: int = 0
    value_delta_yi: float = 0
    timestamp: datetime
    themes: list[str] = Field(default_factory=list)
    industry: str = ""
    official_industry: str | None = None
    primary_theme: str | None = None
    industry_display_name: str | None = None
    data_quality_bucket: DataQualityBucket = "official_full"
    formal_grade: bool = True
    blocked_reason: str | None = None
    trade_date: str | None = None
    quote_time: datetime | None = None
    last_price: float | None = None
    change: float | None = None
    turnover: float | None = None
    flow_direction: Direction | None = None
    flow_amount: float | None = None
    data_source: str | None = None
    freshness_status: str | None = None
    divergence_reason: str | None = None


class ImpactStock(BaseModel):
    code: str
    name: str
    price: float
    change_pct: float
    direction: Direction
    signed_flow_yi: float
    display_signed_flow_yi: float
    stock_flow_proxy_amount: float = 0
    delta_signed_flow_yi: float
    previous_delta_proxy_amount: float = 0
    value_delta_yi: float = 0
    impact_pct: float
    contribution_ratio: float = 0
    quote_time: datetime | None = None


class TopicFlow(BaseModel):
    topic_name: str
    topic_type: Literal["industry", "theme", "custom"]
    inflow_yi: float
    outflow_yi: float
    net_yi: float
    delta_inflow_yi: float
    delta_outflow_yi: float
    delta_net_yi: float
    abs_total_yi: float
    direction: Direction
    concentration_pct: float
    top_impacts: list[ImpactStock]
    signal_score: int
    signal_level: Literal["weak", "normal", "strong", "very_strong"]
    timestamp: datetime
    data_quality_bucket: DataQualityBucket = "official_full"
    formal_grade: bool = True
    blocked_reason: str | None = None
    affected_stock_count: int = 0
    same_direction_count: int = 1
    net_near_zero: bool = False
    strong_stock_count: int = 0
    weak_stock_count: int = 0
    top1_contribution_pct: float = 0
    ex_top1_net_yi: float = 0
    median_delta_flow_yi: float = 0
    up_count: int = 0
    down_count: int = 0
    median_flow_yi: float = 0
    trimmed_net_flow_yi: float = 0
    top_stock_concentration_pct: float = 0


class TopicState(BaseModel):
    topic_name: str
    last_direction: Direction = "NEUTRAL"
    same_direction_count: int = 0
    last_net_yi: float = 0
    last_abs_total_yi: float = 0
    last_emit_at: datetime | None = None
    last_formal_grade: bool = False
    last_data_quality_bucket: DataQualityBucket = "seed"


class SignalEvent(BaseModel):
    id: str
    timestamp: datetime
    target_type: Literal["stock", "topic"]
    target_id: str
    event_type: str = "flow_signal"
    fingerprint: str = ""
    market_date: str | None = None
    source_ts: datetime | None = None
    direction: Direction
    amount_yi: float
    net_yi: float
    previous_net_yi: float
    delta_from_previous_yi: float
    price: float | None = None
    change_pct: float | None = None
    score: int
    message: str
    related_stocks: list[ImpactStock] = Field(default_factory=list)
    top_impacts_snapshot: list[ImpactStock] = Field(default_factory=list)
    topic_name: str | None = None
    topic_net_yi_at_emit: float | None = None
    topic_delta_net_yi_at_emit: float | None = None
    topic_inflow_yi_at_emit: float | None = None
    topic_outflow_yi_at_emit: float | None = None
    stock_price_at_emit: float | None = None
    stock_change_pct_at_emit: float | None = None
    stock_amount_yi_at_emit: float | None = None
    impact_pct_at_emit: float | None = None
    data_quality_bucket_at_emit: DataQualityBucket | None = None
    formal_grade_at_emit: bool | None = None
    blocked_reason_at_emit: str | None = None
    signal_level: str = "normal"
    data_quality_bucket: DataQualityBucket = "official_full"
    formal_grade: bool = True
    blocked_reason: str | None = None
    direction_reason: str | None = None
    is_formal_push_allowed: bool = True
    sent_count: int = 0
    discord_sent_at: datetime | None = None
    explain_flags: list[str] = Field(default_factory=list)


class ScanDebugSummary(BaseModel):
    scan_started_at: datetime
    scan_finished_at: datetime | None = None
    market_date: str
    source_used: str
    source_status: str = "unknown"
    source_ts: datetime | None = None
    market_data_time: datetime | None = None
    data_latency_seconds: int | None = None
    is_realtime: bool = False
    is_intraday: bool = False
    realtime_provider: str | None = None
    result_count: int = 0
    twse_count: int = 0
    tpex_count: int = 0
    realtime_count: int = 0
    excluded_count: int = 0
    sent_count: int = 0
    skipped_duplicate_count: int = 0
    skipped_non_formal_count: int = 0
    stale_count: int = 0
    official_full_count: int = 0
    fallback_count: int = 0
    error_count: int = 0
    errors: list[str] = Field(default_factory=list)


class DiscordQueueItem(BaseModel):
    id: str
    fingerprint: str
    signal_id: str
    target_id: str
    status: Literal["pending", "sent", "failed", "skipped_non_formal"]
    payload: SignalEvent
    retry_count: int = 0
    next_retry_at: datetime | None = None
    discord_response_code: int | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class AlertRule(BaseModel):
    id: str
    name: str
    enabled: bool = True
    channel: Literal["discord"] = "discord"
    min_abs_net_yi: float = 5
    min_delta_yi: float = 1
    official_full_only: bool = True
    created_at: datetime
    updated_at: datetime


class UserPreferences(BaseModel):
    id: str = "local"
    official_full_only: bool = False
    show_non_formal_warning: bool = True
    default_stock_query: str = "3035"
    updated_at: datetime | None = None


class DeviceRegistration(BaseModel):
    id: str
    device_name: str
    platform: Literal["web", "desktop", "ios", "android", "other"] = "web"
    sync_status: Literal["local_only", "sync_ready"] = "local_only"
    created_at: datetime
    updated_at: datetime


class MarketFlowDTO(BaseModel):
    estimated_inflow_yi: float
    estimated_outflow_yi: float
    estimated_net_yi: float
    estimated_delta_yi: float
    market_inflow_proxy_amount: float = 0
    market_outflow_proxy_amount: float = 0
    market_net_proxy_amount: float = 0
    market_delta_proxy_amount: float = 0
    timestamp: datetime | None = None
    data_quality_bucket: DataQualityBucket
    formal_grade: bool
    blocked_reason: str | None = None
    push_blocked_reason: str | None = None
    is_realtime: bool = False
    is_intraday: bool = False
    market_data_time: datetime | None = None
    data_latency_seconds: int | None = None
    realtime_provider: str | None = None
    scan_id: str | None = None
    snapshot_id: str | None = None
    batch_label: str | None = None


class MarketStatusDTO(BaseModel):
    session_status: Literal["preopen", "regular", "after_close", "closed", "unknown"]
    session_label: str
    freshness_status: Literal["即時行情", "準即時觀察", "延遲", "收盤", "盤前", "休市", "資料暫停"]
    monitoring_mode: Literal["authorized_realtime", "public_proxy", "delayed", "closed", "paused"] = "paused"
    is_realtime_monitoring: bool
    market_data_time: datetime | None = None
    last_scan_at: datetime | None = None
    next_scan_at: datetime | None = None
    reason: str
    user_message: str
    scan_id: str | None = None
    snapshot_id: str | None = None
    batch_label: str | None = None


class RankingItemDTO(BaseModel):
    stock_id: str | None = None
    stock_name: str | None = None
    code: str
    name: str
    price: float | None = None
    last_price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    trade_date: str | None = None
    quote_time: datetime | None = None
    turnover: float | None = None
    direction: Direction
    flow_direction: Direction | None = None
    net_yi: float
    flow_amount: float | None = None
    inflow_yi: float = 0
    outflow_yi: float = 0
    display_signed_flow_yi: float = 0
    stock_flow_proxy_amount: float = 0
    delta_yi: float | None = None
    delta_signed_flow_yi: float | None = None
    previous_delta_proxy_amount: float | None = None
    impact_pct: float | None = None
    contribution_ratio: float | None = None
    relative_flow_ratio: float | None = None
    relative_flow_pct: float | None = None
    relative_basis: str | None = None
    sector_abs_total_yi: float | None = None
    sector_strength_pct: float | None = None
    topics: list[str] = Field(default_factory=list)
    official_industry: str | None = None
    primary_theme: str | None = None
    display_group: str | None = None
    data_quality_bucket: DataQualityBucket
    formal_grade: bool
    blocked_reason: str | None = None
    data_source: str | None = None
    freshness_status: str | None = None
    flow_label: str | None = None
    divergence_reason: str | None = None
    timestamp: datetime | None = None


class TopicCardDTO(BaseModel):
    topic_name: str
    topic_type: Literal["industry", "theme", "custom"]
    direction: Direction
    net_yi: float
    topic_net_proxy_amount: float = 0
    delta_net_yi: float
    previous_delta_proxy_amount: float = 0
    last_net_yi: float | None = None
    inflow_yi: float
    outflow_yi: float
    concentration_pct: float
    top_stock_concentration_pct: float
    strong_stock_count: int
    weak_stock_count: int
    up_count: int
    down_count: int
    radar_score: int
    signal_level: str
    same_direction_count: int
    data_quality_bucket: DataQualityBucket
    formal_grade: bool
    blocked_reason: str | None = None
    top_impacts: list[ImpactStock] = Field(default_factory=list)
    timestamp: datetime


class SignalCardDTO(BaseModel):
    id: str
    topic_name: str
    target_type: Literal["stock", "topic"]
    signal_level: str
    timestamp: datetime
    direction: Direction
    price: float | None = None
    change_pct: float | None = None
    amount_yi: float
    stock_flow_proxy_amount: float = 0
    delta_yi: float
    previous_delta_proxy_amount: float = 0
    topic_net_yi: float
    topic_net_proxy_amount: float = 0
    topic_delta_net_yi: float
    impact_pct: float = 0
    contribution_ratio: float = 0
    data_quality_bucket: DataQualityBucket
    formal_grade: bool
    blocked_reason: str | None = None


class ProviderResult(BaseModel):
    snapshots: list[StockSnapshot] = Field(default_factory=list)
    source_used: str
    source_status: Literal["official_full", "official_intraday", "official_partial", "fallback", "seed", "failed"]
    source_ts: datetime | None = None
    market_data_time: datetime | None = None
    data_latency_seconds: int | None = None
    is_realtime: bool = False
    is_intraday: bool = False
    realtime_provider: str | None = None
    twse_count: int = 0
    tpex_count: int = 0
    realtime_count: int = 0
    excluded_count: int = 0
    errors: list[str] = Field(default_factory=list)
