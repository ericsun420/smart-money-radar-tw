from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.data_provider.normalizer import normalize_snapshot
from app.data_provider.stock_universe import is_common_stock_code
from app.data_provider.theme_mapping import apply_theme_mapping
from app.data_provider.tpex_provider import normalize_tpex_row
from app.data_provider.twse_mis_provider import normalize_mis_item
from app.engine.direction_engine import infer_direction
from app.engine.quality import apply_snapshot_quality
from app.engine.score_engine import score_topic_signal
from app.engine.signal_engine import build_stock_signal, build_topic_signal, should_emit_topic_signal
from app.engine.topic_aggregator import aggregate_topics
from app.main import app
from app.notifier.discord import format_discord_message
from app.notifier.discord_queue import DiscordQueue
from app.scheduler import SCAN_JOB_ID, scheduler
from app.storage.models import ScanDebugSummary, Settings, SignalEvent, StockSnapshot, TopicState
from app.storage.repository import InMemoryRepository
from app.storage.sqlite_store import SQLiteStore
from app.time_utils import TAIPEI_TZ


def make_test_db(name: str) -> SQLiteStore:
    root = Path("test_dbs")
    root.mkdir(exist_ok=True)
    return SQLiteStore(str(root / f"{name}_{uuid4().hex}.sqlite3"))


def official_snapshot(code: str, price: float, value_yi: float, ts: datetime, *, industry: str = "Semi") -> StockSnapshot:
    return StockSnapshot(
        code=code,
        name=code,
        market="TSE",
        industry=industry,
        themes=["AI"],
        price=price,
        previous_close=price - 1,
        open=price - 1,
        high=price,
        low=price - 2,
        change_pct=1,
        volume=1_000_000,
        trade_value=value_yi * 100_000_000,
        trade_value_yi=value_yi,
        timestamp=ts,
        data_quality_bucket="official_full",
        formal_grade=True,
        provider_type="official_full",
        source_status="official",
        units_normalized=True,
        vwap_twd=price - 0.5,
    )


def test_seed_and_cache_are_not_formal():
    repo = InMemoryRepository(store=make_test_db("radar"), use_provider=False)
    topic = repo.topic_detail("半導體業")["topic_flow"]
    assert topic["formal_grade"] is False
    assert topic["blocked_reason"].startswith("topic_contains_non_formal_stock")
    assert all(signal.formal_grade is False for signal in repo.dashboard()["latest_signals"])


def test_display_and_delta_flow_are_separate():
    now = datetime.now()
    prev = official_snapshot("2330", 99, 90, now - timedelta(minutes=5))
    cur = official_snapshot("2330", 100, 100, now)
    flow = infer_direction(cur, prev, None, min_value_delta_yi=0.05)
    assert flow.display_signed_flow_yi == 100
    assert flow.delta_signed_flow_yi == 10


def test_stock_signal_uses_quote_time_as_source_ts():
    scan_time = datetime(2026, 5, 7, 20, 31, tzinfo=TAIPEI_TZ)
    quote_time = datetime(2026, 5, 7, 13, 33, tzinfo=TAIPEI_TZ)
    prev = official_snapshot("2330", 99, 90, scan_time - timedelta(minutes=5))
    cur = official_snapshot("2330", 100, 100, scan_time).model_copy(
        update={"market_data_time": quote_time, "source_ts": quote_time}
    )
    flow = infer_direction(cur, prev, None, min_value_delta_yi=0.05)
    signal = build_stock_signal(flow)
    assert signal.timestamp == scan_time
    assert signal.source_ts == quote_time


def test_same_direction_count_accumulates_and_reversal_resets():
    now = datetime.now()
    f1 = infer_direction(official_snapshot("1", 101, 10, now), official_snapshot("1", 100, 9, now - timedelta(minutes=5)), None, min_value_delta_yi=0.05)
    topics, states = aggregate_topics([f1], timestamp=now, topic_states={})
    assert topics[0].same_direction_count == 1
    topics, states = aggregate_topics([f1], timestamp=now + timedelta(minutes=5), topic_states=states)
    assert topics[0].same_direction_count == 2
    f2 = infer_direction(official_snapshot("1", 99, 11, now + timedelta(minutes=10)), official_snapshot("1", 101, 10, now + timedelta(minutes=5)), f1, min_value_delta_yi=0.05)
    topics, states = aggregate_topics([f2], timestamp=now + timedelta(minutes=10), topic_states=states)
    assert topics[0].direction == "OUTFLOW"
    assert topics[0].same_direction_count == 1


