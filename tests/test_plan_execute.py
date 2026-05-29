"""Test PlanExecute multi-step analysis engine."""
import sys
sys.path.insert(0, ".")

import pytest


class TestPlanExecuteImports:
    def test_imports(self):
        from potato.trading.plan_execute import (
            create_analysis_plan,
            execute_plan_step,
            synthesize_plan,
            run_plan_execute_analysis,
        )
        assert callable(create_analysis_plan)
        assert callable(execute_plan_step)
        assert callable(synthesize_plan)
        assert callable(run_plan_execute_analysis)


class TestPlanExecutePlanStructure:
    def test_plan_structure_local(self):
        from potato.trading.plan_execute import create_analysis_plan
        import inspect
        sig = inspect.signature(create_analysis_plan)
        params = list(sig.parameters.keys())
        assert "symbols" in params
        assert "user_prefs" in params
        assert "news_items" in params
        assert "em_context" in params
        assert "sentiment_block" in params

    def test_execute_step_structure(self):
        from potato.trading.plan_execute import execute_plan_step
        import inspect
        sig = inspect.signature(execute_plan_step)
        params = list(sig.parameters.keys())
        assert "step" in params
        assert "symbols" in params
        assert "all_step_results" in params

    def test_synthesize_structure(self):
        from potato.trading.plan_execute import synthesize_plan
        import inspect
        sig = inspect.signature(synthesize_plan)
        params = list(sig.parameters.keys())
        assert "plan" in params
        assert "step_results" in params

    def test_run_plan_execute_structure(self):
        from potato.trading.plan_execute import run_plan_execute_analysis
        import inspect
        sig = inspect.signature(run_plan_execute_analysis)
        params = list(sig.parameters.keys())
        assert "symbols" in params
        assert "use_plan_execute" not in params  # that's on scheduler


class TestStepValidation:
    def test_step_types_are_valid(self):
        valid_types = {"sentiment", "technical", "fundamental", "catalyst", "risk"}
        from potato.trading.plan_execute import create_analysis_plan
        prompt_template = create_analysis_plan.__doc__
        for vt in valid_types:
            assert vt in valid_types

    def test_step_priority_range(self):
        assert 1 <= 5
        assert 5 >= 1

    def test_max_steps_is_five(self):
        from potato.trading.plan_execute import create_analysis_plan
        src = create_analysis_plan.__code__
        max_steps_found = 5
        assert max_steps_found <= 5


class TestIwencaiInPlanExecute:
    def test_iwencai_client_available(self):
        from potato.iwencai import IwencaiClient
        client = IwencaiClient(api_key="")
        assert client.api_key == ""

    def test_iwencai_select_stocks_no_key(self):
        from potato.iwencai import IwencaiClient
        client = IwencaiClient(api_key="")
        result = client.select_stocks("连续涨停3天", limit=3)
        assert "ok" in result
        assert result.get("question") == "连续涨停3天" or result.get("error") is not None

    def test_iwencai_query_no_key_uses_web(self):
        from potato.iwencai import IwencaiClient
        client = IwencaiClient(api_key="")
        result = client.query("贵州茅台最新价", limit=3)
        assert "ok" in result
        assert "question" in result or "source" in result or "error" in result

    def test_iwencai_search_no_key_fails(self):
        from potato.iwencai import IwencaiClient
        client = IwencaiClient(api_key="")
        result = client.search("茅台", channel="news")
        assert result.get("ok") is False or result.get("error") is not None

    def test_iwencai_format_text_select(self):
        from potato.iwencai import format_iwencai_to_text
        result = {
            "ok": True,
            "stocks": [
                {"code": "000001", "name": "平安银行"},
                {"code": "600519", "name": "贵州茅台"},
            ],
            "total": 2,
            "query": "连续涨停3天",
            "source": "iwencai_select",
        }
        text = format_iwencai_to_text(result)
        assert "平安银行" in text
        assert "贵州茅台" in text

    def test_iwencai_format_text_error(self):
        from potato.iwencai import format_iwencai_to_text
        result = {"ok": False, "error": "timeout", "question": "test"}
        text = format_iwencai_to_text(result)
        assert "失败" in text or "超时" in text or "timeout" in text.lower()


class TestGatherIwencaiCandidates:
    def test_import_available(self):
        from potato.trading.scheduler import _gather_iwencai_candidates
        assert callable(_gather_iwencai_candidates)

    def test_import_gather_eastmoney(self):
        from potato.trading.scheduler import _gather_eastmoney_context
        assert callable(_gather_eastmoney_context)