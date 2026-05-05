# Smart Money Radar 原版網站部署

這份部署方式是跑原本完整的 FastAPI/static 網站，不是 Streamlit 簡化版。

## Render 免費部署

1. 到 Render 建立帳號：
   https://render.com/
2. New → Blueprint
3. 選 GitHub repo：
   `ericsun420/smart-money-radar-tw`
4. Render 會讀取 repo 根目錄的 `render.yaml`
5. 建立服務後，Render 會提供固定網址，例如：
   `https://smart-money-radar-tw.onrender.com`

## 安全設定

外網預設只適合讀取資料。即使未設定 token，非 localhost 的 POST API 也會被擋下。

建議在 Render Environment 裡設定：

- `SMART_MONEY_ACCESS_TOKEN`
- `SMART_MONEY_ADMIN_TOKEN`

設定 access token 後，入口會變成：

```text
https://你的-render網址/?token=你的SMART_MONEY_ACCESS_TOKEN
```

第一次開啟會寫入 cookie，後續手機瀏覽不必每次貼 token。

## 注意

- Render free 服務可能會休眠，第一次開啟需要等待冷啟動。
- 本 App 顯示的是推估資金流向，不是真實主力買賣或逐筆內外盤。
- 若資料源回傳延遲，UI 會以觀察模式顯示。
