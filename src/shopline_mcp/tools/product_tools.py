"""
商品與庫存相關 Tools — 供 AI Agent 調用
"""

from typing import Optional
from pydantic import Field

from shopline_mcp.app import mcp
from shopline_mcp.tools.base_tool import (
    api_get, fetch_all_pages, fetch_pages_with_total, money_to_float,
    get_translation, resolve_field, extract_image_urls, MAX_SCAN_PAGES, pages_for
)
from collections import defaultdict


def _variant_fields(v):
    """取出變體的顏色/尺寸。

    優先用 feed_variations（有明確的 color / size 具名欄位），
    沒有時才退回 fields_translations 的位置陣列（第 0 個當顏色、第 1 個當尺寸）。
    """
    fields = v.get("fields_translations", {}).get("zh-hant", [])
    feed = v.get("feed_variations") or {}

    color = (get_translation(feed["color"]) if "color" in feed
             else (fields[0] if len(fields) > 0 else ""))
    size = (get_translation(feed["size"]) if "size" in feed
            else (fields[1] if len(fields) > 1 else ""))
    return color, size


def _summarize_variant(v):
    """將 Shopline variation 物件整理成統一的回傳結構（含變體圖）"""
    color, size = _variant_fields(v)
    images = extract_image_urls(v)

    return {
        "id": v.get("id"),
        "sku": v.get("sku"),
        "color": color,
        "size": size,
        "price": money_to_float(v.get("price")),
        "price_sale": money_to_float(v.get("price_sale")),
        "cost": money_to_float(v.get("cost")),
        "quantity": v.get("quantity", 0) or 0,
        "total_orderable_quantity": v.get("total_orderable_quantity", 0),
        "image_url": images[0] if images else None,
    }


def _summarize_product(p):
    """將 Shopline product 物件整理成統一的回傳結構（含圖片 URL）"""
    variations = p.get("variations", [])
    total_qty = sum(v.get("quantity", 0) or 0 for v in variations)
    if not variations:
        total_qty = p.get("quantity", 0) or 0

    supplier = p.get("supplier") or {}
    supplier_name = supplier.get("name", "") if isinstance(supplier, dict) else ""

    images = extract_image_urls(p)

    return {
        "id": p.get("id"),
        "title": get_translation(p.get("title_translations")),
        "sku": p.get("sku"),
        "barcode": p.get("barcode") or p.get("gtin"),
        "brand": p.get("brand"),
        "supplier": supplier_name,
        "price": money_to_float(p.get("price")),
        "price_sale": money_to_float(p.get("price_sale")),
        "cost": money_to_float(p.get("cost")),
        "quantity": total_qty,
        "category_ids": p.get("category_ids", []),
        "status": p.get("status"),
        "variants_count": len(variations),
        "tags": p.get("tags", []),
        "image_url": images[0] if images else None,
        "images": images,
    }


# ============================================================
# Tool 1: get_product_list — 商品列表 / 商品搜尋
# ============================================================
@mcp.tool()
def get_product_list(
    keyword: Optional[str] = Field(default=None, description="關鍵字搜尋，由 Shopline 後端比對商品名稱 / SKU / 條碼"),
    sku: Optional[str] = Field(default=None, description="以 SKU 精準查詢（完全相符）。查特定貨品時優先用這個，不會漏抓"),
    barcode: Optional[str] = Field(default=None, description="以條碼(gtin)精準查詢"),
    category_id: Optional[str] = Field(default=None, description="依分類篩選，可用逗號分隔多個分類 ID"),
    status: Optional[str] = Field(default=None, description="商品狀態篩選：active / draft / removed / hidden"),
    brand: Optional[str] = Field(default=None, description="品牌篩選（Shopline 無此查詢參數，於結果集內比對）"),
    max_results: int = Field(default=50, description="最多回傳筆數。設大即可列出全部，不再有 500 筆上限"),
) -> dict:
    """搜尋 / 列出商品，含 SKU 變體、價格、品牌、庫存數量與商品圖 URL。

    查詢一律交由 Shopline 後端比對（不做本地模糊比對），因此含 & 的名稱、
    特殊排版的品名（如「8入-粗版」）都能正確命中，且結果不受筆數上限截斷。

    【呼叫的 Shopline API】
    - GET /v1/products/search（有任何查詢條件時）
    - GET /v1/products（完全無條件的列全部）
    """
    keyword = resolve_field(keyword)
    sku = resolve_field(sku)
    barcode = resolve_field(barcode)
    category_id = resolve_field(category_id)
    status = resolve_field(status)
    brand = resolve_field(brand)
    max_results = resolve_field(max_results)

    # 組 server-side 查詢參數，交給 Shopline 後端比對
    params = {}
    if keyword:
        params["query"] = keyword
    if sku:
        params["sku"] = sku
    if barcode:
        params["barcode"] = barcode
    if category_id:
        params["category_id"] = category_id
    if status:
        params["status"] = status

    # brand 需在結果集內比對，故不能只抓 max_results 筆就停
    scan_pages = MAX_SCAN_PAGES if brand else pages_for(max_results)

    endpoint = "products_search" if params else "products"
    products, total_count = fetch_pages_with_total(
        endpoint, params=params or None, max_pages=scan_pages
    )

    if brand:
        # 本地篩選後 API 的 total_count 不再代表結果數，改用實際比對筆數
        brand_lower = brand.lower()
        products = [
            p for p in products
            if brand_lower in (p.get("brand") or "").lower()
        ]
        total_count = len(products)

    results = [_summarize_product(p) for p in products[:max_results]]

    # total_count 來自 API，才能反映「符合條件的全部筆數」；
    # 只比對抓回筆數會在剛好抓滿一頁時誤報未截斷。
    total_found = total_count if total_count is not None else len(products)

    return {
        "total_found": total_found,
        "returned": len(results),
        "truncated": total_found > len(results),
        "query": params or None,
        "products": results
    }


