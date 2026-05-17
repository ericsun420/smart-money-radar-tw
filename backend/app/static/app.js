const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

const h = escapeHtml;
const yi = (value, signed = true) => `${signed && Number(value || 0) > 0 ? "+" : ""}${Number(value || 0).toFixed(2)}億`;
const pct = (value) => `${Number(value || 0) > 0 ? "+" : ""}${Number(value || 0).toFixed(2)}%`;
const timeText = (value) => value ? new Date(value).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" }) : "-";
const directionText = (direction) => direction === "INFLOW" ? "推估流入" : direction === "OUTFLOW" ? "推估流出" : "中性";
const directionArrow = (direction) => direction === "INFLOW" ? "↑" : direction === "OUTFLOW" ? "↓" : "";
const directionClass = (direction) => direction === "INFLOW" ? "red" : direction === "OUTFLOW" ? "green" : "";
const levelText = (level) => ({ weak: "弱", normal: "一般", strong: "強", very_strong: "熱門" }[level] || level || "一般");
const flowAmount = (row) => Number(row.stock_flow_proxy_amount ?? row.display_signed_flow_yi ?? 0);
const deltaProxy = (row) => Number(row.previous_delta_proxy_amount ?? row.delta_signed_flow_yi ?? row.delta_yi ?? 0);
const unknownTopicValues = new Set(["", "-", "Unclassified", "未分類", "undefined", "null"]);
const isUnknownTopic = (value) => unknownTopicValues.has(String(value ?? "").trim());
const cleanTopics = (topics = []) => [...new Set((topics || []).map((topic) => String(topic || "").trim()).filter((topic) => !isUnknownTopic(topic)))];
const displayTopicName = (value, fallback = "個股資金異動") => isUnknownTopic(value) ? fallback : String(value);
const displayIndustryName = (value) => isUnknownTopic(value) ? "未分類" : String(value);
const topicsText = (topics) => {
  const cleaned = cleanTopics(topics);
  return cleaned.length ? cleaned.join(" / ") : "題材資料待補";
};
const quoteDateTime = (value) => value ? new Date(value).toLocaleString("zh-TW", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "-";

let topLimit = 5;
let dashboardScrollY = 0;
let previousTab = "dashboard";
let dashboardRetryTimer = null;
let lastDashboardScanId = null;
let lastDashboardSnapshotId = null;
let dashboardNeedsReloadOnReturn = false;
const RECENT_SEARCH_KEY = "SMART_MONEY_RECENT_SEARCHES";

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function postJson(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function batchIdsFromResponses(responses) {
  return [...new Set(responses.map((item) => item?.snapshot_id).filter(Boolean))];
}

async function fetchDashboardBundle() {
  const officialOnly = "false";
  return Promise.all([
    getJson("/api/health"),
    getJson("/api/market/flow"),
    getJson("/api/market/status"),
    getJson(`/api/rankings/latest?official_full_only=${officialOnly}`),
    getJson(`/api/dashboard/latest?official_full_only=${officialOnly}`),
    getJson("/api/discord/queue"),
  ]);
}

async function fetchConsistentDashboardBundle() {
  let bundle = await fetchDashboardBundle();
  let ids = batchIdsFromResponses(bundle.slice(0, 5));
  if (ids.length <= 1) return { bundle, retried: false };
  await sleep(350);
  bundle = await fetchDashboardBundle();
  ids = batchIdsFromResponses(bundle.slice(0, 5));
  return { bundle, retried: true, inconsistent: ids.length > 1 };
}

function setRefreshBusy(isBusy) {
  const button = $("refresh");
  button.disabled = isBusy;
  button.classList.toggle("spinning", isBusy);
  button.textContent = isBusy ? "…" : "↻";
}

function setRefreshStatus(message, tone = "") {
  const target = $("refreshStatus");
  if (!target) return;
  target.textContent = message || "";
  target.className = `refresh-status ${tone}`.trim();
}

function previousChangeText(value, direction) {
  const amount = Number(value || 0);
  if (!amount) return "";
  const label = direction === "OUTFLOW" || amount < 0 ? "較上次流出" : "較上次流入";
  return `${label} ${yi(Math.abs(amount), true)}`;
}

function currentFlowAmount(flow) {
  return Number(flow?.stock_flow_proxy_amount ?? flow?.display_signed_flow_yi ?? flow?.signed_flow_yi ?? flow?.trade_value_yi ?? 0);
}

function stockSummaryCard(detail) {
  const stock = detail.stock_info || {};
  const flow = detail.current_flow || {};
  const topicList = cleanTopics(detail.topics || [stock.primary_theme, stock.official_industry, ...(stock.themes || [])]);
  const direction = flow.direction || stock.flow_direction || "NEUTRAL";
  const amount = Math.abs(currentFlowAmount(flow));
  const quoteTime = stock.market_data_time || stock.source_ts || stock.timestamp || flow.quote_time || flow.timestamp;
  const industry = displayIndustryName(stock.official_industry || stock.industry);
  const primaryTheme = displayTopicName(stock.primary_theme || topicList[0], topicList.length ? topicList[0] : "題材資料待補");
  return `<section class="stock-card stock-profile">
    <div class="stock-profile-head">
      <div>
        <h2>${h(stock.code || "")} ${h(stock.name || "")}</h2>
        <p>${h(industry)}｜${h(primaryTheme)}</p>
      </div>
      <div class="${directionClass(direction)} stock-profile-flow">${directionText(direction)}<b>${yi(amount, false)}</b></div>
    </div>
    <div class="metric-grid compact stock-profile-grid">
      <span>最新價<b>${stock.price ?? "-"}</b></span>
      <span>漲跌幅<b class="${Number(stock.change_pct || 0) >= 0 ? "red" : "green"}">${pct(stock.change_pct)}</b></span>
      <span>成交金額<b>${yi(stock.trade_value_yi, false)}</b></span>
      <span>資料時間<b>${h(quoteDateTime(quoteTime))}</b></span>
      <span>官方產業<b>${h(industry)}</b></span>
      <span>異動次數<b>${Number(detail.signal_count || 0)} 次</b></span>
    </div>
    <div class="topic-summary">
      <span>所屬題材：${topicList.length ? `${topicList.length} 個` : "資料待補"}</span>
      <b>${h(topicsText(topicList))}</b>
    </div>
  </section>`;
}

function getRecentSearches() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_SEARCH_KEY) || "[]").filter(Boolean).slice(0, 8);
  } catch {
    return [];
  }
}

