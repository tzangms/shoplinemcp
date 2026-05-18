# shopline-mcp

MCP server for the [Shopline](https://www.shopline.com/) Open API. Exposes 140+ tools for querying and managing orders, products, customers, promotions, analytics, and store settings from your Shopline store via Claude.

## Installation

Clone the repo and install in a virtualenv:

```bash
git clone https://github.com/tzangms/shoplinemcp.git
cd shoplinemcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

This installs the `shopline-mcp` command into your virtualenv.

## Get a Shopline API token

In your Shopline admin panel:

**Settings → Staff Settings → API Auth → Generate**

Copy the token — you'll need it for the config below.

## Setup

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) and add an entry to `mcpServers`. You must use the **absolute path** to the `shopline-mcp` binary inside your virtualenv (Claude Desktop does not activate venvs):

```json
{
  "mcpServers": {
    "shopline": {
      "command": "/absolute/path/to/your/.venv/bin/shopline-mcp",
      "env": {
        "SHOPLINE_API_TOKEN": "your_token_here"
      }
    }
  }
}
```

To find the absolute path, run `which shopline-mcp` while the venv is activated.

Quit Claude Desktop completely (Cmd+Q) and reopen it. The Shopline tools should now be available.

### Claude Code

```bash
claude mcp add --transport stdio shopline \
  -e SHOPLINE_API_TOKEN=your_token \
  -- /absolute/path/to/your/.venv/bin/shopline-mcp
```

## Tools

The server exposes 140+ tools grouped into these categories:

- **Orders & Sales** — search, detail, fulfillments, transactions, cancel, returns, deliveries, conversations, reviews
- **Products & Inventory** — search, detail, variants, inventory, write operations, purchase orders
- **Customers** — info, orders, groups, store credits, membership tiers, member points, custom fields
- **Promotions** — promotions, flash prices, affiliate campaigns, gifts, addon products, subscriptions
- **Categories** — category tree, detail, write operations
- **Store settings** — merchant, payment, delivery options, channels, taxes, staff, tokens, agents
- **Analytics** — RFM, repurchase, geo, inventory turnover, category sales, promotion ROI, customer lifecycle, slow movers

Run `claude mcp list` (Claude Code) or check the tool picker in Claude Desktop to see the full list once configured.

## API

This server uses the Shopline Open API at `https://open.shopline.io/v1`. It works with stores on `shoplineapp.com` (Taiwan / Asia region).

## Troubleshooting

**Claude Desktop doesn't show the tools** — verify the `command` path is absolute and the binary exists (`ls -l /path/to/.venv/bin/shopline-mcp`). Check Claude Desktop logs at `~/Library/Logs/Claude/`.

**Server runs but tool calls fail with auth errors** — confirm `SHOPLINE_API_TOKEN` is set in the `env` block of the config (not just in your shell), and that the token has the required scopes in Shopline admin.

**Test the server manually**:

```bash
SHOPLINE_API_TOKEN=your_token /path/to/.venv/bin/shopline-mcp
```

It will wait on stdin (correct — MCP uses stdio). Ctrl+C to exit.

## License

MIT
