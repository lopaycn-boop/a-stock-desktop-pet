"""Tests for TrendRadar plugin module."""

import pytest
from unittest.mock import patch, MagicMock


def test_import_trendradar():
    from potato.trendradar import trending, search, sentiment_summary
    assert callable(trending)
    assert callable(search)
    assert callable(sentiment_summary)


def test_platform_map():
    from potato.trendradar import _PLATFORM_MAP
    assert "weibo" in _PLATFORM_MAP
    assert "baidu" in _PLATFORM_MAP
    assert "zhihu" in _PLATFORM_MAP
    assert "eastmoney" in _PLATFORM_MAP
    assert len(_PLATFORM_MAP) >= 10


def test_search_empty_keyword():
    from potato.trendradar import search
    result = search("")
    assert result["ok"] is False
    assert "error" in result


def test_search_long_keyword():
    from potato.trendradar import search
    result = search("x" * 201)
    assert result["ok"] is False


def test_search_valid_keyword():
    from potato.trendradar import search, _CACHE
    _CACHE.clear()
    with patch("potato.trendradar._fetch_platform") as mock_fetch:
        mock_fetch.return_value = {"test title": {"url": "https://example.com", "ranks": [1]}}
        result = search("test", platforms=["weibo"], limit=5)
        assert result["ok"] is True
        assert result["keyword"] == "test"
        assert isinstance(result["items"], list)


def test_trending_basic():
    from potato.trendradar import trending, _CACHE
    _CACHE.clear()
    with patch("potato.trendradar._fetch_platform") as mock_fetch:
        mock_fetch.return_value = {
            "热点1": {"url": "https://weibo.com/1", "ranks": [1]},
            "热点2": {"url": "https://weibo.com/2", "ranks": [2]},
        }
        result = trending(platforms=["weibo"], limit=5)
        assert result["ok"] is True
        assert "weibo" in result["platforms"]
        assert result["count"] == 2
        assert len(result["items"]) >= 1


def test_sentiment_summary():
    from potato.trendradar import sentiment_summary, _CACHE
    _CACHE.clear()
    with patch("potato.trendradar._fetch_platform") as mock_fetch:
        mock_fetch.return_value = {
            "A股大涨": {"url": "https://weibo.com/1", "ranks": [1]},
            "今天天气不错": {"url": "https://weibo.com/2", "ranks": [2]},
        }
        result = sentiment_summary(platforms=["weibo"])
        assert result["ok"] is True
        assert result["total_topics"] == 2
        assert result["total_finance_related"] == 1
        assert 0 <= result["finance_ratio"] <= 1


def test_cache_ttl():
    from potato.trendradar import _CACHE, _cached_fetch
    _CACHE.clear()
    with patch("potato.trendradar._fetch_platform") as mock_fetch:
        mock_fetch.return_value = {"title": {"url": "http://x", "ranks": [1]}}
        result1 = _cached_fetch(["weibo"])
        assert mock_fetch.call_count == 1
        result2 = _cached_fetch(["weibo"])
        assert mock_fetch.call_count == 1  # cache hit, no new fetch


def test_fetch_failure_graceful():
    from potato.trendradar import trending, _CACHE, _DEMO_TRENDING
    _CACHE.clear()
    with patch("potato.trendradar._fetch_platform") as mock_fetch:
        mock_fetch.return_value = None  # network failure
        result = trending(platforms=["weibo"])
        assert result["ok"] is True
        # Should fall back to demo data
        assert len(result["items"]) > 0


def test_parse_items_dict():
    from potato.trendradar import _parse_items
    raw = {"热点标题": {"url": "https://example.com", "ranks": [3]}}
    items = _parse_items(raw)
    assert len(items) == 1
    assert items[0]["title"] == "热点标题"
    assert items[0]["rank"] == 3


def test_parse_items_list():
    from potato.trendradar import _parse_items
    raw = [{"title": "标题1", "url": "https://a.com", "rank": 1}]
    items = _parse_items(raw)
    assert len(items) == 1
    assert items[0]["title"] == "标题1"


def test_ws_handler_trendradar_trending():
    from desktop_pet.backend.main import app
    from potato.trendradar import trending
    routes = [r.path for r in app.routes]
    assert "/ws" in routes


def test_version_includes_trendradar():
    from potato.version import FEATURES
    assert "trendradar" in FEATURES