# ============================================================
# Tool 2: get_product_variants — 商品 SKU 變體明細
# ============================================================
@mcp.tool()
def get_product_variants(
    product_id: str = Field(description="商品 ID"),
) -> dict:
    """取得特定商品的所有 SKU 變體明細，含尺寸×顏色的庫存矩陣與商品圖 URL。

    【呼叫的 Shopline API】
    - GET /v1/products/{product_id}
    """
    product_id = resolve_field(product_id)

    # 直接以 ID 精準查詢，不再撈全表再比對（原作法受筆數上限影響且緩慢）
    try:
        product = api_get("product_detail", path_params={"product_id": product_id})
    except Exception as e:
        return {"error": f"Product {product_id} not found: {e}"}

    if not product or not product.get("id"):
        return {"error": f"Product {product_id} not found"}

    title = get_translation(product.get("title_translations"))
    field_titles = product.get("field_titles", [])
    dim_names = [get_translation(ft.get("name_translations")) for ft in field_titles]

    variants = [_summarize_variant(v) for v in product.get("variations", [])]

    product_images = extract_image_urls(product)

    return {
        "product_id": product_id,
        "title": title,
        "brand": product.get("brand"),
        "sku": product.get("sku"),
        "dimensions": dim_names,
        "variants_count": len(variants),
        "total_quantity": sum(v["quantity"] for v in variants),
        "image_url": product_images[0] if product_images else None,
        "images": product_images,
        "variants": variants,
    }


# ============================================================
# Tool 2b: get_product_by_sku — 以 SKU 精準查貨況與商品圖
# ============================================================
@mcp.tool()
def get_product_by_sku(
    sku: str = Field(description="商品或變體的 SKU（完全相符）"),
) -> dict:
    """以 SKU 精準查詢單一商品的貨況（庫存、價格）與商品圖 URL。

    查特定貨品時最可靠的入口：由 Shopline 後端以 SKU 精準比對，
    不做本地模糊搜尋，因此不會因品名排版、& 符號或筆數上限而漏抓。

    【呼叫的 Shopline API】
    - GET /v1/products/search?sku={sku}
    """
    sku = resolve_field(sku)
    if not sku:
        return {"error": "sku is required"}

    products = fetch_all_pages("products_search", params={"sku": sku}, max_pages=5)

    if not products:
        return {"found": False, "sku": sku, "products": []}

    results = []
    for p in products:
        summary = _summarize_product(p)
        # 帶出該 SKU 對應的變體明細，方便直接看到貨況
        target = sku.strip().lower()
        summary["matched_variants"] = [
            _summarize_variant(v) for v in p.get("variations", [])
            if (v.get("sku") or "").strip().lower() == target
        ]
        results.append(summary)

    return {
        "found": True,
        "sku": sku,
        "total_found": len(results),
        "products": results,
    }


