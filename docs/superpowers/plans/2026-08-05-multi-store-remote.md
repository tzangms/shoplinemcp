# Multi-Store Remote MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓單一 remote HTTP service 依 URL 路徑密鑰服務多個 Shopline 店家，各自 token 隔離。

**Architecture:** 每請求 token 用 `contextvars.ContextVar` 傳遞；`get_headers()` 優先讀 contextvar、否則 fallback 環境變數。`remote.py` 由成對環境變數建 `{密鑰:token}` 表，外包 ASGI middleware 依路徑密鑰選 token（未知回 404），用 uvicorn 跑 FastMCP 的 streamable-http app。

**Tech Stack:** Python 3.10+、`mcp[cli]`（FastMCP streamable_http_app + uvicorn）、contextvars

## Global Constraints

- 所有 API 呼叫收斂於 `config.settings.get_headers()`；只在此處與 `remote.py` 改動，不動任何工具。
- 向後相容：未設多店變數時，`SHOPLINE_MCP_KEY` + `SHOPLINE_API_TOKEN` 單店模式與 stdio 行為不變。
- 密鑰須 URL-safe（`^[A-Za-z0-9_-]+$`）；重複密鑰、缺對應 token、零 store 皆須啟動報錯。
- contextvar 名稱 `current_token`，定義於 `config/settings.py`。
- host `0.0.0.0`；port 讀 `PORT`（預設 `8080`）；DNS-rebinding 預設關、`SHOPLINE_ALLOWED_HOSTS` 設了才白名單。
- 內層固定路徑 `/mcp`；對外路徑 `/<key>/mcp`。

---

### Task 1: settings.py — 每請求 token（contextvar）

**Files:**
- Modify: `src/shopline_mcp/config/settings.py`（新增 contextvar、改 `get_headers`）
- Test: `tests/test_multistore.py`

**Interfaces:**
- Produces:
  - `shopline_mcp.config.settings.current_token: contextvars.ContextVar[str | None]`（default `None`）
  - `get_headers() -> dict`：token 來源 = `current_token.get() or ACCESS_TOKEN`；皆無則 `RuntimeError`。

- [ ] **Step 1: 寫失敗測試**

`tests/test_multistore.py`：
```python
import importlib

import pytest


def test_get_headers_uses_contextvar_when_set(monkeypatch):
    settings = importlib.import_module("shopline_mcp.config.settings")
    monkeypatch.setattr(settings, "ACCESS_TOKEN", "envtoken")
    tok = settings.current_token.set("ctxtoken")
    try:
        h = settings.get_headers()
    finally:
        settings.current_token.reset(tok)
    assert h["Authorization"] == "Bearer ctxtoken"


def test_get_headers_falls_back_to_env(monkeypatch):
    settings = importlib.import_module("shopline_mcp.config.settings")
    monkeypatch.setattr(settings, "ACCESS_TOKEN", "envtoken")
    # 確保沒有 contextvar
    assert settings.current_token.get() is None
    h = settings.get_headers()
    assert h["Authorization"] == "Bearer envtoken"


def test_get_headers_raises_when_no_token(monkeypatch):
    settings = importlib.import_module("shopline_mcp.config.settings")
    monkeypatch.setattr(settings, "ACCESS_TOKEN", "")
    assert settings.current_token.get() is None
    with pytest.raises(RuntimeError):
        settings.get_headers()
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m pytest tests/test_multistore.py -v`
Expected: FAIL（`current_token` 不存在 / get_headers 未讀 contextvar）

- [ ] **Step 3: 實作**

