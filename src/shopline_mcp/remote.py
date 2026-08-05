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

    port = int(os.environ.get("PORT", "8080"))

    allowed =[h.strip() for h in os.environ.get("SHOPLINE_ALLOWED_HOSTS", "").split(",") if h.strip()]
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