def test_cooldown_blocks_same_direction_but_reversal_can_emit():
    now = datetime.now()
    settings = Settings(topic_min_net_yi=5, topic_min_delta_yi=1, repeat_delta_yi=3)
    state = TopicState(topic_name="AI", last_direction="INFLOW", same_direction_count=2, last_net_yi=10, last_emit_at=now)
    f = infer_direction(official_snapshot("1", 101, 10.5, now + timedelta(minutes=1)), official_snapshot("1", 100, 10, now), None, min_value_delta_yi=0.05)
    topics, _ = aggregate_topics([f], timestamp=now + timedelta(minutes=1), topic_states={"AI": state})
    recent = SignalEvent(
        id="x",
        timestamp=now,
        target_type="topic",
        target_id="AI",
        direction="INFLOW",
        amount_yi=10,
        net_yi=10,
        previous_net_yi=9,
        delta_from_previous_yi=1,
        score=5,
        message="recent",
    )
    should_emit, reason = should_emit_topic_signal(topics[0], state, recent, settings)
    assert should_emit is False
    assert reason == "cooldown_repeat_delta_not_met"

    outflow = topics[0].model_copy(update={"direction": "OUTFLOW", "net_yi": -10, "delta_net_yi": -10})
    should_emit, reason = should_emit_topic_signal(outflow, state, recent, settings)
    assert should_emit is True


def test_impact_pct_can_exceed_100_and_net_near_zero_penalizes_score():
    now = datetime.now()
    f_in = infer_direction(official_snapshot("1", 101, 105, now), official_snapshot("1", 100, 100, now - timedelta(minutes=5)), None, min_value_delta_yi=0.05)
    f_out = infer_direction(official_snapshot("2", 99, 100, now), official_snapshot("2", 100, 90, now - timedelta(minutes=5)), None, min_value_delta_yi=0.05)
    topics, _ = aggregate_topics([f_in, f_out], timestamp=now, topic_states={}, net_near_zero_ratio=0.08)
    topic = next(t for t in topics if t.topic_name == "AI")
    assert topic.net_near_zero is True
    assert max(i.impact_pct for i in topic.top_impacts) > 100
    score = score_topic_signal(
        net_yi=topic.net_yi,
        delta_from_previous_yi=topic.delta_net_yi,
        same_direction_count=1,
        affected_stock_count=2,
        concentration_pct=topic.concentration_pct,
        data_quality_bucket=topic.data_quality_bucket,
        top_stock_net_share_pct=200,
        net_near_zero=True,
    )
    assert score <= 5


def test_settings_get_masks_webhook_and_scheduler_reschedules():
    with TestClient(app) as client:
        payload = {
            "auto_refresh": True,
            "scan_interval_minutes": 7,
            "topic_min_net_yi": 5,
            "topic_min_delta_yi": 1,
            "repeat_delta_yi": 3,
            "stock_min_value_yi": 1,
            "stock_min_delta_yi": 0.3,
            "min_value_delta_yi": 0.05,
            "stale_seconds": 600,
            "net_near_zero_ratio": 0.08,
            "only_official_full": False,
            "show_cache_warning": True,
            "discord_webhook_url": "https://discord.com/api/webhooks/abc/secret1234",
            "push_enabled": False,
            "stock_signal_enabled": True,
        }
        res = client.post("/api/settings", json=payload)
        assert res.status_code == 200
        settings = client.get("/api/settings").json()
        assert "secret1234" not in str(settings)
        assert settings["discord_webhook_configured"] is True
        health = client.get("/api/health").json()
        assert health["scan_interval_minutes"] == 7
        assert health["active_scan_interval_minutes"] == 7
        assert health["scheduler_next_run_time"] is not None
        assert health["discord_queue_next_run_time"] is not None


def test_unit_unknown_blocks_formal_grade():
    normalized = normalize_snapshot({"price_twd": 100, "trade_value_twd": 1000})
    assert normalized.unit_ok is False
    snap = official_snapshot("1", 100, 1, datetime.now()).model_copy(
        update={"units_normalized": False, "data_quality_bucket": "unit_unknown", "source_status": "unit_unknown"}
    )
    repo = InMemoryRepository(store=make_test_db("unit"), use_provider=False)
    repo.snapshots = {"1": snap}
    repo.previous_snapshots = {"1": snap.model_copy(update={"price": 99, "trade_value_yi": 0.5})}
    repo.scan()
    flow = repo.stock_detail("1")["current_flow"]
    assert flow.formal_grade is False
    assert flow.blocked_reason is not None