在 `src/shopline_mcp/config/settings.py` 頂部 `import os` 之後加：
```python
import contextvars

# 當前請求要使用的 Shopline token（remote 多店模式由 middleware 設定）。
# 未設定時（stdio／單店）fallback 到環境變數 ACCESS_TOKEN。
current_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "shopline_current_token", default=None
)
```
把既有 `get_headers()` 改為：
```python
def get_headers():
    token = current_token.get() or ACCESS_TOKEN
    if not token:
        raise RuntimeError(
            "SHOPLINE_API_TOKEN environment variable is not set. "
            "Run: export SHOPLINE_API_TOKEN=your_token_here"
        )
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python -m pytest tests/test_multistore.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 回歸**

Run: `python -m pytest -q`
Expected: 既有測試全過。

- [ ] **Step 6: Commit**

```bash
git add src/shopline_mcp/config/settings.py tests/test_multistore.py
git commit -m "feat: per-request Shopline token via contextvar in get_headers"
```

---

### Task 2: remote.py — 建表 + multi-key middleware + uvicorn

**Files:**
- Modify: `src/shopline_mcp/remote.py`
- Test: `tests/test_multistore.py`（沿用同檔，新增函式測試）

**Interfaces:**
- Consumes: `shopline_mcp.config.settings.current_token`（Task 1）
- Produces:
  - `shopline_mcp.remote.build_stores() -> dict[str, str]`：由環境變數建 `{密鑰: token}`。
  - `shopline_mcp.remote.MultiStoreKeyMiddleware`：ASGI callable，`(app, stores)` 建構。
  - `shopline_mcp.remote.main() -> None`。

- [ ] **Step 1: 寫失敗測試（接在 tests/test_multistore.py 後）**

```python
def test_build_stores_legacy_pair(monkeypatch):
    import shopline_mcp.remote as remote
    monkeypatch.setenv("SHOPLINE_MCP_KEY", "keyA")
    monkeypatch.setenv("SHOPLINE_API_TOKEN", "tokA")
    # 清掉可能存在的多店變數
    for k in list(os.environ):
        if k.startswith("SHOPLINE_STORE_"):
            monkeypatch.delenv(k, raising=False)
    stores = remote.build_stores()
    assert stores == {"keyA": "tokA"}


def test_build_stores_paired_env(monkeypatch):
    import shopline_mcp.remote as remote
    monkeypatch.delenv("SHOPLINE_MCP_KEY", raising=False)
    monkeypatch.setenv("SHOPLINE_STORE_B_KEY", "keyB")
    monkeypatch.setenv("SHOPLINE_STORE_B_TOKEN", "tokB")
    stores = remote.build_stores()
    assert stores["keyB"] == "tokB"


def test_build_stores_missing_token_raises(monkeypatch):
    import shopline_mcp.remote as remote
    monkeypatch.delenv("SHOPLINE_MCP_KEY", raising=False)
    monkeypatch.setenv("SHOPLINE_STORE_C_KEY", "keyC")
    monkeypatch.delenv("SHOPLINE_STORE_C_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="SHOPLINE_STORE_C_TOKEN"):
        remote.build_stores()


def test_build_stores_unsafe_key_raises(monkeypatch):
    import shopline_mcp.remote as remote
    monkeypatch.delenv("SHOPLINE_MCP_KEY", raising=False)
    monkeypatch.setenv("SHOPLINE_STORE_D_KEY", "bad/key")
    monkeypatch.setenv("SHOPLINE_STORE_D_TOKEN", "tokD")
    with pytest.raises(RuntimeError):
        remote.build_stores()


def test_build_stores_duplicate_key_raises(monkeypatch):
    import shopline_mcp.remote as remote
    monkeypatch.setenv("SHOPLINE_MCP_KEY", "dup")
    monkeypatch.setenv("SHOPLINE_API_TOKEN", "t1")
    monkeypatch.setenv("SHOPLINE_STORE_E_KEY", "dup")
    monkeypatch.setenv("SHOPLINE_STORE_E_TOKEN", "t2")
    with pytest.raises(RuntimeError):
        remote.build_stores()


def test_build_stores_empty_raises(monkeypatch):
    import shopline_mcp.remote as remote
    monkeypatch.delenv("SHOPLINE_MCP_KEY", raising=False)
    for k in list(os.environ):
        if k.startswith("SHOPLINE_STORE_"):
            monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError):
        remote.build_stores()
```

`import os` 已在檔案頂部（測試檔 Task 1 未 import os，請在檔案最上方加 `import os`）。

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m pytest tests/test_multistore.py -k build_stores -v`
Expected: FAIL（`build_stores` 不存在）

- [ ] **Step 3: 重寫 `src/shopline_mcp/remote.py`**

