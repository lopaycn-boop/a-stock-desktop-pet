import logging
import os
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
        app_data = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        fallback = app_data / "potato-desktop-pet" / "data"
        fallback.mkdir(parents=True, exist_ok=True)
        logger.info("Data dir fallback: %s (original %s not writable)", fallback, _DEFAULT_DATA_DIR)
        return fallback


DATA_DIR = _resolve_data_dir()