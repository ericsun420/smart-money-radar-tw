# Smart Money Radar 台股即時資金雷達 App

Smart Money Radar 是台股盤中資金流向觀察 App。第一版主線只保留五個功能：

1. 即時資金流向
2. 類股雷達掃描
3. 每日資金排行榜
4. 智慧推播提醒
5. 個股資金查詢

本系統使用公開市場資料推估資金流向，僅供觀察資金動能與題材輪動。

## 資料來源

主要資料流程：

1. TWSE MIS 今日報價：`https://mis.twse.com.tw/stock/api/getStockInfo.jsp`
2. TWSE / TPEx 官方 OpenAPI：作為上市櫃普通股與日資料校驗/備援
3. seed/cache：只作測試或開發，不作正式觀察與推播

盤中若 TWSE MIS 報價是今日且新鮮，App 會標示為即時資料。收盤後會使用今日最後可得報價並標示為收盤或觀察模式，不會冒充盤中即時。

## API

- `GET /api/health`
- `GET /api/market/flow`
- `GET /api/dashboard/latest`
- `GET /api/rankings/latest`
- `GET /api/stocks/{code_or_name}`
- `GET /api/stocks/search/{query}`
- `GET /api/topics/{topic_name}`
- `GET /api/settings`
- `GET /api/alert-rules`
- `POST /api/settings`
- `POST /api/alert-rules`
- `POST /api/scan/run`

外網模式建議設定 `SMART_MONEY_ACCESS_TOKEN`。一般 access token 只能讀取 GET API；設定、推播規則與手動掃描需 localhost 或 `SMART_MONEY_ADMIN_TOKEN`。

## 本機啟動

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

或：

```powershell
.\start_origin_server.bat
```

## 手機外出觀看

不買網域固定網址，建議使用 Tailscale Funnel：

```powershell
.\start_tailscale_funnel.ps1
```

說明文件：

```text
TAILSCALE_FUNNEL.md
```

短期測試：

```powershell
.\start_public_tunnel_cloudflare.ps1
```

正式固定網域：

```powershell
.\setup_cloudflare_named_tunnel.ps1 -Hostname radar.example.com
.\start_cloudflare_named_tunnel.ps1
```

請把 `radar.example.com` 換成你的 Cloudflare 網域。完整說明見：

```text
CLOUDFLARE_NAMED_TUNNEL.md
```

## 驗證

```powershell
cd backend
python -m pytest tests -q -p no:cacheprovider
node --check app/static/app.js
```

## 健康檢查重點

`/api/health` 會回傳：

- `data_source`
- `data_source_status`
- `is_realtime`
- `is_intraday`
- `realtime_provider`
- `market_data_time`
- `data_latency_seconds`
- `realtime_count`

若不是盤中新鮮資料，App 會進入觀察模式，不會正式推播。
