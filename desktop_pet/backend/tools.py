"""Screen capture tool — standalone fallback when potato.vision unavailable."""

import base64
import io
import logging

logger = logging.getLogger("potato.pet.tools")


def capture_screen_base64():
    try:
        import pyautogui
        screenshot = pyautogui.screenshot()
        width, height = screenshot.size
        if width > 640:
            scale = 640 / width
            screenshot = screenshot.resize((640, int(height * scale)))
        buffered = io.BytesIO()
        screenshot.save(buffered, format="JPEG", quality=70)
        return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        logger.warning("Screenshot failed: %s", e)
        return None