function saveRecentSearch(query, stock) {
  const label = stock?.code && stock?.name ? `${stock.code} ${stock.name}` : query;
  const item = { query: stock?.code || query, label };
  const next = [item, ...getRecentSearches().filter((old) => old.query !== item.query)].slice(0, 8);
  localStorage.setItem(RECENT_SEARCH_KEY, JSON.stringify(next));
  renderRecentSearches();
}

function renderRecentSearches() {
  const target = $("recentSearches");
  if (!target) return;
  const items = getRecentSearches();
  target.innerHTML = items.length
    ? `<div class="recent-title">最近查詢</div>${items.map((item) => `<button type="button" class="recent-chip" data-recent-stock="${h(item.query)}">${h(item.label)}</button>`).join("")}`
    : "";
  target.querySelectorAll("[data-recent-stock]").forEach((button) => {
    button.onclick = () => {
      $("stockCode").value = button.dataset.recentStock;
      searchStock(button.dataset.recentStock);
    };
  });
}

function topicRankList(title, rows, type, limit = 5) {
  const visibleRows = (rows || []).slice(0, limit);
  const body = visibleRows.length ? visibleRows.map((row, index) => `
    <button class="rank-row" data-topic="${h(row.topic_name)}">
      <span>${index + 1}</span>
      <span>${h(row.topic_name)}</span>
      <span class="${type === "in" ? "red" : "green"}">${yi(row.net_yi)}</span>
      <span class="tiny">⚡ ${Number(row.radar_score || 0)}</span>
    </button>`).join("") : `<div class="rank-empty">暫無符合條件的題材</div>`;
  return `<div><div class="rank-title">${h(title)}</div>${body}</div>`;
}

