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

### Remote HTTP (Claude custom connector)

Deploy once to a host (e.g. Zeabur) and connect from Claude with just a URL — no local install.

1. Deploy this repo. On **Zeabur**, `zbpack.json` runs `python -m shopline_mcp.remote`.
2. Set environment variables on the service:
   - `SHOPLINE_API_TOKEN` — your Shopline API token
   - `SHOPLINE_MCP_KEY` — a secret string used as the URL key
3. In Claude, add a **custom connector** with URL:

   ```
   https://<your-host>/<SHOPLINE_MCP_KEY>/mcp
   ```

The key in the path acts as a simple bearer for a single trusted user. Keep the full URL secret. Optionally set `SHOPLINE_ALLOWED_HOSTS` (comma-separated) to enable host-whitelist DNS-rebinding protection.

#### Multiple stores (multi-tenant)

One deployment can serve several Shopline stores, each with its own URL key and token.

- Keep the single-store pair `SHOPLINE_MCP_KEY` + `SHOPLINE_API_TOKEN` for the first store.
- Add each additional store as a pair: `SHOPLINE_STORE_<LABEL>_KEY` + `SHOPLINE_STORE_<LABEL>_TOKEN`.

Each store gets its own connector URL: `https://<host>/<that-store-key>/mcp`. An unknown key returns 404.

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
