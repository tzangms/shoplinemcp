"""shopline MCP 的 Cloudflare Python Worker 進入點（stateless streamable-http，多店）。

與 shopline_mcp/remote.py（Zeabur，uvicorn 長駐）共用同一組 @mcp.tool() 工具與
多店 middleware；Workers 每個 request 跑一次，所以改用 stateless + JSON 回應。

Secrets（wrangler secret put）：
    SHOPLINE_STORE_<label>_KEY / _TOKEN   多店 pair（可多組）
    SHOPLINE_MCP_KEY / SHOPLINE_API_TOKEN 舊單店 pair（仍支援）
"""
import os
import sys
import types

# remote.py 頂層 import uvicorn（只有 main() 用到）；Pyodide 沒有 uvicorn，塞空 stub 讓它能 import
sys.modules.setdefault("uvicorn", types.ModuleType("uvicorn"))

from js import Object  # noqa: E402
from workers import WorkerEntrypoint, Response  # noqa: E402
import asgi  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Route  # noqa: E402
from mcp.server.fastmcp.server import StreamableHTTPASGIApp  # noqa: E402
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

import shopline_mcp.server  # noqa: E402,F401  # 觸發所有 @mcp.tool() 註冊
from shopline_mcp.app import mcp  # noqa: E402
from shopline_mcp.remote import MultiStoreKeyMiddleware, build_stores  # noqa: E402

_stores: dict[str, str] | None = None


def _load_stores(env) -> dict[str, str]:
    """把 Worker secrets 灌進 os.environ 後用 remote.build_stores() 建店家對應表。

    env 在同一個 isolate 內不變（改 secret 會換新版本、新 isolate），所以只建一次。
    """
    global _stores
    if _stores is None:
        # self.env 是 _EnvWrapper，本身列不出 key；要對底層 JS env 物件取 Object.keys
        for name in Object.keys(env._env):
            if name.startswith("SHOPLINE_"):
                os.environ[name] = str(getattr(env, name))
        _stores = build_stores()
    return _stores


def _build_app(stores: dict[str, str]) -> MultiStoreKeyMiddleware:
    # session manager 的 run() 每個 instance 只能跑一次，而 Workers 的 asgi adapter
    # 每個 request 都跑一輪 lifespan，所以每個 request 建一個 stateless manager。
    mgr = StreamableHTTPSessionManager(
        app=mcp._mcp_server,
        stateless=True,
        json_response=True,
        # 存取控制靠 URL 密鑰；Host 是 workers.dev 網域，關掉針對本機的 DNS-rebinding 防護
        security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    inner = Starlette(
        routes=[Route("/mcp", endpoint=StreamableHTTPASGIApp(mgr))],
        lifespan=lambda app: mgr.run(),
    )
    return MultiStoreKeyMiddleware(inner, stores)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        try:
            stores = _load_stores(self.env)
        except RuntimeError as e:
            return Response(str(e), status=500)
        return await asgi.fetch(_build_app(stores), request.js_object, self.env)
