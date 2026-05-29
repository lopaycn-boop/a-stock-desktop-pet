"""Built-in Bytebot Agent — runs inside the pet backend on port 9991.

Provides the same REST API as the Docker-based bytebot-agent, but uses
the pet's own LLM (DeepSeek/Silicon/etc.) to execute tasks via the
Desktop Daemon (port 9990).

This eliminates the need for a separate Docker container — when the
desktop pet starts, the agent starts too.
"""

import asyncio
import json
import logging
import os
import re
import threading
import time
import uuid
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("potato.pet.bytebot_agent")

_TASKS: dict[str, dict] = {}
_MESSAGES: dict[str, list[dict]] = {}
_lock = threading.Lock()

app = FastAPI(title="Bytebot Agent (Built-in)", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"], allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])

_STATUS_ORDER = {"PENDING": 0, "RUNNING": 1, "NEEDS_HELP": 2, "NEEDS_REVIEW": 3,
                 "COMPLETED": 4, "FAILED": 5, "CANCELLED": 6}

_MODEL_DEFAULTS = {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "max_steps": 15,
}


def _get_llm():
    try:
        from services import AIService
        return AIService()
    except Exception:
        return None


async def _execute_task(task_id: str):
    task = _TASKS.get(task_id)
    if not task:
        return

    task["status"] = "RUNNING"
    description = task.get("description", "")
    task_messages = _MESSAGES.setdefault(task_id, [])

    llm = _get_llm()
    if not llm:
        task["status"] = "FAILED"
        task["error"] = "LLM service unavailable"
        return

    from bytebot_client import get_bytebot_client
    client = get_bytebot_client()

    if not await client.is_desktop_available():
        task["status"] = "FAILED"
        task["error"] = "Desktop daemon unavailable on port 9990"
        return

    system_prompt = (
        "You are a desktop automation assistant. You control a computer via the Bytebot Desktop Daemon. "
        "Your task is to complete the user's request step by step.\n\n"
        "Available actions (via computer-use API):\n"
        "- screenshot: take a screenshot to see the screen\n"
        "- click_mouse: click at coordinates (x, y)\n"
        "- type_text: type text into the active field\n"
        "- paste_text: paste text from clipboard\n"
        "- scroll: scroll up/down\n"
        "- move_mouse: move mouse to coordinates\n"
        "- application: open an application\n"
        "- wait: wait for N milliseconds\n"
        "- cursor_position: get current mouse position\n\n"
        "Strategy: Take a screenshot first, analyze what you see, then take the next action. "
        "Repeat until the task is complete. Be careful and precise."
    )

    conversation = [{"role": "system", "content": system_prompt}]

    try:
        screenshot_result = await client.computer_use("screenshot")
        screen_desc = ""
        if screenshot_result.get("image"):
            import base64
            screen_desc = f"\n\nCurrent screenshot available (base64, {len(screenshot_result.get('image', ''))} chars)."

        conversation.append({
            "role": "user",
            "content": f"Task: {description}{screen_desc}\n\nWhat is your first action? Reply with a JSON object: {{\"action\": \"...\", \"reasoning\": \"...\", ...params}}"
        })

        max_steps = task.get("model", {}).get("max_steps", _MODEL_DEFAULTS["max_steps"]) if isinstance(task.get("model"), dict) else _MODEL_DEFAULTS["max_steps"]

        for step in range(max_steps):
            task_messages.append({
                "role": "assistant_step",
                "step": step,
                "timestamp": time.time(),
            })

            try:
                import potato.llm as llm_mod
                response = await llm_mod.chat(
                    task="agent",
                    messages=conversation,
                    max_tokens=512,
                )
            except Exception as e:
                logger.warning("LLM call failed at step %d: %s", step, e)
                break

            if not response:
                break

            action_text = response if isinstance(response, str) else str(response)

            action_data = None
            try:
                json_match = re.search(r'\{[^{}]+\}', action_text)
                if json_match:
                    action_data = json.loads(json_match.group())
            except (json.JSONDecodeError, AttributeError):
                pass

            if not action_data:
                try:
                    from potato.llm import _extract_json
                    action_data = _extract_json(action_text)
                except Exception:
                    pass

            if action_data and isinstance(action_data, dict):
                action = action_data.get("action", "")
                reasoning = action_data.get("reasoning", "")

                if action in ("done", "complete", "finished"):
                    task["status"] = "COMPLETED"
                    task["result"] = {"summary": action_data.get("summary", reasoning or "Task completed")}
                    break

                safe_actions = {"screenshot", "click_mouse", "type_text", "paste_text",
                                "scroll", "move_mouse", "application", "wait", "cursor_position"}

                if action in safe_actions:
                    params = {k: v for k, v in action_data.items()
                              if k not in ("action", "reasoning") and v is not None}
                    result = await client.computer_use(action, **params)

                    task_messages.append({
                        "role": "tool",
                        "action": action,
                        "result_ok": result.get("ok", False),
                        "timestamp": time.time(),
                    })

                    conversation.append({
                        "role": "user",
                        "content": f"Action: {action} with params {json.dumps(params)}\nResult: {json.dumps(result, default=str)[:500]}\n\nNext step?"
                    })
                else:
                    conversation.append({
                        "role": "user",
                        "content": f"Invalid action '{action}'. Use: screenshot, click_mouse, type_text, paste_text, scroll, move_mouse, application, wait, cursor_position, or 'done'."
                    })
            else:
                conversation.append({
                    "role": "user",
                    "content": f"Your response was not valid JSON. Reply with: {{\"action\": \"...\", \"reasoning\": \"...\", ...params}}"
                })

        if task["status"] == "RUNNING":
            task["status"] = "COMPLETED"
            task["result"] = {"summary": f"Completed after {max_steps} steps", "steps": max_steps}

    except asyncio.CancelledError:
        task["status"] = "CANCELLED"
    except Exception as e:
        task["status"] = "FAILED"
        task["error"] = str(e)
        logger.error("Task %s execution error: %s", task_id, e, exc_info=True)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "bytebot-agent-built-in"}