def test_tpex_transaction_amount_normalizes_trade_value():
    snapshot = normalize_tpex_row(
        {
            "SecuritiesCompanyCode": "5351",
            "CompanyName": "鈺創",
            "Close": "71.30",
            "Change": "+0.70",
            "TradingShares": "54750109",
            "TransactionAmount": "3955903223",
        },
        now=datetime(2026, 4, 29, 10, 50),
    )
    assert snapshot is not None
    assert snapshot.code == "5351"
    assert snapshot.trade_value_yi == 39.56


def test_twse_mis_quote_normalizes_to_official_intraday_proxy():
    now = datetime(2026, 4, 30, 10, 5, tzinfo=TAIPEI_TZ)
    base = official_snapshot("2330", 100, 10, now, industry="半導體業").model_copy(
        update={
            "data_quality_bucket": "official_partial",
            "provider_type": "official_partial",
            "formal_grade": False,
        }
    )
    snapshot = normalize_mis_item(
        {
            "c": "2330",
            "n": "台積電",
            "ex": "tse",
            "z": "102.5",
            "o": "100.0",
            "h": "103.0",
            "l": "99.5",
            "y": "100.0",
            "v": "12345",
            "d": "20260430",
            "t": "10:04:30",
        },
        base,
        now=now,
    )
    assert snapshot is not None
    assert snapshot.data_quality_bucket == "official_intraday"
    assert snapshot.provider_type == "official_intraday"
    assert snapshot.source_status == "official_intraday"
    assert snapshot.is_realtime is True
    assert snapshot.market_data_time is not None
    assert snapshot.data_latency_seconds == 30
    assert snapshot.trade_value_yi == round(102.5 * 12_345_000 / 100_000_000, 2)


def test_official_intraday_can_be_formal_during_regular_session():
    now = datetime(2026, 4, 30, 10, 5, tzinfo=TAIPEI_TZ)
    snap = official_snapshot("2330", 100, 10, now).model_copy(
        update={
            "data_quality_bucket": "official_intraday",
            "provider_type": "official_intraday",
            "source_status": "official_intraday",
            "source_ts": now,
            "market_date": "2026-04-30",
            "is_realtime": True,
            "is_intraday": True,
            "realtime_provider": "twse_mis",
        }
    )
    qualified = apply_snapshot_quality(snap, now=now, stale_seconds=600)
    assert qualified.formal_grade is True
    assert qualified.blocked_reason is None


def test_stale_snapshot_downgraded():
    now = datetime.now()
    snap = official_snapshot("1", 100, 1, now - timedelta(minutes=30)).model_copy(update={"source_ts": now - timedelta(minutes=30)})
    qualified = apply_snapshot_quality(snap, now=now, stale_seconds=60)
    assert qualified.formal_grade is False
    assert qualified.data_quality_bucket == "stale"
    assert qualified.blocked_reason.startswith("stale_timestamp")


def test_discord_contains_data_quality_formal_grade_and_warning():
    now = datetime.now()
    f = infer_direction(official_snapshot("1", 101, 10, now), official_snapshot("1", 100, 9, now - timedelta(minutes=5)), None, min_value_delta_yi=0.05)
    topics, _ = aggregate_topics([f], timestamp=now, topic_states={})
    signal = build_topic_signal(topics[0], None, blocked_reason="data_quality_fail")
    content = format_discord_message(signal, topics[0])
    assert "data_quality:" in content
    assert "formal_grade: False" in content
    assert "formal_tuning: blocked_not_for_formal_tuning" in content
    assert "data_quality_fail" in content


def test_same_signal_not_sent_twice_and_upgrade_can_send_once():
    repo = InMemoryRepository(store=make_test_db("sent"))
    repo.last_debug_summary = ScanDebugSummary(scan_started_at=datetime.now(), market_date="2026-04-29", source_used="test", source_status="official_full")
    now = datetime.now()
    f = infer_direction(official_snapshot("1", 101, 10, now), official_snapshot("1", 100, 9, now - timedelta(minutes=5)), None, min_value_delta_yi=0.05)
    topics, _ = aggregate_topics([f], timestamp=now, topic_states={})
    signal = build_topic_signal(topics[0], None)
    assert repo.can_send_discord(signal) == (True, None)
    repo.mark_discord_sent(signal)
    can_send, reason = repo.can_send_discord(signal)
    assert can_send is False
    assert reason == "duplicate_signal_fingerprint"

    upgraded = signal.model_copy(update={"signal_level": "strong", "fingerprint": signal.fingerprint.replace("normal", "strong")})
    assert repo.can_send_discord(upgraded) == (True, None)


