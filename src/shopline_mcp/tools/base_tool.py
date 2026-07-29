"""
Shopline API 基底工具 — 認證、分頁、錯誤處理共用邏輯
"""
import requests
import time
from pydantic.fields import FieldInfo
from shopline_mcp.config.settings import get_headers, get_url, DEFAULT_PER_PAGE


def resolve_field(value):
    """解決直接呼叫 @mcp.tool() 函數時 Field(default=...) 回傳 FieldInfo 的問題。
    MCP 協議呼叫會經過 pydantic 驗證自動解析，但測試時直接呼叫函數則不會。"""
    if isinstance(value, FieldInfo):
        return value.default
    return value


# 「掃全部」類查詢的安全上限（頁數）。DEFAULT_PER_PAGE=50 時約等於 10,000 筆。
# 用意是防止大店翻頁失控，而非業務上的筆數限制 —— 切勿降到足以截斷正常資料的值。
MAX_SCAN_PAGES = 200


class ShoplineAPIError(Exception):
    def __init__(self, status_code, message, endpoint=""):
        self.status_code = status_code
        self.message = message
        self.endpoint = endpoint
        super().__init__(f"[{status_code}] {endpoint}: {message}")


def _api_request(method, endpoint_key, json_body=None, params=None,
                 path_params=None, retries=3, retry_on_client_error=True):
    """
    內部共用 HTTP 請求函數。不直接由 tool 呼叫。

    retry_on_client_error:
      - True (GET): 任何非 200 都重試（保持既有行為）
      - False (POST/PUT/PATCH/DELETE): 4xx 直接拋錯不重試，僅 5xx/網路層重試
    """
    path_params = path_params or {}
    url = get_url(endpoint_key, **path_params)
    headers = get_headers()

    for attempt in range(retries):
        try:
            resp = requests.request(
                method, url, headers=headers, params=params,
                json=json_body, timeout=60
            )
            if resp.status_code in (200, 201):
                return resp.json()
            if resp.status_code == 204:
                return {}  # No Content（常見於 DELETE 回應）

            is_client_error = 400 <= resp.status_code < 500
            is_server_error = resp.status_code >= 500

            if is_client_error and not retry_on_client_error:
                raise ShoplineAPIError(resp.status_code, resp.text[:500], url)

            if is_server_error or (is_client_error and retry_on_client_error):
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise ShoplineAPIError(resp.status_code, resp.text[:500], url)

            # 其他非預期狀態碼
            raise ShoplineAPIError(resp.status_code, resp.text[:500], url)

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise


def api_get(endpoint_key, params=None, path_params=None, retries=3):
    """發送 GET 請求到 Shopline API，回傳 JSON。含自動重試。"""
    return _api_request("GET", endpoint_key, params=params,
                        path_params=path_params, retries=retries,
                        retry_on_client_error=True)


def api_post(endpoint_key, json_body=None, params=None, path_params=None, retries=3):
    """發送 POST 請求到 Shopline API。4xx 不重試。"""
    return _api_request("POST", endpoint_key, json_body=json_body,
                        params=params, path_params=path_params, retries=retries,
                        retry_on_client_error=False)


def api_put(endpoint_key, json_body=None, params=None, path_params=None, retries=3):
    """發送 PUT 請求到 Shopline API。4xx 不重試。"""
    return _api_request("PUT", endpoint_key, json_body=json_body,
                        params=params, path_params=path_params, retries=retries,
                        retry_on_client_error=False)


def api_patch(endpoint_key, json_body=None, params=None, path_params=None, retries=3):
    """發送 PATCH 請求到 Shopline API。4xx 不重試。"""
    return _api_request("PATCH", endpoint_key, json_body=json_body,
                        params=params, path_params=path_params, retries=retries,
                        retry_on_client_error=False)


def api_delete(endpoint_key, params=None, path_params=None, retries=3):
    """發送 DELETE 請求到 Shopline API。4xx 不重試。"""
    return _api_request("DELETE", endpoint_key, params=params,
                        path_params=path_params, retries=retries,
                        retry_on_client_error=False)


def fetch_all_pages(endpoint_key, params=None, path_params=None, max_pages=None):
    """自動分頁遍歷，回傳所有 items"""
    items, _total = fetch_pages_with_total(endpoint_key, params, path_params, max_pages)
    return items


def fetch_pages_with_total(endpoint_key, params=None, path_params=None, max_pages=None):
    """同 fetch_all_pages，但額外回傳 API 回報的 total_count。

    當 max_pages 會截斷結果時，呼叫端需要真實總數才能正確標示 truncated —
    只比較「抓回筆數」與「回傳筆數」會在剛好抓滿上限時誤判為未截斷。
    回傳 (items, total_count)；API 未提供 total_count 時為 None。
    """
    params = dict(params or {})
    params.setdefault("per_page", DEFAULT_PER_PAGE)
    # orders_search 不支援 sort_by 參數
    if "search" not in endpoint_key:
        params.setdefault("sort_by", "desc")

    all_items = []
    total_count = None
    page = 1

    while True:
        if max_pages and page > max_pages:
            break

        params["page"] = page
        data = api_get(endpoint_key, params=params, path_params=path_params)

        items = data.get("items", [])
        all_items.extend(items)

        pagination = data.get("pagination", {})
        if total_count is None:
            total_count = pagination.get("total_count")
        total_pages = pagination.get("total_pages", 1)

        if page >= total_pages:
            break

        page += 1
        time.sleep(0.2)  # Rate limit 保護

    return all_items, total_count