```python
"""遠端 MCP server 進入點（streamable-http）—— 部署到雲端供 Claude 連線，支援多店家。

與 server.py（stdio 本機版）共用同一組 @mcp.tool() 工具，只是改用 HTTP transport。
每個店家一組 URL 密鑰與 API token；連線網址 https://<host>/<KEY>/mcp 依密鑰選用該店 token。

環境變數：
    SHOPLINE_MCP_KEY / SHOPLINE_API_TOKEN   舊單店 pair（仍支援，會當成一組 store）
    SHOPLINE_STORE_<label>_KEY / _TOKEN      多店 pair（可多組）
    PORT                                     監聽埠（雲端平台提供，預設 8080）
    SHOPLINE_ALLOWED_HOSTS                   選填；設了就用 Host 白名單模式
"""
from __future__ import annotations

import os
import re

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

import shopline_mcp.server  # noqa: F401  # 觸發所有 @mcp.tool() 註冊
from shopline_mcp.app import mcp
from shopline_mcp.config.settings import current_token

_KEY_SAFE_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_STORE_KEY_RE = re.compile(r"^SHOPLINE_STORE_(?P<label>.+)_KEY$")
_PATH_RE = re.compile(r"^/(?P<key>[^/]+)/mcp(?P<rest>.*)$")


def build_stores() -> dict[str, str]:
    """由環境變數建 {URL 密鑰: API token} 對應表。"""
    stores: dict[str, str] = {}

    def add(key: str, token: str, key_src: str, token_src: str) -> None:
        key = key.strip()
        token = token.strip()
        if not key:
            return
        if not _KEY_SAFE_RE.match(key):
            raise RuntimeError(
                f"{key_src} 的密鑰含不允許的字元：只能使用英數字、'-'、'_'。"
            )
        if not token:
            raise RuntimeError(f"缺少 {token_src}：每個店家的密鑰都必須有對應 token。")
        if key in stores:
            raise RuntimeError(f"密鑰重複：{key_src} 的密鑰與其他店家相同，無法區分店家。")
        stores[key] = token

    # 舊單店 pair（向後相容）
    legacy_key = os.environ.get("SHOPLINE_MCP_KEY", "")
    if legacy_key.strip():
        add(legacy_key, os.environ.get("SHOPLINE_API_TOKEN", ""),
            "SHOPLINE_MCP_KEY", "SHOPLINE_API_TOKEN")

    # 多店 pair
    for env_name, key_val in list(os.environ.items()):
        m = _STORE_KEY_RE.match(env_name)
        if not m:
            continue
        label = m.group("label")
        token_name = f"SHOPLINE_STORE_{label}_TOKEN"
        add(key_val, os.environ.get(token_name, ""), env_name, token_name)

    if not stores:
        raise RuntimeError(
            "沒有任何店家設定：請設 SHOPLINE_MCP_KEY+SHOPLINE_API_TOKEN，"
            "或 SHOPLINE_STORE_<label>_KEY+SHOPLINE_STORE_<label>_TOKEN。"
        )
    return stores


class MultiStoreKeyMiddleware:
    """依 URL 路徑密鑰選店家 token 的 ASGI middleware。

    /<key>/mcp[...] → 若 key 命中則設 current_token 並改寫路徑為 /mcp[...] 轉給內層 app；
    未命中回 404。
    """

    def __init__(self, app, stores: dict[str, str]) -> None:
        self.app = app
        self.stores = stores

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        m = _PATH_RE.match(scope.get("path", ""))
        token = self.stores.get(m.group("key")) if m else None
        if token is None:
            await self._not_found(send)
            return
        rest = m.group("rest")
        new_path = "/mcp" + rest
        scope = dict(scope)
        scope["path"] = new_path
        scope["raw_path"] = new_path.encode()
        reset = current_token.set(token)
        try:
            await self.app(scope, receive, send)
        finally:
            current_token.reset(reset)

    async def _not_found(self, send) -> None:
        await send({"type": "http.response.start", "status": 404,
                    "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"Not Found"})


def main() -> None:
    stores = build_stores()

    mcp.settings.host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8080"))
    mcp.settings.port = port

    allowed = [h.strip() for h in os.environ.get("SHOPLINE_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if allowed:
        mcp.settings.transport_security = TransportSecuritySettings(allowed_hosts=allowed)
    else:
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )

    mcp.settings.streamable_http_path = "/mcp"
    inner = mcp.streamable_http_app()
    app = MultiStoreKeyMiddleware(inner, stores)

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python -m pytest tests/test_multistore.py -v`
Expected: PASS（全部）

- [ ] **Step 5: middleware 行為測試（未知密鑰 404 / 命中設 token）**