def test_official_partial_is_blocked_by_discord_server_side_gate():
    repo = InMemoryRepository(store=make_test_db("discord-gate"))
    repo.last_debug_summary = ScanDebugSummary(scan_started_at=datetime.now(), market_date="2026-04-29", source_used="test", source_status="official_partial")
    signal = SignalEvent(
        id="formal-but-source-partial",
        timestamp=datetime.now(),
        target_type="topic",
        target_id="AI",
        direction="INFLOW",
        amount_yi=10,
        net_yi=10,
        previous_net_yi=0,
        delta_from_previous_yi=10,
        score=8,
        message="formal signal",
        fingerprint=f"AI|formal|{uuid4().hex}",
        formal_grade=True,
        is_formal_push_allowed=True,
        data_quality_bucket="official_full",
    )
    can_send, reason = repo.can_send_discord(signal)
    assert can_send is False
    assert reason == "data_source_not_official_full"


def test_static_app_escapes_api_strings_before_inner_html():
    app_js = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "function escapeHtml" in app_js
    assert "replaceAll(\"<\", \"&lt;\")" in app_js
    assert "${h(row.topic_name)}" in app_js
    assert "${h(row.name)}" in app_js
    assert "${h(stock.name)}" in app_js
    assert "featureGrid" not in app_js
    assert "目前資料未達 official_full，僅供盤中觀察" not in app_js
    assert "資料品質：" not in app_js


def test_scheduler_max_instances_one_and_coalesce_enabled():
    with TestClient(app):
        job = scheduler.get_job(SCAN_JOB_ID)
        assert job is not None
        assert job.max_instances == 1
        assert job.coalesce is True
        assert job.misfire_grace_time == 60


def test_dashboard_api_discord_grade_consistency():
    with TestClient(app) as client:
        data = client.get("/api/dashboard/latest").json()
        signal = data["latest_signals"][0]
        topic = client.get(f"/api/topics/{signal['target_id']}").json().get("topic_flow") if signal["target_type"] == "topic" else None
        assert signal["formal_grade"] == signal["is_formal_push_allowed"]
        if topic:
            assert signal["data_quality_bucket"] == topic["data_quality_bucket"]


def test_no_webhook_secret_in_settings_or_discord_error():
    secret = "topsecret9999"
    with TestClient(app) as client:
        payload = {
            "auto_refresh": True,
            "scan_interval_minutes": 5,
            "topic_min_net_yi": 5,
            "topic_min_delta_yi": 1,
            "repeat_delta_yi": 3,
            "stock_min_value_yi": 1,
            "stock_min_delta_yi": 0.3,
            "min_value_delta_yi": 0.05,
            "stale_seconds": 600,
            "net_near_zero_ratio": 0.08,
            "only_official_full": False,
            "show_cache_warning": True,
            "discord_webhook_url": f"https://discord.com/api/webhooks/abc/{secret}",
            "push_enabled": False,
            "stock_signal_enabled": True,
        }
        assert client.post("/api/settings", json=payload).status_code == 200
        assert secret not in str(client.get("/api/settings").json())
        response = client.post("/api/discord/test")
        assert secret not in response.text


def test_dashboard_contains_top50_and_sector_breadth():
    with TestClient(app) as client:
        data = client.get("/api/dashboard/latest").json()
        assert "stock_inflow_top50" in data
        assert "stock_outflow_top50" in data
        assert "unusual_value_top50" in data
        assert "relative_flow_proxy_top50" in data
        assert "relative_flow_proxy_top50" in client.get("/api/rankings/latest").json()
        assert "sector_strength_top" in data
        rankings = client.get("/api/rankings/latest").json()
        assert "relative_flow_top50" not in rankings["ranking_basis"]
        assert rankings["ranking_basis"]["relative_flow_proxy_top50"].startswith("absolute delta_signed_flow_yi")
        topic_name = (data["topic_inflow_top5"] or data["topic_outflow_top5"])[0]["topic_name"]
        topic = client.get(f"/api/topics/{topic_name}").json()["topic_flow"]
        assert "strong_stock_count" in topic
        assert "weak_stock_count" in topic
        assert "top1_contribution_pct" in topic
        assert "ex_top1_net_yi" in topic
        assert "up_count" in topic
        assert "down_count" in topic
        assert "median_flow_yi" in topic
        assert "trimmed_net_flow_yi" in topic
        assert "top_stock_concentration_pct" in topic


