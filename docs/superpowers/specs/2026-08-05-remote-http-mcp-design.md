# Shopline MCP：加上 Remote HTTP 版設計文件

日期：2026-08-05

## 目標

讓現有只能本機（stdio）執行的 Shopline MCP，額外支援 **Remote HTTP（streamable-http）**
模式，部署到雲端後，使用者只要在 Claude 的「自訂連接器」貼一個含密鑰的網址即可連上，
免安裝任何東西。**stdio 本機版與 remote http 版兩者都保留**，共用同一組工具。

參考做法：`flaps` 專案的 `flaps/remote.py`（同樣是 FastMCP，做法可幾乎一對一搬過來）。

## 現況

- `src/shopline_mcp/app.py` — 建立共用單例 `mcp = FastMCP("shopline")`
- `src/shopline_mcp/server.py` — import 所有 tool 模組觸發 `@mcp.tool()` 註冊，最後
  `mcp.run(transport="stdio")`
- 憑證：`config/settings.py` 於 import 時讀 `SHOPLINE_API_TOKEN` 環境變數

換句話說，remote 版只需**換 transport**，工具與憑證機制完全沿用。

## 架構

新增一個 remote 進入點 `src/shopline_mcp/remote.py`，與 stdio 版共用同一個 `mcp` 物件：

1. 先 import `shopline_mcp.server`（觸發所有 `@mcp.tool()` 註冊），取得已註冊工具的 `mcp`。
2. 設定 host / port / 存取控制 / streamable_http_path。
3. `mcp.run(transport="streamable-http")`。

為避免 `server.py` 在 import 時就跑 `mcp.run(transport="stdio")`，需確認其 `mcp.run`
被包在 `if __name__ == "__main__"` 或 `main()` 內——目前 `server.py` 的 `main()` 已如此，
import 該模組只會註冊工具、不會啟動 stdio，安全。

### 存取控制：URL 路徑密鑰（同 Flaps）

- 連接器網址：`https://<host>/<KEY>/mcp`
- 密鑰由環境變數 `SHOPLINE_MCP_KEY` 提供；缺少時啟動即報錯（避免任何人拿到網址就能操作）。
- 透過 `mcp.settings.streamable_http_path = f"/{key}/mcp"` 把密鑰放進路徑，當作單一信任
  對象用的簡易 bearer。
- 走 HTTPS，路徑密鑰不出現在明文網路上；維運上注意別把完整網址貼到會記 log 的地方。

### DNS-rebinding 防護

MCP SDK 預設會開 DNS-rebinding 防護（針對本機瀏覽器可達的 server），跑在雲端 reverse
proxy（Zeabur）後面時，進來的 Host header 是平台網域而非 localhost，會回 **421**。
故：
- 預設關閉該防護（存取控制已由 URL 密鑰負責）：
  `TransportSecuritySettings(enable_dns_rebinding_protection=False)`
- 若設了 `SHOPLINE_ALLOWED_HOSTS`（逗號分隔），改用白名單模式。

### 環境變數

| 變數 | 用途 | 必填 |
|------|------|------|
| `SHOPLINE_API_TOKEN` | Shopline Open API 憑證（沿用現有） | 是 |
| `SHOPLINE_MCP_KEY` | URL 路徑密鑰；連接器網址 `/<KEY>/mcp` | 是（remote） |
| `PORT` | 監聽埠，雲端平台自動注入，預設 8080 | 否 |
| `SHOPLINE_ALLOWED_HOSTS` | 逗號分隔的 Host 白名單；設了就啟用 DNS-rebinding 防護 | 否 |

## remote.py 內容（草案）

```python
"""遠端 MCP server 進入點（streamable-http）—— 部署到雲端供 Claude 連線。

與 server.py（stdio 本機版）共用同一組 @mcp.tool() 工具，只是改用 HTTP transport。
"""
from __future__ import annotations

import os

from mcp.server.transport_security import TransportSecuritySettings

import shopline_mcp.server  # noqa: F401  # 觸發所有 @mcp.tool() 註冊
from shopline_mcp.app import mcp


def main() -> None:
    key = os.environ.get("SHOPLINE_MCP_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "缺少 SHOPLINE_MCP_KEY：遠端版必須設密鑰，否則任何人拿到網址就能操作店家資料。"
        )

    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", "8080"))

    allowed = [h.strip() for h in os.environ.get("SHOPLINE_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if allowed:
        mcp.settings.transport_security = TransportSecuritySettings(allowed_hosts=allowed)
    else:
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )

    mcp.settings.streamable_http_path = f"/{key}/mcp"
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
```

## 部署（Zeabur，同 Flaps 的 project / service 慣例）

- 新增 `zbpack.json`：
  ```json
  {
    "install_command": "pip install .",
    "start_command": "python -m shopline_mcp.remote"
  }
  ```
- 於 Zeabur service 設 `SHOPLINE_API_TOKEN` 與 `SHOPLINE_MCP_KEY` 環境變數。
- `pyproject.toml` 新增 console script（選配）：`shopline-mcp-remote = "shopline_mcp.remote:main"`，
  方便本機以指令啟動測試。

## 相依套件

現有 `mcp[cli]>=1.2.0` 已含 streamable-http transport；`TransportSecuritySettings`
需較新版本 MCP SDK。實作時確認可 import；若不行則提升下限（例如 `mcp[cli]>=1.12`，
與 Flaps 對齊）。無需新增其他套件。

## 測試

- 本機以 `SHOPLINE_MCP_KEY=test python -m shopline_mcp.remote` 啟動，確認：
  - 監聽 `0.0.0.0:8080`
  - `GET /<KEY>/mcp` / MCP handshake 可通
  - 缺 `SHOPLINE_MCP_KEY` 時啟動即報錯
- 沿用現有 stdio 測試，確認未破壞本機版。
- 部署後以 Claude 自訂連接器貼 `https://<host>/<KEY>/mcp` 實測 handshake 與一個唯讀工具。

## 文件

README 新增「Remote HTTP（Claude 自訂連接器）」章節：如何部署到 Zeabur、設定環境變數、
在 Claude 貼網址連上。

## 明確不做（YAGNI）

- 不做 OAuth / 多租戶 / 每用戶不同權限（單一信任對象即可，需要時再議）。
- 不改動任何既有工具邏輯與 stdio 進入點行為。
