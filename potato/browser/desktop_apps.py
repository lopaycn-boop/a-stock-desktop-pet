"""Desktop app launcher — detect and open installed A-stock trading applications.

If the user has an A-stock app installed on their computer (e.g. 东方财富, 同花顺),
小土豆 can directly launch it instead of using the browser.

Supports: Windows / macOS / Linux
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("potato.browser.desktop_apps")

SYSTEM = platform.system()


@dataclass
class DesktopApp:
    """A known stock trading desktop application."""
    app_id: str
    name: str
    platform_id: str
    win_exe: list[str] = field(default_factory=list)
    win_paths: list[str] = field(default_factory=list)
    mac_bundle: str = ""
    linux_bin: list[str] = field(default_factory=list)
    linux_desktop: str = ""


KNOWN_APPS: list[DesktopApp] = [
    DesktopApp(
        app_id="eastmoney",
        name="东方财富",
        platform_id="eastmoney",
        win_exe=["eastmoney.exe", "em.exe"],
        win_paths=[
            r"C:\eastmoney",
            r"C:\Program Files\eastmoney",
            r"C:\Program Files (x86)\eastmoney",
        ],
        mac_bundle="com.eastmoney.mac",
    ),
    DesktopApp(
        app_id="tonghuashun",
        name="同花顺",
        platform_id="tonghuashun",
        win_exe=["hexin.exe", "THS.exe"],
        win_paths=[
            r"C:\同花顺软件\同花顺",
            r"C:\Program Files\同花顺",
            r"C:\Program Files (x86)\同花顺",
        ],
        mac_bundle="com.10jqka.mac",
    ),
    DesktopApp(
        app_id="xueqiu",
        name="雪球",
        platform_id="xueqiu",
        mac_bundle="com.xueqiu.mac",
    ),
]


def _find_win_exe(app: DesktopApp) -> str | None:
    for base in app.win_paths:
        base_path = Path(base)
        if not base_path.exists():
            continue
        for exe_name in app.win_exe:
            for p in base_path.rglob(exe_name):
                return str(p)
    for exe_name in app.win_exe:
        found = shutil.which(exe_name)
        if found:
            return found
    return None


def _find_mac_app(app: DesktopApp) -> str | None:
    if not app.mac_bundle:
        return None
    result = subprocess.run(
        ["mdfind", f"kMDItemCFBundleIdentifier == '{app.mac_bundle}'"],
        capture_output=True, text=True, timeout=5,
    )
    paths = result.stdout.strip().split("\n")
    if paths and paths[0]:
        return paths[0]
    return None


def _find_linux_bin(app: DesktopApp) -> str | None:
    for name in app.linux_bin:
        found = shutil.which(name)
        if found:
            return found
    if app.linux_desktop:
        desktop_path = Path(f"/usr/share/applications/{app.linux_desktop}")
        if desktop_path.exists():
            return str(desktop_path)
    return None


def detect_installed_apps() -> list[dict[str, Any]]:
    """Scan the system for installed stock trading apps."""
    found = []
    for app in KNOWN_APPS:
        path = None
        try:
            if SYSTEM == "Windows":
                path = _find_win_exe(app)
            elif SYSTEM == "Darwin":
                path = _find_mac_app(app)
            elif SYSTEM == "Linux":
                path = _find_linux_bin(app)
        except Exception as exc:
            logger.debug("Detection error for %s: %s", app.app_id, exc)
            continue

        if path:
            found.append({
                "app_id": app.app_id,
                "name": app.name,
                "platform_id": app.platform_id,
                "path": path,
                "system": SYSTEM,
            })
    return found


def launch_app(app_id: str) -> dict[str, Any]:
    """Launch a stock trading app by app_id."""
    app = next((a for a in KNOWN_APPS if a.app_id == app_id), None)
    if not app:
        return {"ok": False, "error": f"Unknown app: {app_id}"}

    try:
        if SYSTEM == "Windows":
            path = _find_win_exe(app)
            if path:
                subprocess.Popen([path], shell=False)
                return {"ok": True, "app": app.name, "path": path, "method": "exe"}

        elif SYSTEM == "Darwin":
            path = _find_mac_app(app)
            if path:
                subprocess.Popen(["open", path])
                return {"ok": True, "app": app.name, "path": path, "method": "open"}
            if app.mac_bundle:
                subprocess.Popen(["open", "-b", app.mac_bundle])
                return {"ok": True, "app": app.name, "bundle": app.mac_bundle, "method": "bundle"}

        elif SYSTEM == "Linux":
            path = _find_linux_bin(app)
            if path:
                if path.endswith(".desktop"):
                    subprocess.Popen(["xdg-open", path])
                else:
                    subprocess.Popen([path])
                return {"ok": True, "app": app.name, "path": path, "method": "bin"}

        return {"ok": False, "app": app.name, "error": "App not found on this system"}

    except Exception as exc:
        return {"ok": False, "app": app.name, "error": str(exc)}


def launch_or_browser(platform_id: str) -> dict[str, Any]:
    """Try to launch the desktop app first; fall back to browser if not installed."""
    matching = [a for a in KNOWN_APPS if a.platform_id == platform_id]
    for app in matching:
        result = launch_app(app.app_id)
        if result.get("ok"):
            return {**result, "mode": "desktop_app"}

    return {"ok": False, "mode": "browser_fallback", "platform_id": platform_id,
            "hint": "Desktop app not found, will use browser instead"}
