# shopline-mcp

MCP server for the [Shopline](https://www.shopline.com/) Open API. Exposes 140+ tools for querying and managing orders, products, customers, promotions, analytics, and store settings from your Shopline store via Claude.

## Get a Shopline API token

In your Shopline admin panel:

**Settings → Staff Settings → API Auth → Generate**

Copy the token — you'll need it for the config below.

## Setup

### Claude Desktop (recommended: uvx)

[Install uv](https://docs.astral.sh/uv/getting-started/installation/) first (`brew install uv` on macOS).

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) and add:

```json
{
  "mcpServers": {
    "shopline": {
      "command": "uvx",
      "args": ["shopline-mcp"],
      "env": {
        "SHOPLINE_API_TOKEN": "your_token_here"
      }
    }
  }
}
```

`uvx` downloads and runs the package on demand — no manual install needed. Quit Claude Desktop completely (Cmd+Q) and reopen.

### Claude Code

```bash
claude mcp add --transport stdio shopline \
  -e SHOPLINE_API_TOKEN=your_token \
  -- uvx shopline-mcp
```

### Alternative: pip install

If you prefer a permanent install:

```bash
pip install shopline-mcp
```

Then use the absolute path to the installed binary (`which shopline-mcp`) as the `command` in your Claude Desktop config.

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

**Claude Desktop doesn't show the tools** — check that `uvx` is in PATH (`which uvx`). Claude Desktop inherits PATH from your shell on launch; if you installed uv after launching Claude Desktop, restart it. Check logs at `~/Library/Logs/Claude/`.

**Tool calls fail with auth errors** — confirm `SHOPLINE_API_TOKEN` is set in the `env` block of the config (not just in your shell), and that the token has the required scopes in Shopline admin.

**Test the server manually**:

```bash
SHOPLINE_API_TOKEN=your_token uvx shopline-mcp
```

It will wait on stdin (correct — MCP uses stdio). Ctrl+C to exit.

## Development

```bash
git clone https://github.com/tzangms/shoplinemcp.git
cd shoplinemcp
uv venv && source .venv/bin/activate
uv pip install -e .
```

## License

MIT
