import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("potato.paths")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_DIR = _PROJECT_ROOT / "data"


def _resolve_data_dir() -> Path:
    try:
        _DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        test_file = _DEFAULT_DATA_DIR / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return _DEFAULT_DATA_DIR
    except (PermissionError, OSError):
        if sys.platform == "darwin":
            fallback = Path.home() / "Library" / "Application Support" / "potato-desktop-pet" / "data"
        elif sys.platform == "linux":
            xdg = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
            fallback = Path(xdg) / "potato-desktop-pet" / "data"
        else:
            fallback = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "potato-desktop-pet" / "data"
        fallback.mkdir(parents=True, exist_ok=True)
        logger.info("Data dir fallback: %s (original %s not writable)", fallback, _DEFAULT_DATA_DIR)
        return fallback


DATA_DIR = _resolve_data_dir()