"""Shopline MCP server."""

from mcp.server.fastmcp import FastMCP

from . import api

mcp = FastMCP("shopline")


@mcp.tool()
def search_orders(query: str) -> str:
    """Search orders by customer email, phone, or order number.

    Args:
        query: Customer email, phone number, or order number
    """
    orders = api.search_orders(query)
    if not orders:
        return f"No orders found for '{query}'."
    lines = []
    for o in orders:
        lines.append(
            f"Order {o.get('order_number', o.get('id', '?'))}: "
            f"status={o.get('status', '?')}, "
            f"payment={o.get('order_payment', {}).get('status', '?')}, "
            f"delivery={o.get('order_delivery', {}).get('status', '?')}, "
            f"total={o.get('total', '?')}, "
            f"date={str(o.get('created_at', ''))[:10]}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_order_detail(order_id: str) -> str:
    """Get detailed information about a specific order including items, payment, and shipping.

    Args:
        order_id: The order ID
    """
    o = api.get_order(order_id)
    if not o:
        return f"Order {order_id} not found."

    items_list = o.get("subtotal_items", o.get("line_items", []))
    items = ", ".join(f"{li.get('title', '?')} x{li.get('quantity', 1)}" for li in items_list)

    payment = o.get("order_payment", {})
    delivery = o.get("order_delivery", {})
    delivery_data = o.get("delivery_data", {})
    tracking = delivery_data.get("tracking_no", delivery_data.get("tracking_number", "N/A"))

    parts = [
        f"Order {o.get('order_number', o.get('id'))}",
        f"Status: {o.get('status', '?')}",
        f"Payment: {payment.get('status', '?')} ({payment.get('method', 'N/A')})",
        f"Delivery: {delivery.get('status', '?')}",
        f"Tracking: {tracking}",
        f"Total: {o.get('total', '?')} {o.get('currency', '')}",
        f"Items: {items}",
        f"Customer: {o.get('customer_name', 'N/A')} ({o.get('customer_email', 'N/A')})",
        f"Created: {str(o.get('created_at', ''))[:10]}",
    ]
    address = o.get("delivery_address", {})
    if address:
        addr_str = f"{address.get('address_1', '')} {address.get('city', '')} {address.get('country_code', '')}".strip()
        if addr_str:
            parts.append(f"Ship to: {address.get('recipient_name', '')} - {addr_str}")
    return "\n".join(parts)


@mcp.tool()
def get_order_fulfillments(order_id: str) -> str:
    """Get shipping/fulfillment status and tracking numbers for an order.

    Args:
        order_id: The order ID
    """
    fulfillments = api.get_order_fulfillments(order_id)
    if not fulfillments:
        return f"No fulfillment info found for order {order_id}."
    lines = []
    for fl in fulfillments:
        status = fl.get("status", "unknown")
        location = fl.get("assigned_location", {}).get("name", "N/A")
        fl_items = ", ".join(
            f"{li.get('title', li.get('sku', '?'))} x{li.get('quantity', 1)}"
            for li in fl.get("line_items", [])
        )
        lines.append(f"Fulfillment: status={status}, location={location}, items=[{fl_items}]")
    return "\n".join(lines)


@mcp.tool()
def get_order_transactions(order_id: str) -> str:
    """Get payment transaction history for an order (payments, refunds).

    Args:
        order_id: The order ID
    """
    transactions = api.get_order_transactions(order_id)
    if not transactions:
        return f"No transactions found for order {order_id}."
    lines = []
    for t in transactions:
        lines.append(
            f"Transaction {t.get('id', '?')}: "
            f"kind={t.get('kind', '?')}, "
            f"status={t.get('status', '?')}, "
            f"amount={t.get('amount', '?')} {t.get('currency', '')}, "
            f"gateway={t.get('gateway', 'N/A')}"
        )
    return "\n".join(lines)


@mcp.tool()
def cancel_order(order_id: str, reason: str = "Cancelled via MCP") -> str:
    """Cancel an order. Use with caution -- this cannot be undone.

    Args:
        order_id: The order ID
        reason: Cancellation reason
    """
    try:
        api.cancel_order(order_id, reason)
        return f"Order {order_id} has been cancelled. Reason: {reason}"
    except Exception as e:
        return f"Failed to cancel order {order_id}: {e}"


@mcp.tool()
def search_products(keyword: str) -> str:
    """Search products by keyword.

    Args:
        keyword: Search keyword
    """
    products = api.search_products(keyword)
    if not products:
        return f"No products found for '{keyword}'."
    lines = []
    for p in products[:10]:
        variants = p.get("variants", [{}])
        price = variants[0].get("price", "?") if variants else "?"
        inventory = sum(v.get("inventory_quantity", 0) for v in variants)
        lines.append(f"{p.get('title', '?')} (ID: {p.get('id', '?')}): price={price}, stock={inventory}")
    return "\n".join(lines)


@mcp.tool()
def get_product_detail(product_id: str) -> str:
    """Get detailed product info including all variants, prices, and inventory.

    Args:
        product_id: The product ID
    """
    p = api.get_product(product_id)
    if not p:
        return f"Product {product_id} not found."
    lines = [
        f"Product: {p.get('title', '?')}",
        f"Status: {p.get('status', '?')}",
        f"Vendor: {p.get('vendor', 'N/A')}",
    ]
    for v in p.get("variants", []):
        lines.append(
            f"  Variant: {v.get('title', v.get('sku', '?'))} -- "
            f"price={v.get('price', '?')}, "
            f"sku={v.get('sku', 'N/A')}, "
            f"stock={v.get('inventory_quantity', '?')}"
        )
    for opt in p.get("options", []):
        lines.append(f"  Option: {opt.get('name', '?')} = {', '.join(opt.get('values', []))}")
    return "\n".join(lines)


@mcp.tool()
def check_inventory(product_id: str) -> str:
    """Check stock/inventory levels for a specific product.

    Args:
        product_id: The product ID
    """
    p = api.get_product(product_id)
    if not p:
        return f"Product {product_id} not found."
    lines = [f"Inventory for: {p.get('title', '?')}"]
    total = 0
    for v in p.get("variants", []):
        qty = v.get("inventory_quantity", 0)
        total += qty
        lines.append(f"  {v.get('title', v.get('sku', '?'))}: {qty} in stock")
    lines.append(f"Total stock: {total}")
    return "\n".join(lines)


@mcp.tool()
def get_customer_info(query: str) -> str:
    """Get customer information including membership and spending history.

    Args:
        query: Customer email or phone number
    """
    customers = api.search_customers(query)
    if not customers:
        return f"No customer found for '{query}'."
    c = customers[0]
    return (
        f"Customer: {c.get('name', 'N/A')}\n"
        f"Email: {c.get('email', 'N/A')}\n"
        f"Phone: {c.get('mobile_phone', 'N/A')}\n"
        f"Total orders: {c.get('order_count', 0)}\n"
        f"Total spent: ${c.get('orders_total_sum', '0')}\n"
        f"Member: {'Yes' if c.get('is_member') else 'No'}\n"
        f"Credit balance: {c.get('credit_balance', '0')}"
    )


@mcp.tool()
def get_customer_orders(query: str) -> str:
    """Get all orders for a specific customer.

    Args:
        query: Customer email or phone number
    """
    orders = api.search_orders(query, limit=10)
    if not orders:
        return f"No orders found for customer '{query}'."
    lines = [f"Orders for {query} ({len(orders)} found):"]
    for o in orders:
        lines.append(
            f"  {o.get('order_number', o.get('id', '?'))}: "
            f"status={o.get('status', '?')}, "
            f"total={o.get('total', '?')}, "
            f"date={str(o.get('created_at', ''))[:10]}"
        )
    return "\n".join(lines)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
