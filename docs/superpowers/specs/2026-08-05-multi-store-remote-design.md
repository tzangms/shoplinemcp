# Shopline MCP Remote：多店家（multi-tenant）設計文件

日期：2026-08-05

## 目標

讓單一 remote HTTP service 同時服務**多個 Shopline 店家**，每家有各自的 URL 密鑰與
API token，互相隔離。連線時用網址路徑裡的密鑰決定用哪一家的 token：

```
https://<host>/<storeA_key>/mcp   → 用 A 店 token
https://<host>/<storeB_key>/mcp   → 用 B 店 token
```

stdio 本機版維持單店，不動。

## 現況與關鍵切入點

所有 Shopline API 呼叫都收斂到單一路徑：
`tools/base_tool._request()` → `config.settings.get_headers()`。
`get_headers()` 目前讀模組全域 `ACCESS_TOKEN`（import 時由 `SHOPLINE_API_TOKEN` 載入）。
因此只要讓 `get_headers()` 改成「每個請求動態取 token」，全部工具自動支援多店，無需逐一改。

## 架構

### 1. 每請求 token（contextvar）

`config/settings.py` 新增：
```python
import contextvars
current_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "shopline_current_token", default=None
)
```
`get_headers()` 改為：
```python
def get_headers():
    token = current_token.get() or ACCESS_TOKEN
    if not token:
        raise RuntimeError("SHOPLINE_API_TOKEN ... not set")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
```
- 有 contextvar（remote 多店）→ 用該店 token。
- 沒有（stdio／單店）→ fallback `ACCESS_TOKEN` 環境變數。行為與現況相同。

> contextvar 在 FastMCP 以 threadpool 執行同步工具時會被 `anyio.to_thread`（copy_context）
> 正確複製到工作執行緒，故工具內的 API 呼叫拿得到當前請求設定的 token。

### 2. 密鑰 → token 對應表（成對環境變數）

`remote.py` 啟動時建表 `stores: dict[str, str]`（密鑰 → token）：

- **舊單店 pair（向後相容、A 店沿用）**：若 `SHOPLINE_MCP_KEY` 有值，加入
  `{SHOPLINE_MCP_KEY: SHOPLINE_API_TOKEN}`。
- **多店 pair**：掃描所有環境變數，對每個符合 `^SHOPLINE_STORE_(?P<label>.+)_KEY$` 的變數，
  取其值為密鑰，並從 `SHOPLINE_STORE_<label>_TOKEN` 取對應 token。
  - 缺對應 token → 啟動報錯（指名該 label）。

驗證：
- 每個密鑰必須 URL-safe（沿用現有 `^[A-Za-z0-9_-]+$`），否則報錯。
- 密鑰不可重複（不同店用同一密鑰）→ 報錯。
- 至少要有一組 store，否則報錯（等同現行「缺密鑰即報錯」）。

### 3. Multi-key ASGI middleware

FastMCP 的 `streamable_http_path` 只能綁單一路徑，故不再用
`mcp.settings.streamable_http_path = f"/{key}/mcp"` + `mcp.run(...)`，改為：

1. 設 `mcp.settings.streamable_http_path = "/mcp"`（內層固定路徑）。
2. 設 `mcp.settings.transport_security`（DNS-rebinding，同現行邏輯）。
3. `inner = mcp.streamable_http_app()`（FastMCP 提供的 Starlette ASGI app）。
4. 外包一層 ASGI middleware `MultiStoreKeyMiddleware(inner, stores)`：
   - 解析 `scope["path"]`，比對 `^/(?P<key>[^/]+)/mcp(?P<rest>.*)$`。
   - 密鑰不在 `stores` → 直接回 404（不洩漏哪個密鑰存在）。
   - 命中 → `token = current_token.set(stores[key])`，改寫
     `scope["path"] = "/mcp" + rest`（與 `raw_path`），呼叫 `inner`，最後 `current_token.reset(token)`。
5. `uvicorn.run(app, host=..., port=int(PORT or 8080))`。

（`uvicorn` 已是 `mcp[cli]` 相依，無需新增套件。）

### 環境變數總表

| 變數 | 用途 | 必填 |
|------|------|------|
| `SHOPLINE_MCP_KEY` | 舊單店密鑰（A 店沿用） | 至少一組 store |
| `SHOPLINE_API_TOKEN` | 舊單店 token（A 店沿用）／stdio | 同上 |
| `SHOPLINE_STORE_<label>_KEY` | 某店 URL 密鑰 | 選填（多店時） |
| `SHOPLINE_STORE_<label>_TOKEN` | 該店 API token | 有對應 KEY 時必填 |
| `PORT` | 監聽埠（Zeabur 注入，預設 8080） | 否 |
| `SHOPLINE_ALLOWED_HOSTS` | Host 白名單（設了才啟用 DNS-rebinding 防護） | 否 |

### 本次部署的實際設定（A 保留、只加 B）

- A 店：`SHOPLINE_MCP_KEY=B0ElLasmQSCgdSg1KzYzHBgT5YxffAkv`、`SHOPLINE_API_TOKEN=<A token>`（現況不動）
- B 店：`SHOPLINE_STORE_B_KEY=<新密鑰>`、`SHOPLINE_STORE_B_TOKEN=<B token>`

連接器網址：
- A：`https://shopline-mcp.zeabur.app/B0ElLasmQSCgdSg1KzYzHBgT5YxffAkv/mcp`（不變）
- B：`https://shopline-mcp.zeabur.app/<新密鑰>/mcp`

## 測試

- 單元：
  - `build_stores()` 由環境變數正確建表（舊 pair + 多店 pair 合併）、缺 token 報錯、
    重複密鑰報錯、非法密鑰報錯、零 store 報錯。
  - `get_headers()` 有 contextvar 用之、無則 fallback env。
  - middleware：未知密鑰回 404；命中設對 token 並改寫路徑；請求結束 reset。
- 本機煙霧：設兩組 store，各自密鑰 initialize handshake 回 200，錯誤密鑰回 404。
- 部署後：兩條連接器網址各自 `get_token_info` 回傳**不同**商家，證明隔離正確。

## 明確不做（YAGNI）

- 不做動態新增店家（改設定需重啟）、不做 per-store 權限或速率限制。
- stdio 版不支援多店（維持單一 `SHOPLINE_API_TOKEN`）。
- 不改任何既有工具邏輯。
