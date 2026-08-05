# Remote HTTP MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 Shopline MCP 除了本機 stdio 外，額外支援 Remote HTTP（streamable-http），部署到 Zeabur 後可在 Claude 自訂連接器貼含密鑰網址連上。

**Architecture:** 新增 `remote.py` 進入點，import 既有 `server`（觸發所有 `@mcp.tool()` 註冊）後共用同一個 `mcp` 單例，只把 transport 換成 `streamable-http`；用 URL 路徑密鑰做存取控制，關閉 DNS-rebinding 防護以配合雲端 reverse proxy。stdio 版完全不動。

**Tech Stack:** Python 3.10+、`mcp[cli]`（FastMCP + streamable-http）、Zeabur（zbpack）

## Global Constraints

- 沿用既有 `mcp = FastMCP("shopline")` 單例（`src/shopline_mcp/app.py`），不得另建第二個 FastMCP。
- 憑證沿用 `SHOPLINE_API_TOKEN`（`config/settings.py` 於 import 時讀取）。
- 存取控制用 URL 路徑密鑰：環境變數 `SHOPLINE_MCP_KEY`，連接器網址 `/<KEY>/mcp`；缺密鑰啟動即報錯。
- host `0.0.0.0`、port 讀 `PORT`（預設 `8080`）。
- 不改動任何既有工具邏輯與 `server.py` 的 stdio 行為。
- 部署對齊 Flaps：Zeabur、`zbpack.json` 的 `start_command: python -m shopline_mcp.remote`。

---

### Task 1: 新增 remote HTTP 進入點並確認相依

**Files:**
- Create: `src/shopline_mcp/remote.py`
- Modify: `pyproject.toml`（新增 console script；必要時提升 mcp 版本下限）
- Test: `tests/test_remote_entry.py`

**Interfaces:**
- Consumes: `shopline_mcp.app.mcp`（既有 FastMCP 單例）、`shopline_mcp.server`（import 副作用即註冊工具）
- Produces: `shopline_mcp.remote.main() -> None`

- [ ] **Step 1: 先確認 SDK 有 streamable-http 與 TransportSecuritySettings**

Run:
```bash
cd /Users/tzangms/.superconductor/worktrees/shoplinemcp/sc-paired-fluxon-1168
python -c "from mcp.server.transport_security import TransportSecuritySettings; print('ok')"
```
Expected: 印出 `ok`。若 ImportError，於 `pyproject.toml` 把 `mcp[cli]>=1.2.0` 提升為 `mcp[cli]>=1.12`，`pip install -e .` 後重試。

- [ ] **Step 2: 寫失敗測試**

`tests/test_remote_entry.py`：
```python
import os
import importlib

import pytest


def test_main_requires_key(monkeypatch):
    monkeypatch.delenv("SHOPLINE_MCP_KEY", raising=False)
    remote = importlib.import_module("shopline_mcp.remote")
    with pytest.raises(RuntimeError, match="SHOPLINE_MCP_KEY"):
        remote.main()


def test_importing_remote_does_not_start_stdio(monkeypatch):
    # import 不得啟動任何 server（mcp.run 只能在 main() 內呼叫）
    called = {}
    remote = importlib.import_module("shopline_mcp.remote")
    from shopline_mcp.app import mcp
    monkeypatch.setattr(mcp, "run", lambda *a, **k: called.setdefault("run", True))
    # 只是 import 過，run 不該被呼叫
    assert "run" not in called


def test_main_configures_key_path_and_runs(monkeypatch):
    monkeypatch.setenv("SHOPLINE_MCP_KEY", "secret123")
    monkeypatch.setenv("PORT", "9000")
    remote = importlib.import_module("shopline_mcp.remote")
    from shopline_mcp.app import mcp

    captured = {}
    monkeypatch.setattr(mcp, "run", lambda *a, **k: captured.setdefault("kwargs", k) or captured.setdefault("args", a))
    remote.main()

    assert mcp.settings.host == "0.0.0.0"
    assert mcp.settings.port == 9000
    assert mcp.settings.streamable_http_path == "/secret123/mcp"
    # transport 以 streamable-http 呼叫
    assert captured["args"][0] == "streamable-http" or captured["kwargs"].get("transport") == "streamable-http"
```

- [ ] **Step 3: 執行測試確認失敗**

Run: `python -m pytest tests/test_remote_entry.py -v`
Expected: FAIL（`ModuleNotFoundError: shopline_mcp.remote`）

- [ ] **Step 4: 實作 `src/shopline_mcp/remote.py`**

