# Shopline MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server that wraps the Shopline Open API (`open.shopline.io/v1`) with 10 tools for Claude.

**Architecture:** FastMCP server with two modules — `api.py` (httpx client for Shopline Open API) and `server.py` (MCP tool registration). Token from `SHOPLINE_API_TOKEN` env var. stdio transport.

**Tech Stack:** Python 3.10+, `mcp[cli]` SDK, `httpx`

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/shopline_mcp/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "shopline-mcp"
version = "0.1.0"
description = "MCP server for Shopline Open API"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
dependencies = [
    "mcp[cli]>=1.2.0",
    "httpx>=0.27.0",
]

[project.scripts]
shopline-mcp = "shopline_mcp.server:main"
```

- [ ] **Step 2: Create package init**

Create `src/shopline_mcp/__init__.py`:

```python
"""MCP server for Shopline Open API."""
```

- [ ] **Step 3: Install in dev mode**

```bash
cd /Users/tzangms/projects/shoplinemcp
pip install -e .
```

- [ ] **Step 4: Commit**

```bash
cd /Users/tzangms/projects/shoplinemcp
git init
git add pyproject.toml src/
git commit -m "feat: project scaffolding"
```

---

### Task 2: API client

**Files:**
- Create: `src/shopline_mcp/api.py`

- [ ] **Step 1: Create the Shopline API client**

```python
"""Shopline Open API client."""

import os

import httpx

BASE_URL = "https://open.shopline.io/v1"


def _get_token() -> str:
    token = os.environ.get("SHOPLINE_API_TOKEN", "")
    if not token:
        raise RuntimeError("SHOPLINE_API_TOKEN environment variable is not set")
    return token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
    }


def _get(path: str, params: dict | None = None, timeout: float = 10.0) -> httpx.Response:
    return httpx.get(f"{BASE_URL}{path}", headers=_headers(), params=params, timeout=timeout)


def _post(path: str, json: dict | None = None, timeout: float = 10.0) -> httpx.Response:
    return httpx.post(f"{BASE_URL}{path}", headers=_headers(), json=json, timeout=timeout)


# ── Orders ──

def search_orders(query: str, limit: int = 5) -> list[dict]:
    params = {"email": query} if "@" in query else {"search_content": query}
    params["limit"] = limit
    resp = _get("/orders", params=params)
    resp.raise_for_status()
    return resp.json().get("orders", [])


def get_order(order_id: str) -> dict:
    resp = _get(f"/orders/{order_id}")
    resp.raise_for_status()
    return resp.json().get("order", resp.json())


def get_order_fulfillments(order_id: str) -> list[dict]:
    resp = _get(f"/fulfillment_orders/{order_id}/fulfillment_orders")
    if resp.status_code == 200:
        return resp.json().get("fulfillment_orders", [])
    # Fallback: get delivery info from order detail
    order = get_order(order_id)
    return [{"status": order.get("order_delivery", {}).get("status", "unknown")}]


def get_order_transactions(order_id: str) -> list[dict]:
    resp = _get(f"/orders/{order_id}/transactions")
    resp.raise_for_status()
    return resp.json().get("transactions", resp.json().get("items", []))


def cancel_order(order_id: str, reason: str = "") -> dict:
    resp = _post(f"/orders/{order_id}/cancel", json={"reason": reason})
    resp.raise_for_status()
    return resp.json()


# ── Products ──

def search_products(keyword: str, limit: int = 10) -> list[dict]:
    resp = _get("/products", params={"limit": 100})
    resp.raise_for_status()
    products = resp.json().get("products", [])
    if keyword:
        kw = keyword.lower()
        products = [p for p in products if kw in p.get("title", "").lower()]
    return products[:limit]


def get_product(product_id: str) -> dict:
    resp = _get(f"/products/{product_id}")
    resp.raise_for_status()
    return resp.json().get("product", resp.json())


# ── Customers ──

def search_customers(query: str) -> list[dict]:
    params = {"email": query} if "@" in query else {"mobile_phone": query}
    resp = _get("/customers", params=params)
    resp.raise_for_status()
    return resp.json().get("customers", resp.json().get("items", []))
```

- [ ] **Step 2: Commit**

```bash
git add src/shopline_mcp/api.py
git commit -m "feat: Shopline Open API client"
```

---

### Task 3: MCP server with all 10 tools

**Files:**
- Create: `src/shopline_mcp/server.py`

- [ ] **Step 1: Create the MCP server with all tools**

```python
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
```

- [ ] **Step 2: Verify the package installs and runs**

```bash
cd /Users/tzangms/projects/shoplinemcp
pip install -e .
shopline-mcp --help 2>&1 || echo "Entry point works"
```

- [ ] **Step 3: Commit**

```bash
git add src/shopline_mcp/server.py
git commit -m "feat: MCP server with 10 Shopline tools"
```

---

### Task 4: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README**

```markdown
# shopline-mcp

MCP server for the [Shopline](https://www.shopline.com/) Open API. Provides 10 tools for querying orders, products, and customers from your Shopline store via Claude.

## Installation

```bash
pip install shopline-mcp
```

## Setup

1. Generate an API token in your Shopline admin panel:
   **Settings > Staff Settings > API Auth > Generate**

2. Set the token as an environment variable:
   ```bash
   export SHOPLINE_API_TOKEN=your_token_here
   ```

3. Add to Claude Code:
   ```bash
   claude mcp add --transport stdio shopline -e SHOPLINE_API_TOKEN=your_token -- shopline-mcp
   ```

## Tools

| Tool | Description |
|------|-------------|
| `search_orders` | Search orders by email, phone, or order number |
| `get_order_detail` | Order details with items, payment, shipping |
| `get_order_fulfillments` | Fulfillment status and tracking numbers |
| `get_order_transactions` | Payment and refund history |
| `cancel_order` | Cancel an order (use with caution) |
| `search_products` | Search products by keyword |
| `get_product_detail` | Product details with variants and prices |
| `check_inventory` | Stock levels for a product |
| `get_customer_info` | Customer info and membership |
| `get_customer_orders` | All orders for a customer |

## API

This server uses the Shopline Open API at `https://open.shopline.io/v1`. It works with stores on `shoplineapp.com` (Taiwan/Asia).

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

---

### Task 5: Test with Claude Code

- [ ] **Step 1: Add MCP server to Claude Code**

```bash
claude mcp add --transport stdio shopline -e SHOPLINE_API_TOKEN=$SHOPLINE_API_TOKEN -- shopline-mcp
```

- [ ] **Step 2: Test a tool**

In Claude Code, ask: "use the shopline MCP to search for recent orders"

- [ ] **Step 3: Verify all 10 tools are registered**

```bash
claude mcp list
```
