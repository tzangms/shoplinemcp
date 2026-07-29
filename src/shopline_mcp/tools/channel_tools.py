"""
渠道 Tools — 銷售渠道資訊查詢
"""

from typing import Optional
from pydantic import Field

from shopline_mcp.app import mcp
from shopline_mcp.tools.base_tool import (
    api_get, get_translation, resolve_field, fetch_across_platforms
)

# Shopline /v1/channels 要求必須帶 platform（或 platforms），未帶會回 422
DEFAULT_CHANNEL_PLATFORMS = ["shopline", "shopline_pos"]


@mcp.tool()
def list_channels(
    platform: Optional[str] = Field(
        default=None,
        description="平台篩選，如 shopline / shopline_pos。不填則自動查詢常見平台並合併結果",
    ),
) -> dict:
    """取得商店所有銷售渠道清單。

    【用途】
    查看商店目前開啟的銷售渠道，例如線上商店、POS、
    Facebook、Instagram 等。適合了解多渠道銷售佈局，
    或做渠道業績分析前的渠道資料確認。

    注意：此端點在部分 token 權限下可能回傳 403，
    渠道資訊亦可從訂單的 channel.created_by_channel_name
    欄位取得。

    【呼叫的 Shopline API】
    - GET /v1/channels?platform={platform}

    【回傳結構】
    dict 含 total, platforms_queried[], platforms_failed[], channels[]。
    每個 channel 包含 id, name, channel_type, platform, enabled, created_at 等。
    platforms_failed 非空代表部分平台查詢失敗，此時 channels 不完整
    （勿將空結果直接解讀為「沒有渠道」）。
    """
    platform = resolve_field(platform)
    platforms = [platform] if platform else DEFAULT_CHANNEL_PLATFORMS

    items, failed, queried = fetch_across_platforms(
        "channels", platforms, paginated=False
    )

    results = []
    for c in items:
        results.append({
            "id": c.get("id"),
            "name": get_translation(c.get("name_translations")) or c.get("name"),
            "channel_type": c.get("channel_type"),
            "platform": c.get("platform"),
            "enabled": c.get("enabled"),
            "created_at": c.get("created_at"),
        })

    return {
        "total": len(results),
        "platforms_queried": queried,
        "platforms_failed": failed,
        "channels": results,
    }


@mcp.tool()
def get_channel_detail(channel_id: str) -> dict:
    """取得指定銷售渠道的詳細資訊。

    【用途】
    查詢單一銷售渠道的完整設定，包含渠道類型、狀態、
    連結設定等。適合確認特定渠道的詳細配置。

    注意：此端點在部分 token 權限下可能回傳 403 或 422。

    【呼叫的 Shopline API】
    - GET /v1/channels/{channel_id}

    【回傳結構】
    dict 含渠道詳細欄位：id, name, channel_type, enabled,
    created_at, updated_at 等。
    """
    data = api_get("channel_detail", path_params={"channel_id": channel_id})
    c = data.get("channel", data) if isinstance(data, dict) else {}

    return {
        "id": c.get("id"),
        "name": get_translation(c.get("name_translations")) or c.get("name"),
        "channel_type": c.get("channel_type"),
        "enabled": c.get("enabled"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
    }