# ============================================================
# Tool 3: get_inventory_overview — 庫存總覽
# ============================================================
@mcp.tool()
def get_inventory_overview(
    brand: Optional[str] = Field(default=None, description="品牌篩選"),
) -> dict:
    """取得全商品庫存總覽：總庫存數量、庫存品項數、缺貨品項數等。從商品 variations 的 quantity 欄位計算。"""
    brand = resolve_field(brand)
    products = fetch_all_pages("products", max_pages=MAX_SCAN_PAGES)

    if brand:
        brand_lower = brand.lower()
        products = [p for p in products if brand_lower in (p.get("brand") or "").lower()]

    total_quantity = 0
    total_cost_value = 0.0
    total_skus = 0
    out_of_stock_skus = 0
    low_stock_skus = 0  # quantity <= 3

    brand_stats = defaultdict(lambda: {"quantity": 0, "skus": 0, "oos": 0})
    product_summary = []

    for p in products:
        title = get_translation(p.get("title_translations"))
        p_brand = p.get("brand") or "未設定"
        variations = p.get("variations", [])

        p_total_qty = 0
        p_sku_count = 0
        p_oos_count = 0

        for v in variations:
            qty = v.get("quantity", 0) or 0
            cost = money_to_float(v.get("cost"))

            total_skus += 1
            p_sku_count += 1
            p_total_qty += qty
            total_quantity += qty
            total_cost_value += cost * qty

            if qty == 0:
                out_of_stock_skus += 1
                p_oos_count += 1
            elif qty <= 3:
                low_stock_skus += 1

            brand_stats[p_brand]["quantity"] += qty
            brand_stats[p_brand]["skus"] += 1
            if qty == 0:
                brand_stats[p_brand]["oos"] += 1

        if not variations:
            qty = p.get("quantity", 0) or 0
            total_skus += 1
            p_sku_count = 1
            p_total_qty = qty
            total_quantity += qty
            if qty == 0:
                out_of_stock_skus += 1
                p_oos_count = 1

        product_summary.append({
            "title": title,
            "brand": p_brand,
            "total_quantity": p_total_qty,
            "sku_count": p_sku_count,
            "out_of_stock_skus": p_oos_count,
        })

    return {
        "total_products": len(products),
        "total_skus": total_skus,
        "total_quantity": total_quantity,
        "total_cost_value": round(total_cost_value, 2),
        "out_of_stock_skus": out_of_stock_skus,
        "low_stock_skus": low_stock_skus,
        "brand_breakdown": {
            k: v for k, v in sorted(brand_stats.items(), key=lambda x: -x[1]["quantity"])
        },
        "products": sorted(product_summary, key=lambda x: x["total_quantity"]),
    }


# ============================================================
# Tool 4: get_low_stock_alerts — 低庫存警示
# ============================================================
@mcp.tool()
def get_low_stock_alerts(
    threshold: int = Field(default=5, description="庫存低於此值即警示"),
) -> dict:
    """取得低庫存或缺貨的 SKU 清單，可自訂庫存門檻值。"""
    threshold = resolve_field(threshold)
    products = fetch_all_pages("products", max_pages=MAX_SCAN_PAGES)

    alerts = []
    for p in products:
        title = get_translation(p.get("title_translations"))
        for v in p.get("variations", []):
            qty = v.get("quantity", 0) or 0
            if qty <= threshold:
                color, size = _variant_fields(v)
                alerts.append({
                    "product_title": title,
                    "sku": v.get("sku"),
                    "color": color,
                    "size": size,
                    "quantity": qty,
                    "status": "缺貨" if qty == 0 else "低庫存",
                    "brand": p.get("brand"),
                })

    alerts.sort(key=lambda x: x["quantity"])

    return {
        "threshold": threshold,
        "total_alerts": len(alerts),
        "out_of_stock": len([a for a in alerts if a["quantity"] == 0]),
        "low_stock": len([a for a in alerts if a["quantity"] > 0]),
        "alerts": alerts,
    }


# ============================================================
# Tool 5: get_warehouses — 倉庫列表
# ============================================================
@mcp.tool()
def get_warehouses() -> dict:
    """取得所有倉庫/門市據點列表。"""
    data = api_get("warehouses", params={"per_page": 50})
    warehouses = data.get("items", [])

    return {
        "total": len(warehouses),
        "warehouses": [
            {
                "id": w.get("id"),
                "name": w.get("name"),
                "status": w.get("status"),
            }
            for w in warehouses
        ]
    }


