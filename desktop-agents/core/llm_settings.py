import os
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QSettings

try:
    import keyring
except ImportError:
    keyring = None

DEFAULT_PROVIDER = "deepseek"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
SETTINGS_ORG = "DesktopAgents"
SETTINGS_APP = "DesktopAgents"
KEYRING_SERVICE = "DesktopAgents"
KEYRING_USERNAME = "LLM_API_KEY"
FALLBACK_KEY_SETTING = "llm/api_key_fallback"
MASKED_KEY = "••••••••"
ROUTE_MODE_CLOUD_WHEN_KEY = "cloud_when_key"
ROUTE_MODE_LOCAL_ONLY = "local_only"
ROUTE_MODES = {ROUTE_MODE_CLOUD_WHEN_KEY, ROUTE_MODE_LOCAL_ONLY}
DEFAULT_REPLY_ROUTE_MODE = ROUTE_MODE_CLOUD_WHEN_KEY


@dataclass
class LLMSettings:
    provider: str = DEFAULT_PROVIDER
    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    source: str = "default"
    reply_route_mode: str = DEFAULT_REPLY_ROUTE_MODE

    def masked_key(self) -> str:
        return MASKED_KEY if self.api_key else ""


def _settings() -> QSettings:
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _keyring_get() -> str:
    if keyring is None:
        return ""
    try:
        value = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        return ""
    return value or ""


def _keyring_set(api_key: str) -> bool:
    if keyring is None:
        return False
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, api_key)
        return True
    except Exception:
        return False


def load_llm_settings() -> LLMSettings:
    settings = _settings()
    env_api_key = _env("LLM_API_KEY") or _env("DEEPSEEK_API_KEY")
    env_provider = _env("LLM_PROVIDER")
    env_base_url = _env("LLM_BASE_URL") or _env("DEEPSEEK_BASE_URL")
    env_model = _env("LLM_MODEL") or _env("DEEPSEEK_MODEL")

    provider = env_provider or str(settings.value("llm/provider", DEFAULT_PROVIDER))
    base_url = env_base_url or str(settings.value("llm/base_url", DEFAULT_BASE_URL))
    model = env_model or str(settings.value("llm/model", DEFAULT_MODEL))
    reply_route_mode = _normalized_reply_route_mode(_env("LLM_REPLY_ROUTE_MODE") or str(settings.value("llm/reply_route_mode", DEFAULT_REPLY_ROUTE_MODE)))
    if env_api_key:
        return LLMSettings(provider=provider, api_key=env_api_key, base_url=base_url, model=model, source="env", reply_route_mode=reply_route_mode)

    saved_key = _keyring_get()
    if saved_key:
        return LLMSettings(provider=provider, api_key=saved_key, base_url=base_url, model=model, source="keyring", reply_route_mode=reply_route_mode)
    fallback_key = str(settings.value(FALLBACK_KEY_SETTING, "") or "").strip()
    if fallback_key:
        return LLMSettings(provider=provider, api_key=fallback_key, base_url=base_url, model=model, source="settings", reply_route_mode=reply_route_mode)
    return LLMSettings(provider=provider, api_key="", base_url=base_url, model=model, source="settings", reply_route_mode=reply_route_mode)


def has_api_key() -> bool:
    return bool(load_llm_settings().api_key.strip())


def load_reply_route_mode() -> str:
    return load_llm_settings().reply_route_mode


def _normalized_reply_route_mode(value: str) -> str:
    return value if value in ROUTE_MODES else DEFAULT_REPLY_ROUTE_MODE


def save_llm_settings(settings: LLMSettings, replace_key: bool = True) -> None:
    store = _settings()
    store.setValue("llm/provider", settings.provider.strip() or DEFAULT_PROVIDER)
    store.setValue("llm/base_url", settings.base_url.strip() or DEFAULT_BASE_URL)
    store.setValue("llm/model", settings.model.strip() or DEFAULT_MODEL)
    store.setValue("llm/reply_route_mode", _normalized_reply_route_mode(settings.reply_route_mode))
    store.sync()
    if replace_key and settings.api_key.strip():
        api_key = settings.api_key.strip()
        _keyring_set(api_key)
        store.setValue(FALLBACK_KEY_SETTING, api_key)
        store.sync()


def settings_to_client_kwargs(settings: LLMSettings) -> dict[str, Any]:
    return {
        "provider": settings.provider,
        "api_key": settings.api_key,
        "base_url": settings.base_url,
        "model": settings.model,
    }
