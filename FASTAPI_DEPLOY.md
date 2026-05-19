# Smart Money Radar FastAPI 部署

目前主線部署方式是 FastAPI + static frontend，不使用 Streamlit 版本作為正式入口。

## Render Blueprint

1. 登入 Render。
2. 選擇 New -> Blueprint。
3. 連接 GitHub repository：

```text
ericsun420/smart-money-radar-tw
```

4. Render 會讀取根目錄 `render.yaml`。
5. 服務啟動後入口為：

```text
https://smart-money-radar-tw.onrender.com
```

## 重要環境變數

- `SMART_MONEY_ACCESS_TOKEN`：一般讀取 token。
- `SMART_MONEY_ADMIN_TOKEN`：管理寫入 token。
- `SMART_MONEY_CORS_ORIGINS`：允許來源，公開模式不要使用 wildcard。

建議值：

```text
https://smart-money-radar-tw.onrender.com,http://127.0.0.1:8000,http://localhost:8000
```

## 啟動命令

Render 目前使用：

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## 健康檢查

```text
/render-health
```

## 部署後檢查

建議依序確認：

```text
/api/health
/api/debug/data_state
/api/market/flow
/api/rankings/latest
/api/stocks/2330
```

收盤後應確認 `source_used` 為 TWSE/TPEx 官方收盤路徑，行情時間應為 `13:30`。
