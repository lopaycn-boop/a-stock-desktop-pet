"""Unified plugin system — integrates external AI tools under a single call interface.

Plugins:
  - AIS (kangvcar/ais): CLI-based terminal error analysis + learning assistant
  - DeepAudit (lintsinghua/XCodeReviewer): AI code audit via REST API

Both are invoked through `call_plugin(name, action, params)` which handles
provider discovery, health checks, and fallback routing.

Usage:
    from potato.plugins import call_plugin, list_plugins

    # Analyze a command error with AIS
    result = call_plugin("ais", "analyze", {
        "command": "git push origin main",
        "exit_code": 1,
        "output": "error: failed to push some refs...",
        "context_level": "standard",
    })

    # Audit code with DeepAudit
    result = call_plugin("ais", "learn", {"topic": "git"})

    result = call_plugin("deepaudit", "audit_snippet", {
        "code": "def login(user, pwd): ...",
        "language": "python",
    })

    result = call_plugin("deepaudit", "audit_repo", {
        "repo_url": "https://github.com/user/repo",
        "branch": "main",
    })
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("potato.plugins")

_RE_UNSAFE_SHELL = re.compile(r"[\n\r\x00-\x1f`$\\!;&|<>]")

def _sanitize_prompt(prompt: str, max_len: int = 4000) -> str:
    prompt = _RE_UNSAFE_SHELL.sub("", prompt)
    return prompt[:max_len]

# ── Plugin Registry ──────────────────────────────────────────────────────

@dataclass
class PluginInfo:
    name: str
    display_name: str
    description: str
    version: str
    actions: list[str]
    requires: list[str]
    available: bool = False
    last_error: str = ""


_PLUGINS: dict[str, PluginInfo] = {}
_TIMEOUT = httpx.Timeout(connect=8.0, read=60.0, write=30.0, pool=60.0)


def register_plugin(info: PluginInfo) -> None:
    _PLUGINS[info.name] = info


def list_plugins() -> list[PluginInfo]:
    """List all registered plugins with availability status."""
    for p in _PLUGINS.values():
        if p.name == "ais":
            p.available = _ais_available()
        elif p.name == "deepaudit":
            p.available = _deepaudit_available()
    return list(_PLUGINS.values())


def call_plugin(name: str, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Unified plugin call interface.

    Args:
        name: Plugin name ("ais" or "deepaudit")
        action: Action to invoke (plugin-specific)
        params: Action parameters

    Returns:
        dict with 'ok', 'plugin', 'action', 'data' or 'error' keys
    """
    params = params or {}

    if name not in _PLUGINS:
        return {"ok": False, "plugin": name, "action": action, "error": f"Unknown plugin: {name}"}

    info = _PLUGINS[name]
    if action not in info.actions:
        return {"ok": False, "plugin": name, "action": action, "error": f"Action '{action}' not supported by {name}"}

    if name == "ais":
        return _call_ais(action, params)
    elif name == "deepaudit":
        return _call_deepaudit(action, params)

    return {"ok": False, "plugin": name, "action": action, "error": f"No handler for plugin: {name}"}


# ══════════════════════════════════════════════════════════════════════════
# AIS Plugin — Terminal Error Analysis & Learning Assistant
# ══════════════════════════════════════════════════════════════════════════

def _ais_available() -> bool:
    return shutil.which("ais") is not None


def _call_ais(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """Invoke AIS CLI actions.

    Actions:
      analyze   — Analyze a failed command and its error output
      learn     — Interactive topic learning (git, docker, vim, etc.)
      history   — View error analysis history
    """
    if action == "analyze":
        return _ais_analyze(params)
    elif action == "learn":
        return _ais_learn(params)
    elif action == "history":
        return _ais_history(params)
    return {"ok": False, "plugin": "ais", "action": action, "error": f"Unknown AIS action: {action}"}


def _ais_analyze(params: dict[str, Any]) -> dict[str, Any]:
    """Analyze a command failure using AIS.

    Params:
        command: The failed command string
        exit_code: Exit code (default 1)
        output: Stdout/stderr output
        context_level: minimal/standard/detailed (default standard)
    """
    command = params.get("command", "")
    exit_code = params.get("exit_code", 1)
    output = params.get("output", "")
    context_level = params.get("context_level", "standard")

    if not _ais_available():
        return _ais_analyze_fallback(params)

    prompt = f"Command failed: `{command}` (exit code: {exit_code})\n"
    if output:
        prompt += f"Output:\n```\n{output[:2000]}\n```\n"
    prompt += "Please analyze this error, explain why it happened, and suggest how to fix it."
    prompt = _sanitize_prompt(prompt)

    try:
        result = subprocess.run(
            ["ais", "ask", prompt],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "AIS_CONTEXT_LEVEL": context_level},
        )
        if result.returncode == 0 and result.stdout.strip():
            return {
                "ok": True, "plugin": "ais", "action": "analyze",
                "data": {
                    "command": command, "exit_code": exit_code,
                    "analysis": result.stdout.strip(), "source": "ais_cli",
                },
            }
        error_msg = result.stderr.strip() or result.stdout.strip() or "AIS returned empty output"
        logger.warning("AIS CLI error: %s", error_msg[:200])
    except subprocess.TimeoutExpired:
        logger.warning("AIS CLI timeout")
    except Exception as exc:
        logger.warning("AIS CLI exception: %s", str(exc)[:200])

    return _ais_analyze_fallback(params)


