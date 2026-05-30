"""Tests for the /verify endpoint and potato.verify module."""

import pytest


def test_verify_module_import():
    from potato.verify import verify
    from potato.version import __version__, __author__, BUILD, FEATURES
    assert __version__ == "1.6.0"
    assert __author__ == "自由的风"
    assert BUILD == "20250530"
    assert len(FEATURES) == 42


def test_verify_module_runs():
    from potato.verify import verify
    result = verify()
    assert result is True


def test_verify_endpoint_registered():
    from desktop_pet.backend.main import app
    routes = [r.path for r in app.routes]
    assert "/verify" in routes


def test_verify_endpoint_logic():
    from potato.verify import verify as _verify
    ok = _verify()
    assert ok is True


def test_health_endpoint_includes_demo_mode():
    from desktop_pet.backend.main import health
    response = health()
    data = response.body if hasattr(response, 'body') else response
    if isinstance(data, bytes):
        import json
        data = json.loads(data)
    assert "data_sources" in data or "demo_mode" in str(data)


def test_version_endpoint_logic():
    from desktop_pet.backend.main import version
    response = version()
    data = response.body if hasattr(response, 'body') else response
    if isinstance(data, bytes):
        import json
        data = json.loads(data)
    assert data.get("version") == "1.6.0" or "1.6.0" in str(data)