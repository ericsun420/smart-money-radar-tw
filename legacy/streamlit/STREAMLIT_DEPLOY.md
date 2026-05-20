# Smart Money Radar Streamlit Cloud 部署

這是最省事的外出手機觀看方案。不需要 Cloudflare、不需要 Tailscale、不需要買網域。

部署後網址會像：

```text
https://你的-app-name.streamlit.app
```

## 這版定位

Streamlit 版是「手機外出觀看版」：

- 打開頁面時抓 TWSE MIS / TWSE / TPEx 公開資料。
- 即時計算推估資金流、類股雷達、每日排行榜。
- 支援個股資金查詢。
- 不跑本機 FastAPI server。
- 不跑常駐 scheduler。
- 不跑 Discord queue。

也就是：它適合外出看盤，不是取代家裡本機完整版。

## 檔案

Streamlit Cloud 會使用：

```text
streamlit_app.py
requirements.txt
.streamlit/config.toml
```

## 部署步驟

1. 把專案推到 GitHub。
2. 打開 Streamlit Community Cloud：  
   https://share.streamlit.io/
3. 選擇 GitHub repo。
4. Branch 選你的主分支。
5. Main file path 填：

```text
streamlit_app.py
```

6. Deploy。

## 使用方式

手機打開 Streamlit Cloud 給你的網址。

頁面左側或上方功能：

- 資金流向
- 個股資金查詢

資料快取 60 秒。按「重新抓取資料」會清除快取並重新掃描。

## 即時資料聲明

盤中若 TWSE MIS 今日報價新鮮，會顯示即時資料。

收盤後會使用今日最後可得報價並顯示收盤或觀察模式，不會冒充盤中即時。

本系統使用公開市場資料推估資金流向，只作觀察，不作投資建議。

