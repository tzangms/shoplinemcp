"""Shopline MCP server."""

import re

from mcp.server.fastmcp import FastMCP

from . import api

mcp = FastMCP("shopline")


@mcp.tool()
def verify_order_owner(order_number: str, email: str = "", phone: str = "") -> str:
    """Verify that the customer is the owner of an order.
    MUST be called before sharing any order details.
    Pass the order number and the email or phone the customer provided.

    Args:
        order_number: Order number
        email: Email provided by the customer (optional)
        phone: Phone provided by the customer (optional)
    """
    provided_email = email.strip().lower()
    provided_phone = re.sub(r"\D", "", phone)
    if not provided_email and not provided_phone:
        return "FAILED: Customer must provide either email or phone for verification."

    orders = api.search_orders(order_number, limit=1)
    if not orders:
        return f"FAILED: Order {order_number} not found."
    order = orders[0]

    order_email = (order.get("customer_email") or "").strip().lower()
    order_phone = re.sub(r"\D", "", order.get("customer_phone") or "")

    if provided_email and provided_email == order_email:
        return f"VERIFIED: Email matches for order {order_number}."
    if provided_phone and provided_phone == order_phone:
        return f"VERIFIED: Phone matches for order {order_number}."

    delivery_data = order.get("delivery_data", {})
    recipient_phone = re.sub(r"\D", "", delivery_data.get("recipient_phone") or "")
    if provided_phone and provided_phone == recipient_phone:
        return f"VERIFIED: Phone matches for order {order_number}."

    return f"FAILED: The provided information does not match order {order_number}. Advise the customer to double-check or contact support."


