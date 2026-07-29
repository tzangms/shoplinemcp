# 遠端部署（Zeabur）

把這個 MCP 從「本機 stdio」改為「團隊共用的遠端服務」。

## 為什麼遠端模式多了兩層防護

本機 stdio 模式下，伺服器跑在你自己的機器上，作業系統就是信任邊界；
而**寫入操作是靠 Claude Desktop / Claude Code 的權限提示擋下來的** ——
那是客戶端行為，伺服器管不到。

一旦變成公開的 HTTP endpoint，這兩個前提都不成立：任何知道網址的人都能連，
而客戶端若沒有權限提示，68 個寫入操作（改庫存、改價格、建立/取消訂單）
就會直接對正式商店生效。所以遠端模式強制加上：

| 防護 | 作用 |
| --- | --- |
| Bearer token 認證 | 沒有金鑰連不上，未設定 `MCP_AUTH_TOKEN` 伺服器直接拒絕啟動 |
| 寫入二階段確認 | 由伺服器端強制，不依賴客戶端是否有權限提示 |

## 環境變數

| 變數 | 必填 | 說明 |
| --- | --- | --- |
| `MCP_TRANSPORT` | 是 | 設為 `http` 啟用遠端模式（預設 `stdio`） |
| `SHOPLINE_API_TOKEN` | 是 | Shopline Open API token |
| `MCP_AUTH_TOKEN` | 是 | 存取本服務的金鑰，發給團隊成員 |
| `MCP_CONFIRM_SECRET` | 否 | 確認碼簽章金鑰，預設沿用 `MCP_AUTH_TOKEN` |
| `PORT` / `HOST` | 否 | 預設 `8000` / `0.0.0.0`，Zeabur 會自動注入 `PORT` |

請用夠長的隨機值當 `MCP_AUTH_TOKEN`：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 部署到 Zeabur

專案內已附 `Dockerfile`，Zeabur 會自動辨識。

1. 在 Zeabur 建立服務，來源選這個 Git repo
2. 設定上表的環境變數（`MCP_TRANSPORT=http` 必須設）
3. 綁定網域，取得 `https://<your-app>.zeabur.app`
4. 驗證：

```bash
curl https://<your-app>.zeabur.app/healthz
# {"status":"ok","write_tools_protected":68}
```

`/healthz` 不需認證但也不含任何商店資料；其餘路徑一律需要金鑰。

## 客戶端設定

MCP endpoint 是 `https://<your-app>.zeabur.app/mcp`。

```bash
claude mcp add --transport http shopline https://<your-app>.zeabur.app/mcp \
  --header "Authorization: Bearer <MCP_AUTH_TOKEN>"
```

## 寫入的二階段確認

遠端模式下，所有寫入工具會多出一個 `confirm_token` 參數：

1. **第一次呼叫**（不帶 `confirm_token`）→ **不會執行**，回傳將要變更的內容與一組確認碼
   ```json
   {
     "requires_confirmation": true,
     "action": "update_product_quantity",
     "arguments": {"product_id": "...", "quantity": 5},
     "confirm_token": "...",
     "expires_in_seconds": 300
   }
   ```
2. AI 向使用者確認後，**帶同一組參數與該確認碼再呼叫一次** → 才真的執行

確認碼以 HMAC 綁定「工具名稱 + 完整參數」，因此：

- 無法拿低風險操作換到的確認碼去執行高風險操作
- 無法在取得確認碼後偷改參數（例如把數量從 5 改成 9999）
- 五分鐘後自動失效
- 無狀態，多副本部署不需共用儲存空間

唯讀工具完全不受影響，行為與本機模式一致。

## 已知限制

- **團隊共用同一組 Shopline token**：目前 token 來自伺服器的環境變數，
  所有使用者操作的是同一個商店，稽核記錄上也無法區分是誰做的。
  若要多商店或個別 token，需改成由呼叫端傳入。
- **速率限制會疊加**：掃描全店商品約需 33 次 API 請求（每頁間隔 0.2 秒），
  多人同時查詢可能觸發 Shopline 的限流。
- **部分回應很大**：`get_inventory_overview` 單次約 300KB，遠端傳輸與 token 計費都需留意。
- **stdio 模式不啟用二階段確認**，維持既有行為（由客戶端權限提示負責）。
