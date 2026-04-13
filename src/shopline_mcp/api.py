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
