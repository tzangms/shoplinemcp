# Shopline MCP Server Design

## Goal

A Python MCP server wrapping the Shopline Open API (`open.shopline.io/v1`) with 10 read-only tools (plus cancel_order) for Claude Code / Claude Desktop.

## Target Users

- Developer (self-use) for querying Shopline store data
- Open source community (PyPI) for any shoplineapp.com merchant

## API

Open API only (`https://open.shopline.io/v1`). Auth via Bearer token from env var `SHOPLINE_API_TOKEN`. No OAuth, no Admin API.

## Tools

| Tool | Description | Endpoint |
|------|-------------|----------|
| `search_orders` | Search by email/phone/order number | `GET /orders` |
| `get_order_detail` | Order detail with items, payment, shipping | `GET /orders/{id}` |
| `get_order_fulfillments` | Fulfillment status and tracking | `GET /fulfillment_orders/{id}/fulfillment_orders` |
| `get_order_transactions` | Payment and refund history | `GET /orders/{id}/transactions` |
| `cancel_order` | Cancel an order (write, use with caution) | `POST /orders/{id}/cancel` |
| `search_products` | Search products by keyword | `GET /products` |
| `get_product_detail` | Product detail with variants, prices, inventory | `GET /products/{id}` |
| `check_inventory` | Stock levels for a product | `GET /products/{id}` |
| `get_customer_info` | Customer info by email or phone | `GET /customers` |
| `get_customer_orders` | All orders for a customer | `GET /orders` |

## Project Structure

```
shoplinemcp/
├── pyproject.toml
├── README.md
└── src/
    └── shopline_mcp/
        ├── __init__.py
        ├── server.py      # MCP server, tool registration, entry point
        └── api.py          # Shopline API client (httpx)
```

## Tech Stack

- Python 3.10+
- `mcp` SDK (official MCP Python SDK)
- `httpx` for API calls
- stdio transport

## Configuration

Single env var: `SHOPLINE_API_TOKEN`

## Usage

```bash
pip install shopline-mcp
claude mcp add --transport stdio shopline -- shopline-mcp
```

## Out of Scope

- Admin API (myshopline.com)
- OAuth flow
- Webhooks / SSE
- Write operations beyond cancel_order
