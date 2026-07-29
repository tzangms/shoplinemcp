"""遠端部署用的 Bearer token 認證中介層。

stdio 模式跑在使用者自己機器上，作業系統就是信任邊界；
一旦改成公開的 HTTP endpoint，任何知道網址的人都能操作商店資料，
因此認證是必要條件而非選配 —— 未設定金鑰時伺服器會拒絕啟動。
"""

import hmac

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# 不需認證即可存取的路徑（健康檢查用，不含任何商店資料）
PUBLIC_PATHS = ("/healthz",)


class BearerAuthMiddleware:
    """檢查 Authorization: Bearer <token>。

    以 hmac.compare_digest 比對，避免以回應時間差推測金鑰。
    """

    def __init__(self, app: ASGIApp, token: str):
        if not token:
            raise ValueError("BearerAuthMiddleware 需要非空的 token")
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("path") in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        scheme, _, provided = auth.partition(" ")

        if scheme.lower() != "bearer" or not hmac.compare_digest(provided.strip(), self.token):
            response = JSONResponse(
                {"error": "unauthorized",
                 "detail": "需要有效的 Authorization: Bearer <token> 標頭"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
