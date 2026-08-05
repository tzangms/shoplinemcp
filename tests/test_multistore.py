import importlib

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
