"""
客戶群組 Tools — 客戶分群列表、成員查詢
"""

from typing import Optional
from pydantic import Field

from shopline_mcp.app import mcp
from shopline_mcp.tools.base_tool import (
    api_get, fetch_all_pages, resolve_field, pages_for
)


@mcp.tool()
def list_customer_groups(
    search_keyword: Optional[str] = Field(default=None, description="群組名稱搜尋關鍵字"),
    max_results: int = Field(default=50, description="最多回傳筆數"),
) -> dict:
    """取得客戶群組列表，支援依名稱搜尋。

    【用途】
    瀏覽或搜尋已建立的客戶群組（分群）。可用於確認客戶標籤分群策略、
    取得群組 ID 後進一步查詢群組成員。

    【呼叫的 Shopline API】
    - GET /v1/customer_groups（無搜尋條件時）
    - GET /v1/customer_groups/search（有搜尋條件時）

    【回傳結構】
    dict 含 total_found, returned, groups[]。
    每個 group 包含 id, name, customers_count, created_at。
    """
    search_keyword = resolve_field(search_keyword)
    if search_keyword:
        params = {"keyword": search_keyword, "per_page": min(max_results, 50)}
        data = api_get("customer_groups_search", params=params)
        groups = data.get("items", [])
    else:
        groups = fetch_all_pages("customer_groups", max_pages=pages_for(max_results))

    results = []
    for g in groups[:max_results]:
        results.append({
            "id": g.get("id"),
            "name": g.get("name"),
            "customers_count": g.get("customers_count", 0),
            "created_at": g.get("created_at"),
            "updated_at": g.get("updated_at"),
        })

    return {
        "total_found": len(groups),
        "returned": len(results),
        "groups": results,
    }


@mcp.tool()
def get_customer_group_members(
    group_id: str = Field(description="客戶群組 ID（由 list_customer_groups 回傳）"),
) -> dict:
    """取得指定客戶群組中的所有客戶 ID 列表。

    【重要限制】
    Shopline Open API v1 目前並未提供查詢群組成員的方式：
    - /v1/customer_groups/{group_id}/customers 回 404（端點不存在）
    - /v1/customers?customer_group_id=... 等篩選參數會被 API 忽略，
      回傳的是「全店客戶」而非群組成員。

    因此本 tool 一律回傳明確錯誤，而不是回傳會被誤認為群組成員的全店名單。
    如需群組名單，請由 Shopline 後台匯出。

    【回傳結構】
    dict 含 error, group_id, supported_alternative。
    """
    group_id = resolve_field(group_id)

    return {
        "error": (
            "Shopline Open API v1 不支援查詢客戶群組成員："
            "群組成員端點不存在，且 customers API 的群組篩選參數無效（會回傳全店客戶）。"
            "請改由 Shopline 後台匯出群組名單。"
        ),
        "group_id": group_id,
        "supported_alternative": "list_customer_groups 可取得群組清單與各群組的基本資訊",
    }
