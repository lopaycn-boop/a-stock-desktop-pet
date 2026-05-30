"""Tests for version module."""

from potato.version import __version__, __author__, BUILD, FEATURES


def test_version_format():
    assert isinstance(__version__, str)
    parts = __version__.split(".")
    assert len(parts) == 3
    for p in parts:
        assert p.isdigit()


def test_author():
    assert __author__ == "自由的风"


def test_build_format():
    assert isinstance(BUILD, str)
    assert len(BUILD) == 8  # YYYYMMDD


def test_features_list():
    assert isinstance(FEATURES, list)
    assert len(FEATURES) > 15
    assert "live2d" in FEATURES
    assert "ai_chat" in FEATURES
    assert "5layer_llm" in FEATURES
    assert "auto_trading" in FEATURES
    assert "eastmoney_ai" in FEATURES
    assert "iwencai" in FEATURES
    assert "plan_execute" in FEATURES
    assert "demo_mode" in FEATURES
    assert "risk_control" in FEATURES
    assert "vault_encryption" in FEATURES
    assert "settings_backup" in FEATURES
    assert "perf_monitor" in FEATURES
    assert "crash_auto_restart" in FEATURES
    assert "code_block_rendering" in FEATURES
    assert "inline_code_rendering" in FEATURES