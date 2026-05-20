from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.storage.repository import InMemoryRepository  # noqa: E402


st.set_page_config(
    page_title="Smart Money Radar",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)


st.markdown(
    """
    <style>
    .stApp {
      background: #070b12;
      color: #edf3fb;
    }
    div[data-testid="stMetricValue"] {
      color: #ffffff;
      font-size: 1.35rem;
    }
    .radar-card {
      border: 1px solid #22324a;
      background: #0e1623;
      border-radius: 12px;
      padding: 16px;
      margin: 8px 0;
    }
    .muted { color: #9fb0c5; font-size: 0.9rem; }
    .red { color: #ff5b66; font-weight: 700; }
    .green { color: #35d07f; font-weight: 700; }
    .chip {
      display: inline-block;
      border-radius: 999px;
      padding: 3px 9px;
      background: #17253a;
      color: #d7e8ff;
      font-size: 0.8rem;
      margin-right: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def yi(value: float | int | None, signed: bool = True) -> str:
    number = float(value or 0)
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:.2f}億"


def pct(value: float | int | None) -> str:
    number = float(value or 0)
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.2f}%"


def direction_text(direction: str | None) -> str:
    if direction == "INFLOW":
        return "推估流入"
    if direction == "OUTFLOW":
        return "推估流出"
    return "中性"


def direction_color(direction: str | None) -> str:
    if direction == "INFLOW":
        return "red"
    if direction == "OUTFLOW":
        return "green"
    return "muted"


def level_text(level: str | None) -> str:
    return {
        "weak": "弱",
        "normal": "一般",
        "strong": "強",
        "very_strong": "熱門",
    }.get(level or "", "一般")


@st.cache_resource
def get_repo() -> InMemoryRepository:
    return InMemoryRepository(use_provider=True)


@st.cache_data(ttl=60, show_spinner=False)
def scan_market() -> dict:
    repo = get_repo()
    repo.scan()
    all_topics = [topic.model_dump(mode="json") for topic in repo.topic_flows.values()]
    return {
        "market": repo.market_flow().model_dump(mode="json"),
        "rankings": repo.rankings(),
        "dashboard": repo.dashboard(),
        "topics": all_topics,
        "stock_names": {code: snapshot.name for code, snapshot in repo.snapshots.items()},
        "health": {
            "last_scan_at": repo.last_scan_at.isoformat() if repo.last_scan_at else None,
            "debug": repo.latest_scan_debug().model_dump(mode="json") if repo.latest_scan_debug() else None,
        },
    }


def stock_detail(query: str) -> dict | None:
    repo = get_repo()
    return repo.stock_detail(query)


def topic_detail(topic_name: str) -> dict | None:
    repo = get_repo()
    return repo.topic_detail(topic_name)


def as_row(item) -> dict:
    return item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)


def topic_net(row: dict) -> float:
    return float(row.get("topic_net_proxy_amount") or row.get("net_yi") or 0)


def topic_rows_for_rank(rankings: dict, all_topics: list[dict], key: str, *, want_outflow: bool, limit: int = 5) -> list[dict]:
    rows = [as_row(item) for item in rankings.get(key, [])]
    used = {row.get("topic_name") for row in rows}

    if len(rows) < limit:
        candidates = sorted(
            [as_row(topic) for topic in all_topics if topic.get("topic_name") not in used],
            key=topic_net,
            reverse=not want_outflow,
        )
        if want_outflow:
            preferred = [row for row in candidates if topic_net(row) < 0]
            fallback = [row for row in candidates if topic_net(row) >= 0]
            candidates = [*preferred, *fallback]
        else:
            preferred = [row for row in candidates if topic_net(row) > 0]
            fallback = [row for row in candidates if topic_net(row) <= 0]
            candidates = [*preferred, *fallback]
        rows.extend(candidates[: max(0, limit - len(rows))])
    return rows[:limit]


def stock_label(code: str | None, stock_names: dict[str, str]) -> str:
    if not code:
        return "-"
    name = stock_names.get(str(code), "")
    return f"{code} {name}" if name else str(code)


def row_table(rows: list, *, amount_key: str = "display_signed_flow_yi", limit: int = 10):
    payload = []
    for index, item in enumerate(rows[:limit], start=1):
        row = as_row(item)
        amount = row.get(amount_key)
        if amount_key in {"relative_flow_pct", "sector_strength_pct"}:
            amount_text = f"{float(amount or 0):.1f}%"
        else:
            amount_text = yi(abs(float(amount or 0)), signed=False)
        payload.append(
            {
                "排名": index,
                "代號": row.get("code"),
                "名稱": row.get("name") or row.get("stock_name") or "-",
                "題材": row.get("primary_theme") or row.get("display_group") or (row.get("topics") or ["-"])[0],
                "方向": row.get("flow_label") or direction_text(row.get("direction")),
                "金額": amount_text,
                "漲跌幅": pct(row.get("change_pct")),
                "現價": row.get("last_price") or row.get("price"),
                "資料狀態": row.get("freshness_status") or "-",
                "資料時間": row.get("quote_time") or row.get("timestamp"),
            }
        )
    st.dataframe(payload, use_container_width=True, hide_index=True)


def topic_rank(title: str, rows: list, *, limit: int = 5):
    st.subheader(title)
    if not rows:
        st.caption("暫無符合條件的題材")
        return
    for index, item in enumerate(rows[:limit], start=1):
        row = as_row(item)
        direction = row.get("direction")
        color = direction_color(direction)
        net = topic_net(row)
        if net < 0:
            color = "green"
        elif net > 0:
            color = "red"
        st.markdown(
            f"""
            <div class="radar-card">
              <b>{index}. {row.get("topic_name")}</b>
              <span class="{color}" style="float:right">{yi(net)}　⚡ {row.get("radar_score", row.get("signal_score", 0))}</span>
              <div class="muted">流入 {yi(row.get("inflow_yi"), False)}｜流出 {yi(row.get("outflow_yi"), False)}｜強/弱 {row.get("strong_stock_count", 0)}/{row.get("weak_stock_count", 0)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_dashboard(data: dict):
    market = data["market"]
    rankings = data["rankings"]
    all_topics = data.get("topics", [])
    stock_names = data.get("stock_names", {})
    health = data["health"]
    debug = health.get("debug") or {}

    status = "即時" if market.get("is_realtime") else ("收盤" if market.get("market_data_time") else "觀察")
    st.caption(f"資料狀態：{status}｜資料時間：{market.get('market_data_time') or health.get('last_scan_at')}")
    if not market.get("formal_grade"):
        st.info("目前為觀察模式：資料未達盤中新鮮即時條件，不會正式推播。")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("推估流入", yi(market.get("market_inflow_proxy_amount"), False))
    c2.metric("推估流出", yi(market.get("market_outflow_proxy_amount"), False))
    c3.metric("推估淨額", yi(market.get("market_net_proxy_amount")))
    c4.metric("本輪變化", yi(market.get("market_delta_proxy_amount")))

    st.divider()
    st.header("類股雷達掃描")
    topic_inflow_rows = topic_rows_for_rank(rankings, all_topics, "topic_inflow_top50", want_outflow=False, limit=5)
    topic_outflow_rows = topic_rows_for_rank(rankings, all_topics, "topic_outflow_top50", want_outflow=True, limit=5)
    left, right = st.columns(2)
    with left:
        topic_rank("資金流入 TOP5", topic_inflow_rows, limit=5)
    with right:
        topic_rank("資金流出 TOP5", topic_outflow_rows, limit=5)

    st.divider()
    st.header("每日資金排行榜")
    tab1, tab2, tab3, tab4 = st.tabs(["流入", "流出", "本輪增量", "相對增量"])
    with tab1:
        row_table(rankings.get("stock_inflow_top50", []), amount_key="display_signed_flow_yi", limit=50)
    with tab2:
        row_table(rankings.get("stock_outflow_top50", []), amount_key="display_signed_flow_yi", limit=50)
    with tab3:
        row_table(rankings.get("unusual_value_top50", []), amount_key="delta_signed_flow_yi", limit=50)
    with tab4:
        row_table(rankings.get("relative_flow_proxy_top50", []), amount_key="relative_flow_pct", limit=50)

    st.divider()
    st.header("智慧推播提醒")
    signals = data["dashboard"].get("latest_signals", [])
    if not signals:
        st.caption("目前沒有新的資金異動提醒。")
    for signal in signals[:20]:
        row = as_row(signal)
        color = direction_color(row.get("direction"))
        target = row.get("target_id")
        title = stock_label(target, stock_names) if row.get("target_type") == "stock" else str(target or "-")
        st.markdown(
            f"""
            <div class="radar-card">
              <span class="chip">{level_text(row.get("signal_level"))}</span>
              <b>{title}</b>
              <span class="{color}"> {direction_text(row.get("direction"))}｜資金熱度 ⚡ {row.get("score", 0)}</span>
              <div class="muted">時間 {row.get("timestamp")}｜題材淨額 {yi(row.get("net_yi"))}｜較上輪 {yi(row.get("delta_from_previous_yi"))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_search():
    st.header("個股資金查詢")
    query = st.text_input("請輸入股票代號或名稱", placeholder="例如 3037 或 欣興")
    if not query:
        st.info("請輸入股票代號或名稱，查看今日所屬題材與資金異動。")
        return

    detail = stock_detail(query.strip())
    if not detail:
        st.warning("查無此股票或今日尚無資金異動。")
        return

    stock = detail["stock_info"]
    flow = detail.get("current_flow")
    topics = detail.get("topics", [])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"{stock.code} {stock.name}", stock.price)
    c2.metric("漲跌幅", pct(stock.change_pct))
    c3.metric("推估金額", yi(abs(flow.display_signed_flow_yi if flow else 0), False))
    c4.metric("異動次數", detail.get("signal_count", 0))
    st.caption(f"所屬題材：{' / '.join(topics) if topics else '-'}")

    st.subheader("今日資金異動")
    cards = detail.get("signal_cards", [])
    if not cards:
        st.caption("今日尚無資金異動。")
        return
    for card in cards[:30]:
        row = as_row(card)
        color = direction_color(row.get("direction"))
        with st.expander(f"{row.get('topic_name')}｜{level_text(row.get('signal_level'))}｜{direction_text(row.get('direction'))}｜{row.get('timestamp')}"):
            st.markdown(
                f"""
                <div class="{color}"><b>題材淨額：{yi(row.get("topic_net_proxy_amount") or row.get("topic_net_yi"))}</b></div>
                <div class="muted">當時價格：{row.get("price", "-")}｜個股推估金額：{yi(row.get("stock_flow_proxy_amount"), False)}｜較上輪：{yi(row.get("previous_delta_proxy_amount"))}</div>
                """,
                unsafe_allow_html=True,
            )
            topic = topic_detail(row.get("topic_name") or "")
            if topic:
                impacts = topic["topic_flow"].get("top_impacts", [])[:5]
                st.write("影響力 TOP5 個股")
                table = []
                for index, impact in enumerate(impacts, start=1):
                    item = as_row(impact)
                    table.append(
                        {
                            "排名": index,
                            "代號": item.get("code"),
                            "名稱": item.get("name"),
                            "方向": direction_text(item.get("direction")),
                            "金額": yi(abs(item.get("stock_flow_proxy_amount") or 0), False),
                            "佔比": f"{float(item.get('contribution_ratio') or 0) * 100:.0f}%",
                            "漲跌幅": pct(item.get("change_pct")),
                            "現價": item.get("price"),
                        }
                    )
                st.dataframe(table, use_container_width=True, hide_index=True)


st.title("Smart Money Radar")
st.caption("台股即時資金雷達 App｜Streamlit 手機觀看版")

with st.sidebar:
    st.header("控制")
    if st.button("重新抓取資料", use_container_width=True):
        scan_market.clear()
        st.rerun()
    st.caption("頁面資料快取 60 秒；盤中會抓取 TWSE MIS 今日報價。")

try:
    payload = scan_market()
except Exception as exc:
    st.error("資料抓取失敗，請稍後重試。")
    st.exception(exc)
    st.stop()

page = st.radio("功能", ["資金流向", "個股資金查詢"], horizontal=True, label_visibility="collapsed")
if page == "資金流向":
    render_dashboard(payload)
else:
    render_search()