於 `tests/test_multistore.py` 追加：
```python
import asyncio


def _run_mw(mw, path):
    sent = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(msg):
        sent.append(msg)
    seen = {}
    async def inner(scope, r, s):
        seen["token"] = __import__("shopline_mcp.config.settings", fromlist=["current_token"]).current_token.get()
        seen["path"] = scope["path"]
        await s({"type": "http.response.start", "status": 200, "headers": []})
        await s({"type": "http.response.body", "body": b"ok"})
    mw.app = inner
    asyncio.run(mw({"type": "http", "path": path}, receive, send))
    return sent, seen


def test_middleware_unknown_key_404():
    import shopline_mcp.remote as remote
    mw = remote.MultiStoreKeyMiddleware(app=None, stores={"good": "tok"})
    sent, _ = _run_mw(mw, "/bad/mcp")
    assert sent[0]["status"] == 404


def test_middleware_known_key_sets_token_and_rewrites():
    import shopline_mcp.remote as remote
    mw = remote.MultiStoreKeyMiddleware(app=None, stores={"good": "tok-good"})
    sent, seen = _run_mw(mw, "/good/mcp")
    assert sent[0]["status"] == 200
    assert seen["token"] == "tok-good"
    assert seen["path"] == "/mcp"
```

- [ ] **Step 6: 執行測試確認通過**

Run: `python -m pytest tests/test_multistore.py -v`
Expected: PASS（全部）

- [ ] **Step 7: 回歸 + 本機煙霧測試（雙店）**

Run（回歸）: `python -m pytest -q` → 全過。
Run（煙霧）:
```bash
SHOPLINE_MCP_KEY=keyA SHOPLINE_API_TOKEN=dummyA \
SHOPLINE_STORE_B_KEY=keyB SHOPLINE_STORE_B_TOKEN=dummyB \
PORT=8080 python -m shopline_mcp.remote &
sleep 3
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}'
echo -n "keyA: "; curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8080/keyA/mcp -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d "$INIT"
echo -n "keyB: "; curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8080/keyB/mcp -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d "$INIT"
echo -n "bad : "; curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8080/nope/mcp -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d "$INIT"
kill %1 2>/dev/null
```
Expected: keyA `200`、keyB `200`、bad `404`。

- [ ] **Step 8: Commit**

```bash
git add src/shopline_mcp/remote.py tests/test_multistore.py
git commit -m "feat: multi-store remote MCP via per-key token map + ASGI middleware"
```

---

### Task 3: README + CLAUDE.md 文件

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: 無
- Produces: 無

- [ ] **Step 1: README 更新 Remote HTTP 段落，補多店設定**

在既有 `### Remote HTTP (Claude custom connector)` 段落末尾追加：
````markdown
#### Multiple stores (multi-tenant)

One deployment can serve several Shopline stores, each with its own URL key and token.

- Keep the single-store pair `SHOPLINE_MCP_KEY` + `SHOPLINE_API_TOKEN` for the first store.
- Add each additional store as a pair: `SHOPLINE_STORE_<LABEL>_KEY` + `SHOPLINE_STORE_<LABEL>_TOKEN`.

Each store gets its own connector URL: `https://<host>/<that-store-key>/mcp`. An unknown key returns 404.
````

- [ ] **Step 2: CLAUDE.md 更新環境變數段落**

在 `### 環境變數` 區塊補上多店變數說明（`SHOPLINE_STORE_<label>_KEY` / `_TOKEN`）與「A 店沿用舊 pair、B 店用新 pair」的實際設定。

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document multi-store remote setup"
```

---

## Self-Review

- **Spec coverage:** contextvar + get_headers fallback（T1）；build_stores 舊/多店/缺token/非法/重複/空（T2 Step1）；middleware 404 與命中改寫（T2 Step5）；uvicorn 跑內層 `/mcp` + 外層 `/<key>/mcp`（T2 Step3）；DNS-rebinding/host/port（T2 Step3）；煙霧雙店（T2 Step7）；文件（T3）——皆覆蓋。
- **Placeholder scan:** 無 TBD/TODO；程式與測試皆完整。
- **Type consistency:** `build_stores() -> dict[str,str]`、`current_token`、`MultiStoreKeyMiddleware(app, stores)` 於 spec、plan、測試一致；路徑正則 `_PATH_RE`、內層 `/mcp` 一致。
