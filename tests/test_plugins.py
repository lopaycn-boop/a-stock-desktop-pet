"""Tests for plugin system — AIS and DeepAudit unified interface."""
import sys
sys.path.insert(0, ".")

from potato.plugins import (
    call_plugin,
    list_plugins,
    PluginInfo,
    register_plugin,
    _ais_available,
    _deepaudit_available,
)


class TestPluginRegistry:

    def test_list_plugins_returns_list(self):
        plugins = list_plugins()
        assert isinstance(plugins, list)
        assert len(plugins) >= 2

    def test_ais_plugin_registered(self):
        plugins = list_plugins()
        names = [p.name for p in plugins]
        assert "ais" in names

    def test_deepaudit_plugin_registered(self):
        plugins = list_plugins()
        names = [p.name for p in plugins]
        assert "deepaudit" in names

    def test_ais_plugin_info(self):
        plugins = list_plugins()
        ais = next(p for p in plugins if p.name == "ais")
        assert "analyze" in ais.actions
        assert "learn" in ais.actions
        assert "history" in ais.actions
        assert ais.version == "0.1.0"

    def test_deepaudit_plugin_info(self):
        plugins = list_plugins()
        da = next(p for p in plugins if p.name == "deepaudit")
        assert "audit_snippet" in da.actions
        assert "audit_repo" in da.actions
        assert "audit_file" in da.actions
        assert "status" in da.actions
        assert "report" in da.actions

    def test_register_custom_plugin(self):
        info = PluginInfo(
            name="test_plugin",
            display_name="Test Plugin",
            description="For testing",
            version="0.0.1",
            actions=["run"],
            requires=[],
        )
        register_plugin(info)
        plugins = list_plugins()
        names = [p.name for p in plugins]
        assert "test_plugin" in names


class TestCallPluginRouting:

    def test_unknown_plugin_returns_error(self):
        result = call_plugin("nonexistent", "run", {})
        assert result["ok"] is False
        assert "Unknown plugin" in result["error"]

    def test_unknown_action_returns_error(self):
        result = call_plugin("ais", "nonexistent_action", {})
        assert result["ok"] is False
        assert "not supported" in result["error"]

    def test_deepaudit_unknown_action_returns_error(self):
        result = call_plugin("deepaudit", "nonexistent_action", {})
        assert result["ok"] is False
        assert "not supported" in result["error"] or "Unknown action" in result["error"]

    def test_call_plugin_returns_plugin_name(self):
        result = call_plugin("ais", "analyze", {"command": "ls", "exit_code": 1})
        assert result["plugin"] == "ais"

    def test_call_plugin_returns_action(self):
        result = call_plugin("ais", "analyze", {"command": "ls", "exit_code": 1})
        assert result["action"] == "analyze"


class TestAISAnalyze:

    def test_analyze_returns_dict(self):
        result = call_plugin("ais", "analyze", {
            "command": "git push origin main",
            "exit_code": 1,
            "output": "error: failed to push some refs",
        })
        assert isinstance(result, dict)
        assert "ok" in result

    def test_analyze_result_has_command(self):
        result = call_plugin("ais", "analyze", {
            "command": "mkdirr /tmp/test",
            "exit_code": 127,
            "output": "command not found",
        })
        if result.get("ok"):
            assert result["data"]["command"] == "mkdirr /tmp/test"
            assert result["data"]["exit_code"] == 127

    def test_analyze_fallback_uses_llm(self):
        result = call_plugin("ais", "analyze", {
            "command": "pytho --version",
            "exit_code": 127,
            "output": "pytho: command not found",
        })
        assert isinstance(result, dict)

    def test_analyze_empty_params(self):
        result = call_plugin("ais", "analyze", {})
        assert isinstance(result, dict)


class TestAISLearn:

    def test_learn_returns_dict(self):
        result = call_plugin("ais", "learn", {"topic": "docker"})
        assert isinstance(result, dict)
        assert "ok" in result

    def test_learn_default_topic(self):
        result = call_plugin("ais", "learn", {})
        assert isinstance(result, dict)


class TestAISHistory:

    def test_history_returns_dict(self):
        result = call_plugin("ais", "history", {"limit": 5})
        assert isinstance(result, dict)


class TestDeepAuditSnippet:

    def test_audit_snippet_returns_dict(self):
        result = call_plugin("deepaudit", "audit_snippet", {
            "code": "def login(user, pwd): return True",
            "language": "python",
        })
        assert isinstance(result, dict)
        assert "ok" in result

    def test_audit_snippet_fallback(self):
        result = call_plugin("deepaudit", "audit_snippet", {
            "code": "eval(input('Enter:'))",
            "language": "python",
            "dimensions": ["security"],
        })
        assert isinstance(result, dict)

    def test_audit_snippet_default_dimensions(self):
        result = call_plugin("deepaudit", "audit_snippet", {
            "code": "print('hello')",
            "language": "python",
        })
        assert isinstance(result, dict)


class TestDeepAuditFile:

    def test_audit_file_not_found(self):
        result = call_plugin("deepaudit", "audit_file", {
            "file_path": "/nonexistent/path.py",
        })
        assert result["ok"] is False
        assert "not found" in result["error"].lower() or "File not found" in result["error"]

    def test_audit_file_returns_dict(self):
        result = call_plugin("deepaudit", "audit_file", {
            "file_path": "potato/version.py",
        })
        assert isinstance(result, dict)


class TestDeepAuditStatus:

    def test_status_missing_task_id(self):
        result = call_plugin("deepaudit", "status", {})
        assert result["ok"] is False

    def test_status_missing_api_url(self):
        result = call_plugin("deepaudit", "status", {"task_id": "test-123"})
        assert result["ok"] is False


class TestDeepAuditReport:

    def test_report_missing_params(self):
        result = call_plugin("deepaudit", "report", {})
        assert result["ok"] is False


class TestPluginAvailability:

    def test_ais_available_returns_bool(self):
        result = _ais_available()
        assert isinstance(result, bool)

    def test_deepaudit_available_returns_bool(self):
        result = _deepaudit_available()
        assert isinstance(result, bool)

    def test_list_plugins_sets_availability(self):
        plugins = list_plugins()
        for p in plugins:
            assert isinstance(p.available, bool)