# Smart Money Radar 台股即時資金雷達 App 第一版基準

更新日期：2026-04-30

## 產品主線

第一版收斂為台股即時資金雷達 App，只保留五個前台功能：

1. 即時資金流向
2. 類股雷達掃描
3. 每日資金排行榜
4. 智慧推播提醒
5. 個股資金查詢

已移除首頁功能介紹卡。產品定位是盤中資金雷達 App，不是交易策略工具、歷史績效工具或單一通知工具。

## 本輪即時資料補強

- 新增 TWSE MIS 盤中即時報價 provider。
- 以 TWSE / TPEx 官方日資料建立上市櫃股票池，再用 MIS 報價覆蓋盤中價格、量與時間。
- 新增 `official_intraday` 狀態，用於代表盤中即時報價通過覆蓋率與新鮮度檢查。
- `/api/health` 與 `/api/market/flow` 增加：
  - `is_realtime`
  - `is_intraday`
  - `realtime_provider`
  - `market_data_time`
  - `data_latency_seconds`
  - `realtime_count`
- 若 MIS 覆蓋率不足，系統自動退回 `official_partial` 觀察模式。

## 重要限制

- MIS 不是逐筆內外盤資料。
- 成交金額為推估 proxy，不是真實逐筆成交金額拆解。
- UI 不宣稱逐筆買賣方向或特定法人交易方向。
- `official_partial`、fallback、cache-only、seed 不進正式推播。

## 外出觀看

- 已支援 access token read-only 外網模式。
- 已支援 admin token 寫入保護。
- Cloudflare quick tunnel 僅供測試。
- 已新增 Cloudflare named tunnel 固定網域腳本：
  - `setup_cloudflare_named_tunnel.ps1`
  - `start_cloudflare_named_tunnel.ps1`
  - `CLOUDFLARE_NAMED_TUNNEL.md`

## 驗收重點

- 首頁不顯示六張功能卡。
- 個股查詢頁不預設 3035。
- UI 預設隱藏資料品質 debug chip。
- 健康檢查可看目前是否為即時盤中資料。
- 題材與個股金額仍以推估資金流呈現。
