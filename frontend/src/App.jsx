import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Bell, RefreshCw, Search, Settings, SlidersHorizontal, TrendingDown, TrendingUp, Zap } from "lucide-react";
import { apiGet, apiPost } from "./api/client";
import "./styles/app.css";

const inflow = (d) => d === "INFLOW";
const money = (v, signed = true) => `${signed && v > 0 ? "+" : ""}${Number(v || 0).toFixed(2)}億`;
const pct = (v) => `${v > 0 ? "+" : ""}${Number(v || 0).toFixed(2)}%`;

function RankList({ title, rows, type, topic, onTopic }) {
  return (
    <section className="rank-col">
      <div className="rank-title">{title}</div>
      {rows.map((row, i) => {
        const isIn = type === "in";
        const amount = topic ? row.net_yi : row.signed_flow_yi;
        return (
          <button key={(row.topic_name || row.code) + i} className="rank-row" onClick={() => topic && onTopic(row.topic_name)}>
            <span className="rank-no">{i + 1}</span>
            <span className="rank-name">{topic ? row.topic_name : `${row.code} ${row.name}`}</span>
            <span className={isIn ? "red" : "green"}>{topic ? money(amount) : money(Math.abs(amount), false)}</span>
            {!topic && <span className={row.change_pct >= 0 ? "red tiny" : "green tiny"}>{pct(row.change_pct)}</span>}
          </button>
        );
      })}
    </section>
  );
}

function Card({ title, children, action }) {
  return (
    <section className="card">
      <div className="card-head">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function SignalCard({ signal, onTopic }) {
  const isIn = inflow(signal.direction);
  return (
    <button className="signal-card" onClick={() => onTopic(signal.target_id)}>
      <div className="signal-top">
        <span className="chip">{signal.signal_level}</span>
        <span className="chip">題材</span>
        <strong>{signal.target_id}</strong>
        <span className={isIn ? "red status" : "green status"}>{isIn ? "資金流入" : "資金流出"} <Zap size={14} /> {signal.score}</span>
      </div>
      <div className="signal-grid">
        <span>時間 <b>{new Date(signal.timestamp).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" })}</b></span>
        <span>淨額 <b className={isIn ? "red" : "green"}>{money(signal.net_yi)}</b></span>
        <span>較上次 <b>{money(signal.delta_from_previous_yi)}</b></span>
        <span>資料品質 <b>{signal.data_quality_bucket}</b></span>
      </div>
    </button>
  );
}

function Dashboard({ onTopic }) {
  const [data, setData] = useState(null);
  const [tick, setTick] = useState(3);
  async function load() {
    setData(await apiGet("/api/dashboard/latest"));
    setTick(3);
  }
  useEffect(() => { load(); }, []);
  useEffect(() => {
    const id = setInterval(() => setTick((x) => (x <= 0 ? 3 : x - 1)), 1000);
    return () => clearInterval(id);
  }, []);
  if (!data) return <div className="page">載入中...</div>;
  return (
    <main className="page">
      <header className="hero">
        <div>
          <h1>即時資金雷達</h1>
          <p>更新秒數 00:0{tick}</p>
        </div>
        <button className="icon-btn" onClick={load} title="重新整理"><RefreshCw size={20} /></button>
      </header>
      <Card title="當日題材排行">
        <div className="split">
          <RankList title="資金流入 TOP5" rows={data.topic_inflow_top5} type="in" topic onTopic={onTopic} />
          <RankList title="資金流出 TOP5" rows={data.topic_outflow_top5} type="out" topic onTopic={onTopic} />
        </div>
      </Card>
      <Card title="當日個股排行">
        <div className="split">
          <RankList title="流入 TOP5" rows={data.stock_inflow_top5} type="in" />
          <RankList title="流出 TOP5" rows={data.stock_outflow_top5} type="out" />
        </div>
      </Card>
      <Card title="即時訊號">
        <div className="feed">{data.latest_signals.map((s) => <SignalCard key={s.id} signal={s} onTopic={onTopic} />)}</div>
      </Card>
    </main>
  );
}

function SearchPage({ onTopic }) {
  const [code, setCode] = useState("3035");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setError("");
    try { setData(await apiGet(`/api/stocks/${code}`)); } catch { setData(null); setError("查無此股票或今日尚無訊號"); }
  }
  useEffect(() => { apiGet("/api/stocks/3035").then(setData); }, []);
  return (
    <main className="page">
      <h1>個股查詢</h1>
      <form className="searchbar" onSubmit={submit}>
        <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="股票代號" />
        <button><Search size={18} /> 查詢</button>
      </form>
      {error && <div className="empty">{error}</div>}
      {data && <StockResult data={data} onTopic={onTopic} />}
    </main>
  );
}

function StockResult({ data, onTopic }) {
  const s = data.stock_info;
  const f = data.current_flow;
  const isIn = inflow(f.direction);
  return (
    <>
      <section className="stock-card">
        <div><h2>{s.code} {s.name}</h2><span>{data.topics.join("、")}</span></div>
        <div className="price">{s.price}</div>
        <div className={s.change_pct >= 0 ? "red" : "green"}>{pct(s.change_pct)}</div>
        <div>成交額：{money(s.trade_value_yi, false)}</div>
        <div className={isIn ? "red" : "green"}>{isIn ? "資金流入" : "資金流出"}</div>
        <div>出現題材：{data.topics.length} 個｜訊號次數：{data.signal_count} 次</div>
        {s.data_quality_bucket !== "official_full" && <div className="warning">cache_only：僅顯示，不進入正式推播與調參</div>}
      </section>
      <Card title="各題材明細">
        {data.signal_history.length === 0 && <div className="empty">今日尚無資金訊號</div>}
        <div className="feed">{data.signal_history.map((x) => <SignalCard key={x.id} signal={x} onTopic={onTopic} />)}</div>
      </Card>
    </>
  );
}

function SettingsPage() {
  const [settings, setSettings] = useState(null);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => { apiGet("/api/settings").then(setSettings); }, []);
  if (!settings) return <main className="page">載入中...</main>;
  const set = (k, v) => setSettings({ ...settings, [k]: v });
  async function save() {
    await apiPost("/api/settings", { ...settings, discord_webhook_url: webhookUrl || "__KEEP_EXISTING__" });
    setWebhookUrl("");
    setMessage("設定已儲存");
  }
  async function testPush() {
    try { const res = await apiPost("/api/discord/test"); setMessage(res.content); } catch (e) { setMessage("測試推播失敗，請確認 webhook URL"); }
  }
  return (
    <main className="page">
      <h1>設定</h1>
      <div className="settings-list">
        <Toggle label="自動刷新" value={settings.auto_refresh} onChange={(v) => set("auto_refresh", v)} />
        <NumberField label="掃描間隔（分鐘）" value={settings.scan_interval_minutes} onChange={(v) => set("scan_interval_minutes", v)} />
        <NumberField label="題材最小淨額門檻（億）" value={settings.topic_min_net_yi} onChange={(v) => set("topic_min_net_yi", v)} />
        <NumberField label="個股最小成交額門檻（億）" value={settings.stock_min_value_yi} onChange={(v) => set("stock_min_value_yi", v)} />
        <Toggle label="只顯示 official_full" value={settings.only_official_full} onChange={(v) => set("only_official_full", v)} />
        <Toggle label="顯示 cache_only 警告" value={settings.show_cache_warning} onChange={(v) => set("show_cache_warning", v)} />
        <label className="field">Discord webhook URL<input value={webhookUrl} placeholder={settings.discord_webhook_masked || "留空沿用既有 webhook"} onChange={(e) => setWebhookUrl(e.target.value)} /></label>
        <Toggle label="推播開關" value={settings.push_enabled} onChange={(v) => set("push_enabled", v)} />
      </div>
      <div className="actions"><button onClick={save}>儲存</button><button onClick={testPush}>測試推播</button></div>
      {message && <pre className="message">{message}</pre>}
    </main>
  );
}

function Toggle({ label, value, onChange }) {
  return <label className="toggle"><span>{label}</span><input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} /></label>;
}

