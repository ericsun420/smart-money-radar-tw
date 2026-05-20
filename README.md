# Smart Money Radar 台股即時資金雷達 App

Smart Money Radar 是台股盤中資金流向觀察工具，以公開市場資料推估個股與題材的資金動能。這不是策略調參工具，也不是單純推播工具。

## 主功能

1. 即時資金流向
2. 類股雷達掃描
3. 每日資金排行榜
4. 智慧推播提醒
5. 個股資金查詢

## 資料說明

- 盤中優先使用 TWSE MIS / public proxy 作為準即時觀察資料。
- 收盤後優先使用 TWSE / TPEx 官方日收盤資料，避免舊 quote 或 cache 污染排行。
- 若沒有授權即時行情 API，前台會標示為準即時觀察、延遲或收盤，不會使用誇大成交方向文案。
- 正式即時推播需要授權即時資料源。目前若是準即時或觀察模式，僅供盤中觀察。

## API

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

公開外網模式建議設定：

- `SMART_MONEY_ACCESS_TOKEN`：讀取用 token
- `SMART_MONEY_ADMIN_TOKEN`：管理用 token

一般 access token 只能讀取畫面與 API；設定、推播規則與手動掃描建議只允許 localhost 或 admin token 操作。

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

目前主線部署為 Render FastAPI/static 版：

```text
https://smart-money-radar-tw.onrender.com
```

Render 設定見 `render.yaml`，服務根目錄為 `backend`。

## 行動外網觀看

- Render：目前主線固定網址。
- Tailscale Funnel：可作為個人設備對外測試。
- Cloudflare quick tunnel：僅建議測試使用，不適合當長期固定網址。
- Cloudflare named tunnel：長期可用，但需固定網域與權限設定。

參考文件：

- `FASTAPI_DEPLOY.md`
- `MOBILE_ACCESS.md`
- `TAILSCALE_FUNNEL.md`
- `CLOUDFLARE_NAMED_TUNNEL.md`

## 舊版 Streamlit

Streamlit 舊版已收納到 `legacy/streamlit/`，僅供參考與比對。主產品線以 FastAPI/static App 為準。

## 測試

```powershell
cd backend
python -m pytest tests -q -p no:cacheprovider
node --check app/static/app.js
```

開發用資料狀態：

```text
/api/debug/data_state
```
