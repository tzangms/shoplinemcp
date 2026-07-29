"""逐一呼叫所有唯讀 tool，回報成功/失敗（需連線至真實商店）。

執行方式：
    SHOPLINE_API_TOKEN=xxx python tests/live_read_tools.py

安全性：只呼叫「函式體內完全沒有 api_post/put/patch/delete」的 tool，
以 AST 靜態分析判定，不靠命名前綴猜測（execute_ / adjust_ 這類寫入操作
曾因前綴判斷而漏網）。寫入類 tool 一律不會被執行。

已知限制：判定成功與否是看「有無拋出例外」。若 tool 回傳的是 error dict
（例如 get_customer_group_members），因 MCP 回應包裝的關係偵測不到，
仍會計為 pass。故 PASS 的正確含義是「未拋例外」，不等於「回傳正確資料」。
"""

import sys, os, json, asyncio, datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'src'))

import shopline_mcp
assert shopline_mcp.__file__.startswith(os.path.join(REPO_ROOT, 'src')), \
    f'載入到錯誤的套件: {shopline_mcp.__file__}'

import shopline_mcp.server  # 註冊所有 tools
from shopline_mcp.app import mcp
from shopline_mcp.tools.base_tool import api_get

import ast, inspect, importlib

WRITE_CALLS = {'api_post', 'api_put', 'api_patch', 'api_delete'}


def readonly_tool_names():
    """靜態分析原始碼：只回傳「函式體內完全沒有寫入呼叫」的 tool 名稱。
    不靠命名前綴猜測，避免誤觸 execute_/adjust_ 之類的寫入操作。"""
    safe, unsafe = set(), set()
    tools_dir = os.path.join(REPO_ROOT, 'src', 'shopline_mcp', 'tools')
    for root, _dirs, files in os.walk(tools_dir):
        for fname in files:
            if not fname.endswith('.py'):
                continue
            path = os.path.join(root, fname)
            tree = ast.parse(open(path, encoding='utf-8').read())
            in_writes_dir = os.path.basename(root) == 'writes'
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                called = {n.func.id for n in ast.walk(node)
                          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
                # writes/ 目錄下一律視為寫入；其餘看是否呼叫寫入 API
                if in_writes_dir or (called & WRITE_CALLS):
                    unsafe.add(node.name)
                else:
                    safe.add(node.name)
    return safe - unsafe

TODAY = datetime.date.today()
D_END = TODAY.strftime('%Y-%m-%d')
D_START = (TODAY - datetime.timedelta(days=90)).strftime('%Y-%m-%d')


def seed_ids():
    s = {}

    def grab(endpoint, key, params=None):
        try:
            d = api_get(endpoint, params=params or {'per_page': 3})
            items = d.get('items') or []
            if items and items[0].get('id'):
                s[key] = items[0]['id']
        except Exception:
            pass

    grab('products', 'product_id')
    grab('orders', 'order_id')
    grab('customers', 'customer_id')
    grab('categories', 'category_id')
    grab('promotions', 'promotion_id')
    grab('warehouses', 'warehouse_id')
    grab('return_orders', 'return_order_id')
    grab('conversations', 'conversation_id')
    grab('delivery_options', 'delivery_option_id')
    grab('merchants', 'merchant_id')
    grab('product_review_comments', 'comment_id')
    grab('flash_price_campaigns', 'campaign_id')
    grab('product_subscriptions', 'subscription_id')
    grab('purchase_orders', 'purchase_order_id')
    grab('customer_groups', 'group_id')
    try:
        s['staff_id'] = api_get('token_info').get('staff', {}).get('id')
    except Exception:
        pass
    try:
        d = api_get('products', params={'per_page': 5})
        for p in d.get('items', []):
            if p.get('sku'):
                s['sku'] = p['sku']
                break
    except Exception:
        pass
    return s


def build_args(schema, seeds):
    """依 tool 的 input schema 填必填參數"""
    required = (schema or {}).get('required', [])
    args, missing = {}, []
    for r in required:
        if r in seeds and seeds[r]:
            args[r] = seeds[r]
        elif 'start' in r:
            args[r] = D_START
        elif 'end' in r:
            args[r] = D_END
        elif r == 'keyword':
            args[r] = '髮圈'
        elif r == 'platform':
            args[r] = 'shopline'
        else:
            missing.append(r)
    return args, missing


async def main():
    tools = await mcp.list_tools()
    seeds = seed_ids()
    print('# seeds ok: ' + ', '.join(k for k, v in seeds.items() if v))
    print('# seeds missing: ' + (', '.join(k for k, v in seeds.items() if not v) or '(none)'))

    safe = readonly_tool_names()
    targets = [t for t in tools if t.name in safe]
    excluded = sorted(t.name for t in tools if t.name not in safe)
    print(f'# 純唯讀 tool: {len(targets)} / 全部 {len(tools)}')
    print(f'# 已排除（含寫入呼叫，不會執行）: {len(excluded)}')
    print('#   ' + ', '.join(excluded) + '\n')

    ok, fail, skip = [], [], []

    import time
    for t in sorted(targets, key=lambda x: x.name):
        args, missing = build_args(t.inputSchema, seeds)
        if missing:
            skip.append((t.name, missing))
            print(f'SKIP {t.name}  missing={missing}', flush=True)
            continue
        t0 = time.time()
        try:
            res = await mcp.call_tool(t.name, args)
            payload = res[1] if isinstance(res, tuple) and len(res) > 1 else res
            txt = json.dumps(payload, ensure_ascii=False, default=str)
            dt = time.time() - t0
            if '"error"' in txt[:400]:
                fail.append((t.name, args, 'returned error: ' + txt[:220]))
                print(f'FAIL {t.name} ({dt:.1f}s) error: {txt[:150]}', flush=True)
            else:
                ok.append((t.name, args, len(txt)))
                print(f'ok   {t.name} ({dt:.1f}s) [{len(txt)}B]', flush=True)
        except Exception as e:
            dt = time.time() - t0
            fail.append((t.name, args, f'{type(e).__name__}: {str(e)[:240]}'))
            print(f'FAIL {t.name} ({dt:.1f}s) {type(e).__name__}: {str(e)[:150]}', flush=True)

    print(f'=== PASS ({len(ok)}) ===')
    for n, a, s in ok:
        print(f'  ok   {n}' + (f'  {json.dumps(a, ensure_ascii=False, default=str)}' if a else '') + f'  [{s}B]')
    print(f'\n=== FAIL ({len(fail)}) ===')
    for n, a, e in fail:
        print(f'  FAIL {n}' + (f'  {json.dumps(a, ensure_ascii=False, default=str)}' if a else ''))
        print(f'       {e}')
    print(f'\n=== SKIP ({len(skip)}) ===')
    for n, m in skip:
        print(f'  skip {n}  missing={m}')


if __name__ == '__main__':
    asyncio.run(main())
