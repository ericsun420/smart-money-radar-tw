# Smart Money Radar 台股即時資金雷達 App

Smart Money Radar 是台股盤中與收盤資金流向觀察工具。主線只保留五個使用者功能：

1. 即時資金流向
2. 類股雷達掃描
3. 每日資金排行榜
4. 智慧推播提醒
5. 個股資金查詢

本專案定位為資金流向觀察 App。畫面與 API 使用「推估資金流」語言，不使用誇大或無資料依據的交易歸因文案。

## 資料來源

- 盤中：優先使用 TWSE MIS / public proxy 作為準即時觀察資料。
- 收盤後：強制優先使用 TWSE / TPEx 官方日收盤資料，避免盤中 proxy 覆蓋官方收盤價。
- 沒有授權即時行情 API 時，資料會標示為觀察模式，不做正式推播。

目前公開資料來源仍屬觀察用途。若日後提供 Fugle、Fubon 或其他授權行情 API key，才可升級成正式即時行情來源。

## 主要 API

- `GET /api/health`
- `GET /api/market/flow`
- `GET /api/market/status`
- `GET /api/dashboard/latest`
- `GET /api/rankings/latest`
- `GET /api/stocks/{code_or_name}`
- `GET /api/stocks/search/{query}`
- `GET /api/topics/{topic_name}`
- `GET /api/settings`
- `GET /api/alert-rules`
- `POST /api/scan/run`

公開部署時建議設定：

- `SMART_MONEY_ACCESS_TOKEN`：一般讀取 token
- `SMART_MONEY_ADMIN_TOKEN`：管理寫入 token

一般 access token 只應用於查看資料。設定、規則與正式寫入操作應只允許 localhost 或 admin token。

## 本機啟動

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

或使用：

```powershell
.\start_origin_server.bat
```

## Render 部署

目前正式外出觀看版本使用 Render FastAPI/static 網站：

```text
https://smart-money-radar-tw.onrender.com
```

Render 會讀取根目錄 `render.yaml`，以 `backend` 作為服務根目錄。

## 手機外出觀看

建議優先使用 Render 固定網址。其他方式只作為備援或測試：

- Tailscale Funnel：可用，但設定較複雜。
- Cloudflare quick tunnel：只適合短期測試，網址不固定。
- Cloudflare named tunnel：需要自有網域。

更多說明見：

- `FASTAPI_DEPLOY.md`
- `MOBILE_ACCESS.md`
- `TAILSCALE_FUNNEL.md`
- `CLOUDFLARE_NAMED_TUNNEL.md`

## 驗證

```powershell
cd backend
python -m pytest tests -q -p no:cacheprovider
node --check app/static/app.js
```

若要檢查 Render 目前資料狀態：

```text
/api/debug/data_state
```

重點檢查：

- `source_used`
- `market_data_time`
- `snapshot_id`
- `result_count`
- `sample_snapshots`
- `ranking_preview`

## 收盤資料規則

13:35 之後，系統應以官方日收盤資料為準。收盤資料的行情時間固定標示為 `13:30`，不使用程式抓取時間假裝行情仍在更新。
