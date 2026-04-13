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