function stockRankList(title, rows, amountKey, limit = 5) {
  return `<div><div class="rank-title">${h(title)}</div>${(rows || []).slice(0, limit).map((row, index) => {
    const amount = ["relative_flow_pct", "sector_strength_pct"].includes(amountKey)
      ? `${Number(row[amountKey] || 0).toFixed(1)}%`
      : yi(Math.abs(amountKey === "stock_flow_proxy_amount" ? flowAmount(row) : deltaProxy(row)), false);
    const topic = row.primary_theme || row.display_group || (row.topics || [])[0] || "-";
    const dataTime = row.quote_time ? new Date(row.quote_time).toLocaleString("zh-TW", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "-";
    const status = row.freshness_status || "-";
    const flowLabel = row.flow_label || directionText(row.direction);
    return `<button class="rank-row stock-rank" data-stock="${h(row.code)}">
      <span>${index + 1}</span>
      <span>${h(row.code)} ${h(row.name)}<small>${h(topic)}｜資料時間 ${h(dataTime)}｜${h(status)}</small></span>
      <span class="${directionClass(row.direction)}">${amount}</span>
      <span class="${Number(row.change_pct) >= 0 ? "red" : "green"} tiny">${pct(row.change_pct)}<small>${row.last_price ?? row.price ?? "-"}</small><small>${h(flowLabel)}</small></span>
    </button>`;
  }).join("")}</div>`;
}

function marketStatusCard(status) {
  const badgeClass = status.is_realtime_monitoring ? "live" : (status.monitoring_mode === "public_proxy" ? "quasi" : "observe");
  return `<div class="market-status ${badgeClass}">
    <div>
      <b>${h(status.session_label || "市場狀態")}</b>
      <span>${h(status.user_message || "")}</span>
    </div>
    <div class="market-status-meta">
      <span>行情時間 <b>${timeText(status.market_data_time)}</b></span>
      <span>資料狀態 <b>${h(status.freshness_status || "-")}</b></span>
    </div>
  </div>`;
}

function overviewCard(health, market, queue, marketStatus) {
  const stats = queue.stats || {};
  const pushPauseReason = market["push_" + "blocked_" + "reason"];
  const observation = pushPauseReason ? `<div class="mode">觀察模式：目前僅供盤中觀察，正式推播已暫停。</div>` : "";
  const batch = health.batch_label || market.batch_label || "-";
  const snapshot = health.snapshot_id || market.snapshot_id || "-";
  return `<section class="card">
    <h2>即時資金流向</h2>
    ${marketStatusCard(marketStatus || {})}
    <div class="metric-grid">
      <span>推估流入<b class="red">${yi(market.market_inflow_proxy_amount, false)}</b></span>
      <span>推估流出<b class="green">${yi(market.market_outflow_proxy_amount, false)}</b></span>
      <span>推估淨額<b class="${market.market_net_proxy_amount >= 0 ? "red" : "green"}">${yi(market.market_net_proxy_amount)}</b></span>
      <span>本輪變化<b>${yi(market.market_delta_proxy_amount)}</b></span>
      <span>掃描間隔<b>${Number(health.scan_interval_minutes || 0)} 分鐘</b></span>
      <span>下次更新<b>${timeText(health.scheduler_next_run_time)}</b></span>
      <span>推播佇列<b>${Number(stats.pending || 0)} 待推播 / ${Number(stats.sent || 0)} 已推播</b></span>
      <span>資料批次<b>${h(batch)}</b></span>
      <span>批次狀態<b>${health.scan_in_progress ? "掃描中" : (health.is_empty ? "同步中" : "已載入")}</b></span>
    </div>
    <div class="batch-note">本頁行情、排行榜與提醒使用同一批資料：${h(snapshot)}</div>
    ${observation}
  </section>`;
}