# ============================================================
# Tool 6: get_stock_by_warehouse — 各倉庫 SKU 庫存
# ============================================================
@mcp.tool()
def get_stock_by_warehouse(
    product_id: Optional[str] = Field(default=None, description="商品 ID（不填則查詢全部商品，但較慢）"),
    warehouse_id: Optional[str] = Field(default=None, description="倉庫 ID 篩選（僅看特定倉庫）"),
    sku: Optional[str] = Field(default=None, description="以 SKU 精準定位商品後再查倉庫庫存（建議，快且不會漏）"),
    max_products: int = Field(default=50, description="未指定商品時最多掃描幾個商品（每個商品需一次 API 呼叫，故較慢）"),
) -> dict:
    """取得商品在各倉庫/門市的庫存分佈矩陣。可查詢單一商品或全部商品的各倉庫庫存。

    查特定貨品時請帶 sku 或 product_id；不帶條件的全掃描因為每個商品都要一次
    API 呼叫，會受 max_products 限制（回傳的 scan_truncated 會標示是否被截斷）。
    """
    product_id = resolve_field(product_id)
    warehouse_id = resolve_field(warehouse_id)
    sku = resolve_field(sku)
    max_products = resolve_field(max_products)

    # 取得倉庫名稱對照
    wh_data = api_get("warehouses", params={"per_page": 50})
    wh_map = {w["id"]: w.get("name", w["id"]) for w in wh_data.get("items", [])}

    scan_truncated = False

    # 帶 sku 時先用 server-side 精準查詢定位商品 ID
    if not product_id and sku:
        matched = fetch_all_pages("products_search", params={"sku": sku}, max_pages=5)
        if not matched:
            return {"error": f"找不到 SKU 為 {sku} 的商品", "products_queried": 0}
        target_ids = [p["id"] for p in matched if p.get("id")]
        if not target_ids:
            # 有比對到商品卻拿不到 ID：明確回報，不可靜默退回全店掃描
            return {"error": f"SKU {sku} 對應的商品缺少 ID，無法查詢庫存",
                    "products_queried": 0}
    elif product_id:
        target_ids = [product_id]
    else:
        target_ids = None

    if target_ids is not None:
        products_stocks = []
        for pid in target_ids:
            try:
                products_stocks.append(
                    api_get("product_stocks", path_params={"product_id": pid})
                )
            except Exception:
                continue
    else:
        # 全部商品（分頁取得商品列表，逐一查庫存）。
        # 每個商品都要一次額外 API 呼叫，所以只抓得到 max_products 所需的頁數，
        # 再用第 1 頁的 total_count 判斷是否被截斷，而不是白抓整個目錄。
        first_page = api_get("products", params={"per_page": 1, "page": 1})
        total_count = (first_page.get("pagination") or {}).get("total_count") or 0
        scan_truncated = total_count > max_products

        products = fetch_all_pages("products", max_pages=pages_for(max_products))
        products_stocks = []
        import time as _time
        for p in products[:max_products]:
            try:
                stock = api_get("product_stocks", path_params={"product_id": p["id"]})
                products_stocks.append(stock)
                _time.sleep(0.2)
            except Exception:
                continue

    # 彙總
    warehouse_totals = defaultdict(lambda: {"total_quantity": 0, "sku_count": 0, "oos_skus": 0})
    product_details = []

    for ps in products_stocks:
        title = get_translation(ps.get("title_translations"))
        pid = ps.get("id", "")

        for v in ps.get("variations", []):
            variant_sku = v.get("sku", "")
            color, size = _variant_fields(v)

            stocks = v.get("stocks", [])
            variant_detail = {
                "product_title": title,
                "product_id": pid,
                "sku": variant_sku,
                "color": color,
                "size": size,
                "warehouses": {},
            }

            for s in stocks:
                wid = s.get("warehouse_id", "")
                qty = s.get("quantity", 0)
                wname = wh_map.get(wid, wid)

                if warehouse_id and wid != warehouse_id:
                    continue

                variant_detail["warehouses"][wname] = qty
                warehouse_totals[wname]["total_quantity"] += qty
                warehouse_totals[wname]["sku_count"] += 1
                if qty == 0:
                    warehouse_totals[wname]["oos_skus"] += 1

            if variant_detail["warehouses"]:
                product_details.append(variant_detail)

    # 排序倉庫
    sorted_warehouses = sorted(warehouse_totals.items(), key=lambda x: -x[1]["total_quantity"])

    return {
        "products_queried": len(products_stocks),
        "scan_truncated": scan_truncated,
        "total_variants": len(product_details),
        "details_truncated": len(product_details) > 100,
        "warehouse_summary": {k: v for k, v in sorted_warehouses},
        "details": product_details[:100],  # 限制回傳筆數
    }


