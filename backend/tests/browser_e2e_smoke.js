const assert = require("node:assert/strict");

const base = process.env.RADAR_BASE_URL || "http://127.0.0.1:8000";
const accessToken = process.env.RADAR_ACCESS_TOKEN || "";

async function get(path) {
  const res = await fetch(`${base}${path}`, {
    headers: accessToken ? { "x-smart-money-token": accessToken } : {},
  });
  assert.equal(res.ok, true, `${path} returned ${res.status}`);
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res.text();
}

(async () => {
  const html = await get("/");
  assert.match(html, /Smart Money Radar/);
  assert.doesNotMatch(html, /featureGrid/);

  const appJs = await get("/static/app.js");
  assert.match(appJs, /即時資金流向/);
  assert.match(html, /個股資金查詢/);
  assert.match(html, /請輸入股票代號或名稱/);
  assert.doesNotMatch(html, /value="3035"/);
  assert.doesNotMatch(appJs, /searchStock\("3035"\)/);
  assert.doesNotMatch(appJs, /本資料僅供觀察，不可正式推播/);
  assert.doesNotMatch(appJs, /qualityBadge\(t\)/);
  assert.doesNotMatch(appJs, /跨平台同步/);
  assert.doesNotMatch(appJs, /主力買賣|真實內外盤|真實主力買超/);

  const css = await get("/static/styles.css");
  assert.match(css, /@media \(max-width: 680px\)/);

  const health = await get("/api/health");
  assert.equal(health.ok, true);

  const market = await get("/api/market/flow");
  assert.equal(market.formal_grade, false);
  assert.equal(market.data_quality_bucket, "official_partial");

  const rankings = await get("/api/rankings/latest");
  assert.ok(rankings.stock_inflow_top50.length > 0);
  assert.ok(rankings.relative_flow_proxy_top50.length > 0);
  assert.equal(Object.hasOwn(rankings, "relative_flow_top50"), false);

  const stock5351 = await get("/api/stocks/5351");
  assert.equal(stock5351.stock_info.code, "5351");
  assert.ok(Array.isArray(stock5351.signal_cards));

  const stock2464 = await get("/api/stocks/2464");
  assert.equal(stock2464.stock_info.code, "2464");
  assert.ok(Array.isArray(stock2464.signal_cards));

  const topicName = encodeURIComponent((rankings.topic_inflow_top50[0] || rankings.topic_outflow_top50[0]).topic_name);
  const topic = await get(`/api/topics/${topicName}`);
  assert.ok(topic.topic_flow.top_impacts.length > 0);

  assert.equal(appJs.includes('"><img src=x onerror=alert(1)>'), false);
  assert.equal(appJs.includes("<script>alert(1)</script>"), false);
  console.log("browser_e2e_smoke passed");
})();