function emptyDashboardMessage(health, marketStatus) {
  if (health.scan_in_progress) {
    return {
      title: "正在取得市場資料",
      body: "伺服器正在跑第一輪掃描，完成後畫面會自動更新。Render 剛醒來時通常會需要一小段時間。",
    };
  }
  if (health.last_scan_error) {
    return {
      title: "資料源暫無回應",
      body: `最近一次掃描失敗：${health.last_scan_error}。可以按右上角重新掃描，或等下一輪排程。`,
    };
  }
  if (marketStatus?.user_message) {
    return {
      title: marketStatus.session_label || "目前沒有排行榜資料",
      body: marketStatus.user_message,
    };
  }
  return {
    title: "資料同步中",
    body: "服務剛啟動，正在抓取第一輪市場資料。畫面會自動重試；若你剛開 Render，通常需要一小段時間醒來。",
  };
}

function topicCard(topic) {
  return `<button class="topic-card" data-topic="${h(topic.topic_name)}">
    <div class="topic-head">
      <div><h3>${h(topic.topic_name)}</h3></div>
      <b class="${directionClass(topic.direction)}">${directionText(topic.direction)} ${directionArrow(topic.direction)}｜資金熱度 ⚡${Number(topic.radar_score || 0)}</b>
    </div>
    <div class="metric-grid compact">
      <span>題材淨額<b class="${directionClass(topic.direction)}">${yi(topic.topic_net_proxy_amount)}</b></span>
      <span>較上輪<b>${yi(topic.previous_delta_proxy_amount)}</b></span>
      <span>流入<b class="red">${yi(topic.inflow_yi, false)}</b></span>
      <span>流出<b class="green">${yi(topic.outflow_yi, false)}</b></span>
      <span>資金集中度<b>${Number(topic.concentration_pct || 0).toFixed(0)}%</b></span>
      <span>強 / 弱股數<b>${Number(topic.strong_stock_count || 0)} / ${Number(topic.weak_stock_count || 0)}</b></span>
    </div>
  </button>`;
}

function feedCard(signal) {
  const isStock = signal.target_type === "stock";
  const stockName = isStock ? String(signal.message || "").match(/^stock\s+\S+\s+(.+?)\s+(inflow|outflow|neutral)$/)?.[1] : "";
  const targetLabel = isStock ? `${signal.target_id}${stockName ? ` ${stockName}` : ""}` : `題材 ${signal.target_id}`;
  const amountLabel = isStock ? "個股推估金額" : "題材淨額";
  const clickTarget = isStock ? signal.target_id : signal.target_id;
  return `<button class="signal" data-${isStock ? "stock" : "topic"}="${h(clickTarget)}">
    <div class="signal-row">
      <b>${h(targetLabel)}</b>
      <span class="chip">${isStock ? "個股異動" : "題材異動"}</span>
      <span class="arrow">›</span>
    </div>
    <b class="${directionClass(signal.direction)}">${directionText(signal.direction)} ${directionArrow(signal.direction)}｜資金熱度 ⚡${Number(signal.score || 0)}</b>
    <div class="grid">
      <span>異動時間<b>${timeText(signal.timestamp)}</b></span>
      <span>${amountLabel}<b class="${directionClass(signal.direction)}">${yi(signal.net_yi)}</b></span>
      <span>較上輪<b>${yi(signal.delta_from_previous_yi)}</b></span>
      <span>行情時間<b>${timeText(signal.source_ts)}</b></span>
    </div>
  </button>`;
}