# ============================================================
# Tool 7: get_locked_inventory — 鎖定（預留）庫存查詢
# ============================================================
@mcp.tool()
def get_locked_inventory() -> dict:
    """
    【用途】
    取得目前被鎖定（預留）的庫存商品清單，協助分析哪些 SKU 有待出貨的預留數量。

    【呼叫的 Shopline API】
    - GET /v1/products（讀取 locked_inventory_count 欄位彙總）

    註：Shopline 並無 /v1/products/locked-inventory 端點，該路徑會被路由成
    /v1/products/{productId} 而回 422，故改由商品與變體的 locked_inventory_count 計算。

    【回傳結構】
    - total: 鎖定庫存的 SKU 總筆數
    - total_locked_quantity: 鎖定數量加總
    - products_scanned: 實際掃描的商品數
    - items: 每筆含 product_id、product_title、sku、color、size、locked_quantity
    """
    products = fetch_all_pages("products", max_pages=MAX_SCAN_PAGES)

    items = []
    for p in products:
        title = get_translation(p.get("title_translations"))
        variations = p.get("variations") or []

        for v in variations:
            locked = v.get("locked_inventory_count") or 0
            if locked:
                color, size = _variant_fields(v)
                items.append({
                    "product_id": p.get("id"),
                    "product_title": title,
                    "sku": v.get("sku"),
                    "color": color,
                    "size": size,
                    "locked_quantity": locked,
                })

        if not variations:
            locked = p.get("locked_inventory_count") or 0
            if locked:
                items.append({
                    "product_id": p.get("id"),
                    "product_title": title,
                    "sku": p.get("sku"),
                    "locked_quantity": locked,
                })

    items.sort(key=lambda x: -x["locked_quantity"])

    return {
        "total": len(items),
        "total_locked_quantity": sum(i["locked_quantity"] for i in items),
        "products_scanned": len(products),
        "items": items,
    }


# ============================================================
# Tool 8: list_purchase_orders — POS 採購單列表
# ============================================================
@mcp.tool()
def list_purchase_orders(
    max_results: int = Field(default=50, description="最多回傳筆數"),
) -> dict:
    """
    【用途】
    取得 POS 採購單列表，用於了解進貨狀況與採購歷史。

    【呼叫的 Shopline API】
    - GET /v1/pos/purchase_orders

    【回傳結構】
    - total_found: 查詢到的採購單總數
    - returned: 實際回傳筆數
    - purchase_orders: 每筆含 id、status、total、created_at
    """
    max_pages = max(1, (max_results + 49) // 50)
    orders = fetch_all_pages("purchase_orders", max_pages=max_pages)

    results = []
    for o in orders[:max_results]:
        results.append({
            "id": o.get("id"),
            "status": o.get("status"),
            "total": money_to_float(o.get("total")),
            "created_at": o.get("created_at"),
        })

    return {
        "total_found": len(orders),
        "returned": len(results),
        "purchase_orders": results,
    }


# ============================================================
# Tool 9: get_purchase_order_detail — POS 採購單明細
# ============================================================
@mcp.tool()
def get_purchase_order_detail(
    purchase_order_id: str = Field(description="採購單 ID"),
) -> dict:
    """
    【用途】
    取得單一 POS 採購單的完整明細，含採購品項、數量、金額等資訊。

    【呼叫的 Shopline API】
    - GET /v1/pos/purchase_orders/{purchase_order_id}

    【回傳結構】
    - id、status、created_at、total
    - items: 每筆含 product_title、sku、quantity、unit_cost
    """
    data = api_get("purchase_order_detail", path_params={"purchase_order_id": purchase_order_id})

    raw_items = data.get("items", []) if isinstance(data, dict) else []
    items = []
    for item in raw_items:
        items.append({
            "product_title": get_translation(item.get("title_translations")),
            "sku": item.get("sku"),
            "quantity": item.get("quantity", 0),
            "unit_cost": money_to_float(item.get("unit_cost")),
        })

    return {
        "id": data.get("id"),
        "status": data.get("status"),
        "created_at": data.get("created_at"),
        "total": money_to_float(data.get("total")),
        "items_count": len(items),
        "items": items,
    }
