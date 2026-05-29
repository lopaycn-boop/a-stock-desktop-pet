"""Vision system — 小土豆的眼睛。

截屏 → 视觉模型分析 → 理解界面 → 生成操作指令。

三种视觉模式：
1. mano-cua (首选): Mano-P GUI-VLA 模型，纯视觉操控，支持所有 GUI
2. DeepSeek 多模态: 截图发给 DeepSeek 分析界面内容
3. pyautogui 截屏: 基础截图能力，配合 LLM 文字分析

操作执行：
- mano-cua: 自主 "看→想→做" 循环，直到任务完成
- pyautogui: 根据 AI 分析结果执行点击/输入坐标
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any

logger = logging.getLogger("potato.vision")


def _safe_import_pyautogui():
    """Import pyautogui safely — returns None if unavailable (headless, no tkinter)."""
    try:
        _orig_exit = __builtins__["exit"] if isinstance(__builtins__, dict) else None
    except (TypeError, KeyError):
        _orig_exit = None
    _orig_sys_exit = os.sys.exit

    class _BlockExit(Exception):
        pass

    def _no_exit(*a, **kw):
        raise _BlockExit()

    try:
        import sys as _sys
        _sys.exit = _no_exit
        import pyautogui
        _sys.exit = _orig_sys_exit
        return pyautogui
    except (_BlockExit, SystemExit, ImportError, Exception) as e:
        import sys as _sys
        _sys.exit = _orig_sys_exit
        logger.debug("pyautogui unavailable: %s", e)
        return None


def _capture_pil(max_width: int = 1280):
    """Capture screenshot as PIL Image, or None."""
    pag = _safe_import_pyautogui()
    if not pag:
        return None
    from PIL import Image
    screenshot = pag.screenshot()
    width, height = screenshot.size
    if width > max_width:
        scale = max_width / width
        screenshot = screenshot.resize((max_width, int(height * scale)), Image.LANCZOS)
    return screenshot


def capture_screen_base64(quality: int = 70, max_width: int = 1280) -> str | None:
    """截取当前屏幕，压缩后转 base64。"""
    try:
        img = _capture_pil(max_width)
        if not img:
            return None
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        logger.warning("Screenshot failed: %s", e)
        return None


def capture_screen_bytes(quality: int = 70, max_width: int = 1280) -> bytes | None:
    """截取屏幕返回 JPEG bytes。"""
    try:
        img = _capture_pil(max_width)
        if not img:
            return None
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    except Exception as e:
        logger.warning("Screenshot failed: %s", e)
        return None


# ── mano-cua integration ──

def has_mano_cua() -> bool:
    """Check if mano-cua CLI is installed."""
    return shutil.which("mano-cua") is not None


def mano_cua_run(task: str, *, local: bool = False, max_steps: int = 30,
                 timeout: int = 120) -> dict[str, Any]:
    """Run a GUI task via mano-cua (Mano-P visual agent).

    mano-cua captures screenshots, sends to vision model, gets action
    instructions (click coordinates, text to type, etc.), executes them,
    and loops until the task is done.
    """
    if not has_mano_cua():
        return {"ok": False, "error": "mano-cua not installed. Install: brew tap Mininglamp-AI/tap && brew install mano-cua"}

    cmd = ["mano-cua", "run", task, "--max-steps", str(max_steps)]
    if local:
        cmd.append("--local")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"mano-cua timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def mano_cua_stop() -> dict[str, Any]:
    """Stop current mano-cua task."""
    if not has_mano_cua():
        return {"ok": False, "error": "mano-cua not installed"}
    try:
        proc = subprocess.run(["mano-cua", "stop"], capture_output=True, text=True, timeout=10)
        return {"ok": proc.returncode == 0, "stdout": proc.stdout}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── DeepSeek vision analysis ──

async def analyze_screenshot_with_llm(
    screenshot_b64: str,
    question: str = "请描述当前屏幕上的内容，特别关注股票/交易相关的信息。",
    settings=None,
) -> dict[str, Any]:
    """Send screenshot to DeepSeek (or other multimodal LLM) for visual analysis."""
    try:
        from openai import AsyncOpenAI
        from potato.config import load_settings

        settings = settings or load_settings()
        api_key = settings.deepseek_api_key
        base_url = "https://api.deepseek.com"

        if not api_key:
            return {"ok": False, "error": "DEEPSEEK_API_KEY not configured"}

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        messages = [
            {
                "role": "system",
                "content": "你是小土豆的视觉模块。分析截图内容，重点关注股票价格、交易界面、按钮位置等信息。用中文回答。",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}"},
                    },
                ],
            },
        ]

        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=1500,
            temperature=0.3,
        )
        content = response.choices[0].message.content
        return {"ok": True, "analysis": content}
    except Exception as e:
        logger.warning("Vision LLM analysis failed: %s", e)
        return {"ok": False, "error": str(e)}


# ── pyautogui GUI actions ──

def gui_click(x: int, y: int) -> dict[str, Any]:
    """Click at screen coordinates."""
    pag = _safe_import_pyautogui()
    if not pag:
        return {"ok": False, "error": "pyautogui unavailable (no display?)"}
    try:
        pag.click(x, y)
        return {"ok": True, "action": "click", "x": x, "y": y}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def gui_type_text(text: str, interval: float = 0.05) -> dict[str, Any]:
    """Type text at current cursor position."""
    pag = _safe_import_pyautogui()
    if not pag:
        return {"ok": False, "error": "pyautogui unavailable"}
    try:
        pag.typewrite(text, interval=interval) if text.isascii() else pag.write(text)
        return {"ok": True, "action": "type", "text": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def gui_hotkey(*keys: str) -> dict[str, Any]:
    """Press a hotkey combination (e.g. 'ctrl', 'c')."""
    pag = _safe_import_pyautogui()
    if not pag:
        return {"ok": False, "error": "pyautogui unavailable"}
    try:
        pag.hotkey(*keys)
        return {"ok": True, "action": "hotkey", "keys": list(keys)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def gui_scroll(clicks: int, x: int | None = None, y: int | None = None) -> dict[str, Any]:
    """Scroll at position."""
    pag = _safe_import_pyautogui()
    if not pag:
        return {"ok": False, "error": "pyautogui unavailable"}
    try:
        pag.scroll(clicks, x=x, y=y)
        return {"ok": True, "action": "scroll", "clicks": clicks}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def gui_move_to(x: int, y: int) -> dict[str, Any]:
    """Move mouse to coordinates."""
    pag = _safe_import_pyautogui()
    if not pag:
        return {"ok": False, "error": "pyautogui unavailable"}
    try:
        pag.moveTo(x, y)
        return {"ok": True, "action": "move", "x": x, "y": y}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Composite: AI-driven visual operation loop ──

async def visual_operate(
    task: str,
    *,
    max_steps: int = 15,
    use_mano: bool | None = None,
    settings=None,
) -> dict[str, Any]:
    """AI-driven visual operation: screenshot → analyze → act → repeat.

    Priority:
    1. mano-cua if installed (best: dedicated GUI-VLA model)
    2. DeepSeek vision + pyautogui (fallback: general multimodal LLM)
    """
    if use_mano is None:
        use_mano = has_mano_cua()

    if use_mano:
        logger.info("Using mano-cua for visual task: %s", task[:80])
        return mano_cua_run(task, max_steps=max_steps)

    logger.info("Using DeepSeek vision + pyautogui for: %s", task[:80])
    results = []

    for step in range(max_steps):
        screenshot = capture_screen_base64()
        if not screenshot:
            results.append({"step": step, "error": "screenshot_failed"})
            break

        prompt = f"""当前任务: {task}