async function loadDashboard() {
  try {
    const { bundle, retried, inconsistent } = await fetchConsistentDashboardBundle();
    const [health, market, marketStatus, rankings, dashboard, queue] = bundle;
    if (retried && inconsistent) {
      setRefreshStatus("資料批次同步中，畫面已重抓一次；若仍不一致，下一輪掃描會自動修正。", "ok");
    }
    if (!dashboard.updated_at && Number(health.result_count || 0) === 0) {
      if (!dashboardRetryTimer) {
        setRefreshStatus("資料同步中，伺服器剛醒來，稍後會自動重試...", "ok");
        dashboardRetryTimer = setTimeout(() => {
          dashboardRetryTimer = null;
          loadDashboard();
        }, 8000);
      }
    } else if (dashboardRetryTimer) {
      clearTimeout(dashboardRetryTimer);
      dashboardRetryTimer = null;
      setRefreshStatus(`資料已載入，資料時間 ${health.market_data_time ? timeText(health.market_data_time) : timeText(dashboard.updated_at)}。`, "ok");
    }
    lastDashboardScanId = dashboard.scan_id || health.scan_id || lastDashboardScanId;
    lastDashboardSnapshotId = dashboard.snapshot_id || health.snapshot_id || lastDashboardSnapshotId;
    $("updated").textContent = `更新 ${timeText(dashboard.updated_at)}`;
    $("overview").innerHTML = overviewCard(health, market, queue || { stats: {} }, marketStatus);
    if (dashboard.is_empty || Number(health.result_count || 0) === 0) {
      const empty = emptyDashboardMessage(health, marketStatus);
      $("rankings").innerHTML = `<section class="card empty-state"><h2>${h(empty.title)}</h2><p>${h(empty.body)}</p><button class="primary" onclick="refreshNow()">立即重新掃描</button></section>`;
      $("signals").innerHTML = `<section class="card empty-state"><h2>最新資金異動提醒</h2><p>第一輪掃描完成後，這裡只會顯示本輪新增的資金異動；行情時間過舊時會暫停顯示。</p></section>`;
      bindClicks();
      return;
    }
    $("rankings").innerHTML = `
      <section class="card"><h2>類股雷達掃描</h2><div class="split">
        ${topicRankList("資金流入 TOP5", rankings.topic_inflow_top50 || [], "in")}
        ${topicRankList("資金流出 TOP5", rankings.topic_outflow_top50 || [], "out")}
      </div></section>
      <section class="card"><h2>每日資金排行榜</h2><div class="split">
        ${stockRankList("個股流入 TOP5", rankings.stock_inflow_top50 || [], "display_signed_flow_yi")}
        ${stockRankList("個股流出 TOP5", rankings.stock_outflow_top50 || [], "display_signed_flow_yi")}
      </div></section>
      <section class="card"><h2>題材雷達卡片</h2><div class="topic-grid">
        ${(dashboard.topic_cards || []).map(topicCard).join("")}
      </div></section>
      <section class="card">
        <div class="card-head"><h2>每日資金排行榜</h2><button id="toggleTopLimit" class="primary">${topLimit === 5 ? "展開 TOP50" : "收合 TOP5"}</button></div>
        <div class="quad">
          ${stockRankList("絕對流入", rankings.stock_inflow_top50 || [], "display_signed_flow_yi", topLimit)}
          ${stockRankList("絕對流出", rankings.stock_outflow_top50 || [], "display_signed_flow_yi", topLimit)}
          ${stockRankList("本輪增量", rankings.unusual_value_top50 || [], "delta_signed_flow_yi", topLimit)}
          ${stockRankList("相對增量", rankings.relative_flow_proxy_top50 || [], "relative_flow_pct", topLimit)}
        </div>
      </section>
      <section class="card"><h2>類股內強度</h2>
        ${stockRankList("類股內排名", rankings.sector_strength_top || [], "sector_strength_pct", 20)}
      </section>`;
    const signalCards = (dashboard.latest_signals || []).map(feedCard).join("");
    const signalEmptyMessage = marketStatus?.user_message || "目前沒有符合即時條件的資金異動。";
    const signalEmpty = `<div class="empty">${h(signalEmptyMessage)}</div>`;
    $("signals").innerHTML = `<section class="card"><h2>最新資金異動提醒</h2><p class="muted">這裡只列出由新行情觸發的題材或個股資金異動；行情時間過舊時會自動暫停顯示。</p>${signalCards || signalEmpty}</section>`;
    bindClicks();
  } catch (error) {
    $("updated").textContent = "載入失敗";
    $("overview").innerHTML = `<section class="card"><h2>前端載入失敗</h2><div class="warning">${h(error?.message || error)}</div></section>`;
    throw error;
  }
}

