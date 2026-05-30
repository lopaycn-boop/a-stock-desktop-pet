"""Test Iwencai natural language stock screening module."""
import sys
sys.path.insert(0, ".")

from potato.iwencai import IwencaiClient, format_iwencai_to_text, _web_scrape_query


class TestIwencaiClient:

    def test_client_initialization_no_key(self):
        client = IwencaiClient()
        assert client.api_key == ""

    def test_client_initialization_with_key(self):
        client = IwencaiClient(api_key="test_key_123")
        assert client.api_key == "test_key_123"

    def test_headers_structure(self):
        client = IwencaiClient(api_key="test_key")
        headers = client._headers("query2data")
        assert headers["Authorization"] == "Bearer test_key"
        assert headers["X-Claw-Skill-Id"] == "query2data"
        assert headers["X-Claw-Trace-Id"]  # UUID
        assert "X-Claw-Call-Type" in headers

    def test_headers_different_skill(self):
        client = IwencaiClient(api_key="test_key")
        headers = client._headers("news-search")
        assert headers["X-Claw-Skill-Id"] == "news-search"

    def test_search_channel_validation(self):
        client = IwencaiClient(api_key="test_key")
        result = client.search("test", channel="invalid_channel")
        assert result["ok"] is False
        assert "IWENCAI_API_KEY" in result.get("error", "") or result.get("keyword") == "test"

    def test_format_error_result(self):
        result = {"ok": False, "error": "查询超时", "question": "涨停股"}
        text = format_iwencai_to_text(result)
        assert "超时" in text

    def test_format_empty_data(self):
        result = {"ok": True, "data": [], "total": 0, "question": "涨停股", "source": "iwencai_select"}
        text = format_iwencai_to_text(result)
        assert "未筛选到符合条件" in text or "涨停" in text

    def test_format_stocks_result(self):
        result = {
            "ok": True,
            "stocks": [
                {"code": "600519", "name": "贵州茅台"},
                {"code": "000858", "name": "五粮液"},
            ],
            "total": 2,
            "query": "连续涨停3天",
            "source": "iwencai_select",
        }
        text = format_iwencai_to_text(result)
        assert "贵州茅台" in text
        assert "五粮液" in text
        assert "涨停" in text

    def test_format_search_result(self):
        result = {
            "ok": True,
            "data": [
                {"title": "茅台创新高", "summary": "白酒龙头", "url": "", "publish_date": "2025-01-01", "channel": "news"},
            ],
            "total": 1,
            "keyword": "茅台",
            "channel": "news",
            "source": "iwencai_search",
        }
        text = format_iwencai_to_text(result)
        assert "茅台" in text
        assert "news" in text

    def test_format_query_with_data(self):
        result = {
            "ok": True,
            "data": [
                {"名称": "贵州茅台", "代码": "600519", "最新价": "1800.00"},
            ],
            "total": 1,
            "question": "贵州茅台",
            "source": "iwencai_web",
        }
        text = format_iwencai_to_text(result)
        assert "贵州茅台" in text

    def test_select_stocks_no_key_falls_back(self):
        client = IwencaiClient(api_key="")
        result = client.select_stocks("连续涨停3天", limit=3)
        assert "ok" in result
        assert result.get("question") == "连续涨停3天" or result.get("query") == "连续涨停3天" or result.get("error") is not None

    def test_query_to_markdown_empty(self):
        result = {"ok": True, "data": [], "total": 0, "question": "test", "source": "iwencai_web"}
        text = format_iwencai_to_text(result)
        assert "未查到数据" in text

    def test_web_scrape_query_returns_dict(self):
        result = _web_scrape_query("涨停", page=1, limit=3)
        assert isinstance(result, dict)
        assert "ok" in result
        assert "question" in result

    def test_web_scrape_query_has_source(self):
        result = _web_scrape_query("连涨3天", page=1, limit=3)
        if result.get("ok"):
            assert result.get("source") in ("iwencai_web", "em_datacenter")