def test_market_flow_endpoint_and_name_search_contract():
    with TestClient(app) as client:
        market = client.get("/api/market/flow")
        assert market.status_code == 200
        payload = market.json()
        for key in ["estimated_inflow_yi", "estimated_outflow_yi", "estimated_net_yi", "estimated_delta_yi", "data_quality_bucket", "formal_grade"]:
            assert key in payload

        stock = client.get("/api/stocks/search/3035")
        assert stock.status_code == 200
        body = stock.json()
        assert body["stock_info"]["official_industry"] is not None
        assert "primary_theme" in body["stock_info"]
        assert "signal_cards" in body
        by_name = client.get("/api/stocks/search/智原")
        assert by_name.status_code == 200
        assert by_name.json()["stock_info"]["code"] == "3035"


def test_mainline_readme_and_ui_do_not_use_strategy_or_overclaim_terms():
    project_root = Path(__file__).resolve().parents[2]
    backend_root = project_root / "backend"
    readme = (project_root / "README.md").read_text(encoding="utf-8")
    index = (backend_root / "app/static/index.html").read_text(encoding="utf-8")
    app_js = (backend_root / "app/static/app.js").read_text(encoding="utf-8")
    public_text = "\n".join([readme, index, app_js])
    banned = [
        "A1 stable",
        "A gate",
        "mature_hard",
        "mature_soft",
        "L0-L10",
        "回測",
        "起漲第一根",
        "三根內延續",
        "真實主力買超",
        "真實內外盤",
        "主力買賣",
    ]
    for term in banned:
        assert term not in public_text
    for feature in ["即時資金流向", "類股雷達掃描", "每日資金排行榜", "智慧推播提醒", "個股資金查詢"]:
        assert feature in public_text
    assert "跨平台同步" not in index
    assert "featureGrid" not in index


def test_cross_platform_sync_is_not_exposed_in_mainline():
    with TestClient(app) as client:
        rules = client.get("/api/alert-rules")
        assert rules.status_code == 200
        assert client.get("/api/devices").status_code == 404


def test_discord_queue_ignores_non_formal_signal():
    queue = DiscordQueue()
    signal = SignalEvent(
        id="n",
        timestamp=datetime.now(),
        target_type="stock",
        target_id="2330",
        direction="INFLOW",
        amount_yi=1,
        net_yi=1,
        previous_net_yi=0,
        delta_from_previous_yi=1,
        score=5,
        message="non formal",
        formal_grade=False,
        is_formal_push_allowed=False,
    )
    queue.enqueue(signal)
    assert queue.queued == []


def test_official_partial_never_formal():
    now = datetime.now()
    snap = official_snapshot("1", 100, 1, now).model_copy(
        update={
            "data_quality_bucket": "official_partial",
            "provider_type": "official_partial",
            "formal_grade": False,
            "blocked_reason": "daily_quote_is_not_intraday_full",
        }
    )
    qualified = apply_snapshot_quality(snap, now=now, stale_seconds=600)
    assert qualified.formal_grade is False
    assert qualified.data_quality_bucket == "official_partial"
    assert qualified.blocked_reason is not None


def test_relative_flow_ranking_not_dominated_by_large_absolute_flow():
    repo = InMemoryRepository(store=make_test_db("relative"), use_provider=False)
    now = datetime.now()
    big_prev = official_snapshot("2330", 100, 1000, now - timedelta(minutes=5), industry="Semi")
    big_cur = official_snapshot("2330", 101, 1010, now, industry="Semi")
    small_prev = official_snapshot("3008", 100, 1, now - timedelta(minutes=5), industry="Optics")
    small_cur = official_snapshot("3008", 101, 2, now, industry="Optics")
    repo.previous_snapshots = {"2330": big_prev, "3008": small_prev}
    repo.snapshots = {"2330": big_cur, "3008": small_cur}
    repo.scan()
    relative = repo.rankings()["relative_flow_proxy_top50"]
    assert relative[0].code == "3008"
    absolute = repo.rankings()["unusual_value_top50"]
    assert absolute[0].code == "2330"