已执行 {step} 步。

请分析截图，返回 JSON:
{{
    "observation": "当前屏幕上看到了什么",
    "plan": "下一步应该做什么",
    "action": {{
        "type": "click/type/hotkey/scroll/done/wait",
        "x": 数字或null,
        "y": 数字或null,
        "text": "要输入的文字或null",
        "keys": ["热键组合"] 或 null,
        "clicks": 滚动量或null
    }},
    "done": true/false
}}"""

        analysis = await analyze_screenshot_with_llm(screenshot, prompt, settings)
        if not analysis.get("ok"):
            results.append({"step": step, "error": analysis.get("error")})
            break

        try:
            ai_response = json.loads(analysis["analysis"])
        except (json.JSONDecodeError, TypeError):
            results.append({"step": step, "raw": analysis.get("analysis", "")[:200]})
            continue

        action = ai_response.get("action", {})
        action_type = action.get("type", "")

        if ai_response.get("done") or action_type == "done":
            results.append({"step": step, "status": "task_complete", "observation": ai_response.get("observation")})
            break

        action_result = {"step": step, "action_type": action_type}
        if action_type == "click" and action.get("x") is not None:
            action_result.update(gui_click(int(action["x"]), int(action["y"])))
        elif action_type == "type" and action.get("text"):
            action_result.update(gui_type_text(action["text"]))
        elif action_type == "hotkey" and action.get("keys"):
            action_result.update(gui_hotkey(*action["keys"]))
        elif action_type == "scroll" and action.get("clicks") is not None:
            action_result.update(gui_scroll(int(action["clicks"]), action.get("x"), action.get("y")))
        elif action_type == "wait":
            time.sleep(1)
            action_result["ok"] = True
        else:
            action_result["error"] = f"unknown action: {action_type}"

        results.append(action_result)
        time.sleep(0.5)

    return {
        "ok": any(r.get("status") == "task_complete" for r in results),
        "steps": len(results),
        "results": results,
        "method": "mano-cua" if use_mano else "deepseek-vision+pyautogui",
    }
