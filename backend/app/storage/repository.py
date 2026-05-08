from __future__ import annotations

from datetime import datetime
from threading import Lock

from app.data_provider.provider_orchestrator import fetch_market_snapshots
from app.data_provider.seed_data import build_seed_snapshots
from app.data_provider.theme_mapping import apply_theme_mappings
from app.engine.direction_engine import infer_direction
from app.engine.quality import apply_snapshot_quality
from app.engine.signal_engine import build_stock_signal, build_topic_signal, should_emit_stock_signal, should_emit_topic_signal
from app.engine.topic_aggregator import aggregate_topics
from app.notifier.notification_service import NotificationService
from app.storage.models import MarketFlowDTO, MarketStatusDTO, RankingItemDTO, ScanDebugSummary, Settings, SignalCardDTO, SignalEvent, StockFlow, StockSnapshot, TopicCardDTO, TopicFlow, TopicState
from app.storage.sqlite_store import SQLiteStore
from app.time_utils import ensure_taipei, is_regular_tw_session, market_date, taipei_now

FORMAL_SOURCE_STATUSES = {"official_full", "official_intraday"}


class InMemoryRepository:
    def __init__(self, *, store: SQLiteStore | None = None, use_provider: bool = True) -> None:
        self.settings = Settings()
        self.store = store or SQLiteStore()
        self.notifications = NotificationService(self.store)
        stored_settings = self.store.load_settings()
        if stored_settings:
            self.settings = stored_settings
        self.use_provider = use_provider
        if self.use_provider:
            self.previous_snapshots: dict[str, StockSnapshot] = {}
            self.snapshots: dict[str, StockSnapshot] = {}
        else:
            prev, cur = build_seed_snapshots()
            prev = apply_theme_mappings(prev)
            cur = apply_theme_mappings(cur)
            self.previous_snapshots = {s.code: s for s in prev}
            self.snapshots = {s.code: s for s in cur}
        self.stock_flows: dict[str, StockFlow] = {}
        self.topic_flows: dict[str, TopicFlow] = {}
        self.topic_states: dict[str, TopicState] = self.store.load_topic_states()
        self.signals: list[SignalEvent] = self.store.load_signals()
        self.last_scan_at: datetime | None = None
        self.last_debug_summary: ScanDebugSummary | None = self.store.load_latest_scan()
        self._scan_lock = Lock()
        if not self.use_provider:
            self.scan()

    def refresh_snapshots_from_provider(self) -> ScanDebugSummary:
        if not self.use_provider:
            now = taipei_now()
            return ScanDebugSummary(
                scan_started_at=now,
                market_date=market_date(now),
                source_used="seed_provider",
                source_status="seed",
                source_ts=max((s.source_ts or s.timestamp for s in self.snapshots.values()), default=None),
                result_count=len(self.snapshots),
                errors=["provider_disabled_for_test_or_dev"],
                error_count=1,
            )
        provider_result = fetch_market_snapshots()
        if provider_result.snapshots:
            self.previous_snapshots = self.snapshots or self.previous_snapshots
            self.snapshots = {s.code: s for s in provider_result.snapshots}
        now = taipei_now()
        return ScanDebugSummary(
            scan_started_at=now,
            market_date=market_date(now),
            source_used=provider_result.source_used,
            source_status=provider_result.source_status,
            source_ts=provider_result.source_ts,
            market_data_time=provider_result.market_data_time,
            data_latency_seconds=provider_result.data_latency_seconds,
            is_realtime=provider_result.is_realtime,
            is_intraday=provider_result.is_intraday,
            realtime_provider=provider_result.realtime_provider,
            result_count=len(provider_result.snapshots),
            twse_count=provider_result.twse_count,
            tpex_count=provider_result.tpex_count,
            realtime_count=provider_result.realtime_count,
            excluded_count=provider_result.excluded_count,
            errors=provider_result.errors,
            error_count=len(provider_result.errors),
        )

    def scan(self) -> None:
        if not self._scan_lock.acquire(blocking=False):
            return
        summary = self.refresh_snapshots_from_provider()
        started = summary.scan_started_at
        try:
            qualified_snapshots = {
                code: apply_snapshot_quality(snapshot, now=started, stale_seconds=self.settings.stale_seconds)
                for code, snapshot in self.snapshots.items()
            }
            summary.result_count = len(qualified_snapshots)
            summary.stale_count = sum(1 for s in qualified_snapshots.values() if s.data_quality_bucket == "stale")
            summary.official_full_count = sum(1 for s in qualified_snapshots.values() if s.data_quality_bucket in {"official_full", "official_intraday"} and s.formal_grade)
            summary.fallback_count = sum(1 for s in qualified_snapshots.values() if s.data_quality_bucket in {"fallback", "seed", "cache_only", "mock", "unit_unknown"})

            self.stock_flows = {
                code: infer_direction(
                    snapshot,
                    self.previous_snapshots.get(code),
                    self.stock_flows.get(code),
                    min_value_delta_yi=self.settings.min_value_delta_yi,
                )
                for code, snapshot in qualified_snapshots.items()
            }
            previous_states = dict(self.topic_states)
            topics, next_states = aggregate_topics(
                list(self.stock_flows.values()),
                timestamp=started,
                topic_states=previous_states,
                net_near_zero_ratio=self.settings.net_near_zero_ratio,
            )
            self.topic_states = next_states
            self.topic_flows = {t.topic_name: t for t in topics}

            topic_impact_codes = {impact.code for topic in topics for impact in topic.top_impacts}
            emitted_signals: list[SignalEvent] = []
            for topic in topics:
                previous_state = previous_states.get(topic.topic_name)
                recent = self._latest_signal("topic", topic.topic_name)
                should_emit, blocked_reason = should_emit_topic_signal(topic, previous_state, recent, self.settings)
                if should_emit:
                    signal = build_topic_signal(topic, previous_state)
                    emitted_signals.append(signal)
                    self.topic_states[topic.topic_name].last_emit_at = signal.timestamp
                elif blocked_reason and recent is None and abs(topic.net_yi) >= self.settings.topic_min_net_yi:
                    summary.skipped_non_formal_count += 1
                    emitted_signals.append(build_topic_signal(topic, previous_state, blocked_reason=blocked_reason))
                elif blocked_reason:
                    summary.skipped_non_formal_count += 1

            for flow in self.stock_flows.values():
                recent = self._latest_signal("stock", flow.code)
                should_emit, blocked_reason = should_emit_stock_signal(flow, topic_impact_codes, recent, self.settings)
                if should_emit:
                    emitted_signals.append(build_stock_signal(flow))
                elif blocked_reason and recent is None and flow.trade_value_yi >= self.settings.stock_min_value_yi:
                    summary.skipped_non_formal_count += 1
                    emitted_signals.append(build_stock_signal(flow, blocked_reason=blocked_reason))
                elif blocked_reason:
                    summary.skipped_non_formal_count += 1

            known_fingerprints = {s.fingerprint for s in self.signals if s.fingerprint}
            for signal in emitted_signals:
                if signal.fingerprint and signal.fingerprint in known_fingerprints:
                    summary.skipped_duplicate_count += 1
                    continue
                self.signals.insert(0, signal)
                self.store.append_signal(signal)
                known_fingerprints.add(signal.fingerprint)
                can_send, blocked_reason = self.can_send_discord(signal)
                if self.settings.push_enabled:
                    self.notifications.enqueue_signal(signal, can_send=can_send, blocked_reason=blocked_reason)
            self.store.save_topic_states(self.topic_states)
            self.last_scan_at = started
        except Exception as exc:
            summary.error_count += 1
            summary.errors.append(type(exc).__name__)
            raise
        finally:
            summary.scan_finished_at = taipei_now()
            self.last_debug_summary = summary
            self.store.save_latest_scan(summary)
            self._scan_lock.release()

    def _latest_signal(self, target_type: str, target_id: str) -> SignalEvent | None:
        return next((s for s in self.signals if s.target_type == target_type and s.target_id == target_id), None)

    def update_settings(self, settings: Settings) -> Settings:
        previous_webhook = self.settings.discord_webhook_url
        if settings.discord_webhook_url == "__KEEP_EXISTING__":
            settings.discord_webhook_url = previous_webhook
        self.settings = settings
        self.store.save_settings(settings)
        return self.settings

    def can_send_discord(self, signal: SignalEvent) -> tuple[bool, str | None]:
        source_status = self.last_debug_summary.source_status if self.last_debug_summary else "unknown"
        if source_status not in FORMAL_SOURCE_STATUSES:
            return False, "data_source_not_official_full"
        if not signal.is_formal_push_allowed or not signal.formal_grade:
            return False, signal.blocked_reason or "signal_not_formal"
        if not signal.fingerprint:
            return False, "missing_signal_fingerprint"
        if self.store.was_discord_sent(signal.fingerprint):
            return False, "duplicate_signal_fingerprint"
        return True, None

    def mark_discord_sent(self, signal: SignalEvent) -> SignalEvent:
        marked = self.store.mark_discord_sent(signal)
        self.signals = [marked if s.id == signal.id else s for s in self.signals]
        self.store.append_signal(marked)
        if self.last_debug_summary:
            self.last_debug_summary.sent_count += 1
            self.store.save_latest_scan(self.last_debug_summary)
        return marked

    def dashboard(self, *, official_full_only: bool = False) -> dict:
        rankings = self.rankings(official_full_only=official_full_only)
        source_status = self.last_debug_summary.source_status if self.last_debug_summary else "unknown"
        market_flow = self.market_flow()
        return {
            "updated_at": self.last_scan_at,
            "stock_signal_enabled": self.settings.stock_signal_enabled,
            "observation_mode": not market_flow.formal_grade,
            "push_blocked_reason": market_flow.push_blocked_reason,
            "topic_inflow_top5": rankings["topic_inflow_top50"][:5],
            "topic_outflow_top5": rankings["topic_outflow_top50"][:5],
            "stock_inflow_top5": rankings["stock_inflow_top50"][:5],
            "stock_outflow_top5": rankings["stock_outflow_top50"][:5],
            "stock_inflow_top50": rankings["stock_inflow_top50"],
            "stock_outflow_top50": rankings["stock_outflow_top50"],
            "unusual_value_top50": rankings["unusual_value_top50"],
            "relative_flow_proxy_top50": rankings["relative_flow_proxy_top50"],
            "sector_strength_top": rankings["sector_strength_top"],
            "topic_cards": self._topic_cards(
                sorted([t for t in self.topic_flows.values() if t.net_yi > 0], key=lambda x: x.net_yi, reverse=True)[:50],
                sorted([t for t in self.topic_flows.values() if t.net_yi < 0], key=lambda x: x.net_yi)[:50],
            )[:30],
            "latest_signals": rankings["latest_signals"],
        }

    def _topic_cards(self, inflow_topics: list[TopicFlow], outflow_topics: list[TopicFlow]) -> list[TopicCardDTO]:
        merged = sorted([*inflow_topics, *outflow_topics], key=lambda topic: abs(topic.net_yi), reverse=True)
        cards: list[TopicCardDTO] = []
        for topic in merged:
            previous_net = topic.net_yi - topic.delta_net_yi
            cards.append(
                TopicCardDTO(
                    topic_name=topic.topic_name,
                    topic_type=topic.topic_type,
                    direction=topic.direction,
                    net_yi=topic.net_yi,
                    topic_net_proxy_amount=topic.net_yi,
                    delta_net_yi=topic.delta_net_yi,
                    previous_delta_proxy_amount=topic.delta_net_yi,
                    inflow_yi=topic.inflow_yi,
                    outflow_yi=topic.outflow_yi,
                    concentration_pct=topic.concentration_pct,
                    top_stock_concentration_pct=topic.top_stock_concentration_pct,
                    strong_stock_count=topic.strong_stock_count,
                    weak_stock_count=topic.weak_stock_count,
                    up_count=topic.up_count,
                    down_count=topic.down_count,
                    radar_score=topic.signal_score,
                    signal_level=topic.signal_level,
                    same_direction_count=topic.same_direction_count,
                    data_quality_bucket=topic.data_quality_bucket,
                    formal_grade=topic.formal_grade,
                    blocked_reason=topic.blocked_reason,
                    last_net_yi=round(previous_net, 2),
                    top_impacts=topic.top_impacts,
                    timestamp=topic.timestamp,
                )
            )
        return cards

    def rankings(self, *, official_full_only: bool = False) -> dict:
        flows = self._main_ranking_flows(list(self.stock_flows.values()))
        topics, _ = aggregate_topics(
            flows,
            timestamp=self.last_scan_at or taipei_now(),
            topic_states=self.topic_states,
            net_near_zero_ratio=self.settings.net_near_zero_ratio,
        )
        signals = self._latest_signal_cards(self.signals)
        if official_full_only:
            topics = [t for t in topics if t.formal_grade and t.data_quality_bucket in {"official_full", "official_intraday"}]
            flows = [f for f in flows if f.formal_grade and f.data_quality_bucket in {"official_full", "official_intraday"}]
            signals = [s for s in signals if s.formal_grade and s.data_quality_bucket in {"official_full", "official_intraday"}]
        return {
            "updated_at": self.last_scan_at,
            "ranking_basis": {
                "stock_inflow_top50": "display_signed_flow_yi cumulative estimated_flow descending",
                "stock_outflow_top50": "display_signed_flow_yi cumulative estimated_flow ascending",
                "unusual_value_top50": "absolute delta_signed_flow_yi current scan increment",
                "relative_flow_proxy_top50": "absolute delta_signed_flow_yi divided by previous snapshot trade_value_yi proxy; not a 20d average",
                "sector_strength_top": "stock absolute display flow share within official industry abs_total_yi",
            },
            "stock_signal_enabled": self.settings.stock_signal_enabled,
            "topic_inflow_top50": self._topic_cards(sorted([t for t in topics if t.net_yi > 0], key=lambda x: x.net_yi, reverse=True)[:50], []),
            "topic_outflow_top50": self._topic_cards([], sorted([t for t in topics if t.net_yi < 0], key=lambda x: x.net_yi)[:50]),
            "stock_inflow_top50": [self._flow_dto(f) for f in sorted([f for f in flows if f.display_signed_flow_yi > 0], key=lambda x: x.display_signed_flow_yi, reverse=True)[:50]],
            "stock_outflow_top50": [self._flow_dto(f) for f in sorted([f for f in flows if f.display_signed_flow_yi < 0], key=lambda x: x.display_signed_flow_yi)[:50]],
            "unusual_value_top50": [self._flow_dto(f) for f in sorted(flows, key=lambda x: abs(x.delta_signed_flow_yi), reverse=True)[:50]],
            "relative_flow_proxy_top50": self._relative_flow_top(flows)[:50],
            "sector_strength_top": self._sector_strength_top(topics, flows)[:50],
            "latest_signals": signals,
        }

    def _latest_signal_cards(self, signals: list[SignalEvent]) -> list[SignalEvent]:
        normalized: list[SignalEvent] = []
        for signal in signals:
            quote_time = None
            if signal.target_type == "stock":
                flow = self.stock_flows.get(signal.target_id)
                quote_time = flow.quote_time if flow else None
                if not quote_time:
                    snapshot = self.snapshots.get(signal.target_id)
                    quote_time = snapshot.market_data_time or snapshot.source_ts if snapshot else None
            elif signal.target_type == "topic":
                topic = self.topic_flows.get(signal.target_id)
                if topic:
                    quote_time = max((impact.quote_time for impact in topic.top_impacts if impact.quote_time), default=None)
            if not quote_time:
                quote_time = signal.source_ts
            if signal.source_ts is None or ensure_taipei(signal.source_ts) == ensure_taipei(signal.timestamp):
                signal = signal.model_copy(update={"source_ts": quote_time})
            if self._is_fresh_signal_alert(signal):
                normalized.append(signal)
            if len(normalized) >= 20:
                break
        return normalized

    def _is_fresh_signal_alert(self, signal: SignalEvent) -> bool:
        if signal.source_ts is None:
            return False
        signal_time = ensure_taipei(signal.timestamp)
        source_time = ensure_taipei(signal.source_ts)
        if market_date(signal_time) != market_date(source_time):
            return False
        max_signal_source_lag = max(self.settings.stale_seconds, self.settings.scan_interval_minutes * 60 + 60)
        return abs((signal_time - source_time).total_seconds()) <= max_signal_source_lag

    def _main_ranking_flows(self, flows: list[StockFlow]) -> list[StockFlow]:
        """Keep stale or wrong-date quotes out of the public TOP lists.

        Official daily/closing data can still be shown as observation mode, but
        intraday stale quotes and mismatched trade dates must not drive the main
        rankings.
        """

        now = taipei_now()
        reference_time = self.last_scan_at or now
        today = market_date(reference_time)
        eligible: list[StockFlow] = []
        for flow in flows:
            snapshot = self.snapshots.get(flow.code)
            if not snapshot:
                continue
            quote_date = snapshot.market_date or market_date(snapshot.market_data_time or snapshot.source_ts or snapshot.timestamp)
            if quote_date != today:
                continue
            blocked_reason = snapshot.blocked_reason or flow.blocked_reason or ""
            if snapshot.data_quality_bucket == "stale" or blocked_reason.startswith(("stale_timestamp", "market_date_mismatch")):
                continue
            if is_regular_tw_session(now) and snapshot.data_latency_seconds is not None and snapshot.data_latency_seconds > self.settings.stale_seconds:
                continue
            eligible.append(flow)
        return eligible

    def _freshness_status(self, snapshot: StockSnapshot | None) -> str:
        if not snapshot:
            return "暫緩"
        if snapshot.data_quality_bucket == "stale":
            return "暫緩"
        if snapshot.is_realtime and snapshot.data_latency_seconds is not None and snapshot.data_latency_seconds <= self.settings.stale_seconds:
            return "即時"
        if snapshot.market_data_time and not is_regular_tw_session(snapshot.market_data_time):
            return "收盤"
        if snapshot.provider_type == "official_partial":
            return "收盤" if not is_regular_tw_session(taipei_now()) else "延遲"
        return "延遲"

    def _flow_label(self, flow: StockFlow, change: float) -> tuple[str, str | None]:
        if flow.direction == "NEUTRAL":
            return "中性", None
        direction_text = "推估流入" if flow.direction == "INFLOW" else "推估流出"
        if change >= 0 and flow.direction == "OUTFLOW" and abs(change) >= max(flow.price * 0.05, 0):
            return "資金分歧", "price_limit_up_or_strong_gain_but_proxy_outflow"
        if change <= 0 and flow.direction == "INFLOW" and abs(change) >= max(flow.price * 0.05, 0):
            return "資金分歧", "price_sharp_drop_but_proxy_inflow"
        return direction_text, None

    def _flow_dto(self, flow: StockFlow) -> RankingItemDTO:
        snapshot = self.snapshots.get(flow.code)
        price = snapshot.price if snapshot else flow.price
        previous_close = snapshot.previous_close if snapshot else (price - flow.price_delta if price is not None else 0)
        change = round((price or 0) - (previous_close or 0), 2)
        change_pct = snapshot.change_pct if snapshot else flow.change_pct
        quote_time = snapshot.market_data_time or snapshot.source_ts or snapshot.timestamp if snapshot else flow.quote_time or flow.timestamp
        trade_date = snapshot.market_date if snapshot else flow.trade_date
        turnover = snapshot.trade_value_yi if snapshot else flow.trade_value_yi
        data_source = snapshot.realtime_provider or snapshot.provider_type if snapshot else flow.data_source
        freshness_status = self._freshness_status(snapshot)
        flow_label, divergence_reason = self._flow_label(flow, change)
        return RankingItemDTO(
            stock_id=flow.code,
            stock_name=flow.name,
            code=flow.code,
            name=flow.name,
            price=price,
            last_price=price,
            change=change,
            change_pct=change_pct,
            trade_date=trade_date,
            quote_time=quote_time,
            turnover=turnover,
            direction=flow.direction,
            flow_direction=flow.direction,
            net_yi=flow.display_signed_flow_yi,
            flow_amount=flow.display_signed_flow_yi,
            inflow_yi=flow.display_signed_flow_yi if flow.direction == "INFLOW" else 0,
            outflow_yi=abs(flow.display_signed_flow_yi) if flow.direction == "OUTFLOW" else 0,
            display_signed_flow_yi=flow.display_signed_flow_yi,
            stock_flow_proxy_amount=flow.display_signed_flow_yi,
            delta_yi=flow.delta_signed_flow_yi,
            delta_signed_flow_yi=flow.delta_signed_flow_yi,
            previous_delta_proxy_amount=flow.delta_signed_flow_yi,
            topics=list(dict.fromkeys([*([] if not flow.official_industry or flow.official_industry in {"Unclassified", "未分類"} else [flow.official_industry]), *flow.themes])),
            official_industry=flow.official_industry,
            primary_theme=flow.primary_theme,
            display_group=self._display_group(flow),
            data_quality_bucket=flow.data_quality_bucket,
            formal_grade=flow.formal_grade,
            blocked_reason=flow.blocked_reason,
            data_source=data_source,
            freshness_status=freshness_status,
            flow_label=flow_label,
            divergence_reason=divergence_reason,
            timestamp=flow.timestamp,
        )

    def _relative_flow_top(self, flows: list[StockFlow]) -> list[RankingItemDTO]:
        rows: list[RankingItemDTO] = []
        for flow in flows:
            previous = self.previous_snapshots.get(flow.code)
            baseline = abs(previous.trade_value_yi) if previous else 0
            if baseline <= 0:
                baseline = max(abs(flow.trade_value_yi - flow.value_delta_yi), 0.01)
            ratio = abs(flow.delta_signed_flow_yi) / baseline
            rows.append(
                self._flow_dto(flow).model_copy(
                    update={
                        "relative_flow_ratio": round(ratio, 4),
                        "relative_flow_pct": round(ratio * 100, 2),
                        "relative_basis": "previous_snapshot_trade_value_yi_proxy_not_20d_average",
                    }
                )
            )
        return sorted(rows, key=lambda row: row.relative_flow_ratio or 0, reverse=True)

    def _sector_strength_top(self, topics: list[TopicFlow], flows: list[StockFlow]) -> list[RankingItemDTO]:
        topic_by_name = {topic.topic_name: topic for topic in topics}
        rows: list[RankingItemDTO] = []
        for flow in flows:
            sector_key = flow.official_industry if flow.official_industry not in {"", "Unclassified", "未分類"} else self._display_group(flow)
            topic = topic_by_name.get(sector_key or "")
            if not topic or topic.abs_total_yi <= 0:
                continue
            rows.append(
                self._flow_dto(flow).model_copy(
                    update={
                        "sector_abs_total_yi": topic.abs_total_yi,
                        "sector_strength_pct": round(abs(flow.display_signed_flow_yi) / topic.abs_total_yi * 100, 2),
                    }
                )
            )
        return sorted(rows, key=lambda row: row.sector_strength_pct or 0, reverse=True)

    def _display_group(self, flow: StockFlow) -> str | None:
        if flow.official_industry and flow.official_industry not in {"Unclassified", "未分類"}:
            return flow.official_industry
        return flow.primary_theme or flow.industry_display_name or None

    def market_flow(self) -> MarketFlowDTO:
        flows = list(self.stock_flows.values())
        estimated_inflow = sum(abs(f.display_signed_flow_yi) for f in flows if f.direction == "INFLOW")
        estimated_outflow = sum(abs(f.display_signed_flow_yi) for f in flows if f.direction == "OUTFLOW")
        estimated_delta = sum(f.delta_signed_flow_yi for f in flows)
        source_status = self.last_debug_summary.source_status if self.last_debug_summary else "seed"
        data_quality = "official_full" if source_status == "official_full" else source_status
        if data_quality not in {"official_full", "official_intraday", "official_partial", "cache_only", "fallback", "seed", "mock", "stale", "unit_unknown"}:
            data_quality = "fallback"
        formal_count = sum(1 for f in flows if f.formal_grade and f.data_quality_bucket in {"official_full", "official_intraday"})
        formal_ratio = (formal_count / len(flows)) if flows else 0
        formal = data_quality in {"official_full", "official_intraday"} and formal_ratio >= 0.8
        if formal:
            push_blocked_reason = None
            blocked_reason = None
        elif data_quality in {"official_full", "official_intraday"}:
            push_blocked_reason = "intraday_coverage_not_fresh_enough"
            blocked_reason = f"intraday_coverage_not_fresh_enough:{formal_count}/{len(flows)}"
        else:
            push_blocked_reason = "data_source_not_official_full"
            blocked_reason = f"data_source_not_official_full:{source_status}"
        return MarketFlowDTO(
            estimated_inflow_yi=round(estimated_inflow, 2),
            estimated_outflow_yi=round(estimated_outflow, 2),
            estimated_net_yi=round(estimated_inflow - estimated_outflow, 2),
            estimated_delta_yi=round(estimated_delta, 2),
            market_inflow_proxy_amount=round(estimated_inflow, 2),
            market_outflow_proxy_amount=round(estimated_outflow, 2),
            market_net_proxy_amount=round(estimated_inflow - estimated_outflow, 2),
            market_delta_proxy_amount=round(estimated_delta, 2),
            timestamp=self.last_scan_at,
            data_quality_bucket=data_quality,  # type: ignore[arg-type]
            formal_grade=formal,
            blocked_reason=blocked_reason,
            push_blocked_reason=push_blocked_reason,
            is_realtime=bool(self.last_debug_summary and self.last_debug_summary.is_realtime),
            is_intraday=bool(self.last_debug_summary and self.last_debug_summary.is_intraday),
            market_data_time=self.last_debug_summary.market_data_time if self.last_debug_summary else None,
            data_latency_seconds=self.last_debug_summary.data_latency_seconds if self.last_debug_summary else None,
            realtime_provider=self.last_debug_summary.realtime_provider if self.last_debug_summary else None,
        )

    def market_status(self, *, next_scan_at: datetime | None = None) -> MarketStatusDTO:
        now = taipei_now()
        debug = self.last_debug_summary
        market_data_time = debug.market_data_time if debug else None
        if now.weekday() >= 5:
            session_status = "closed"
            session_label = "休市"
        elif now.time() < datetime.strptime("09:00", "%H:%M").time():
            session_status = "preopen"
            session_label = "盤前準備"
        elif is_regular_tw_session(now):
            session_status = "regular"
            session_label = "盤中監控"
        else:
            session_status = "after_close"
            session_label = "收盤觀察"

        if not market_data_time:
            freshness_status = "暫緩"
            is_realtime_monitoring = False
            reason = "no_market_data_time"
            user_message = "尚未取得行情資料，系統會在下一輪掃描後更新。"
        else:
            data_time = ensure_taipei(market_data_time)
            same_market_date = market_date(data_time) == market_date(now)
            latency = abs((now - data_time).total_seconds())
            if not same_market_date:
                freshness_status = "暫緩"
                is_realtime_monitoring = False
                reason = "market_data_not_today"
                user_message = "行情資料不是今日資料，暫停即時提醒。"
            elif session_status == "preopen":
                freshness_status = "盤前"
                is_realtime_monitoring = False
                reason = "market_not_open_yet"
                user_message = "尚未開盤，資金異動會在 09:00 後開始累積。"
            elif session_status == "regular":
                if debug and debug.is_realtime and latency <= self.settings.stale_seconds:
                    freshness_status = "即時"
                    is_realtime_monitoring = True
                    reason = "realtime_quotes_fresh"
                    user_message = "盤中監控中，最新資金異動只會使用新行情觸發。"
                elif latency <= self.settings.stale_seconds:
                    freshness_status = "延遲"
                    is_realtime_monitoring = False
                    reason = "source_not_realtime"
                    user_message = "目前是延遲或觀察資料，排行可參考，正式即時提醒暫停。"
                else:
                    freshness_status = "暫緩"
                    is_realtime_monitoring = False
                    reason = "market_data_stale"
                    user_message = "行情時間過舊，暫停最新資金異動提醒。"
            elif session_status == "after_close":
                freshness_status = "收盤"
                is_realtime_monitoring = False
                reason = "market_closed"
                user_message = "目前為收盤觀察資料，不列入即時提醒。"
            else:
                freshness_status = "休市"
                is_realtime_monitoring = False
                reason = "market_closed"
                user_message = "目前休市，僅保留最近行情觀察。"

        return MarketStatusDTO(
            session_status=session_status,
            session_label=session_label,
            freshness_status=freshness_status,
            is_realtime_monitoring=is_realtime_monitoring,
            market_data_time=market_data_time,
            last_scan_at=self.last_scan_at,
            next_scan_at=next_scan_at,
            reason=reason,
            user_message=user_message,
        )

    def stock_detail(self, code: str) -> dict | None:
        snapshot = self.snapshots.get(code)
        if not snapshot:
            query = code.strip().lower()
            aliases = {
                "智原": "3035",
                "鴻海": "2317",
                "聯發科": "2454",
                "台積電": "2330",
                "南電": "8046",
                "台玻": "1802",
                "中華化": "1727",
                "上緯投控": "3708",
                "聯策": "6658",
            }
            snapshot = self.snapshots.get(aliases.get(code.strip(), ""))
        if not snapshot:
            snapshot = next(
                (s for s in self.snapshots.values() if s.name.lower() == query or query in s.name.lower()),
                None,
            )
        if not snapshot:
            return None
        code = snapshot.code
        flow = self.stock_flows.get(code)
        stock_topics = [
            topic for topic in [snapshot.official_industry or snapshot.industry, *snapshot.themes]
            if topic and topic not in {"Unclassified", "未分類"}
        ]
        signal_history = [
            s for s in self.signals
            if s.target_id == code or any(i.code == code for i in s.related_stocks) or s.target_id in stock_topics
        ]
        enriched_history = [self._stock_signal_card(signal, code) for signal in signal_history]
        return {
            "stock_info": snapshot,
            "current_flow": flow,
            "stock_signal_enabled": self.settings.stock_signal_enabled,
            "signal_count": len(signal_history),
            "topics": list(dict.fromkeys(stock_topics)),
            "signal_history": signal_history,
            "signal_cards": enriched_history,
        }

    def _stock_signal_card(self, signal: SignalEvent, code: str) -> SignalCardDTO:
        related = next((impact for impact in signal.related_stocks if impact.code == code), None)
        flow = self.stock_flows.get(code)
        return SignalCardDTO(
            id=signal.id,
            topic_name=signal.target_id if signal.target_type == "topic" else signal.topic_name or ((flow.primary_theme or flow.industry) if flow else ""),
            target_type=signal.target_type,
            signal_level=signal.signal_level,
            timestamp=signal.timestamp,
            direction=related.direction if related else signal.direction,
            price=related.price if related else signal.stock_price_at_emit or signal.price,
            change_pct=related.change_pct if related else signal.stock_change_pct_at_emit or signal.change_pct,
            amount_yi=abs(related.display_signed_flow_yi) if related else signal.stock_amount_yi_at_emit or abs(signal.amount_yi),
            stock_flow_proxy_amount=abs(related.display_signed_flow_yi) if related else signal.stock_amount_yi_at_emit or abs(signal.amount_yi),
            delta_yi=related.delta_signed_flow_yi if related else signal.delta_from_previous_yi,
            previous_delta_proxy_amount=related.delta_signed_flow_yi if related else signal.delta_from_previous_yi,
            topic_net_yi=signal.topic_net_yi_at_emit if signal.topic_net_yi_at_emit is not None else signal.net_yi,
            topic_net_proxy_amount=signal.topic_net_yi_at_emit if signal.topic_net_yi_at_emit is not None else signal.net_yi,
            topic_delta_net_yi=signal.topic_delta_net_yi_at_emit if signal.topic_delta_net_yi_at_emit is not None else signal.delta_from_previous_yi,
            impact_pct=signal.impact_pct_at_emit if signal.impact_pct_at_emit is not None else (related.impact_pct if related else 0),
            contribution_ratio=(signal.impact_pct_at_emit if signal.impact_pct_at_emit is not None else (related.impact_pct if related else 0)) / 100,
            data_quality_bucket=signal.data_quality_bucket,
            formal_grade=signal.formal_grade,
            blocked_reason=signal.blocked_reason,
        )

    def topic_detail(self, topic_name: str) -> dict | None:
        topic = self.topic_flows.get(topic_name)
        if not topic:
            return None
        history = [s for s in self.signals if s.target_id == topic_name]
        topic_payload = topic.model_dump()
        topic_payload["radar_score"] = topic_payload.pop("signal_score", 0)
        top5_sum_abs = round(sum(abs(stock.display_signed_flow_yi) for stock in topic.top_impacts[:5]), 2)
        topic_abs_total = topic.abs_total_yi or top5_sum_abs
        top5_coverage_ratio = round((top5_sum_abs / topic_abs_total) if topic_abs_total else 0, 4)
        topic_payload["topic_net_proxy_amount"] = topic.net_yi
        topic_payload["top5_sum_abs"] = top5_sum_abs
        topic_payload["top5_coverage_ratio"] = top5_coverage_ratio
        if top5_coverage_ratio >= 0.7:
            topic_payload["top5_coverage_label"] = "主要由前五檔帶動"
        elif top5_coverage_ratio < 0.4:
            topic_payload["top5_coverage_label"] = "此題材由多檔分散貢獻"
        else:
            topic_payload["top5_coverage_label"] = "前五檔與其他個股共同帶動"
        return {"topic_flow": topic_payload, "top_impacts": topic.top_impacts, "history": history, "topic_state": self.topic_states.get(topic_name)}

    def latest_scan_debug(self) -> ScanDebugSummary | None:
        return self.last_debug_summary

    def discord_queue_stats(self) -> dict:
        return self.store.discord_queue_stats()

    def discord_queue_items(self, limit: int = 50) -> list:
        return self.store.list_discord_queue(limit=limit)


repo = InMemoryRepository()