def test_3037_latest_quote_overrides_ranking_and_stock_detail_regression():
    repo = InMemoryRepository(store=make_test_db("quote-3037"), use_provider=False)
    now = datetime(2026, 4, 30, 10, 10, tzinfo=TAIPEI_TZ)
    previous = official_snapshot("3037", 803, 120, now - timedelta(minutes=5), industry="ElectronicParts").model_copy(
        update={
            "name": "欣興",
            "previous_close": 803,
            "change_pct": 0,
            "source_ts": now - timedelta(minutes=5),
            "market_data_time": now - timedelta(minutes=5),
            "data_latency_seconds": 0,
            "market_date": "2026-04-30",
            "data_quality_bucket": "official_intraday",
            "provider_type": "official_intraday",
            "source_status": "official_intraday",
            "is_realtime": True,
            "is_intraday": True,
            "realtime_provider": "twse_mis",
        }
    )
    current = official_snapshot("3037", 883, 285.96, now, industry="ElectronicParts").model_copy(
        update={
            "name": "欣興",
            "previous_close": 803,
            "open": 828,
            "high": 883,
            "low": 815,
            "change_pct": 9.96,
            "source_ts": now,
            "market_data_time": now,
            "data_latency_seconds": 0,
            "market_date": "2026-04-30",
            "data_quality_bucket": "official_intraday",
            "provider_type": "official_intraday",
            "source_status": "official_intraday",
            "is_realtime": True,
            "is_intraday": True,
            "realtime_provider": "twse_mis",
        }
    )
    repo.previous_snapshots = {"3037": previous}
    repo.snapshots = {"3037": current}
    repo.stock_flows = {"3037": infer_direction(current, previous, None, min_value_delta_yi=0.05)}
    repo.last_scan_at = now

    rankings = repo.rankings()
    all_rows = [
        *rankings["stock_inflow_top50"],
        *rankings["stock_outflow_top50"],
        *rankings["unusual_value_top50"],
        *rankings["relative_flow_proxy_top50"],
    ]
    rows_3037 = [row for row in all_rows if row.code == "3037"]
    assert rows_3037
    assert all(row.last_price == 883 for row in rows_3037)
    assert all(row.price == 883 for row in rows_3037)
    assert all(row.change == 80 for row in rows_3037)
    assert all(round(row.change_pct or 0, 2) == 9.96 for row in rows_3037)
    assert all(row.trade_date == "2026-04-30" for row in rows_3037)
    assert rows_3037[0].freshness_status == "即時"
    assert not any(row.code == "3037" for row in rankings["stock_outflow_top50"])
    assert any(row.code == "3037" for row in rankings["stock_inflow_top50"])

    detail = repo.stock_detail("3037")
    assert detail is not None
    assert detail["stock_info"].price == 883
    assert round(detail["stock_info"].change_pct, 2) == 9.96
    assert detail["current_flow"].direction == "INFLOW"


def test_stale_or_wrong_date_quotes_are_excluded_from_public_rankings():
    repo = InMemoryRepository(store=make_test_db("stale-ranking"), use_provider=False)
    now = datetime(2026, 4, 30, 10, 10, tzinfo=TAIPEI_TZ)
    previous = official_snapshot("9999", 100, 1, now - timedelta(minutes=5), industry="Test")
    stale = official_snapshot("9999", 120, 50, now - timedelta(days=1), industry="Test").model_copy(
        update={
            "market_date": "2026-04-29",
            "source_ts": now - timedelta(days=1),
            "market_data_time": now - timedelta(days=1),
            "data_quality_bucket": "stale",
            "blocked_reason": "market_date_mismatch:2026-04-29",
        }
    )
    repo.previous_snapshots = {"9999": previous}
    repo.snapshots = {"9999": stale}
    repo.stock_flows = {"9999": infer_direction(stale, previous, None, min_value_delta_yi=0.05)}
    repo.last_scan_at = now
    rankings = repo.rankings()
    assert all(row.code != "9999" for row in rankings["stock_inflow_top50"])
    assert all(row.code != "9999" for row in rankings["stock_outflow_top50"])
    assert all(row.code != "9999" for row in rankings["unusual_value_top50"])
    assert all(row.code != "9999" for row in rankings["relative_flow_proxy_top50"])


def test_sector_breadth_flags_single_stock_distortion():
    now = datetime.now()
    flows = [
        infer_direction(official_snapshot("1", 101, 100, now, industry="Glass"), official_snapshot("1", 100, 90, now - timedelta(minutes=5), industry="Glass"), None, min_value_delta_yi=0.05),
        infer_direction(official_snapshot("2", 99, 8, now, industry="Glass"), official_snapshot("2", 100, 7, now - timedelta(minutes=5), industry="Glass"), None, min_value_delta_yi=0.05),
        infer_direction(official_snapshot("3", 99, 7, now, industry="Glass"), official_snapshot("3", 100, 6, now - timedelta(minutes=5), industry="Glass"), None, min_value_delta_yi=0.05),
        infer_direction(official_snapshot("4", 99, 6, now, industry="Glass"), official_snapshot("4", 100, 5, now - timedelta(minutes=5), industry="Glass"), None, min_value_delta_yi=0.05),
        infer_direction(official_snapshot("5", 99, 5, now, industry="Glass"), official_snapshot("5", 100, 4, now - timedelta(minutes=5), industry="Glass"), None, min_value_delta_yi=0.05),
    ]
    topics, _ = aggregate_topics(flows, timestamp=now, topic_states={})
    topic = next(t for t in topics if t.topic_name == "Glass")
    assert topic.strong_stock_count == 1
    assert topic.weak_stock_count == 4
    assert topic.top_stock_concentration_pct > 70
    assert topic.trimmed_net_flow_yi < topic.net_yi


