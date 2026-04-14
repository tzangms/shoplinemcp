"""Chatie-compatible tools — verify_order_owner and masked data helpers."""

import re

from pydantic import Field

from shopline_mcp.app import mcp
from shopline_mcp.tools.base_tool import api_get, fetch_all_pages, money_to_float, get_translation


# ── Data masking helpers ──

def _mask_email(email):
    if not email or "@" not in email:
        return email or "N/A"
    local, domain = email.rsplit("@", 1)
    if len(local) <= 3:
        return f"{local[0]}***@{domain}"
    return f"{local[:3]}***{local[-1]}@{domain}"


def _mask_phone(phone):
    if not phone:
        return "N/A"
    digits = re.sub(r"\D", "", phone)
    if len(digits) <= 4:
        return phone
    return digits[:4] + "***" + digits[-2:]


# ── Tools ──

@mcp.tool()
def verify_order_owner(
    order_number: str = Field(description="Order number"),
    email: str = Field(default="", description="Email provided by the customer (optional)"),
    phone: str = Field(default="", description="Phone provided by the customer (optional)"),
) -> str:
    """Verify that the customer is the owner of an order.
    MUST be called before sharing any order details.
    Pass the order number and the email or phone the customer provided.
    """
    provided_email = email.strip().lower()
    provided_phone = re.sub(r"\D", "", phone)
    if not provided_email and not provided_phone:
        return "FAILED: Customer must provide either email or phone for verification."

    orders = fetch_all_pages("orders_search", params={"query": order_number, "per_page": 1}, max_pages=1)
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
def get_masked_customer_info(
    query: str = Field(description="Customer email or phone number"),
) -> str:
    """Get customer info with masked PII (email, phone). Verify identity before sharing.
    Never reveal full email, phone, or spending details to unverified users.
    """
    params = {"keyword": query, "per_page": 1}
    data = api_get("customers_search", params=params)
    customers = data.get("items", [])
    if not customers:
        return f"No customer found for '{query}'."
    c = customers[0]
    return (
        f"Customer: {c.get('name', 'N/A')}\n"
        f"Email: {_mask_email(c.get('email'))}\n"
        f"Phone: {_mask_phone(c.get('phone'))}\n"
        f"Total orders: {c.get('orders_count', 0)}\n"
        f"Total spent: {money_to_float(c.get('total_spent'))}\n"
        f"Member tier: {c.get('membership_tier_id', 'N/A')}"
    )