async function refreshNow() {
  setRefreshBusy(true);
  setRefreshStatus("同步中，正在掃描最新資金資料...");
  let scanResult = null;
  const previousScanId = lastDashboardScanId;
  try {
    try {
      scanResult = await postJson("/api/scan/run");
    } catch (error) {
      scanResult = { scan_started: false, reason: "scan_request_failed" };
    }
    await loadDashboard();
    const health = await getJson("/api/health");
    const dataTime = health.market_data_time ? `資料時間 ${timeText(health.market_data_time)}` : "資料時間 -";
    const nextTime = health.scheduler_next_run_time ? `下一輪 ${timeText(health.scheduler_next_run_time)}` : "";
    const changed = Boolean(scanResult?.batch_changed || (health.scan_id && previousScanId && health.scan_id !== previousScanId));
    let scanMessage = "已重新載入最新畫面";
    if (scanResult?.scan_started) {
      scanMessage = scanResult.forced_opening_scan ? "已補抓開盤資料" : "已重新掃描";
    } else if (scanResult?.reason === "scan_already_running") {
      scanMessage = "掃描已在進行中";
    } else if (scanResult?.reason === "manual_scan_cooldown") {
      scanMessage = `剛掃描過，${scanResult.cooldown_seconds || 30} 秒後可再掃描`;
    }
    const changedText = changed
      ? "已取得新一輪資料"
      : (scanResult?.scan_started ? "已掃描，但資料來源尚未更新" : "資料批次未變");
    setRefreshStatus(`${scanMessage}，${changedText}，${dataTime}${nextTime ? `，${nextTime}` : ""}。`, "ok");
  } catch (error) {
    setRefreshStatus(`刷新失敗：${error?.message || error}`, "error");
  } finally {
    setRefreshBusy(false);
  }
}

function stockSignalCard(signal) {
  const price = signal.price ?? "-";
  const deltaText = previousChangeText(signal.previous_delta_proxy_amount, signal.direction);
  const topicName = displayTopicName(signal.topic_name);
  const canOpenTopic = !isUnknownTopic(signal.topic_name) && topicName !== "個股資金異動";
  return `<button class="signal stock-signal" ${canOpenTopic ? `data-topic="${h(signal.topic_name)}"` : ""}>
    <div class="signal-row">
      <b>${h(topicName)} <span class="chip">${h(levelText(signal.signal_level))}</span></b>
      <span>最新價 ${price}</span>
      <span>${timeText(signal.timestamp)}</span>
      <span class="arrow">${canOpenTopic ? "›" : ""}</span>
    </div>
    <div class="${directionClass(signal.direction)}">${directionText(signal.direction)} ${yi(signal.stock_flow_proxy_amount, false)}　題材淨額：${yi(signal.topic_net_proxy_amount)}</div>
    ${deltaText ? `<div class="${directionClass(signal.direction)}">${h(deltaText)}</div>` : ""}
  </button>`;
}

async function searchStock(query) {
  const normalized = String(query || "").trim();
  if (!normalized) {
    $("stockResult").innerHTML = `<section class="card empty">請輸入股票代號或名稱，查看今日所屬題材與資金異動。</section>`;
    return;
  }
  try {
    const detail = await getJson(`/api/stocks/${encodeURIComponent(normalized)}`);
    if (lastDashboardSnapshotId && detail.snapshot_id && detail.snapshot_id !== lastDashboardSnapshotId) {
      setRefreshStatus("個股資料已切到新批次，返回資金流向時會同步更新首頁。", "ok");
      dashboardNeedsReloadOnReturn = true;
    }
    saveRecentSearch(normalized, detail.stock_info || {});
    $("stockResult").innerHTML = `${stockSummaryCard(detail)}
    <section class="card">
      <h2>今日資金異動（點題材查看詳細名單）</h2>
      ${detail.signal_cards.length ? detail.signal_cards.map(stockSignalCard).join("") : "今日尚無資金異動"}
    </section>`;
    bindClicks();
  } catch {
    $("stockResult").innerHTML = `<section class="card empty">查無此股票或今日尚無資金異動。</section>`;
  }
}

