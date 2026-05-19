# Smart Money Radar 手機外出觀看

目前建議使用 Render 固定網址作為手機外出觀看入口：

```text
https://smart-money-radar-tw.onrender.com
```

如果部署環境設定了 `SMART_MONEY_ACCESS_TOKEN`，第一次開啟請使用：

```text
https://smart-money-radar-tw.onrender.com/?token=你的_ACCESS_TOKEN
```

成功後瀏覽器會寫入 cookie，之後可直接開 Render 網址。

## 權限邊界

- 一般 access token：只用於查看資料。
- admin token：只用於管理設定、推播規則與寫入操作。
- 手機外出觀看不應使用 admin token。

## 推薦方案

### Render

最簡單、固定網址、適合外出查看。缺點是免費方案可能冷啟動，需要等待服務喚醒。

### Tailscale Funnel

可用，但需要 Tailscale 管理設定與 Funnel 權限。適合私人使用，不是目前主線部署方式。

### Cloudflare quick tunnel

只適合短期測試，網址可能變動，不建議作為日常入口。

### Cloudflare named tunnel

穩定，但需要自有網域。

## 資料狀態說明

- 盤中：若公開來源可取得新資料，畫面會顯示準即時觀察。
- 收盤後：系統應切回 TWSE / TPEx 官方日收盤資料。
- 若資料源暫停或 Render 剛醒來，首頁會自動補掃並短暫輪詢。
