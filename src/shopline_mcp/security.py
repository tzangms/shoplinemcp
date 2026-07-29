"""寫入操作的二階段確認機制 — 供遠端（HTTP）部署使用。

為什麼需要這個：
MCP 協議本身沒有「請使用者確認」的機制。本機 stdio 模式下擋在前面的是
Claude Desktop / Claude Code 的權限提示，那是「客戶端」行為，伺服器管不到。
一旦部署成遠端 HTTP endpoint，客戶端若未設定權限提示，寫入操作（改庫存、
改價格、建立/取消訂單）就會直接對正式商店生效。

因此改由伺服器端強制兩段式確認：
1. 第一次呼叫寫入 tool → 不執行，回傳「即將執行什麼」與一個 confirm_token
2. 帶著同一個 confirm_token 再呼叫一次 → 才真的執行

confirm_token 以 HMAC 綁定「工具名稱 + 完整參數」，因此無法拿低風險操作換來的
token 去執行高風險操作，也無法竄改參數。token 為無狀態（自帶到期時間），
多副本部署不需共用儲存空間。
"""

import hashlib
import hmac
import inspect
import json
import time

# 呼叫這些即代表會改動 Shopline 資料
WRITE_API_CALLS = ("api_post", "api_put", "api_patch", "api_delete")

CONFIRM_TTL_SECONDS = 300  # confirm_token 有效期限
_CONFIRM_ARG = "confirm_token"


def is_write_tool(fn) -> bool:
    """判斷 tool 是否會改動資料。

    以「函式原始碼中是否呼叫寫入 API」為準，不靠名稱前綴猜測 ——
    命名前綴曾經漏掉 execute_ / adjust_ 這類寫入操作。
    tools/writes/ 底下一律視為寫入。
    """
    module = getattr(fn, "__module__", "") or ""
    if ".tools.writes." in module:
        return True
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        # 取不到原始碼時保守視為寫入，寧可多要一次確認
        return True
    return any(f"{call}(" in source for call in WRITE_API_CALLS)


def _canonical(tool_name: str, arguments: dict) -> str:
    """把工具名稱與參數正規化成穩定字串，作為簽章來源"""
    payload = {"tool": tool_name, "args": arguments or {}}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def issue_token(secret: str, tool_name: str, arguments: dict, now: float | None = None) -> str:
    """簽發綁定該次呼叫內容的確認碼"""
    expires = int((now if now is not None else time.time()) + CONFIRM_TTL_SECONDS)
    body = f"{expires}.{_canonical(tool_name, arguments)}"
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{expires}.{sig}"


def verify_token(secret: str, token: str, tool_name: str, arguments: dict,
                 now: float | None = None) -> tuple[bool, str]:
    """驗證確認碼。回傳 (是否有效, 失敗原因)"""
    if not token or "." not in token:
        return False, "confirm_token 格式錯誤"

    expires_raw, _, sig = token.partition(".")
    try:
        expires = int(expires_raw)
    except ValueError:
        return False, "confirm_token 格式錯誤"

    current = now if now is not None else time.time()
    if current > expires:
        return False, "confirm_token 已過期，請重新取得"

    body = f"{expires}.{_canonical(tool_name, arguments)}"
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        return False, "confirm_token 與本次呼叫的工具或參數不符，請重新取得"

    return True, ""


def confirmation_required_response(tool_name: str, arguments: dict, token: str) -> dict:
    """尚未確認時回給呼叫端的內容 —— 說明將要發生什麼，並附上確認碼"""
    return {
        "requires_confirmation": True,
        "action": tool_name,
        "arguments": arguments,
        "message": (
            f"「{tool_name}」會變更 Shopline 正式商店的資料，尚未執行。"
            "請向使用者確認上述 arguments 無誤後，帶著相同參數與下方 confirm_token "
            "再呼叫一次即可執行。"
        ),
        "confirm_token": token,
        "expires_in_seconds": CONFIRM_TTL_SECONDS,
    }


def install_write_confirmation(mcp, secret: str) -> int:
    """在 ToolManager 上加裝二階段確認。回傳受保護的 tool 數量。

    包住 ToolManager.call_tool（所有工具呼叫的唯一收斂點），
    因此無法繞過，也不需逐一修改 68 個寫入函式。
    同時在 list_tools 為寫入工具的 schema 補上 confirm_token 參數，
    呼叫端才知道有這個欄位可帶。
    """
    manager = mcp._tool_manager
    protected = {
        name for name, tool in manager._tools.items() if is_write_tool(tool.fn)
    }

    original_call = manager.call_tool
    original_list = manager.list_tools

    async def guarded_call_tool(name, arguments, *args, **kwargs):
        if name not in protected:
            return await original_call(name, arguments, *args, **kwargs)

        arguments = dict(arguments or {})
        token = arguments.pop(_CONFIRM_ARG, None)

        if not token:
            new_token = issue_token(secret, name, arguments)
            return confirmation_required_response(name, arguments, new_token)

        ok, reason = verify_token(secret, token, name, arguments)
        if not ok:
            return {
                "error": reason,
                "action": name,
                "hint": "先不帶 confirm_token 呼叫一次以取得新的確認碼。",
            }

        return await original_call(name, arguments, *args, **kwargs)

    def guarded_list_tools():
        tools = original_list()
        for tool in tools:
            if tool.name not in protected:
                continue
            params = tool.parameters
            props = params.setdefault("properties", {})
            props.setdefault(_CONFIRM_ARG, {
                "type": "string",
                "title": "Confirm Token",
                "description": (
                    "二階段確認碼。第一次呼叫請留空，工具會回傳將要執行的內容與 "
                    "confirm_token；向使用者確認後，帶同一組參數與此確認碼再呼叫一次才會執行。"
                ),
            })
        return tools

    manager.call_tool = guarded_call_tool
    manager.list_tools = guarded_list_tools
    return len(protected)