def test_discord_queue_persists_pending_and_sent_across_store_instances():
    db_path = Path("test_dbs") / f"queue_{uuid4().hex}.sqlite3"
    store = SQLiteStore(str(db_path))
    signal = SignalEvent(
        id="q1",
        timestamp=datetime.now(),
        target_type="topic",
        target_id="AI",
        direction="INFLOW",
        amount_yi=5,
        net_yi=5,
        previous_net_yi=0,
        delta_from_previous_yi=5,
        score=5,
        message="queue test",
        fingerprint="AI|normal|formal=True|date=2026-04-29|event=flow_signal|source_ts=1",
    )
    store.enqueue_discord(signal, status="pending")
    restarted = SQLiteStore(str(db_path))
    pending = restarted.list_discord_queue(statuses={"pending"})
    assert len(pending) == 1
    restarted.mark_discord_sent(signal)
    restarted_again = SQLiteStore(str(db_path))
    assert restarted_again.list_discord_queue(statuses={"pending"}) == []
    assert restarted_again.discord_queue_stats()["sent"] == 1


def test_stock_universe_excludes_etf_code_space_but_keeps_ky_common_stock():
    assert is_common_stock_code("0050") is False
    assert is_common_stock_code("0201") is False
    assert is_common_stock_code("4958") is True


def test_theme_mapping_supports_multi_theme_stock():
    snap = official_snapshot("2317", 100, 10, datetime.now(), industry="OtherElectronics")
    mapped = apply_theme_mapping(snap)
    assert mapped.industry == "其他電子業"
    assert mapped.official_industry == "其他電子業"
    assert mapped.primary_theme == "其他電子業"
    assert "AI伺服器" in mapped.themes
    assert "GB200" in mapped.themes
    assert "低軌衛星" in mapped.themes
    unclassified = official_snapshot("3035", 100, 10, datetime.now(), industry="Unclassified")
    mapped_unclassified = apply_theme_mapping(unclassified)
    assert mapped_unclassified.industry == "Unclassified"
    assert mapped_unclassified.official_industry == "Unclassified"
    assert mapped_unclassified.primary_theme == "半導體業"
    assert "Unclassified" not in mapped_unclassified.themes


def test_dashboard_topic_cards_and_stock_signal_cards_contract():
    repo = InMemoryRepository(store=make_test_db("cards"), use_provider=False)
    dashboard = repo.dashboard()
    assert dashboard["topic_cards"]
    card = dashboard["topic_cards"][0]
    for key in ["topic_name", "net_yi", "delta_net_yi", "inflow_yi", "outflow_yi", "concentration_pct", "radar_score", "top_impacts"]:
        assert hasattr(card, key)

    detail = repo.stock_detail("3035")
    assert detail is not None
    assert "signal_cards" in detail
    assert detail["topics"]
    assert any(topic in detail["topics"] for topic in ["半導體業", "IC設計", "車用晶片", "ASIC"])
    if detail["signal_cards"]:
        signal_card = detail["signal_cards"][0]
        for key in ["topic_name", "timestamp", "amount_yi", "topic_net_yi", "topic_delta_net_yi", "impact_pct"]:
            assert hasattr(signal_card, key)


def test_topic_cards_use_previous_net_from_emit_delta_not_updated_state():
    repo = InMemoryRepository(store=make_test_db("topic-card-prev"), use_provider=False)
    card = repo.dashboard()["topic_cards"][0]
    assert round(card.net_yi - card.delta_net_yi, 2) == card.last_net_yi


def test_signal_cards_use_emit_snapshot_not_current_topic_flow():
    repo = InMemoryRepository(store=make_test_db("signal-snapshot"), use_provider=False)
    detail = repo.stock_detail("3035")
    assert detail and detail["signal_cards"]
    card = detail["signal_cards"][0]
    signal = next(s for s in repo.signals if s.id == card.id)
    original_topic_net = card.topic_net_yi
    if signal.target_type == "topic" and signal.target_id in repo.topic_flows:
        repo.topic_flows[signal.target_id] = repo.topic_flows[signal.target_id].model_copy(update={"net_yi": 999999, "delta_net_yi": 999999})
    card_after_mutation = repo._stock_signal_card(signal, "3035")
    assert card_after_mutation.topic_net_yi == original_topic_net


