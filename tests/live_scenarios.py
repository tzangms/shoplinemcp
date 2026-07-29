"""模擬店長日常會問的電商查詢情境，全部唯讀（需連線至真實商店）。

執行方式：
    SHOPLINE_API_TOKEN=xxx python tests/live_scenarios.py

用途是驗證常見問題能否得到合理答案（業績、熱銷、低庫存、SKU 查詢、
退貨、地區分佈、回購率等），屬冒煙測試而非單元測試。
"""

import sys, os, json, asyncio, datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'src'))

import shopline_mcp
assert shopline_mcp.__file__.startswith(os.path.join(REPO_ROOT, 'src'))

import shopline_mcp.server
from shopline_mcp.app import mcp

TODAY = datetime.date.today()
D30 = (TODAY - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
D90 = (TODAY - datetime.timedelta(days=90)).strftime('%Y-%m-%d')
END = TODAY.strftime('%Y-%m-%d')

# (情境描述, tool, 參數)
SCENARIOS = [
    ("這個月賣得最好的商品是哪些？", "get_top_products",
     {"start_date": D30, "end_date": END}),
    ("最近 30 天業績如何？", "get_sales_summary",
     {"start_date": D30, "end_date": END}),
    ("業績趨勢走向？", "get_sales_trend",
     {"start_date": D30, "end_date": END}),
    ("哪些商品快沒貨了？", "get_low_stock_alerts", {"threshold": 5}),
    ("『彈力髮圈』這個商品還有貨嗎？", "get_product_list",
     {"keyword": "彈力髮圈", "max_results": 10}),
    ("查一下 SKU A0102-BRO04 的庫存", "get_product_by_sku",
     {"sku": "A0102-BRO04"}),
    ("最近有哪些待處理的訂單？", "query_orders",
     {"start_date": D30, "end_date": END, "status": "pending"}),
    ("這個月有多少退貨？", "list_return_orders", {}),
    ("退款金額統計？", "get_refund_summary", {"start_date": D90, "end_date": END}),
    ("客人都住哪些縣市？", "get_customer_geo_analysis",
     {"start_date": D90, "end_date": END}),
    ("回購率多少？", "get_repurchase_analysis",
     {"start_date": D90, "end_date": END}),
    ("哪些商品滯銷？", "get_slow_movers",
     {"start_date": D90, "end_date": END}),
    ("目前有哪些促銷活動在跑？", "list_promotions", {}),
    ("店內分類結構長怎樣？", "get_category_tree", {}),
    ("各門市庫存分佈？", "get_stock_by_warehouse", {"sku": "A0102-BRO04"}),
    ("有哪些付款/物流方式？", "list_delivery_options", {}),
]


def brief(payload, limit=340):
    """濃縮輸出，只看關鍵欄位"""
    if isinstance(payload, dict):
        out = {}
        for k, v in payload.items():
            if isinstance(v, list):
                out[k] = f'[{len(v)} 筆]' + (f' 首筆={json.dumps(v[0], ensure_ascii=False)[:150]}' if v else '')
            elif isinstance(v, dict):
                out[k] = f'{{{len(v)} keys}} ' + json.dumps(v, ensure_ascii=False)[:120]
            else:
                out[k] = v
        return json.dumps(out, ensure_ascii=False)[:limit]
    return json.dumps(payload, ensure_ascii=False, default=str)[:limit]


async def main():
    import time
    ok = fail = 0
    for desc, tool, args in SCENARIOS:
        t0 = time.time()
        print(f'\n【{desc}】')
        print(f'  tool: {tool}({json.dumps(args, ensure_ascii=False)})')
        try:
            res = await mcp.call_tool(tool, args)
            payload = res[1] if isinstance(res, tuple) and len(res) > 1 else res
            if isinstance(payload, dict) and 'result' in payload and len(payload) == 1:
                payload = payload['result']
            dt = time.time() - t0
            print(f'  ✓ ({dt:.1f}s) {brief(payload)}')
            ok += 1
        except Exception as e:
            dt = time.time() - t0
            print(f'  ✗ ({dt:.1f}s) {type(e).__name__}: {str(e)[:200]}')
            fail += 1
    print(f'\n===== 情境測試: {ok} 成功 / {fail} 失敗 =====')


if __name__ == '__main__':
    asyncio.run(main())