async function openTopic(topicName) {
  if (!topicName) return;
  const detail = await getJson(`/api/topics/${encodeURIComponent(topicName)}`);
  if (lastDashboardSnapshotId && detail.snapshot_id && detail.snapshot_id !== lastDashboardSnapshotId) {
    setRefreshStatus("題材明細已切到新批次，返回資金流向時會同步更新首頁。", "ok");
    dashboardNeedsReloadOnReturn = true;
  }
  const topic = detail.topic_flow;
  const safeTopicName = displayTopicName(topic.topic_name);
  const titleLine = `【${levelText(topic.signal_level)}】異動 ${safeTopicName} ${directionText(topic.direction)}${directionArrow(topic.direction)} ${timeText(topic.timestamp)}`;
  $("sheetBody").innerHTML = `
    <div class="sheet-title">
      <h2>${h(titleLine)}</h2>
    </div>
    <div class="sheet-net ${directionClass(topic.direction)}">題材淨額：${yi(topic.topic_net_proxy_amount)}</div>
    <div class="sheet-flow">流入：${yi(topic.inflow_yi, false)}｜流出：${yi(topic.outflow_yi, false)}</div>
    <div class="mode">${h(topic.top5_coverage_label || "")}</div>
    <hr />
    <h2>影響力 TOP 5 個股 <small>（點擊查看個股資金異動歷史）</small></h2>
    ${(topic.top_impacts || []).slice(0, 5).map((stock, index) => {
      const changeClass = Number(stock.change_pct || 0) >= 0 ? "red" : "green";
      const changeArrow = Number(stock.change_pct || 0) >= 0 ? "↑" : "↓";
      const deltaText = previousChangeText(stock.delta_signed_flow_yi, stock.direction);
      return `<button class="impact-row" data-stock="${h(stock.code)}">
        <span class="impact-rank">${index + 1}.</span>
        <span class="impact-main"><b>${h(stock.code)} ${h(stock.name)}</b>
          <small class="${changeClass}">${changeArrow} ${pct(stock.change_pct)}　${stock.price}</small>
          <small class="${directionClass(stock.direction)}">${directionText(stock.direction).replace("資金", "")} ${yi(Math.abs(stock.stock_flow_proxy_amount), false)}　佔${Number((stock.contribution_ratio || 0) * 100).toFixed(0)}%</small>
          ${deltaText ? `<small class="${directionClass(stock.direction)}">${h(deltaText)}</small>` : ""}
        </span>
        <span class="arrow">›</span>
      </button>`;
    }).join("")}`;
  $("sheet").classList.remove("hidden");
  bindClicks();
}

function bindClicks() {
  document.querySelectorAll("[data-topic]").forEach((element) => {
    element.onclick = () => openTopic(element.dataset.topic);
  });
  document.querySelectorAll("[data-stock]").forEach((element) => {
    element.onclick = () => {
      if (!$("dashboard").classList.contains("hidden")) dashboardScrollY = window.scrollY;
      showTab("search", { fromStockClick: true });
      $("stockCode").value = element.dataset.stock;
      searchStock(element.dataset.stock);
    };
  });
  const toggle = $("toggleTopLimit");
  if (toggle) {
    toggle.onclick = () => {
      topLimit = topLimit === 5 ? 50 : 5;
      loadDashboard();
    };
  }
}

