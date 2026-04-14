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

# --- Custom tools (chatie-compatible) ---
import shopline_mcp.tools.chatie_tools  # noqa: F401

from shopline_mcp.app import mcp


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
