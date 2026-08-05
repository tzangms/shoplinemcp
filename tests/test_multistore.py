import asyncio
import importlib
import os

import pytest


def test_get_headers_uses_contextvar_when_set(monkeypatch):
    settings = importlib.import_module("shopline_mcp.config.settings")
    monkeypatch.setattr(settings, "ACCESS_TOKEN", "envtoken")
    tok = settings.current_token.set("ctxtoken")
    try:
        h = settings.get_headers()
    finally:
        settings.current_token.reset(tok)
    assert h["Authorization"] == "Bearer ctxtoken"


def test_get_headers_falls_back_to_env(monkeypatch):
    settings = importlib.import_module("shopline_mcp.config.settings")
    monkeypatch.setattr(settings, "ACCESS_TOKEN", "envtoken")
    # 確保沒有 contextvar
    assert settings.current_token.get() is None
    h = settings.get_headers()
    assert h["Authorization"] == "Bearer envtoken"


def test_get_headers_raises_when_no_token(monkeypatch):
    settings = importlib.import_module("shopline_mcp.config.settings")
    monkeypatch.setattr(settings, "ACCESS_TOKEN", "")
    assert settings.current_token.get() is None
    with pytest.raises(RuntimeError):
        settings.get_headers()


def test_build_stores_legacy_pair(monkeypatch):
    import shopline_mcp.remote as remote
    monkeypatch.setenv("SHOPLINE_MCP_KEY", "keyA")
    monkeypatch.setenv("SHOPLINE_API_TOKEN", "tokA")
    # 清掉可能存在的多店變數
    for k in list(os.environ):
        if k.startswith("SHOPLINE_STORE_"):
            monkeypatch.delenv(k, raising=False)
    stores = remote.build_stores()
    assert stores == {"keyA": "tokA"}


def test_build_stores_paired_env(monkeypatch):
    import shopline_mcp.remote as remote
    monkeypatch.delenv("SHOPLINE_MCP_KEY", raising=False)
    for k in list(os.environ):
        if k.startswith("SHOPLINE_STORE_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SHOPLINE_STORE_B_KEY", "keyB")
    monkeypatch.setenv("SHOPLINE_STORE_B_TOKEN", "tokB")
    stores = remote.build_stores()
    assert stores["keyB"] == "tokB"


def test_build_stores_missing_token_raises(monkeypatch):
    import shopline_mcp.remote as remote
    monkeypatch.delenv("SHOPLINE_MCP_KEY", raising=False)
    monkeypatch.setenv("SHOPLINE_STORE_C_KEY", "keyC")
    monkeypatch.delenv("SHOPLINE_STORE_C_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="SHOPLINE_STORE_C_TOKEN"):
        remote.build_stores()


def test_build_stores_unsafe_key_raises(monkeypatch):
    import shopline_mcp.remote as remote
    monkeypatch.delenv("SHOPLINE_MCP_KEY", raising=False)
    monkeypatch.setenv("SHOPLINE_STORE_D_KEY", "bad/key")
    monkeypatch.setenv("SHOPLINE_STORE_D_TOKEN", "tokD")
    with pytest.raises(RuntimeError):
        remote.build_stores()


def test_build_stores_duplicate_key_raises(monkeypatch):
    import shopline_mcp.remote as remote
    monkeypatch.setenv("SHOPLINE_MCP_KEY", "dup")
    monkeypatch.setenv("SHOPLINE_API_TOKEN", "t1")
    monkeypatch.setenv("SHOPLINE_STORE_E_KEY", "dup")
    monkeypatch.setenv("SHOPLINE_STORE_E_TOKEN", "t2")
    with pytest.raises(RuntimeError):
        remote.build_stores()


def _run_mw(mw, path):
    sent = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(msg):
        sent.append(msg)
    seen = {}
    async def inner(scope, r, s):
        seen["token"] = __import__("shopline_mcp.config.settings", fromlist=["current_token"]).current_token.get()
        seen["path"] = scope["path"]
        await s({"type": "http.response.start", "status": 200, "headers": []})
        await s({"type": "http.response.body", "body": b"ok"})
    mw.app = inner
    asyncio.run(mw({"type": "http", "path": path}, receive, send))
    return sent, seen


def test_middleware_unknown_key_404():
    import shopline_mcp.remote as remote
    mw = remote.MultiStoreKeyMiddleware(app=None, stores={"good": "tok"})
    sent, _ = _run_mw(mw, "/bad/mcp")
    assert sent[0]["status"] == 404


def test_middleware_known_key_sets_token_and_rewrites():
    import shopline_mcp.remote as remote
    mw = remote.MultiStoreKeyMiddleware(app=None, stores={"good": "tok-good"})
    sent, seen = _run_mw(mw, "/good/mcp")
    assert sent[0]["status"] == 200
    assert seen["token"] == "tok-good"
    assert seen["path"] == "/mcp"


def test_build_stores_empty_raises(monkeypatch):
    import shopline_mcp.remote as remote
    monkeypatch.delenv("SHOPLINE_MCP_KEY", raising=False)
    for k in list(os.environ):
        if k.startswith("SHOPLINE_STORE_"):
            monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError):
        remote.build_stores()


def test_main_default_disables_dns_rebinding(monkeypatch):
    import shopline_mcp.remote as remote
    from shopline_mcp.app import mcp

    monkeypatch.setenv("SHOPLINE_MCP_KEY", "k")
    monkeypatch.setenv("SHOPLINE_API_TOKEN", "t")
    monkeypatch.delenv("SHOPLINE_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("PORT", "8080")

    captured = {}

    def fake_run(app, host=None, port=None, **kwargs):
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(remote.uvicorn, "run", fake_run)

    remote.main()

    assert mcp.settings.streamable_http_path == "/mcp"
    assert mcp.settings.transport_security.enable_dns_rebinding_protection is False
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 8080


def test_main_allowed_hosts_enables_whitelist(monkeypatch):
    import shopline_mcp.remote as remote
    from shopline_mcp.app import mcp

    monkeypatch.setenv("SHOPLINE_MCP_KEY", "k")
    monkeypatch.setenv("SHOPLINE_API_TOKEN", "t")
    monkeypatch.setenv("SHOPLINE_ALLOWED_HOSTS", "example.com")
    monkeypatch.setenv("PORT", "8080")

    def fake_run(app, host=None, port=None, **kwargs):
        pass

    monkeypatch.setattr(remote.uvicorn, "run", fake_run)

    remote.main()

    assert "example.com" in mcp.settings.transport_security.allowed_hosts
