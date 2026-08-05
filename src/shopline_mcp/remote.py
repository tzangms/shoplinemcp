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
import re

from mcp.server.transport_security import TransportSecuritySettings

import shopline_mcp.server  # noqa: F401  # 觸發所有 @mcp.tool() 註冊
from shopline_mcp.app import mcp

_KEY_SAFE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def main() -> None:
    key = os.environ.get("SHOPLINE_MCP_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "缺少 SHOPLINE_MCP_KEY：遠端版必須設密鑰，否則任何人拿到網址就能操作店家資料。"
        )
    if not _KEY_SAFE_RE.match(key):
        raise RuntimeError(
            "SHOPLINE_MCP_KEY 含不允許的字元：只能使用英數字、'-'、'_'，"
            "避免產生異常路徑（例如包含 '/' 導致路徑破損或類似路徑穿越的結構）。"
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

    mcp.run("streamable-http")


if __name__ == "__main__":
    main()