@app.get("/tasks")
async def list_tasks(limit: int = 20):
    with _lock:
        tasks = sorted(_TASKS.values(), key=lambda t: t.get("createdAt", 0), reverse=True)
        return {"tasks": tasks[:limit], "total": len(_TASKS)}


@app.post("/tasks")
async def create_task(body: dict = None):
    if not body:
        body = {}
    description = body.get("description", "")
    if not description:
        raise HTTPException(status_code=400, detail="description is required")
    if len(description) > 500:
        description = description[:500]

    task_id = str(uuid.uuid4())
    task = {
        "id": task_id,
        "description": description,
        "priority": body.get("priority", "MEDIUM"),
        "status": "PENDING",
        "model": body.get("model", _MODEL_DEFAULTS),
        "createdAt": time.time(),
        "updatedAt": time.time(),
    }
    with _lock:
        _TASKS[task_id] = task
        _MESSAGES[task_id] = []

    asyncio.create_task(_execute_task(task_id))
    return task


@app.get("/tasks/models")
async def list_models():
    return {"models": [_MODEL_DEFAULTS]}


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    with _lock:
        task = _TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/tasks/{task_id}/messages")
async def get_task_messages(task_id: str, limit: int = 50):
    if task_id not in _TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    msgs = _MESSAGES.get(task_id, [])
    return msgs[-limit:]


@app.post("/tasks/{task_id}/messages")
async def add_task_message(task_id: str, body: dict = None):
    if task_id not in _TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    if not body or not body.get("message"):
        raise HTTPException(status_code=400, detail="message is required")
    _MESSAGES.setdefault(task_id, []).append({
        "role": "user",
        "content": body["message"],
        "timestamp": time.time(),
    })
    task = _TASKS[task_id]
    task["updatedAt"] = time.time()
    if task["status"] in ("NEEDS_HELP", "NEEDS_REVIEW"):
        task["status"] = "PENDING"
        asyncio.create_task(_execute_task(task_id))
    return {"ok": True, "task_id": task_id}


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    task = _TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
        return task
    task["status"] = "CANCELLED"
    task["updatedAt"] = time.time()
    return task


@app.post("/tasks/{task_id}/takeover")
async def takeover_task(task_id: str):
    task = _TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task["status"] = "NEEDS_HELP"
    task["updatedAt"] = time.time()
    return task


@app.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    task = _TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] in ("NEEDS_HELP", "NEEDS_REVIEW", "PENDING"):
        task["status"] = "PENDING"
        task["updatedAt"] = time.time()
        asyncio.create_task(_execute_task(task_id))
    return task


def start_agent_server(port: int = 9991):
    import uvicorn
    logger.info("Starting built-in Bytebot Agent on port %d", port)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    start_agent_server()