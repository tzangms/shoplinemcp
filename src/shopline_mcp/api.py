"""Shopline Open API client."""

import os
import re

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


def _patch(path: str, json: dict | None = None, timeout: float = 10.0) -> httpx.Response:
    return httpx.patch(f"{BASE_URL}{path}", headers=_headers(), json=json, timeout=timeout)


# ── Formatting helpers ──

def fmt_money(value):
    """Format a money value — Open API uses {"cents": N, "label": "..."}, or a plain value."""
    if isinstance(value, dict):
        return value.get("label", value.get("dollars", "?"))
    return value


def get_title(product):
    """Extract product title — Open API may use title_translations."""
    title = product.get("title")
    if title:
        return title
    translations = product.get("title_translations", {})
    return translations.get("zh-hant", translations.get("en", "?"))


def mask_email(email):
    if not email or "@" not in email:
        return email or "N/A"
    local, domain = email.rsplit("@", 1)
    if len(local) <= 3:
        return f"{local[0]}***@{domain}"
    return f"{local[:3]}***{local[-1]}@{domain}"


def mask_phone(phone):
    if not phone:
        return "N/A"
    digits = re.sub(r"\D", "", phone)
    if len(digits) <= 4:
        return phone
    return digits[:4] + "***" + digits[-2:]


def mask_address(address):
    if not address or not isinstance(address, dict):
        return None
    city = address.get("city", "")
    country = address.get("country_code", "")
    return f"{city} {country}".strip() or None


def stock_level(qty):
    if qty <= 0:
        return "out of stock"
    if qty <= 5:
        return "low stock"
    return "in stock"


# ── Orders ──

def search_orders(query: str, limit: int = 5) -> list[dict]:
    resp = _get("/orders/search", params={"query": query, "per_page": limit})
    resp.raise_for_status()
    return resp.json().get("orders", [])


def get_order(order_id: str) -> dict:
    resp = _get(f"/orders/{order_id}")
    resp.raise_for_status()
    data = resp.json()
    return data.get("order", data)


def get_order_fulfillments(order_id: str) -> dict | list:
    """Open API has no fulfillment_orders endpoint — extract from order detail."""
    order = get_order(order_id)
    return order


def get_order_transactions(order_id: str) -> dict:
    """Open API has no transactions endpoint — extract payment from order detail."""
    order = get_order(order_id)
    return order


def cancel_order(order_id: str, reason: str = "") -> dict:
    resp = _patch(f"/orders/{order_id}/cancel", json={"cancelled_reason": reason})
    resp.raise_for_status()
    return resp.json()


# ── Products ──

def search_products(keyword: str, limit: int = 10) -> list[dict]:
    resp = _get("/products", params={"per_page": 100})
    resp.raise_for_status()
    products = resp.json().get("products", [])
    if keyword:
        kw = keyword.lower()
        products = [p for p in products if kw in get_title(p).lower()]
    return products[:limit]


def get_product(product_id: str) -> dict | None:
    resp = _get(f"/products/{product_id}")
    resp.raise_for_status()
    data = resp.json()
    return data if data.get("id") else None


# ── Customers ──

def search_customers(query: str) -> list[dict]:
    resp = _get("/customers/search", params={"query": query, "per_page": 1})
    resp.raise_for_status()
    data = resp.json()
    return data.get("customers", data.get("items", []))
