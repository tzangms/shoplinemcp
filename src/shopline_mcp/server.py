"""Shopline MCP server entry point."""

# Import tool modules to trigger @mcp.tool() registration

# --- Read tools: Orders & Sales ---
import shopline_mcp.tools.order_tools  # noqa: F401
import shopline_mcp.tools.analytics_tools  # noqa: F401

# --- Read tools: Products & Inventory ---
import shopline_mcp.tools.product_tools  # noqa: F401

# --- Read tools: Customers ---
import shopline_mcp.tools.customer_tools  # noqa: F401
import shopline_mcp.tools.customer_group_tools  # noqa: F401
import shopline_mcp.tools.store_credit_tools  # noqa: F401
import shopline_mcp.tools.membership_tier_tools  # noqa: F401
import shopline_mcp.tools.member_point_tools  # noqa: F401
import shopline_mcp.tools.custom_field_tools  # noqa: F401

# --- Read tools: Categories & Promotions ---
import shopline_mcp.tools.category_tools  # noqa: F401
import shopline_mcp.tools.promotion_tools  # noqa: F401
import shopline_mcp.tools.flash_price_tools  # noqa: F401
import shopline_mcp.tools.affiliate_tools  # noqa: F401
import shopline_mcp.tools.gift_tools  # noqa: F401
import shopline_mcp.tools.addon_product_tools  # noqa: F401
import shopline_mcp.tools.subscription_tools  # noqa: F401

# --- Read tools: Order extended ---
import shopline_mcp.tools.return_order_tools  # noqa: F401
import shopline_mcp.tools.order_delivery_tools  # noqa: F401
import shopline_mcp.tools.conversation_tools  # noqa: F401
import shopline_mcp.tools.review_tools  # noqa: F401

# --- Read tools: Store settings ---
import shopline_mcp.tools.merchant_tools  # noqa: F401
import shopline_mcp.tools.payment_tools  # noqa: F401
import shopline_mcp.tools.delivery_option_tools  # noqa: F401
import shopline_mcp.tools.channel_tools  # noqa: F401
import shopline_mcp.tools.settings_tools  # noqa: F401
import shopline_mcp.tools.tax_tools  # noqa: F401
import shopline_mcp.tools.staff_tools  # noqa: F401
import shopline_mcp.tools.token_tools  # noqa: F401
import shopline_mcp.tools.agent_tools  # noqa: F401

# --- Write tools ---
import shopline_mcp.tools.writes.customer_writes  # noqa: F401
import shopline_mcp.tools.writes.order_writes  # noqa: F401
import shopline_mcp.tools.writes.product_writes  # noqa: F401
import shopline_mcp.tools.writes.promotion_writes  # noqa: F401
import shopline_mcp.tools.writes.category_writes  # noqa: F401
import shopline_mcp.tools.writes.return_order_writes  # noqa: F401
import shopline_mcp.tools.writes.conversation_writes  # noqa: F401
import shopline_mcp.tools.writes.review_writes  # noqa: F401
import shopline_mcp.tools.writes.gift_writes  # noqa: F401
import shopline_mcp.tools.writes.purchase_order_writes  # noqa: F401
import shopline_mcp.tools.writes.media_writes  # noqa: F401
import shopline_mcp.tools.writes.order_delivery_writes  # noqa: F401
import shopline_mcp.tools.writes.delivery_option_writes  # noqa: F401
import shopline_mcp.tools.writes.merchant_writes  # noqa: F401

import os

from shopline_mcp.app import mcp


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} 未設定。遠端模式會把商店資料與 68 個寫入操作暴露在網路上，"
            f"因此缺少 {name} 時拒絕啟動。"
        )
    return value


def build_http_app():
    """組出可部署的 ASGI app（Zeabur / 任何 ASGI 主機皆可用）。

    與 stdio 模式的差異在於多了兩層防護：
    - Bearer token 認證：沒有它，任何知道網址的人都能操作商店
    - 寫入二階段確認：遠端沒有客戶端權限提示可依賴，改由伺服器強制
    """
    from shopline_mcp.http_auth import BearerAuthMiddleware
    from shopline_mcp.security import install_write_confirmation

    auth_token = _require("MCP_AUTH_TOKEN")
    _require("SHOPLINE_API_TOKEN")

    # 確認碼的簽章金鑰預設沿用存取金鑰，可另外指定
    confirm_secret = os.environ.get("MCP_CONFIRM_SECRET", "").strip() or auth_token

    protected = install_write_confirmation(mcp, confirm_secret)

    mcp.settings.host = os.environ.get("HOST", "0.0.0.0")
    mcp.settings.port = int(os.environ.get("PORT", "8000"))

    app = mcp.streamable_http_app()

    async def healthz(request):
        from starlette.responses import JSONResponse
        return JSONResponse({"status": "ok", "write_tools_protected": protected})

    app.add_route("/healthz", healthz, methods=["GET"])
    app.add_middleware(BearerAuthMiddleware, token=auth_token)
    return app


def main():
    transport = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower()

    if transport == "stdio":
        mcp.run(transport="stdio")
        return

    if transport in ("http", "streamable-http"):
        import uvicorn
        app = build_http_app()
        uvicorn.run(app, host=mcp.settings.host, port=mcp.settings.port)
        return

    raise RuntimeError(
        f"不支援的 MCP_TRANSPORT: {transport!r}（可用 stdio 或 http）"
    )


if __name__ == "__main__":
    main()
