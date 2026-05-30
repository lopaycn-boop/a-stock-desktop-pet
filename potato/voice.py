"""Voice system — 小土豆的耳朵和嘴巴。

STT (语音识别):
  1. RapidASR (首选): Paraformer 本地离线识别，中英文混合
  2. SiliconFlow SenseVoice (备选): 云端 STT API

TTS (语音合成):
  1. Edge-TTS (首选): 微软神经网络语音，免费，御姐音色 XiaoxiaoNeural
  2. SiliconFlow CosyVoice (备选): 云端 TTS API

Voice style: 御姐诱人女声 — 成熟、温柔、有磁性
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import tempfile
import wave
from pathlib import Path
from typing import Any

logger = logging.getLogger("potato.voice")

# ── Voice Configuration ──

VOICE_PROFILES = {
    "yujie": {
        "name": "御姐",
        "edge_voice": "zh-CN-XiaoxiaoNeural",
        "rate": "-5%",
        "pitch": "-2Hz",
        "description": "成熟御姐音色，温柔有磁性",
    },
    "sweet": {
        "name": "甜美",
        "edge_voice": "zh-CN-XiaoyiNeural",
        "rate": "+0%",
        "pitch": "+2Hz",
        "description": "甜美温柔少女音",
    },
    "cantonese": {
        "name": "粤语",
        "edge_voice": "zh-HK-HiuGaaiNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "description": "粤语女声",
    },
    "taiwanese": {
        "name": "台湾腔",
        "edge_voice": "zh-TW-HsiaoChenNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "description": "台湾甜美女声",
    },
}

DEFAULT_PROFILE = "yujie"


def get_voice_profile(profile_id: str = "") -> dict[str, str]:
    return VOICE_PROFILES.get(profile_id or DEFAULT_PROFILE, VOICE_PROFILES[DEFAULT_PROFILE])


# ── TTS: Edge-TTS (primary, free, offline-capable with cache) ──

async def tts_edge(
    text: str,
    profile_id: str = "",
    output_format: str = "mp3",
) -> bytes | None:
    """Generate speech using Edge-TTS (Microsoft Neural Voices).

    Returns MP3 bytes. Free, no API key needed. 御姐音色 by default.
    """
    try:
        import edge_tts

        profile = get_voice_profile(profile_id)
        comm = edge_tts.Communicate(
            text,
            voice=profile["edge_voice"],
            rate=profile["rate"],
            pitch=profile["pitch"],
        )

        buf = io.BytesIO()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])

        audio_bytes = buf.getvalue()
        if not audio_bytes:
            return None
        return audio_bytes
    except Exception as e:
        logger.warning("Edge-TTS failed: %s", e)
        return None


async def tts_edge_b64(
    text: str,
    profile_id: str = "",
) -> str | None:
    """Generate speech, return base64-encoded MP3."""
    audio = await tts_edge(text, profile_id)
    if audio:
        return base64.b64encode(audio).decode("utf-8")
    return None


# ── TTS: SiliconFlow CosyVoice (fallback, needs API key) ──

async def tts_silicon(text: str, emotion: str = "neutral") -> str | None:
    """Generate speech using SiliconFlow CosyVoice. Returns base64 MP3."""
    api_key = os.getenv("SILICON_API_KEY", "")
    base_url = os.getenv("SILICON_BASE_URL", "https://api.siliconflow.cn/v1")
    model = os.getenv("TTS_MODEL", "FunAudioLLM/CosyVoice2-0.5B")
    voice = os.getenv("TTS_VOICE", "FunAudioLLM/CosyVoice2-0.5B:anna")

    if not api_key:
        return None

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        prompt_text = f"<{emotion}>{text}"
        response = await client.audio.speech.create(
            model=model, voice=voice, input=prompt_text, response_format="mp3"
        )
        return base64.b64encode(response.content).decode("utf-8")
    except Exception as e:
        logger.warning("SiliconFlow TTS failed: %s", e)
        return None


async def text_to_speech(
    text: str,
    emotion: str = "neutral",
    profile_id: str = "",
    prefer_local: bool = True,
) -> str | None:
    """Unified TTS: try Edge-TTS first (御姐), fall back to SiliconFlow.

    Returns base64-encoded MP3 audio.
    """
    if prefer_local:
        result = await tts_edge_b64(text, profile_id)
        if result:
            return result
        logger.info("Edge-TTS unavailable, trying SiliconFlow")

    result = await tts_silicon(text, emotion)
    if result:
        return result

    if not prefer_local:
        result = await tts_edge_b64(text, profile_id)
        if result:
            return result

    logger.warning("All TTS engines failed")
    return None


# ── STT: RapidASR (primary, fully local, Paraformer ONNX) ──

_rapid_model = None
_rapid_lock = asyncio.Lock() if hasattr(asyncio, "Lock") else None


async def _get_rapid_model():
    """Lazy-load RapidParaformer model (downloads on first use)."""
    global _rapid_model
    if _rapid_model is not None:
        return _rapid_model

    try:
        from rapid_paraformer import RapidParaformer, download_hf_model
        from potato.paths import DATA_DIR as _DATA_DIR

        model_dir = _DATA_DIR / "rapid_asr"
        model_dir.mkdir(parents=True, exist_ok=True)
        config_path = model_dir / "resources" / "config.yaml"

        if not config_path.exists():
            logger.info("Downloading RapidASR Paraformer model (first time)...")
            download_hf_model(repo_id="SWHL/RapidParaformer", save_dir=str(model_dir))

        if config_path.exists():
            _rapid_model = RapidParaformer(str(config_path))
            logger.info("RapidASR model loaded (local Paraformer)")
            return _rapid_model
        else:
            logger.warning("RapidASR model not found after download")
            return None
    except ImportError:
        logger.debug("rapid_paraformer not installed")
        return None
    except Exception as e:
        logger.warning("RapidASR model load failed: %s", e)
        return None


async def stt_rapid(audio_bytes: bytes, sample_rate: int = 16000) -> str:
    """Recognize speech using RapidASR (local Paraformer).

    Accepts raw PCM bytes or WAV bytes. Returns recognized text.
    """
    model = await _get_rapid_model()
    if model is None:
        return ""

    try:
        import numpy as np

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            if audio_bytes[:4] == b"RIFF":
                f.write(audio_bytes)
            else:
                with wave.open(f, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(audio_bytes)

        result = model(tmp_path)
        os.unlink(tmp_path)

        if isinstance(result, list):
            return " ".join(result)
        return str(result) if result else ""
    except Exception as e:
        logger.warning("RapidASR recognition failed: %s", e)
        return ""


# ── STT: SiliconFlow SenseVoice (fallback, cloud) ──

async def stt_silicon(audio_base64: str) -> str:
    """Recognize speech using SiliconFlow SenseVoice. Returns text."""
    api_key = os.getenv("SILICON_API_KEY", "")
    base_url = os.getenv("SILICON_BASE_URL", "https://api.siliconflow.cn/v1")
    model = os.getenv("STT_MODEL", "FunAudioLLM/SenseVoiceSmall")

    if not api_key:
        return ""

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        audio_bytes = base64.b64decode(audio_base64)
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "input.webm"
        transcript = await client.audio.transcriptions.create(model=model, file=audio_file)
        return transcript.text
    except Exception as e:
        logger.warning("SiliconFlow STT failed: %s", e)
        return ""


async def speech_to_text(
    audio_data: str | bytes,
    prefer_local: bool = True,
) -> str:
    """Unified STT: try RapidASR first (local), fall back to SiliconFlow.

    audio_data: base64 string or raw bytes.
    """
    if prefer_local:
        raw_bytes = base64.b64decode(audio_data) if isinstance(audio_data, str) else audio_data
        result = await stt_rapid(raw_bytes)
        if result:
            return result
        logger.info("RapidASR unavailable/empty, trying SiliconFlow")

    b64_data = audio_data if isinstance(audio_data, str) else base64.b64encode(audio_data).decode()
    result = await stt_silicon(b64_data)
    if result:
        return result

    if not prefer_local:
        raw_bytes = base64.b64decode(audio_data) if isinstance(audio_data, str) else audio_data
        result = await stt_rapid(raw_bytes)
        if result:
            return result

    return ""


# ── Voice Call support (social platforms) ──

class VoiceCallSession:
    """Manages a real-time voice conversation session.

    Used for:
    1. Desktop pet real-time voice chat (WebSocket audio streaming)
    2. Social platform voice calls (Telegram voice, 飞书/钉钉 audio messages)
    """

    def __init__(self, session_id: str = "", profile_id: str = "yujie"):
        self.session_id = session_id or f"call-{id(self)}"
        self.profile_id = profile_id
        self.is_active = False
        self.turn_count = 0

    async def start(self) -> dict[str, Any]:
        self.is_active = True
        self.turn_count = 0
        profile = get_voice_profile(self.profile_id)
        logger.info("Voice call started: %s (voice: %s)", self.session_id, profile["name"])
        return {"ok": True, "session_id": self.session_id, "voice": profile["name"]}

    async def process_audio_turn(self, audio_data: str | bytes) -> dict[str, Any]:
        """Process one turn: STT → AI response → TTS.

        Returns dict with recognized text, AI reply text, and reply audio (b64).
        """
        if not self.is_active:
            return {"ok": False, "error": "call not active"}

        self.turn_count += 1

        user_text = await speech_to_text(audio_data)
        if not user_text:
            return {
                "ok": True,
                "user_text": "",
                "reply_text": "",
                "reply_audio_b64": None,
                "note": "no_speech_detected",
            }

        return {
            "ok": True,
            "user_text": user_text,
            "turn": self.turn_count,
        }

    async def generate_reply_audio(self, reply_text: str, emotion: str = "neutral") -> str | None:
        """Generate TTS audio for a reply text."""
        return await text_to_speech(reply_text, emotion, self.profile_id)

    async def end(self) -> dict[str, Any]:
        self.is_active = False
        logger.info("Voice call ended: %s (%d turns)", self.session_id, self.turn_count)
        return {"ok": True, "session_id": self.session_id, "turns": self.turn_count}


# ── Social platform voice message helpers ──

async def process_voice_message(
    audio_b64: str,
    platform: str = "telegram",
) -> dict[str, Any]:
    """Process an incoming voice message from a social platform.

    Steps: decode audio → STT → return text for AI processing.
    """
    text = await speech_to_text(audio_b64)
    return {
        "ok": bool(text),
        "platform": platform,
        "recognized_text": text,
    }


async def generate_voice_reply(
    text: str,
    emotion: str = "neutral",
    profile_id: str = "yujie",
) -> dict[str, Any]:
    """Generate a voice reply for sending back to social platform.

    Returns base64 MP3 audio ready to send.
    """
    audio_b64 = await text_to_speech(text, emotion, profile_id)
    return {
        "ok": audio_b64 is not None,
        "text": text,
        "audio_b64": audio_b64,
        "voice_profile": get_voice_profile(profile_id)["name"],
    }
