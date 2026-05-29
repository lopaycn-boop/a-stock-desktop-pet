"""Tests for demo mode — smart simulated responses when no API keys available."""

import json
import pytest
from unittest.mock import patch

from potato.llm import _demo_response, TASK_TYPES


class TestDemoResponse:
    """Test _demo_response generates context-aware simulated responses."""

    def test_demo_analysis_stock_keyword(self):
        result = _demo_response("帮我分析贵州茅台", task="analysis", use_json=True)
        assert result["ok"] is True
        assert result["demo"] is True
        assert result["provider"] == "demo"
        assert result["model"] == "demo-mode"
        assert result["tokens_in"] == 0
        content = json.loads(result["content"])
        assert "操作建议" in content["reply"]
        assert "演示模式" in content["reply"]

    def test_demo_analysis_select_keyword(self):
        result = _demo_response("推荐几只好股票", task="analysis", use_json=True)
        assert result["ok"] is True
        assert result["demo"] is True
        content = json.loads(result["content"])
        assert "操作建议" in content["reply"]

    def test_demo_analysis_buy_keyword(self):
        result = _demo_response("今天适合买入吗", task="analysis", use_json=True)
        assert result["ok"] is True
        content = json.loads(result["content"])
        assert "操作建议" in content["reply"]

    def test_demo_market_keyword(self):
        result = _demo_response("今天A股行情如何", task="analysis", use_json=True)
        assert result["ok"] is True
        content = json.loads(result["content"])
        assert "模拟行情" in content["reply"]
        assert "演示模式" in content["reply"]

    def test_demo_hot_topic_keyword(self):
        result = _demo_response("最近有什么热点板块", task="analysis", use_json=True)
        assert result["ok"] is True
        content = json.loads(result["content"])
        assert "热点速递" in content["reply"]

    def test_demo_research_task(self):
        result = _demo_response("帮我查一下新能源研报", task="research", use_json=False)
        assert result["ok"] is True
        assert result["demo"] is True
        assert "演示模式" in result["content"]

    def test_demo_research_keyword_in_prompt(self):
        result = _demo_response("搜索最新资讯", task="chat", use_json=False)
        assert result["ok"] is True
        assert "演示模式" in result["content"]

    def test_demo_sentiment_keyword(self):
        result = _demo_response("今天市场情绪怎么样", task="chat", use_json=False)
        assert result["ok"] is True
        assert "市场情绪" in result["content"]
        assert "演示模式" in result["content"]

    def test_demo_fallback_chat(self):
        result = _demo_response("你好呀", task="chat", use_json=False)
        assert result["ok"] is True
        assert result["demo"] is True
        assert result["provider"] == "demo"

    def test_demo_fallback_json(self):
        result = _demo_response("随便聊聊", task="fallback", use_json=True)
        assert result["ok"] is True
        content = json.loads(result["content"])
        assert "emotion" in content
        assert "演示模式" in content["reply"] or "API Key" in content["reply"]

    def test_demo_zero_cost(self):
        result = _demo_response("分析持仓", task="analysis")
        assert result["tokens_in"] == 0
        assert result["tokens_out"] == 0

    def test_demo_all_task_types_valid(self):
        for task in TASK_TYPES:
            result = _demo_response("test", task=task, use_json=False)
            assert result["ok"] is True
            assert result["demo"] is True

    def test_demo_empty_prompt(self):
        result = _demo_response("", task="chat", use_json=False)
        assert result["ok"] is True

    def test_demo_none_prompt(self):
        result = _demo_response(None, task="chat", use_json=False)
        assert result["ok"] is True

    def test_demo_analysis_with_json_false(self):
        result = _demo_response("分析大盘", task="analysis", use_json=False)
        assert result["ok"] is True
        assert isinstance(result["content"], str)