function NumberField({ label, value, onChange }) {
  return <label className="field">{label}<input type="number" step="0.1" value={value} onChange={(e) => onChange(Number(e.target.value))} /></label>;
}

function TopicSheet({ topic, onClose }) {
  const [data, setData] = useState(null);
  useEffect(() => { if (topic) apiGet(`/api/topics/${encodeURIComponent(topic)}`).then(setData); }, [topic]);
  if (!topic) return null;
  const flow = data?.topic_flow;
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <section className="sheet" onClick={(e) => e.stopPropagation()}>
        {!flow ? "載入中..." : <>
          <div className="sheet-handle" />
          <h2>{flow.topic_name}</h2>
          <div className={inflow(flow.direction) ? "red status-line" : "green status-line"}>{inflow(flow.direction) ? "資金流入" : "資金流出"} ⚡ {flow.signal_score}</div>
          <div className="sheet-grid">
            <span>訊號時間 <b>{new Date(flow.timestamp).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" })}</b></span>
            <span>題材淨額 <b>{money(flow.net_yi)}</b></span>
            <span>流入總額 <b>{money(flow.inflow_yi, false)}</b></span>
            <span>流出總額 <b>{money(flow.outflow_yi, false)}</b></span>
            <span>資金集中度 <b>{flow.concentration_pct.toFixed(0)}%</b></span>
          </div>
          <h3>前 5 大影響個股</h3>
          {flow.top_impacts.map((s, i) => (
            <div className="impact" key={s.code}>
              <span>{i + 1}. {s.code} {s.name}</span>
              <b className={s.change_pct >= 0 ? "red" : "green"}>{pct(s.change_pct)}</b>
              <span>{s.price}</span>
              <span className={inflow(s.direction) ? "red" : "green"}>{money(Math.abs(s.signed_flow_yi), false)}｜佔{s.impact_pct.toFixed(0)}%</span>
            </div>
          ))}
        </>}
      </section>
    </div>
  );
}

function App() {
  const [tab, setTab] = useState("dashboard");
  const [topic, setTopic] = useState(null);
  const body = useMemo(() => tab === "dashboard" ? <Dashboard onTopic={setTopic} /> : tab === "search" ? <SearchPage onTopic={setTopic} /> : <SettingsPage />, [tab]);
  return (
    <>
      {body}
      <nav className="tabs">
        <button className={tab === "dashboard" ? "active" : ""} onClick={() => setTab("dashboard")}><TrendingUp size={18} />資金流向</button>
        <button className={tab === "search" ? "active" : ""} onClick={() => setTab("search")}><Search size={18} />搜尋</button>
        <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}><SlidersHorizontal size={18} />設定</button>
      </nav>
      <TopicSheet topic={topic} onClose={() => setTopic(null)} />
    </>
  );
}

createRoot(document.getElementById("root")).render(<App />);
