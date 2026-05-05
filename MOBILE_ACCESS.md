# Smart Money Radar 外出手機觀看

Smart Money Radar 可以用兩種方式在手機觀看：

1. 不買網域固定網址：Tailscale Funnel
2. 短期測試：Cloudflare quick tunnel
3. 自有網域：Cloudflare named tunnel + 固定網域

## 建議免費固定網址：Tailscale Funnel

Tailscale Funnel 不需要買網域，會給你固定 `ts.net` HTTPS 網址。

第一次請先安裝並登入 Tailscale：

```text
https://tailscale.com/download/windows
```

啟動：

```powershell
.\start_tailscale_funnel.ps1
```

詳細步驟請看：

```text
TAILSCALE_FUNNEL.md
```

## 自有網域：Cloudflare named tunnel

如果你要外出工作也能穩定觀看，請使用 named tunnel。

第一次設定：

```powershell
.\setup_cloudflare_named_tunnel.ps1 -Hostname radar.example.com
```

日常啟動：

```powershell
.\start_cloudflare_named_tunnel.ps1
```

手機網址：

```text
https://radar.example.com/?token=你的AccessToken
```

詳細步驟請看：

```text
CLOUDFLARE_NAMED_TUNNEL.md
```

## 短期測試：quick tunnel

quick tunnel 會產生臨時網址，可能失效或更換，只適合測試：

```powershell
.\start_public_tunnel_cloudflare.ps1
```

## 外網安全邊界

外網 access token 只能 read-only：

- 可看首頁
- 可讀 GET API
- 不可改設定
- 不可改推播規則
- 不可手動掃描

管理操作只允許 localhost 或 admin token。

## 資料狀態

盤中若 TWSE MIS 報價是今天且新鮮，App 會顯示即時資料。

收盤後 App 會使用今日最後可得報價並顯示「收盤」或「觀察模式」，不會冒充盤中即時。
