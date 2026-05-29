import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
ROOT = BACKEND_DIR.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _vault_get(key_name: str) -> str:
    try:
        from potato.vault import Vault
        val = Vault().get(key_name)
        if val:
            return val
    except Exception:
        pass
    return ""


def _resolve_key(env_var: str, vault_key: str, override_dict: dict) -> str:
    return override_dict.get(vault_key) or os.getenv(env_var, "") or _vault_get(vault_key)


_OVERRIDES = {}


class Config:
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL = os.getenv("POTATO_LLM_MODEL", "deepseek-chat").split("/")[-1]

    SILICON_BASE = os.getenv("SILICON_BASE_URL", "https://api.siliconflow.cn/v1")
    TTS_MODEL = os.getenv("TTS_MODEL", "FunAudioLLM/CosyVoice2-0.5B")
    TTS_VOICE = os.getenv("TTS_VOICE", "FunAudioLLM/CosyVoice2-0.5B:anna")
    STT_MODEL = os.getenv("STT_MODEL", "FunAudioLLM/SenseVoiceSmall")

    POTATO_API_URL = os.getenv("POTATO_API_URL", "http://127.0.0.1:8080")
    POTATO_API_KEY = os.getenv("POTATO_API_KEY", "")

    @staticmethod
    def get_llm_key():
        return _OVERRIDES.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "") or _vault_get("DEEPSEEK_API_KEY")

    @staticmethod
    def get_silicon_key():
        return _OVERRIDES.get("SILICON_API_KEY") or os.getenv("SILICON_API_KEY", "") or _vault_get("SILICON_API_KEY")

    @staticmethod
    def get_liner_key():
        return _OVERRIDES.get("LINER_API_KEY") or os.getenv("LINER_API_KEY", "") or _vault_get("LINER_API_KEY")

    @staticmethod
    def get_openai_key():
        return _OVERRIDES.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "") or _vault_get("OPENAI_API_KEY")

    @staticmethod
    def set_override(key, value):
        _OVERRIDES[key] = value


Config.LLM_API_KEY = Config.get_llm_key()
Config.SILICON_KEY = Config.get_silicon_key()
Config.LINER_KEY = Config.get_liner_key()
Config.OPENAI_KEY = Config.get_openai_key()