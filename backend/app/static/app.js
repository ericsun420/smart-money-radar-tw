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

let topLimit = 5;
let dashboardScrollY = 0;
let previousTab = "dashboard";
let dashboardRetryTimer = null;

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

function overviewCard(health, market, queue) {
  const stats = queue.stats || {};
  const pushPauseReason = market["push_" + "blocked_" + "reason"];
  const observation = pushPauseReason ? `<div class="mode">觀察模式：目前僅供盤中觀察，正式推播已暫停。</div>` : "";
  return `<section class="card">
    <h2>即時資金流向</h2>
    <div class="metric-grid">
      <span>推估流入<b class="red">${yi(market.market_inflow_proxy_amount, false)}</b></span>
      <span>推估流出<b class="green">${yi(market.market_outflow_proxy_amount, false)}</b></span>
      <span>推估淨額<b class="${market.market_net_proxy_amount >= 0 ? "red" : "green"}">${yi(market.market_net_proxy_amount)}</b></span>
      <span>本輪變化<b>${yi(market.market_delta_proxy_amount)}</b></span>
      <span>掃描間隔<b>${Number(health.scan_interval_minutes || 0)} 分鐘</b></span>
      <span>下次更新<b>${timeText(health.scheduler_next_run_time)}</b></span>
      <span>推播佇列<b>${Number(stats.pending || 0)} 待推播 / ${Number(stats.sent || 0)} 已推播</b></span>
    </div>
    ${observation}
  </section>`;
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
    const officialOnly = "false";
    const [health, market, rankings, dashboard, queue] = await Promise.all([
      getJson("/api/health"),
      getJson("/api/market/flow"),
      getJson(`/api/rankings/latest?official_full_only=${officialOnly}`),
      getJson(`/api/dashboard/latest?official_full_only=${officialOnly}`),
      getJson("/api/discord/queue"),
    ]);
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
    $("updated").textContent = `更新 ${timeText(dashboard.updated_at)}`;
    $("overview").innerHTML = overviewCard(health, market, queue || { stats: {} });
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
    $("signals").innerHTML = `<section class="card"><h2>最新資金異動提醒</h2><p class="muted">這裡列出達到提醒條件的題材或個股資金異動，方便外出時快速判斷要不要點進去追蹤。</p>${(dashboard.latest_signals || []).map(feedCard).join("")}</section>`;
    bindClicks();
  } catch (error) {
    $("updated").textContent = "載入失敗";
    $("overview").innerHTML = `<section class="card"><h2>前端載入失敗</h2><div class="warning">${h(error?.message || error)}</div></section>`;
    throw error;
  }
}

async function refreshNow() {
  setRefreshBusy(true);
  setRefreshStatus("同步中，正在重新讀取最新資金資料...");
  let scanMessage = "";
  try {
    try {
      await postJson("/api/scan/run");
      scanMessage = "已完成手動掃描";
    } catch (error) {
      scanMessage = "已重新載入最新畫面";
    }
    await loadDashboard();
    const health = await getJson("/api/health");
    const dataTime = health.market_data_time ? `資料時間 ${timeText(health.market_data_time)}` : "資料時間 -";
    const nextTime = health.scheduler_next_run_time ? `下一輪 ${timeText(health.scheduler_next_run_time)}` : "";
    setRefreshStatus(`${scanMessage}，${dataTime}${nextTime ? `，${nextTime}` : ""}。`, "ok");
  } catch (error) {
    setRefreshStatus(`刷新失敗：${error?.message || error}`, "error");
  } finally {
    setRefreshBusy(false);
  }
}

function stockSignalCard(signal) {
  const price = signal.price ?? "-";
  const deltaText = previousChangeText(signal.previous_delta_proxy_amount, signal.direction);
  return `<button class="signal stock-signal" data-topic="${h(signal.topic_name)}">
    <div class="signal-row">
      <b>${h(signal.topic_name || "題材異動")} <span class="chip">${h(levelText(signal.signal_level))}</span></b>
      <span>${price}</span>
      <span>${timeText(signal.timestamp)}</span>
      <span class="arrow">›</span>
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
    const stock = detail.stock_info;
    $("stockResult").innerHTML = `<section class="stock-card summary-card">
      <div class="summary-line">
        <span>所屬題材：${Number(detail.topics.length || 0)} 個</span>
        <span>異動次數：${Number(detail.signal_count || 0)} 次</span>
      </div>
      <div>題材：${h(detail.topics.join(" / ") || "-")}</div>
    </section>
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
  const topic = detail.topic_flow;
  const titleLine = `【${levelText(topic.signal_level)}】異動 ${topic.topic_name} ${directionText(topic.direction)}${directionArrow(topic.direction)} ${timeText(topic.timestamp)}`;
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
  $("backToDashboard")?.classList.toggle("hidden", tabName !== "search" || (!options.fromStockClick && previousTab !== "dashboard"));
  if (tabName === "dashboard") {
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