def test_failed_discord_queue_item_becomes_due_for_retry():
    store = make_test_db("queue-retry")
    signal = SignalEvent(
        id="retry1",
        timestamp=datetime.now(),
        target_type="topic",
        target_id="AI",
        direction="INFLOW",
        amount_yi=5,
        net_yi=5,
        previous_net_yi=0,
        delta_from_previous_yi=5,
        score=5,
        message="retry test",
        fingerprint=f"AI|retry|{uuid4().hex}",
    )
    item = store.enqueue_discord(signal, status="pending")
    store.update_discord_queue_item(item.id, status="failed", retry_count=1, next_retry_at=datetime.now() - timedelta(seconds=1), last_error="HTTPStatusError:429")
    assert store.retry_due_discord_items() == 1
    due = store.list_due_discord_queue()
    assert due[0].status == "pending"


def test_public_access_token_redirect_and_read_only_writes(monkeypatch):
    monkeypatch.setenv("SMART_MONEY_ACCESS_TOKEN", "user-token")
    monkeypatch.delenv("SMART_MONEY_ADMIN_TOKEN", raising=False)
    with TestClient(app, follow_redirects=False) as client:
        assert client.get("/").status_code == 401
        first = client.get("/?token=user-token")
        assert first.status_code == 303
        assert "smart_money_access" in first.headers.get("set-cookie", "")
        assert client.get("/api/health", headers={"x-smart-money-token": "user-token"}).status_code == 200
        denied = client.post(
            "/api/scan/run",
            headers={"x-smart-money-token": "user-token", "x-forwarded-for": "203.0.113.10"},
        )
        assert denied.status_code == 403
    with TestClient(app, follow_redirects=False) as fresh_client:
        assert fresh_client.get("/api/health").status_code == 401


def test_admin_token_can_write_from_public_headers(monkeypatch):
    monkeypatch.setenv("SMART_MONEY_ACCESS_TOKEN", "user-token")
    monkeypatch.setenv("SMART_MONEY_ADMIN_TOKEN", "admin-token")
    public_headers = {"x-smart-money-token": "user-token", "x-forwarded-for": "203.0.113.10"}
    admin_headers = {
        "x-smart-money-token": "user-token",
        "x-smart-money-admin-token": "admin-token",
        "x-forwarded-for": "203.0.113.10",
    }
    with TestClient(app) as client:
        denied = client.post("/api/scan/run", headers=public_headers)
        assert denied.status_code == 403
        allowed = client.post("/api/scan/run", headers=admin_headers)
        assert allowed.status_code == 200

        settings_payload = Settings().model_dump(mode="json")
        assert client.post("/api/settings", json=settings_payload, headers=public_headers).status_code == 403
        assert client.post("/api/settings", json=settings_payload, headers=admin_headers).status_code == 200

        now = datetime.now().isoformat()
        alert_payload = {"id": "", "name": "admin-test", "created_at": now, "updated_at": now}
        assert client.post("/api/alert-rules", json=alert_payload, headers=public_headers).status_code == 403
        assert client.post("/api/alert-rules", json=alert_payload, headers=admin_headers).status_code == 200


def test_official_partial_blocks_formal_push_api():
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        market = client.get("/api/market/flow").json()
        if health["data_source_status"] == "official_partial":
            assert health["push_blocked_reason"] == "data_source_not_official_full"
            assert market["push_blocked_reason"] == "data_source_not_official_full"
        elif health["data_source_status"] == "official_intraday":
            assert health["is_realtime"] is True
            assert health["realtime_provider"] == "twse_mis"
            assert market["data_quality_bucket"] == "official_intraday"
        else:
            assert health["push_blocked_reason"] is not None


def test_stock_search_rate_limit(monkeypatch):
    monkeypatch.setenv("SMART_MONEY_ACCESS_TOKEN", "rate-token")
    forwarded_ip = f"198.51.100.{uuid4().int % 200 + 1}"
    with TestClient(app) as client:
        headers = {"x-smart-money-token": "rate-token", "x-forwarded-for": forwarded_ip}
        statuses = [client.get("/api/stocks/2464", headers=headers).status_code for _ in range(65)]
        assert 429 in statuses