@mcp.tool()
def search_orders(query: str) -> str:
    """Search orders by customer email, phone, or order number.
    Personal info in results is masked. Verify customer identity before sharing details.

    Args:
        query: Customer email, phone number, or order number
    """
    orders = api.search_orders(query)
    if not orders:
        return f"No orders found for '{query}'."
    lines = []
    for o in orders:
        total = api.fmt_money(o.get("total", "?"))
        order_number = o.get("order_number", o.get("id", "?"))
        order_id = o.get("id")
        order_label = f"Order {order_number}"
        if order_id:
            order_label += f" (ID: {order_id})"
        lines.append(
            f"{order_label}: "
            f"status={o.get('status', '?')}, "
            f"payment={o.get('order_payment', {}).get('status', '?')}, "
            f"delivery={o.get('order_delivery', {}).get('status', '?')}, "
            f"total={total}, "
            f"date={str(o.get('created_at', ''))[:10]}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_order_detail(order_id: str) -> str:
    """Get order details (items, payment status, shipping).
    Personal info is masked. Only share with verified order owner.

    Args:
        order_id: The order ID
    """
    o = api.get_order(order_id)
    if not o:
        return f"Order {order_id} not found."

    items_list = o.get("subtotal_items", o.get("line_items", []))
    item_strs = []
    for li in items_list:
        title = li.get("title") or api.get_title(li) or "?"
        qty = li.get("quantity", 1)
        item_strs.append(f"{title} x{qty}")
    items = ", ".join(item_strs)

    payment = o.get("order_payment", {})
    delivery = o.get("order_delivery", {})
    delivery_data = o.get("delivery_data", {})
    tracking = delivery_data.get("tracking_no", delivery_data.get("tracking_number", "N/A"))

    total = api.fmt_money(o.get("total", "?"))
    payment_method = payment.get("method", payment.get("payment_type", "N/A"))

    parts = [
        f"Order {o.get('order_number', o.get('id'))}",
        f"Status: {o.get('status', '?')}",
        f"Payment: {payment.get('status', '?')} ({payment_method})",
        f"Delivery: {delivery.get('status', '?')}",
        f"Tracking: {tracking}",
        f"Total: {total}",
        f"Items: {items}",
        f"Customer: {o.get('customer_name', 'N/A')} ({api.mask_email(o.get('customer_email'))})",
        f"Created: {str(o.get('created_at', ''))[:10]}",
    ]
    masked_addr = api.mask_address(o.get("delivery_address"))
    if masked_addr:
        parts.append(f"Ship to: {masked_addr}")
    return "\n".join(parts)


@mcp.tool()
def get_order_fulfillments(order_id: str) -> str:
    """Get shipping/fulfillment status and tracking numbers for an order.
    Only share with verified order owner.

    Args:
        order_id: The order ID
    """
    o = api.get_order_fulfillments(order_id)
    if not o:
        return f"Order {order_id} not found."
    delivery = o.get("order_delivery", {})
    delivery_data = o.get("delivery_data", {})
    tracking = delivery_data.get("tracking_no", delivery_data.get("tracking_number", "N/A"))
    return (
        f"Order {o.get('order_number', order_id)}\n"
        f"Delivery status: {delivery.get('status', '?')}\n"
        f"Tracking number: {tracking}\n"
        f"Delivery platform: {delivery.get('delivery_platform', 'N/A')}"
    )


@mcp.tool()
def get_order_transactions(order_id: str) -> str:
    """Get payment info for an order. Contains sensitive payment data -- only share with verified order owner.

    Args:
        order_id: The order ID
    """
    o = api.get_order_transactions(order_id)
    if not o:
        return f"Order {order_id} not found."
    payment = o.get("order_payment", {})
    if not payment:
        return f"No payment info found for order {order_id}."
    amount = api.fmt_money(payment.get("total", "?"))
    parts = [
        f"Payment for order {o.get('order_number', order_id)}:",
        f"  Method: {payment.get('payment_type', 'N/A')}",
        f"  Status: {payment.get('status', '?')}",
        f"  Amount: {amount}",
        f"  Paid at: {str(payment.get('paid_at', 'N/A'))[:19]}",
    ]
    last_four = payment.get("last_four_digits")
    if last_four:
        parts.append(f"  Card: ****{last_four}")
    return "\n".join(parts)


@mcp.tool()
def cancel_order(order_id: str, reason: str = "Cancelled via MCP") -> str:
    """Cancel an order. This cannot be undone. Requires explicit customer confirmation before executing.

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
    """Search products by keyword. Returns product name, price, and stock availability (not exact quantities).

    Args:
        keyword: Search keyword
    """
    products = api.search_products(keyword)
    if not products:
        return f"No products found for '{keyword}'."
    lines = []
    for p in products[:10]:
        title = api.get_title(p)
        variants = p.get("variants", p.get("variations", []))
        if variants:
            price = api.fmt_money(variants[0].get("price", "?"))
            total_qty = sum(v.get("inventory_quantity", v.get("quantity", 0)) for v in variants)
        else:
            price = api.fmt_money(p.get("price", "?"))
            total_qty = p.get("quantity", 0)
        lines.append(f"{title} (ID: {p.get('id', '?')}): price={price}, availability={api.stock_level(total_qty)}")
    return "\n".join(lines)


@mcp.tool()
def get_product_detail(product_id: str) -> str:
    """Get product info including variants and prices. Stock shown as availability level, not exact count.

    Args:
        product_id: The product ID
    """
    p = api.get_product(product_id)
    if not p:
        return f"Product {product_id} not found."
    title = api.get_title(p)
    lines = [
        f"Product: {title}",
        f"Status: {p.get('status', '?')}",
        f"Vendor: {p.get('vendor', p.get('supplier', 'N/A'))}",
    ]
    variants = p.get("variants", p.get("variations", []))
    if variants:
        for v in variants:
            v_title = v.get("title", v.get("sku", "?"))
            qty = v.get("inventory_quantity", v.get("quantity", 0))
            lines.append(
                f"  Variant: {v_title} -- "
                f"price={api.fmt_money(v.get('price', '?'))}, "
                f"sku={v.get('sku', 'N/A')}, "
                f"availability={api.stock_level(qty)}"
            )
    else:
        lines.append(f"  Price: {api.fmt_money(p.get('price', '?'))}, availability={api.stock_level(p.get('quantity', 0))}")
    options = p.get("options", p.get("variant_options", []))
    if options:
        for opt in options:
            name = opt.get("name", "?")
            values = opt.get("values", [])
            lines.append(f"  Option: {name} = {', '.join(str(v) for v in values)}")
    return "\n".join(lines)


@mcp.tool()
def check_inventory(product_id: str) -> str:
    """Check stock availability for a product. Returns availability level (in stock / low stock / out of stock), not exact quantities.

    Args:
        product_id: The product ID
    """
    p = api.get_product(product_id)
    if not p:
        return f"Product {product_id} not found."
    title = api.get_title(p)
    lines = [f"Inventory for: {title}"]
    total = 0
    variants = p.get("variants", p.get("variations", []))
    if variants:
        for v in variants:
            qty = v.get("inventory_quantity", v.get("quantity", 0))
            total += qty
            v_title = v.get("title", v.get("sku", "?"))
            lines.append(f"  {v_title}: {api.stock_level(qty)}")
    else:
        total = p.get("quantity", 0)
    lines.append(f"Overall: {api.stock_level(total)}")
    return "\n".join(lines)


@mcp.tool()
def get_customer_info(query: str) -> str:
    """Get customer info (masked). Verify identity before sharing.
    Never reveal full email, phone, or spending details to unverified users.

    Args:
        query: Customer email or phone number
    """
    customers = api.search_customers(query)
    if not customers:
        return f"No customer found for '{query}'."
    c = customers[0]
    return (
        f"Customer: {c.get('name', 'N/A')}\n"
        f"Email: {api.mask_email(c.get('email'))}\n"
        f"Phone: {api.mask_phone(c.get('mobile_phone'))}\n"
        f"Total orders: {c.get('order_count', 0)}\n"
        f"Member: {'Yes' if c.get('is_member') else 'No'}"
    )


@mcp.tool()
def get_customer_orders(query: str) -> str:
    """Get order history for a customer. Verify customer identity before sharing results.

    Args:
        query: Customer email or phone number
    """
    orders = api.search_orders(query, limit=10)
    if not orders:
        return f"No orders found for customer '{query}'."
    lines = [f"Orders for {query} ({len(orders)} found):"]
    for o in orders:
        total = api.fmt_money(o.get("total", "?"))
        lines.append(
            f"  {o.get('order_number', o.get('id', '?'))}: "
            f"status={o.get('status', '?')}, "
            f"total={total}, "
            f"date={str(o.get('created_at', ''))[:10]}"
        )
    return "\n".join(lines)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