def _ais_analyze_fallback(params: dict[str, Any]) -> dict[str, Any]:
    """Fallback: use potato's own LLM to analyze command errors when AIS is not available."""
    from potato.llm import chat
    command = params.get("command", "")
    exit_code = params.get("exit_code", 1)
    output = params.get("output", "")

    prompt = (
        f"The following command failed with exit code {exit_code}:\n\n"
        f"Command: `{command}`\n\n"
    )
    if output:
        prompt += f"Output:\n```\n{output[:2000]}\n```\n\n"
    prompt += (
        "Please analyze this error:\n"
        "1. **Why did it fail?** — Explain the root cause\n"
        "2. **How to fix it?** — Provide specific fix commands\n"
        "3. **Learning tip** — Brief explanation to help avoid this error in the future\n"
    )

    try:
        analysis = chat(prompt, task_type="analysis")
        return {
            "ok": True, "plugin": "ais", "action": "analyze",
            "data": {
                "command": command, "exit_code": exit_code,
                "analysis": analysis, "source": "potato_llm_fallback",
            },
        }
    except Exception as exc:
        return {
            "ok": False, "plugin": "ais", "action": "analyze",
            "error": f"Both AIS and LLM fallback failed: {str(exc)[:200]}",
        }


def _ais_learn(params: dict[str, Any]) -> dict[str, Any]:
    """Interactive topic learning via AIS.

    Params:
        topic: Learning topic (git, docker, vim, ssh, linux, etc.)
    """
    topic = _sanitize_prompt(str(params.get("topic", "linux")), max_len=100)
    if not _ais_available():
        return _ais_learn_fallback(params)

    try:
        result = subprocess.run(
            ["ais", "learn", topic],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            return {
                "ok": True, "plugin": "ais", "action": "learn",
                "data": {"topic": topic, "content": result.stdout.strip(), "source": "ais_cli"},
            }
    except subprocess.TimeoutExpired:
        logger.warning("AIS learn timeout")
    except Exception as exc:
        logger.warning("AIS learn exception: %s", str(exc)[:200])

    return _ais_learn_fallback(params)


def _ais_learn_fallback(params: dict[str, Any]) -> dict[str, Any]:
    """Fallback: use potato's own LLM for topic learning."""
    from potato.llm import chat
    topic = params.get("topic", "linux")
    prompt = (
        f"Teach me about {topic} in a structured, beginner-friendly way.\n\n"
        f"Cover:\n"
        f"1. What is {topic}?\n"
        f"2. Top 5 most common {topic} commands/concepts\n"
        f"3. Common mistakes and how to avoid them\n"
        f"4. Quick reference cheat sheet\n"
    )
    try:
        content = chat(prompt, task_type="chat")
        return {
            "ok": True, "plugin": "ais", "action": "learn",
            "data": {"topic": topic, "content": content, "source": "potato_llm_fallback"},
        }
    except Exception as exc:
        return {"ok": False, "plugin": "ais", "action": "learn", "error": str(exc)[:200]}


def _ais_history(params: dict[str, Any]) -> dict[str, Any]:
    """View AIS error analysis history."""
    limit = params.get("limit", 10)
    if not _ais_available():
        return {"ok": False, "plugin": "ais", "action": "history", "error": "AIS CLI not available"}

    try:
        result = subprocess.run(
            ["ais", "history", str(limit)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return {
                "ok": True, "plugin": "ais", "action": "history",
                "data": {"entries": result.stdout.strip(), "limit": limit, "source": "ais_cli"},
            }
    except Exception as exc:
        logger.warning("AIS history exception: %s", str(exc)[:200])

    return {"ok": False, "plugin": "ais", "action": "history", "error": "AIS history unavailable"}


# ══════════════════════════════════════════════════════════════════════════
# DeepAudit Plugin — AI Code Review & Audit
# ══════════════════════════════════════════════════════════════════════════

_DEEPAUDIT_URL_KEY = "DEEPAUDIT_API_URL"
_DEEPAUDIT_URL = os.environ.get(_DEEPAUDIT_URL_KEY, "http://localhost:8000/api/v1")


def _deepaudit_available() -> bool:
    if _ais_available():
        return True
    try:
        resp = httpx.get(f"{_DEEPAUDIT_URL}/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


def _call_deepaudit(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """Invoke DeepAudit/XCodeReviewer actions.

    Actions:
      audit_snippet  — Analyze a code snippet
      audit_repo     — Audit a git repository
      audit_file     — Audit a local file
      status         — Check audit task status
      report         — Retrieve audit report
    """
    if action == "audit_snippet":
        return _deepaudit_snippet(params)
    elif action == "audit_repo":
        return _deepaudit_repo(params)
    elif action == "audit_file":
        return _deepaudit_file(params)
    elif action == "status":
        return _deepaudit_status(params)
    elif action == "report":
        return _deepaudit_report(params)
    return {"ok": False, "plugin": "deepaudit", "action": action, "error": f"Unknown action: {action}"}


def _deepaudit_snippet(params: dict[str, Any]) -> dict[str, Any]:
    """Analyze a code snippet via DeepAudit API or LLM fallback.

    Params:
        code: Source code string
        language: Programming language (python, javascript, etc.)
        dimensions: Audit dimensions (default: all 5)
    """
    code = params.get("code", "")
    language = params.get("language", "python")
    dimensions = params.get("dimensions", ["bug", "security", "performance", "style", "maintainability"])

    api_url = os.environ.get(_DEEPAUDIT_URL_KEY, "")
    if api_url:
        try:
            client = httpx.Client(timeout=_TIMEOUT)
            resp = client.post(
                f"{api_url}/api/v1/analysis/instant",
                json={
                    "code": code, "language": language,
                    "dimensions": dimensions, "context_level": "standard",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ok": True, "plugin": "deepaudit", "action": "audit_snippet",
                    "data": {**data, "source": "deepaudit_api"},
                }
        except Exception as exc:
            logger.debug("DeepAudit API unavailable, using LLM fallback: %s", str(exc)[:100])

    return _deepaudit_llm_fallback(code, language, dimensions)


def _deepaudit_repo(params: dict[str, Any]) -> dict[str, Any]:
    """Audit a git repository via DeepAudit.

    Params:
        repo_url: Git repository URL
        branch: Branch name (default: main)
    """
    repo_url = params.get("repo_url", "")
    branch = params.get("branch", "main")
    api_url = os.environ.get(_DEEPAUDIT_URL_KEY, "")

    if api_url:
        try:
            client = httpx.Client(timeout=_TIMEOUT)
            resp = client.post(
                f"{api_url}/api/v1/audit",
                json={"repo_url": repo_url, "branch": branch},
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return {
                    "ok": True, "plugin": "deepaudit", "action": "audit_repo",
                    "data": {**data, "source": "deepaudit_api"},
                }
        except Exception as exc:
            logger.debug("DeepAudit API unavailable: %s", str(exc)[:100])

    return {
        "ok": False, "plugin": "deepaudit", "action": "audit_repo",
        "error": f"DeepAudit API not available. Set {_DEEPAUDIT_URL_KEY} or start the DeepAudit service.",
    }


def _deepaudit_file(params: dict[str, Any]) -> dict[str, Any]:
    """Audit a local file by reading its contents and using snippet analysis.

    Params:
        file_path: Path to the source file
        dimensions: Audit dimensions (default: all 5)
    """
    file_path = params.get("file_path", "")
    dimensions = params.get("dimensions", ["bug", "security", "performance", "style", "maintainability"])

    if not file_path or not os.path.isfile(file_path):
        return {"ok": False, "plugin": "deepaudit", "action": "audit_file", "error": f"File not found: {file_path}"}

    ext = os.path.splitext(file_path)[1].lstrip(".")
    lang_map = {"py": "python", "js": "javascript", "ts": "typescript", "go": "go", "rs": "rust", "java": "java", "rb": "ruby", "cpp": "cpp", "c": "c", "cs": "csharp"}
    language = lang_map.get(ext, ext)

    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            code = f.read()
    except Exception as exc:
        return {"ok": False, "plugin": "deepaudit", "action": "audit_file", "error": f"Read error: {exc}"}

    result = _deepaudit_snippet({"code": code, "language": language, "dimensions": dimensions})
    if result.get("ok") and result.get("data"):
        result["data"]["file_path"] = file_path
    else:
        result.setdefault("data", {})["file_path"] = file_path
    return result


def _deepaudit_status(params: dict[str, Any]) -> dict[str, Any]:
    """Check audit task status."""
    task_id = params.get("task_id", "")
    api_url = os.environ.get(_DEEPAUDIT_URL_KEY, "")
    if not api_url or not task_id:
        return {"ok": False, "plugin": "deepaudit", "action": "status", "error": "Missing task_id or DEEPAUDIT_API_URL"}

    try:
        client = httpx.Client(timeout=_TIMEOUT)
        resp = client.get(f"{api_url}/api/v1/audit/{task_id}/status")
        if resp.status_code == 200:
            return {"ok": True, "plugin": "deepaudit", "action": "status", "data": resp.json(), "source": "deepaudit_api"}
    except Exception as exc:
        return {"ok": False, "plugin": "deepaudit", "action": "status", "error": str(exc)[:200]}
    return {"ok": False, "plugin": "deepaudit", "action": "status", "error": "Task not found"}


def _deepaudit_report(params: dict[str, Any]) -> dict[str, Any]:
    """Retrieve an audit report."""
    task_id = params.get("task_id", "")
    fmt = params.get("format", "json")
    api_url = os.environ.get(_DEEPAUDIT_URL_KEY, "")
    if not api_url or not task_id:
        return {"ok": False, "plugin": "deepaudit", "action": "report", "error": "Missing task_id or DEEPAUDIT_API_URL"}

    try:
        client = httpx.Client(timeout=_TIMEOUT)
        resp = client.get(f"{api_url}/api/v1/audit/{task_id}/report", params={"format": fmt})
        if resp.status_code == 200:
            return {"ok": True, "plugin": "deepaudit", "action": "report", "data": resp.json() if fmt == "json" else resp.text, "source": "deepaudit_api"}
    except Exception as exc:
        return {"ok": False, "plugin": "deepaudit", "action": "report", "error": str(exc)[:200]}
    return {"ok": False, "plugin": "deepaudit", "action": "report", "error": "Report not found"}


def _deepaudit_llm_fallback(code: str, language: str, dimensions: list[str]) -> dict[str, Any]:
    """Use potato's LLM for code audit when DeepAudit service is unavailable."""
    from potato.llm import chat

    dim_labels = {
        "bug": "Bug Detection",
        "security": "Security Vulnerabilities",
        "performance": "Performance Issues",
        "style": "Code Style & Readability",
        "maintainability": "Maintainability",
    }
    dim_text = "\n".join(f"- **{dim_labels.get(d, d)}**: Check for {d}-related issues" for d in dimensions)

    prompt = (
        f"Perform a thorough code audit of the following {language} code.\n\n"
        f"Analyze these dimensions:\n{dim_text}\n\n"
        f"For each issue found, provide:\n"
        f"- **What**: What is the issue?\n"
        f"- **Why**: Why is it a problem?\n"
        f"- **How**: How to fix it? (with code example)\n\n"
        f"```{language}\n{code}\n```\n\n"
        f"Output a structured analysis in JSON format with keys: "
        f"\"summary\", \"issues\" (array of {{dimension, severity, what, why, how, line}}), "
        f"\"score\" (0-100 overall quality), \"recommendations\" (array of strings)."
    )

    try:
        analysis = chat(prompt, task_type="analysis")
        return {
            "ok": True, "plugin": "deepaudit", "action": "audit_snippet",
            "data": {
                "language": language, "dimensions": dimensions,
                "analysis": analysis, "source": "potato_llm_fallback",
            },
        }
    except Exception as exc:
        return {"ok": False, "plugin": "deepaudit", "action": "audit_snippet", "error": f"LLM fallback failed: {str(exc)[:200]}"}


# ══════════════════════════════════════════════════════════════════════════
# Plugin Registration
# ══════════════════════════════════════════════════════════════════════════

register_plugin(PluginInfo(
    name="ais",
    display_name="AIS Terminal Assistant",
    description="AI-driven terminal error analysis and learning assistant (kangvcar/ais). "
                "Analyzes failed commands, explains root causes, and provides interactive topic learning.",
    version="0.1.0",
    actions=["analyze", "learn", "history"],
    requires=["ais CLI or potato LLM"],
))

register_plugin(PluginInfo(
    name="deepaudit",
    display_name="DeepAudit Code Reviewer",
    description="AI code audit tool (lintsinghua/XCodeReviewer). "
                "Supports snippet analysis, repo auditing, and multi-dimension code review "
                "with What-Why-How explanations.",
    version="0.1.0",
    actions=["audit_snippet", "audit_repo", "audit_file", "status", "report"],
    requires=["DeepAudit API server or potato LLM"],
))