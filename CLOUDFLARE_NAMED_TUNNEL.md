# Smart Money Radar 固定網域 Cloudflare Named Tunnel

這份文件是正式外出觀看用。它取代 `trycloudflare.com` quick tunnel，避免網址一直更換。

## 前提

1. 你有 Cloudflare 帳號。
2. 你的網域已經託管在 Cloudflare，例如 `example.com`。
3. 你要使用一個子網域，例如：

```text
radar.example.com
```

Cloudflare named tunnel 官方流程是：登入、建立 tunnel、寫 config、route DNS、run tunnel。參考 Cloudflare 官方文件：  
https://developers.cloudflare.com/tunnel/advanced/local-management/create-local-tunnel/

## 第一次設定

在專案根目錄執行：

```powershell
.\setup_cloudflare_named_tunnel.ps1 -Hostname radar.example.com
```

請把 `radar.example.com` 換成你的固定網域。

執行後會做這些事：

1. 開啟 Cloudflare login。
2. 建立 `smart-money-radar` named tunnel。
3. 產生 `~\.cloudflared\smart-money-radar.yml`。
4. 建立 DNS route。
5. 產生 `.smart-money-radar.env.ps1`。
6. 產生或保存 read-only access token。

完成後會顯示：

```text
https://radar.example.com/?token=你的AccessToken
```

手機外出時就是開這個網址。

## 日常啟動

之後每次要開固定網域服務：

```powershell
.\start_cloudflare_named_tunnel.ps1
```

或明確指定：

```powershell
.\start_cloudflare_named_tunnel.ps1 -Hostname radar.example.com
```

## 權限邊界

外網使用 `SMART_MONEY_ACCESS_TOKEN` 是 read-only：

- 可讀首頁與 GET API。
- 不可修改設定。
- 不可修改推播規則。
- 不可手動觸發掃描。

寫入操作只允許：

- localhost
- 或帶 `SMART_MONEY_ADMIN_TOKEN`

## 502 / 1033 怎麼處理

如果 Cloudflare 顯示 502 或 1033，通常代表：

1. 本機 FastAPI origin 沒跑起來。
2. cloudflared tunnel 沒跑。
3. DNS route 還沒生效。
4. tunnel config 的 hostname 或 port 寫錯。

檢查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health -Headers @{ "x-smart-money-token" = "你的AccessToken" }
```

如果本機 health 不通，先重啟：

```powershell
.\start_cloudflare_named_tunnel.ps1
```

## 注意

收盤後 App 會使用今日最後可得報價並顯示「收盤」或「觀察模式」，不會冒充盤中即時。