function showTab(tabName, options = {}) {
  const currentTab = document.querySelector(".tabs button.active")?.dataset.tab || "dashboard";
  if (currentTab === "dashboard" && tabName !== "dashboard") dashboardScrollY = window.scrollY;
  if (tabName !== currentTab) previousTab = currentTab;
  document.querySelectorAll(".tabs button").forEach((item) => item.classList.remove("active"));
  document.querySelector(`[data-tab="${tabName}"]`)?.classList.add("active");
  document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.add("hidden"));
  $(tabName).classList.remove("hidden");
  $("backToDashboard")?.classList.toggle("hidden", tabName !== "search");
  if (tabName === "dashboard") {
    if (dashboardNeedsReloadOnReturn) {
      dashboardNeedsReloadOnReturn = false;
      loadDashboard().catch(() => {});
    }
    requestAnimationFrame(() => window.scrollTo({ top: dashboardScrollY, behavior: options.instant ? "auto" : "smooth" }));
  } else {
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: options.instant ? "auto" : "smooth" }));
  }
}

document.querySelectorAll(".tabs button").forEach((button) => {
  button.onclick = () => {
    showTab(button.dataset.tab);
  };
});

$("refresh").onclick = refreshNow;
if ($("officialOnly")) $("officialOnly").onchange = loadDashboard;
$("backToDashboard").onclick = () => showTab("dashboard");
$("stockForm").onsubmit = (event) => {
  event.preventDefault();
  searchStock($("stockCode").value);
};
renderRecentSearches();
$("closeSheet").onclick = () => $("sheet").classList.add("hidden");
$("sheet").onclick = (event) => {
  if (event.target.id === "sheet") $("sheet").classList.add("hidden");
};

$("saveSettings").onclick = async () => {
  const payload = {
    auto_refresh: $("autoRefresh").checked,
    scan_interval_minutes: Number($("scanInterval").value),
    topic_min_net_yi: Number($("topicMinNet").value),
    topic_min_delta_yi: 1,
    repeat_delta_yi: 3,
    stock_min_value_yi: Number($("stockMinValue").value),
    stock_min_delta_yi: 0.3,
    min_value_delta_yi: 0.05,
    stale_seconds: 600,
    net_near_zero_ratio: 0.08,
    only_official_full: $("onlyOfficialFull").checked,
    show_cache_warning: $("showCacheWarning").checked,
    discord_webhook_url: $("webhook").value || "__KEEP_EXISTING__",
    push_enabled: $("pushEnabled").checked,
    stock_signal_enabled: true
  };
  try {
    const result = await postJson("/api/settings", payload);
    $("settingsMessage").textContent = `已儲存；目前掃描間隔 ${result.effective_scan_interval_minutes} 分鐘`;
    $("webhook").value = "";
    await loadSettings();
    await loadDashboard();
  } catch (error) {
    $("settingsMessage").textContent = error.message;
  }
};

$("testDiscord").onclick = async () => {
  try {
    const result = await postJson("/api/discord/test");
    $("settingsMessage").textContent = result.content;
  } catch (error) {
    $("settingsMessage").textContent = error.message;
  }
};

$("flushDiscord").onclick = async () => {
  try {
    const result = await postJson("/api/discord/flush");
    $("settingsMessage").textContent = JSON.stringify(result, null, 2);
    await loadDashboard();
  } catch (error) {
    $("settingsMessage").textContent = error.message;
  }
};

async function loadSettings() {
  const settings = await getJson("/api/settings");
  $("autoRefresh").checked = settings.auto_refresh;
  $("scanInterval").value = settings.scan_interval_minutes;
  $("topicMinNet").value = settings.topic_min_net_yi;
  $("stockMinValue").value = settings.stock_min_value_yi;
  $("onlyOfficialFull").checked = settings.only_official_full;
  $("showCacheWarning").checked = settings.show_cache_warning;
  $("pushEnabled").checked = settings.push_enabled;
  $("webhookMasked").value = settings.discord_webhook_masked || (settings.discord_webhook_configured ? "***" : "not configured");
}

window.addEventListener("error", (event) => {
  const target = $("overview");
  if (target && !target.innerHTML) {
    target.innerHTML = `<section class="card"><h2>前端錯誤</h2><div class="warning">${h(event.message)}</div></section>`;
  }
});

loadDashboard();
loadSettings().catch((error) => {
  $("settingsMessage").textContent = error.message;
});