```python
"""遠端 MCP server 進入點（streamable-http）—— 部署到雲端供 Claude 連線。

與 server.py（stdio 本機版）共用同一組 @mcp.tool() 工具，只是改用 HTTP transport。
對方在 Claude 的「自訂連接器」貼一個含密鑰的網址即可連上，免裝任何東西。

環境變數：
    SHOPLINE_API_TOKEN       Shopline 憑證（同本機版，由雲端平台注入）
    SHOPLINE_MCP_KEY         URL 密鑰；連接器網址為 https://<host>/<KEY>/mcp
    PORT                     監聽埠（雲端平台自動提供，預設 8080）
    SHOPLINE_ALLOWED_HOSTS   選填；設了就改用 Host 白名單模式
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

    # 跑在雲端反向代理（Zeabur）後面，進來的 Host header 是平台網域而非 localhost，
    # MCP SDK 預設的 DNS-rebinding 防護會回 421。存取控制已由 URL 密鑰負責，故關閉；
    # 可用 SHOPLINE_ALLOWED_HOSTS 改成白名單模式。
    allowed = [h.strip() for h in os.environ.get("SHOPLINE_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if allowed:
        mcp.settings.transport_security = TransportSecuritySettings(allowed_hosts=allowed)
    else:
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )

    # 密鑰放路徑裡，當作給單一信任對象用的簡易 bearer：
    #   https://<host>/<SHOPLINE_MCP_KEY>/mcp
    mcp.settings.streamable_http_path = f"/{key}/mcp"

    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 於 `pyproject.toml` 的 `[project.scripts]` 新增 remote 指令**

在既有：
```toml
[project.scripts]
shopline-mcp = "shopline_mcp.server:main"
```
下方加一行：
```toml
shopline-mcp-remote = "shopline_mcp.remote:main"
```

- [ ] **Step 6: 執行測試確認通過**

Run: `python -m pytest tests/test_remote_entry.py -v`
Expected: PASS（3 passed）

- [ ] **Step 7: 回歸——確認 stdio 版工具仍正常註冊**

Run:
```bash
python -c "import shopline_mcp.server; from shopline_mcp.app import mcp; import asyncio; print(len(asyncio.run(mcp.list_tools())))"
```
Expected: 印出工具數量（>100），且過程未啟動任何 server。

- [ ] **Step 8: Commit**

```bash
git add src/shopline_mcp/remote.py pyproject.toml tests/test_remote_entry.py
git commit -m "feat: add remote HTTP (streamable-http) MCP entry point"
```

---

### Task 2: Zeabur 部署設定

**Files:**
- Create: `zbpack.json`

**Interfaces:**
- Consumes: `shopline_mcp.remote:main`（Task 1 產出的進入點）
- Produces: 無（部署設定）

- [ ] **Step 1: 建立 `zbpack.json`**

```json
{
  "install_command": "pip install .",
  "start_command": "python -m shopline_mcp.remote"
}
```

- [ ] **Step 2: 本機煙霧測試——啟動 remote server**

Run:
```bash
SHOPLINE_MCP_KEY=testkey SHOPLINE_API_TOKEN=dummy PORT=8080 python -m shopline_mcp.remote &
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/testkey/mcp -X POST \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}'
kill %1 2>/dev/null
```
Expected: HTTP 狀態碼 `200`（handshake 可通）。若回 `421` 表示 DNS-rebinding 防護未關，回 Task 1 檢查。

- [ ] **Step 3: Commit**

```bash
git add zbpack.json
git commit -m "chore: add Zeabur deploy config for remote MCP"
```

---

### Task 3: README 文件

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: 無
- Produces: 無

- [ ] **Step 1: 在 README 既有 Setup 章節後新增 Remote HTTP 段落**

於 `## Setup` 下、Claude Code 段落之後插入：

````markdown
### Remote HTTP (Claude custom connector)

Deploy once to a host (e.g. Zeabur) and connect from Claude with just a URL — no local install.

1. Deploy this repo. On **Zeabur**, `zbpack.json` runs `python -m shopline_mcp.remote`.
2. Set environment variables on the service:
   - `SHOPLINE_API_TOKEN` — your Shopline API token
   - `SHOPLINE_MCP_KEY` — a secret string used as the URL key
3. In Claude, add a **custom connector** with URL:

   ```
   https://<your-host>/<SHOPLINE_MCP_KEY>/mcp
   ```

The key in the path acts as a simple bearer for a single trusted user. Keep the full URL secret. Optionally set `SHOPLINE_ALLOWED_HOSTS` (comma-separated) to enable host-whitelist DNS-rebinding protection.
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document remote HTTP setup for Claude custom connector"
```

---

## Self-Review

- **Spec coverage:** remote.py 進入點（T1）、URL 密鑰 + 缺密鑰報錯（T1 Step2/4）、DNS-rebinding 關閉/白名單（T1 Step4 + T2 Step2 驗證）、host/port（T1）、環境變數表（README T3）、Zeabur zbpack（T2）、console script（T1 Step5）、相依確認（T1 Step1）、stdio 不破壞（T1 Step7）——皆覆蓋。
- **Placeholder scan:** 無 TBD/TODO；所有程式碼與測試皆為完整內容。
- **Type consistency:** `main() -> None` 於 remote.py、pyproject script、zbpack、測試一致；環境變數名稱 `SHOPLINE_MCP_KEY` / `SHOPLINE_ALLOWED_HOSTS` / `PORT` 全文一致。
