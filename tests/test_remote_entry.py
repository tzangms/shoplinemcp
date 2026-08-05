import importlib

import pytest


def test_main_requires_key(monkeypatch):
    monkeypatch.delenv("SHOPLINE_MCP_KEY", raising=False)
    remote = importlib.import_module("shopline_mcp.remote")
    with pytest.raises(RuntimeError, match="SHOPLINE_MCP_KEY"):
        remote.main()


def test_importing_remote_does_not_start_stdio(monkeypatch):
    # import 不得啟動任何 server（mcp.run 只能在 main() 內呼叫）。
    # 先 patch 掉 mcp.run 再 reload 模組，確認 import 過程從未呼叫 run。
    from shopline_mcp.app import mcp

    called = {}
    monkeypatch.setattr(mcp, "run", lambda *a, **k: called.setdefault("run", True))
    importlib.reload(importlib.import_module("shopline_mcp.remote"))
    assert "run" not in called


def test_main_rejects_unsafe_key_characters(monkeypatch):
    monkeypatch.setenv("SHOPLINE_MCP_KEY", "bad/key")
    remote = importlib.import_module("shopline_mcp.remote")
    with pytest.raises(RuntimeError, match="SHOPLINE_MCP_KEY"):
        remote.main()


def test_main_configures_key_path_and_runs(monkeypatch):
    monkeypatch.setenv("SHOPLINE_MCP_KEY", "secret123")
    monkeypatch.setenv("PORT", "9000")
    remote = importlib.import_module("shopline_mcp.remote")
    from shopline_mcp.app import mcp

    captured = {}
    monkeypatch.setattr(mcp, "run", lambda *a, **k: captured.update(args=a, kwargs=k))
    remote.main()

    assert mcp.settings.host == "0.0.0.0"
    assert mcp.settings.port == 9000
    assert mcp.settings.streamable_http_path == "/secret123/mcp"
    # transport 以 streamable-http 呼叫
    assert captured["args"] == ("streamable-http",)
