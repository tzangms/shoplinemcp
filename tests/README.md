# Tests

These are **live integration scripts**, not unit tests. They call the real
Shopline API against a real store, so they are deliberately named without a
`test_` prefix — pytest will not collect them, and CI will not fire requests at
a production store by accident.

Both scripts are **read-only**. Neither creates, updates, nor deletes anything.

## Running

```bash
export SHOPLINE_API_TOKEN=your_token
python tests/live_scenarios.py     # fast  — ~15 common store-owner questions
python tests/live_read_tools.py    # slow  — every read-only tool (~20 min)
```

`live_read_tools.py` is slow because the analytics tools each walk months of
orders; expect 90–170s per analytics tool.

## live_scenarios.py

Smoke test: asks the questions a shop owner actually asks (this month's sales,
top sellers, low stock, stock for a SKU, returns, geography, repurchase rate,
slow movers, promotions, categories, warehouse stock, delivery options) and
prints a condensed answer for each. Good first check after changing a tool.

Note that some assertions are implicitly tied to the store the token points at
(e.g. it looks up SKU `A0102-BRO04`). Adjust `SCENARIOS` for a different store.

## live_read_tools.py

Sweeps every read-only tool, seeding required IDs (product, order, customer,
category, …) from live data first, then reporting pass / fail / skip.

**Write safety**: the script selects tools by AST-analysing the source and
keeping only those whose function body never calls `api_post` / `api_put` /
`api_patch` / `api_delete`. It does not guess from naming prefixes — an earlier
prefix-based version missed `execute_order_shipment` and called it. Anything in
`tools/writes/` is excluded outright.

**Reading the results**: `PASS` means "did not raise". A tool that returns an
error dict rather than raising (such as `get_customer_group_members`, which
reports an unsupported Shopline endpoint by design) still counts as a pass,
because the error text is not visible through MCP's response wrapper. Treat the
count as a crash check, not a correctness check.

Some failures are expected and are Shopline-side, not bugs here:

| Tool | Reason |
| --- | --- |
| `get_archived_orders` | `/v1/orders/archived` returns 410 Gone |
| `get_order_labels`, `get_order_tags`, `get_order_transactions` | Not present in Shopline API v1 |
| `get_customer_tier_history`, `get_delivery_time_slots`, `get_affiliate_campaign_*` | Feature not enabled on the test store |