def pages_for(max_items):
    """由需要的筆數反推頁數，取代寫死的 max_pages（原本等於硬性筆數上限）"""
    return max(1, (max_items + DEFAULT_PER_PAGE - 1) // DEFAULT_PER_PAGE)


def fetch_across_platforms(endpoint_key, platforms, params=None, max_pages=None,
                           paginated=True, max_items=None):
    """對「必須帶 platform 參數」的端點（如 channels / conversations）逐一查詢並合併。

    Shopline 部分端點未帶 platform 會直接回 422，且無「查全部」的寫法，
    因此只能逐一查詢再合併。

    回傳 (items, failed_platforms, queried_platforms)。呼叫端應將 failed_platforms
    一併回報，否則全部平台失敗時會回傳空清單，與「真的沒有資料」無法區分；
    queried_platforms 只含實際查詢過的平台 —— 額度用完提早結束時，未查詢的平台
    不可列為已查詢，否則會被誤讀成「該平台沒有資料」。
    """
    items = []
    failed = []
    queried = []

    for plat in platforms:
        if max_items is not None and len(items) >= max_items:
            break
        queried.append(plat)

        call_params = dict(params or {})
        call_params["platform"] = plat

        # 依剩餘額度取頁數，避免每個平台各抓滿一份再丟掉
        if max_items is not None:
            remaining = max_items - len(items)
            page_cap = min(max_pages, pages_for(remaining)) if max_pages else pages_for(remaining)
        else:
            page_cap = max_pages

        try:
            if paginated:
                batch = fetch_all_pages(endpoint_key, params=call_params, max_pages=page_cap)
            else:
                data = api_get(endpoint_key, params=call_params)
                batch = data.get("items", []) if isinstance(data, dict) else []
        except Exception as e:
            failed.append({"platform": plat, "error": str(e)[:200]})
            continue

        for item in batch:
            if isinstance(item, dict):
                item.setdefault("platform", plat)
            items.append(item)

    return items, failed, queried


def fetch_all_pages_by_date_segments(endpoint_key, start_date, end_date, params=None):
    """
    對於超過 10,000 筆的查詢，用日期分段拉取。
    start_date / end_date 格式: "YYYY-MM-DDTHH:MM:SSZ"
    """
    from datetime import datetime, timedelta

    params = dict(params or {})
    all_items = []

    start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    segment_days = 30

    current = start
    while current < end:
        seg_end = min(current + timedelta(days=segment_days), end)
        params["created_after"] = current.strftime("%Y-%m-%dT%H:%M:%SZ")
        params["created_before"] = seg_end.strftime("%Y-%m-%dT%H:%M:%SZ")

        items = fetch_all_pages(endpoint_key, params=params)
        all_items.extend(items)

        current = seg_end

    return all_items


def money_to_float(money_obj):
    """將 Shopline 金額物件轉為 float，例如 {"cents": 2720, "dollars": 2720.0} → 2720.0"""
    if not money_obj:
        return 0.0
    return float(money_obj.get("dollars", 0) or 0)


def extract_image_urls(obj, limit=10):
    """從 Shopline 商品/變體物件取出圖片 URL 清單。

    Shopline 各 endpoint 的圖片欄位形態不一致（media / images / image），
    且每個 media item 可能是 {"images": {"original": {"url": ...}}} 或直接帶 url，
    因此這裡採容錯解析：任何形態都盡量取到 original（退而求其次取第一個有 url 的尺寸）。
    """
    if not obj:
        return []

    def _url_from_media_item(item):
        if isinstance(item, str):
            return item
        if not isinstance(item, dict):
            return None
        # {"images": {"original": {"url": ...}, "large": {...}}}
        images = item.get("images")
        if isinstance(images, dict):
            original = images.get("original")
            if isinstance(original, dict) and original.get("url"):
                return original["url"]
            for size in images.values():
                if isinstance(size, dict) and size.get("url"):
                    return size["url"]
                if isinstance(size, str) and size:
                    return size
        # {"url": ...} 或 {"original": {"url": ...}}
        if item.get("url"):
            return item["url"]
        original = item.get("original")
        if isinstance(original, dict) and original.get("url"):
            return original["url"]
        if isinstance(original, str) and original:
            return original
        return None

    urls = []
    # Shopline 商品主圖為 medias（複數），變體為 media（單數），
    # 分類為 banner_medias；image_url 為部分端點的扁平字串欄位。
    for key in ("medias", "media", "banner_medias", "images", "image",
                "image_url", "photos", "detail_medias"):
        value = obj.get(key)
        if not value:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            url = _url_from_media_item(item)
            if url and url not in urls:
                urls.append(url)
        if urls:
            break

    return urls[:limit]


def get_translation(obj, lang="zh-hant", fallback="en"):
    """取得翻譯文字"""
    if not obj:
        return ""
    if isinstance(obj, str):
        return obj
    return obj.get(lang, obj.get(fallback, ""))
