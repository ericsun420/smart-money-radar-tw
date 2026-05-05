# Smart Money Radar Tailscale Funnel 固定網址

Tailscale Funnel 可以把本機 `127.0.0.1:8000` 對外成固定 HTTPS 網址，不需要買網域。

網址會像：

```text
https://你的電腦名.你的tailnet.ts.net
```

手機外出觀看時加上 access token：

```text
https://你的電腦名.你的tailnet.ts.net/?token=你的AccessToken
```

## 前提

1. 安裝 Tailscale for Windows：  
   https://tailscale.com/download/windows
2. 登入 Tailscale。
3. 在 Tailscale admin console 啟用 Funnel。
4. 本機電腦要開著，Smart Money Radar 才能從外面連。

Tailscale Funnel 官方說明：  
https://tailscale.com/kb/1223/funnel

## 如果 Funnel 還沒開通

如果 `tailscale funnel` 沒有產生網址，通常是 tailnet 尚未啟用 Funnel 權限或 HTTPS certificate。

你仍可先用 Tailscale 私有固定網址，不公開到整個網際網路：

```powershell
.\start_tailscale_private_access.ps1
```

手機需要安裝 Tailscale 並登入同一個帳號，網址會像：

```text
http://desktop-o605cge.tailb9f600.ts.net:8000/?token=你的AccessToken
```

這不是公開網址，但對你自己外出手機觀看最安全、最穩。

## 啟動

在專案根目錄執行：

```powershell
.\start_tailscale_funnel.ps1
```

腳本會做：

1. 確認 Tailscale CLI 存在。
2. 啟動 Smart Money Radar origin server。
3. 檢查 `/api/health`。
4. 執行 `tailscale funnel --bg 8000`。
5. 顯示手機可用網址。

## 停止 Funnel

```powershell
tailscale funnel reset
```

或：

```powershell
tailscale funnel 8000 off
```

## 安全邊界

Smart Money Radar 的外網 access token 仍然有效：

- 一般 token 只能 read-only。
- 外網不能改設定。
- 外網不能改推播規則。
- 外網不能手動掃描。
- 管理操作只允許 localhost 或 admin token。

## 注意

Tailscale Funnel 是公開網址。不要把 token 貼到公開地方。

如果你的網址打不開，通常是：

1. Tailscale 未登入。
2. Funnel 沒啟用。
3. 本機 origin server 沒跑。
4. Windows 防火牆或 Tailscale 權限未允許。
