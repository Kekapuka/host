"""User settings stored in settings.json (API keys are encrypted with DPAPI on Windows)."""
from __future__ import annotations

import base64
import copy
import logging
import threading
from typing import Any, Callable

from . import paths
from .util import read_json, write_json_atomic

log = logging.getLogger("jarvis.settings")

DEFAULTS: dict[str, Any] = {
    "volume": 70,
    "silent": False,
    "theme": "light",
    "language": "ru",
    "animations": True,
    "voice_engine": "neural",
    "stt_language": "auto",
    "wake_word": "джарвис",
    "mic_autostart": False,
    "mic_device": None,
    "confirm_words": ["да", "правильно", "подтверждаю"],
    "cancel_words": ["нет", "отмена", "отменить"],
    "chain_words": ["и", "затем", "потом"],
    "ai_provider": "openrouter",
    "ai_api_key": "",  # DeepSeek
    "openrouter_api_key": "",
    "ollama_url": "http://localhost:11434",
    "custom_url": "",
    "custom_api_key": "",
    "ai_model": "auto",
}

CHOICES = {
    "theme": ("light", "dark"),
    "language": ("ru", "en"),
    "voice_engine": ("neural", "system"),
    "stt_language": ("auto", "ru", "en"),
    "ai_provider": ("openrouter", "ollama", "deepseek", "custom"),
}
WORD_LISTS = ("confirm_words", "cancel_words", "chain_words")
SECRETS = ("ai_api_key", "openrouter_api_key", "custom_api_key")


def _clean_words(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple)):
        raise ValueError("ожидается список слов")
    out: list[str] = []
    for item in value:
        word = " ".join(str(item).strip().lower().split())[:40]
        if word and word not in out:
            out.append(word)
    return out[:30]


def validate(key: str, value: Any) -> Any:
    if key not in DEFAULTS:
        raise KeyError(f"Неизвестная настройка: {key}")
    if key == "volume":
        return max(1, min(100, int(round(float(value)))))
    if key in ("silent", "animations", "mic_autostart"):
        return bool(value)
    if key in CHOICES:
        if value not in CHOICES[key]:
            raise ValueError(f"{key}: недопустимое значение {value!r}")
        return value
    if key == "wake_word":
        word = " ".join(str(value).strip().lower().split())[:40]
        if not word:
            raise ValueError("Префикс не может быть пустым")
        return word
    if key in WORD_LISTS:
        return _clean_words(value)
    if key == "mic_device":
        if value in (None, "", "default"):
            return None
        return str(value)[:200]
    if key in SECRETS or key in ("ollama_url", "custom_url"):
        return str(value or "").strip()[:300]
    if key == "ai_model":
        return (str(value or "").strip() or "auto")[:80]
    return value


class Settings:
    def __init__(self, path=None):
        self._path = path or paths.settings_file()
        self._lock = threading.RLock()
        self._data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self.load()

    # --- persistence ------------------------------------------------------------------------
    def load(self) -> None:
        raw = read_json(self._path, {}) or {}
        with self._lock:
            for key in DEFAULTS:
                if key in raw:
                    try:
                        self._data[key] = validate(key, raw[key])
                    except (ValueError, TypeError, KeyError) as exc:
                        log.warning("Ignoring setting %s: %s", key, exc)
            for name in SECRETS:
                enc = raw.get(f"{name}_dpapi")
                if not enc:
                    continue
                try:
                    from .winapi import dpapi_unprotect

                    self._data[name] = dpapi_unprotect(base64.b64decode(enc)).decode("utf-8")
                except Exception as exc:
                    log.warning("Cannot decrypt %s: %s", name, exc)

    def save(self) -> None:
        with self._lock:
            data = copy.deepcopy(self._data)
        for name in SECRETS:
            secret = data.pop(name, "")
            if not secret:
                continue
            if paths.IS_WINDOWS:
                try:
                    from .winapi import dpapi_protect

                    data[f"{name}_dpapi"] = base64.b64encode(dpapi_protect(secret.encode("utf-8"))).decode()
                    continue
                except Exception as exc:
                    log.warning("DPAPI failed, storing %s as plain text: %s", name, exc)
            data[name] = secret
        write_json_atomic(self._path, data)

    # --- access -----------------------------------------------------------------------------
    def get(self, key: str) -> Any:
        with self._lock:
            return copy.deepcopy(self._data[key])

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def all(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Validate and apply several values; returns {key: new_value} of what changed."""
        clean = {k: validate(k, v) for k, v in (patch or {}).items()}
        changed: dict[str, Any] = {}
        with self._lock:
            if clean.get("ai_provider", self._data["ai_provider"]) != self._data["ai_provider"]:
                clean.setdefault("ai_model", "auto")  # models differ between providers
            for key, value in clean.items():
                if self._data.get(key) != value:
                    self._data[key] = value
                    changed[key] = value
        if changed:
            self.save()
            for listener in list(self._listeners):
                try:
                    listener(changed)
                except Exception:
                    log.exception("settings listener failed")
        return changed

    def on_change(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.append(callback)
