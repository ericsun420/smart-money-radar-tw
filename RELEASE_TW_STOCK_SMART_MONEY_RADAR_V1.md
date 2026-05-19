# Smart Money Radar 台股即時資金雷達 App 第一版基準

日期：2026-05-19

## 產品主線

本版本收斂為台股資金雷達 App，只保留五個主功能：

1. 即時資金流向
2. 類股雷達掃描
3. 每日資金排行榜
4. 智慧推播提醒
5. 個股資金查詢

產品定位為資金流向觀察 App，主線集中在市場、類股與個股資金動能。

## 已完成

- 移除首頁功能介紹卡與不屬於第一版主線的功能文案。
- 搜尋頁改成空狀態，不預設查詢 3035。
- 個股查詢支援代號與名稱搜尋。
- 題材 Bottom Sheet 顯示題材淨額、流入/流出與影響力 TOP5。
- 首頁、排行榜、個股頁、題材頁回傳同一批 `scan_id / snapshot_id`。
- Render 冷啟動時，首頁會自動補掃並輪詢等待資料。
- 開盤後資料還停在盤前或過期時，手動刷新會繞過 cooldown 立即補抓。
- 收盤後強制優先使用 TWSE / TPEx 官方日收盤資料。
- 收盤資料行情時間固定標示為 `13:30`，避免用抓取時間誤導。
- 非正式資料來源維持觀察模式，不做正式推播。

## 資料來源規則

- 盤中：使用 TWSE MIS / public proxy 作為準即時觀察。
- 收盤後：使用 TWSE / TPEx 官方日收盤。
- 未提供授權即時行情 API 前，只呈現推估資金流與觀察模式。

## 驗證項目

- `node --check backend/app/static/app.js`
- `pytest tests/test_p0_hardening.py -q -p no:cacheprovider`
- `/api/health`
- `/api/debug/data_state`
- `/api/rankings/latest`
- `/api/stocks/{code_or_name}`

## 注意事項

Render 免費方案可能冷啟動。若首頁初次打開無資料，系統會自動補掃，但仍需等待資料源回應。
