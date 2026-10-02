"""AI providers: answering questions and turning unknown phrases into actions.

OpenRouter (free models), Ollama (runs on this PC), DeepSeek (paid API) and any OpenAI-compatible
API share one client: all of them speak the /chat/completions protocol (Ollama is called through
its own /api/chat to raise the context size).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from . import __version__, catalog
from .actions import AI_SAFE_ACTIONS
from .util import time_vars

log = logging.getLogger("jarvis.ai")

DEEPSEEK_URL = "https://api.deepseek.com"
OPENROUTER_URL = "https://openrouter.ai/api/v1"
OLLAMA_URL = "http://localhost:11434"
FALLBACK_MODEL = "deepseek-v4-flash"
FREE_ROUTER = "openrouter/free"  # OpenRouter picks any free model that supports the request
OLLAMA_SUGGESTED = "qwen2.5:7b"
OPENROUTER_FREE_PER_DAY = (50, 1000)  # free-model requests a day: never paid / after buying $10 of credits
MODELS_TTL = 6 * 3600

PROVIDERS: dict[str, dict[str, str]] = {
    "openrouter": {"name": "OpenRouter", "key": "openrouter_api_key"},
    "ollama": {"name": "Ollama", "url": "ollama_url"},
    "deepseek": {"name": "DeepSeek", "key": "ai_api_key"},
    "custom": {"name": "API", "key": "custom_api_key", "url": "custom_url"},
}


def _t(lang: str, ru: str, en: str) -> str:
    return en if lang == "en" else ru


class AIError(RuntimeError):
    """A user-readable error. `hint` says how to fix it; `code` is its kind: no_key, auth, no_balance,
    daily_limit, rate_limit, busy, privacy, offline, timeout, model, no_models, empty, ..."""

    def __init__(self, message: str, *, status: int | None = None, detail: str = "", hint: str = "",
                 code: str = "error"):
        super().__init__(message)
        self.status = status
        self.detail = detail
        self.hint = hint
        self.code = code


@dataclass(frozen=True)
class Conn:
    """Where and how to reach the provider."""
    provider: str
    base: str  # OpenAI-compatible base URL
    key: str = ""
    lang: str = "ru"
    root: str = ""  # Ollama server address

    @property
    def name(self) -> str:
        if self.provider == "custom":
            return urllib.parse.urlsplit(self.base).hostname or "API"
        return PROVIDERS[self.provider]["name"]

    @property
    def needs_key(self) -> bool:
        return self.provider in ("deepseek", "openrouter")


def ollama_root(url: str | None) -> str:
    url = (url or "").strip() or OLLAMA_URL
    if "://" not in url:
        url = "http://" + url
    url = url.rstrip("/")
    for suffix in ("/v1", "/api"):
        if url.endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")
    return url


def api_base(url: str | None) -> str:
    """Normalise a user-entered OpenAI-compatible API address."""
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        host = url.split("/")[0].split(":")[0]
        local = host in ("localhost", "127.0.0.1") or host.startswith(("192.168.", "10."))
        url = ("http://" if local else "https://") + url
    url = url.rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if url.endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")
    return url


# --- choosing a model ---------------------------------------------------------------------------
_NOT_CHAT = ("embed", "guard", "whisper", "tts", "audio", "image", "vision", "-vl", "ocr", "rerank",
             "moderation", "bge", "minilm")
_REASONING = ("r1", "reason", "think", "qwq", "gpt-oss")  # slow for a voice assistant
_FREE_PREFER = (
    "deepseek/deepseek-chat", "deepseek/deepseek-v3", "moonshotai/kimi-k2", "meta-llama/llama-3.3-70b",
    "qwen/qwen3-235b", "google/gemma-3-27b", "mistralai/mistral-small", "meta-llama/llama-4", "z-ai/glm",
    "qwen/", "google/gemma", "mistralai/", "meta-llama/", "deepseek/", "openai/",
)
_LOCAL_PREFER = ("qwen2.5", "qwen3", "gemma3", "llama3.1", "llama3.3", "llama3", "mistral", "gemma", "phi")


def _version_key(model_id: str) -> tuple:
    nums = re.findall(r"\d+", model_id)
    return tuple(int(n) for n in nums)


def pick_model(models: list[str]) -> str:
    """DeepSeek: prefer the newest fast chat model: deepseek-v4.1-flash > deepseek-v4-flash > deepseek-chat."""
    usable = [m for m in models if "expire" not in m and "embed" not in m]
    flash = sorted((m for m in usable if "flash" in m), key=_version_key, reverse=True)
    if flash:
        return flash[0]
    if "deepseek-chat" in usable:
        return "deepseek-chat"
    plain = [m for m in usable if "reason" not in m and "think" not in m]
    return (plain or usable or [FALLBACK_MODEL])[0]


def _size_b(model_id: str) -> float | None:
    """Parameter count in billions taken from a model name ("llama-3.3-70b" -> 70)."""
    sizes = [float(n) for n in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)b(?![a-z])", model_id.lower())]
    return max(sizes) if sizes else None


def is_free_model(model: dict[str, Any]) -> bool:
    if str(model.get("id") or "").endswith(":free"):
        return True
    pricing = model.get("pricing") or {}
    try:
        return float(pricing.get("prompt")) == 0 and float(pricing.get("completion")) == 0
    except (TypeError, ValueError):
        return False


def rank_free_models(models: list[dict[str, Any]]) -> list[str]:
    """Free OpenRouter chat models, best first: fast non-reasoning models of known families."""
    ranked = []
    for model in models:
        model_id = str(model.get("id") or "")
        low = model_id.lower()
        if not model_id or low.startswith("openrouter/") or not is_free_model(model):
            continue
        outputs = (model.get("architecture") or {}).get("output_modalities") or ["text"]
        if "text" not in outputs or any(w in low for w in _NOT_CHAT):
            continue
        size = _size_b(low)
        if size is not None and size < 7:  # too small to follow the command list
            continue
        pref = next((i for i, p in enumerate(_FREE_PREFER) if low.startswith(p)), len(_FREE_PREFER))
        reasoning = any(w in low.split("/")[-1] for w in _REASONING)
        try:
            context = int(model.get("context_length") or 0)
        except (TypeError, ValueError):
            context = 0
        ranked.append((reasoning, pref, -context, model_id))
    ranked.sort()
    return [r[-1] for r in ranked]


def pick_local_model(models: list[str]) -> str:
    """Ollama: a chat model, preferring families that speak Russian well."""
    usable = [m for m in models if not any(w in m.lower() for w in _NOT_CHAT)] or list(models)

    def rank(name: str) -> tuple:
        low = name.lower().split("/")[-1]
        pref = next((i for i, p in enumerate(_LOCAL_PREFER) if low.startswith(p)), len(_LOCAL_PREFER))
        return any(w in low for w in _REASONING), pref

    return sorted(usable, key=rank)[0]


def pick_any_model(models: list[str]) -> str:
    """Any OpenAI-compatible API: the first fast chat model it lists."""
    usable = [m for m in models if not any(w in m.lower() for w in _NOT_CHAT)] or list(models)

    def rank(name: str) -> tuple:
        low = name.lower()
        fast = any(w in low for w in ("flash", "chat", "instruct", "turbo", "versatile"))
        return any(w in low for w in _REASONING), not fast

    return sorted(usable, key=rank)[0]


def _strip_thinking(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S | re.I)
    if re.match(r"\s*<think>", text, re.I):  # cut off while still "thinking"
        return ""
    return text.strip()


# --- errors -------------------------------------------------------------------------------------
def deepseek_paid_hint(lang: str) -> str:
    return _t(lang,
              "API DeepSeek платный: новый ключ не работает, пока не пополнен баланс на platform.deepseek.com "
              "(бесплатный только чат на chat.deepseek.com). Пополните баланс или выберите бесплатный "
              "провайдер OpenRouter.",
              "The DeepSeek API is paid: a new key does not work until you top up the balance on "
              "platform.deepseek.com (only the chat at chat.deepseek.com is free). Top it up or switch to the "
              "free OpenRouter provider.")


def _no_key(c: Conn) -> AIError:
    return AIError(_t(c.lang, f"Не указан ключ {c.name}", f"No {c.name} API key"),
                   hint=_t(c.lang, "Вставьте ключ в Настройки → ИИ-провайдер.",
                           "Paste the key in Settings → AI provider."), code="no_key")


def _no_local_models(c: Conn) -> AIError:
    return AIError(_t(c.lang, "В Ollama нет скачанных моделей", "Ollama has no models yet"),
                   hint=_t(c.lang, f"Откройте командную строку и выполните: ollama pull {OLLAMA_SUGGESTED}",
                           f"Open a terminal and run: ollama pull {OLLAMA_SUGGESTED}"), code="no_models")


def _offline(c: Conn, reason: Any) -> AIError:
    if c.provider == "ollama":
        return AIError(
            _t(c.lang, f"Ollama не запущена ({c.root})", f"Ollama is not running ({c.root})"),
            hint=_t(c.lang, "Установите Ollama с ollama.com и запустите её, затем скачайте модель командой "
                            f"ollama pull {OLLAMA_SUGGESTED}",
                    f"Install Ollama from ollama.com, start it and download a model: ollama pull {OLLAMA_SUGGESTED}"),
            code="offline")
    return AIError(
        _t(c.lang, f"Нет соединения с {c.name}: {reason}", f"Cannot reach {c.name}: {reason}"),
        hint=_t(c.lang, "Проверьте интернет. Если сайт недоступен в вашей стране, включите VPN или выберите "
                        "другой провайдер.",
                "Check the internet connection. If the site is blocked in your country, use a VPN or another "
                "provider."),
        code="offline")


def _timeout(c: Conn) -> AIError:
    hint = ""
    if c.provider == "ollama":
        hint = _t(c.lang, "Первый запрос загружает модель в память — это может занять минуту. Попробуйте ещё раз "
                          "или выберите модель поменьше.",
                  "The first request loads the model into memory, which can take a minute. Try again or use a "
                  "smaller model.")
    return AIError(_t(c.lang, f"{c.name} не ответил вовремя", f"{c.name} did not answer in time"),
                   hint=hint, code="timeout")


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", "replace")
    except Exception:
        return ""
    try:
        payload = json.loads(raw)
    except ValueError:
        return raw.strip()[:300]
    return _payload_error(payload)


def _payload_error(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    err = payload.get("error")
    if isinstance(err, str):
        return err
    if isinstance(err, dict):
        message = str(err.get("message") or "")
        meta = err.get("metadata")
        raw = meta.get("raw") if isinstance(meta, dict) else None
        if isinstance(raw, str) and raw and raw not in message:
            message = f"{message} ({raw[:300]})"
        return message.strip()
    return str(payload.get("message") or payload.get("detail") or "")[:300]


def _http_error(c: Conn, status: int, detail: str) -> AIError:
    lang, name, low = c.lang, c.name, detail.lower()

    def err(ru: str, en: str, code: str, hint_ru: str = "", hint_en: str = "", show_detail: bool = False):
        hint = _t(lang, hint_ru, hint_en)
        if show_detail and detail:
            hint = f"{hint} ({detail})" if hint else detail
        return AIError(_t(lang, ru, en), status=status, detail=detail, hint=hint, code=code)

    if status == 401 or (status == 403 and "key" in low):
        return err(f"Неверный ключ {name}", f"Invalid {name} API key", "auth",
                   "Скопируйте ключ ещё раз целиком, без пробелов, или создайте новый.",
                   "Copy the whole key again, without spaces, or create a new one.")
    if status == 402:
        if c.provider == "deepseek":
            return AIError(_t(lang, "На балансе DeepSeek нет денег: API DeepSeek платный. Пополните баланс или "
                                    "выберите в настройках бесплатный OpenRouter",
                              "The DeepSeek balance is empty: the DeepSeek API is paid. Top it up or choose the "
                              "free OpenRouter in the settings"),
                           status=status, detail=detail, hint=deepseek_paid_hint(lang), code="no_balance")
        if c.provider == "openrouter":
            return err("Баланс OpenRouter ниже нуля — даже бесплатные модели недоступны, пока его не пополнить",
                       "The OpenRouter balance is negative — even free models are blocked until it is topped up",
                       "no_balance")
        return err(f"Недостаточно средств на балансе {name}", f"Insufficient {name} balance", "no_balance",
                   show_detail=True)
    if status == 429:
        if c.provider == "openrouter":
            if "per-day" in low or "per day" in low:
                return err("Бесплатные запросы OpenRouter на сегодня закончились",
                           "Today's free OpenRouter requests are used up", "daily_limit",
                           f"Лимит — {OPENROUTER_FREE_PER_DAY[0]} запросов в сутки ({OPENROUTER_FREE_PER_DAY[1]} — "
                           "после разового пополнения на $10). Он обновится завтра, а пока можно выбрать Ollama.",
                           f"The limit is {OPENROUTER_FREE_PER_DAY[0]} requests a day ({OPENROUTER_FREE_PER_DAY[1]} "
                           "after a one-time $10 top-up). It resets tomorrow; meanwhile you can use Ollama.")
            if "per-min" in low or "per minute" in low:
                return err("Слишком часто: у бесплатных моделей OpenRouter не больше 20 запросов в минуту",
                           "Too fast: free OpenRouter models allow 20 requests a minute", "rate_limit")
            return err("Бесплатная модель сейчас перегружена, попробуйте через минуту",
                       "The free model is busy right now, try again in a minute", "busy",
                       "Можно выбрать другую модель в настройках ИИ.", "You can pick another model in the AI settings.")
        return err(f"Слишком много запросов к {name}, попробуйте позже",
                   f"Too many requests to {name}, try again later", "rate_limit")
    if status == 404 and "data policy" in low:
        return err("OpenRouter: бесплатные модели запрещены настройками приватности",
                   "OpenRouter: free models are blocked by your privacy settings", "privacy",
                   "Откройте openrouter.ai/settings/privacy и включите «Enable free endpoints that may publish "
                   "prompts».",
                   "Open openrouter.ai/settings/privacy and turn on “Enable free endpoints that may publish prompts”.")
    if status == 404 or (status == 400 and "model" in low and ("exist" in low or "not found" in low)):
        if c.provider == "ollama":
            m = re.search(r"model ['\"]?([^'\"\s,]+)", detail)
            model = m.group(1) if m else OLLAMA_SUGGESTED
            return err(f"Модель {model} не скачана в Ollama", f"The model {model} is not downloaded in Ollama",
                       "model", f"Выполните в командной строке: ollama pull {model}",
                       f"Run in a terminal: ollama pull {model}")
        return err(f"У {name} нет такой модели", f"{name} has no such model", "model",
                   "Выберите модель «Автоматически» в настройках ИИ.",
                   "Choose the “Automatic” model in the AI settings.", show_detail=True)
    if status == 403:
        return err(f"{name} отказал в доступе", f"{name} denied access", "forbidden", show_detail=True)
    if status in (400, 413, 422):
        return err(f"{name} отклонил запрос", f"{name} rejected the request", "bad_request", show_detail=True)
    if status >= 500:
        return err(f"Сбой на стороне {name}, попробуйте позже", f"{name} server error, try again later", "server",
                   show_detail=True)
    return err(f"Ошибка {name} ({status})", f"{name} error ({status})", "error", show_detail=True)


def _balance_text(data: dict[str, Any]) -> tuple[str, bool]:
    parts, positive = [], False
    for info in data.get("balance_infos") or []:
        try:
            total = float(info.get("total_balance") or 0)
        except (TypeError, ValueError):
            total = 0.0
        positive = positive or total > 0
        parts.append(f"{total:.2f} {info.get('currency') or ''}".strip())
    return ", ".join(parts), positive


# --- client -------------------------------------------------------------------------------------
class AIClient:
    def __init__(self, settings):
        self._settings = settings  # anything with .get(key)
        self._lock = threading.Lock()
        self._auto: dict[tuple[str, str, str], list[str]] = {}
        self._router_models: tuple[float, list[dict[str, Any]]] | None = None
        self._unsupported: set[tuple[str, str]] = set()  # (provider, request field) the API rejected

    def _setting(self, key: str, default: Any = "") -> Any:
        try:
            value = self._settings.get(key)
        except KeyError:
            value = None
        return default if value is None else value

    def conn(self, provider: str | None = None, key: str | None = None, url: str | None = None) -> Conn:
        if provider not in PROVIDERS:
            provider = self._setting("ai_provider", "deepseek")
        if provider not in PROVIDERS:
            provider = "deepseek"
        spec = PROVIDERS[provider]
        if key is None:
            key = self._setting(spec["key"]) if "key" in spec else ""
        if url is None:
            url = self._setting(spec["url"]) if "url" in spec else ""
        key = str(key or "").strip()
        lang = self._setting("language", "ru")
        if provider == "deepseek":
            return Conn(provider, DEEPSEEK_URL, key, lang)
        if provider == "openrouter":
            return Conn(provider, OPENROUTER_URL, key, lang)
        if provider == "ollama":
            root = ollama_root(url)
            return Conn(provider, root + "/v1", "", lang, root)
        return Conn(provider, api_base(url), key, lang)

    @property
    def configured(self) -> bool:
        c = self.conn()
        return bool(c.key) if c.needs_key else bool(c.base)

    # --- HTTP -------------------------------------------------------------------------------
    def _request(self, c: Conn, method: str, path: str, body: dict | None = None, timeout: float = 30,
                 base: str | None = None, auth: bool = True) -> Any:
        if auth and c.needs_key and not c.key:
            raise _no_key(c)
        base = base or c.base
        if not base:
            raise AIError(_t(c.lang, "Не указан адрес API", "The API address is empty"),
                          hint=_t(c.lang, "Укажите адрес в Настройки → ИИ-провайдер.",
                                  "Enter it in Settings → AI provider."), code="url")
        headers = {"Accept": "application/json", "User-Agent": f"Jarvis/{__version__}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if auth and c.key:
            headers["Authorization"] = f"Bearer {c.key}"
        if c.provider == "openrouter":
            headers["X-Title"] = "Jarvis"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = _error_detail(exc)
            log.info("%s %s %s -> HTTP %s %s", c.name, method, path, exc.code, detail[:300])
            raise _http_error(c, exc.code, detail) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise _timeout(c) from exc
            raise _offline(c, exc.reason) from exc
        except TimeoutError as exc:
            raise _timeout(c) from exc
        except OSError as exc:  # connection reset while reading
            raise _offline(c, exc) from exc
        try:
            return json.loads(raw.decode("utf-8")) if raw.strip() else {}
        except ValueError as exc:
            raise AIError(_t(c.lang, f"Непонятный ответ от {c.name}", f"Unexpected answer from {c.name}"),
                          code="bad_response") from exc

    # --- models -----------------------------------------------------------------------------
    def list_models(self, c: Conn) -> list[str]:
        """Models the provider offers (for OpenRouter: free ones, best first)."""
        if c.provider == "openrouter":
            return rank_free_models(self._openrouter_models(c))
        if c.provider == "ollama":
            data = self._request(c, "GET", "/api/tags", timeout=8, base=c.root)
            return [m.get("name") or m.get("model") for m in data.get("models") or []
                    if isinstance(m, dict) and (m.get("name") or m.get("model"))]
        data = self._request(c, "GET", "/models", timeout=15)
        return [m["id"] for m in data.get("data") or [] if isinstance(m, dict) and m.get("id")]

    def _openrouter_models(self, c: Conn) -> list[dict[str, Any]]:
        with self._lock:
            if self._router_models and time.time() - self._router_models[0] < MODELS_TTL:
                return self._router_models[1]
        data = self._request(c, "GET", "/models", timeout=20, auth=False)  # public list
        models = [m for m in data.get("data") or [] if isinstance(m, dict)]
        with self._lock:
            self._router_models = (time.time(), models)
        return models

    def candidates(self, c: Conn) -> list[str]:
        """Models to try, best first: the one chosen in the settings or the automatic choice."""
        chosen = str(self._setting("ai_model", "auto") or "auto").strip()
        if chosen != "auto":
            return [chosen]
        cache_key = (c.provider, c.base, c.key)
        with self._lock:
            if cache_key in self._auto:
                return self._auto[cache_key]
        if c.provider == "ollama":
            models = self.list_models(c)
            if not models:
                raise _no_local_models(c)
            found = [pick_local_model(models)]
        elif c.provider == "custom":
            try:
                models = self.list_models(c)
            except AIError as exc:
                if exc.code in ("auth", "offline", "timeout", "url"):
                    raise
                models = []
            if not models:
                raise AIError(_t(c.lang, "Укажите модель в настройках ИИ", "Enter a model in the AI settings"),
                              hint=_t(c.lang, "Сервис не сообщил список моделей — впишите название модели вручную.",
                                      "The service did not list its models — type the model name."), code="model")
            found = [pick_any_model(models)]
        else:
            try:
                if c.provider == "deepseek":
                    found = [pick_model(self.list_models(c))]
                else:
                    found = [*self.list_models(c)[:2], FREE_ROUTER]
            except AIError as exc:
                if exc.code in ("auth", "no_key"):
                    raise
                log.warning("Cannot list %s models: %s", c.name, exc)
                return [FALLBACK_MODEL] if c.provider == "deepseek" else [FREE_ROUTER]
        with self._lock:
            self._auto[cache_key] = found
        return found

    def _forget(self, c: Conn) -> None:
        with self._lock:
            self._auto.pop((c.provider, c.base, c.key), None)

    # --- chat -------------------------------------------------------------------------------
    def chat(self, messages: list[dict[str, str]], json_mode: bool = False, max_tokens: int = 700,
             temperature: float = 0.5) -> str:
        return self.complete(self.conn(), messages, json_mode, max_tokens, temperature)[0]

    def complete(self, c: Conn, messages: list[dict[str, str]], json_mode: bool = False, max_tokens: int = 700,
                 temperature: float = 0.5) -> tuple[str, str]:
        """-> (answer, the model that answered)"""
        if c.needs_key and not c.key:
            raise _no_key(c)
        models = self.candidates(c)
        if c.provider in ("openrouter", "ollama"):
            max_tokens = max(max_tokens, 1500)  # free and local models may "think" before answering
        if c.provider == "ollama":
            content, used = self._ollama_chat(c, models[0], messages, json_mode, max_tokens, temperature)
        else:
            content, used = self._openai_chat(c, models, messages, json_mode, max_tokens, temperature)
        content = _strip_thinking(content)
        if not content:
            raise AIError(_t(c.lang, f"Модель {used} вернула пустой ответ", f"The model {used} returned nothing"),
                          hint=_t(c.lang, "Выберите другую модель в настройках ИИ.",
                                  "Pick another model in the AI settings."), code="empty")
        return content, used

    def _openai_chat(self, c: Conn, models: list[str], messages: list[dict[str, str]], json_mode: bool,
                     max_tokens: int, temperature: float) -> tuple[str, str]:
        body: dict[str, Any] = {"model": models[0], "messages": messages, "max_tokens": max_tokens,
                                "temperature": temperature, "stream": False}
        if c.provider == "openrouter" and len(models) > 1:
            body["models"] = models[:3]  # OpenRouter falls back to the next one when a model is busy
        if json_mode and (c.provider, "response_format") not in self._unsupported:
            body["response_format"] = {"type": "json_object"}
        if c.provider == "deepseek" and (c.provider, "thinking") not in self._unsupported:
            body["thinking"] = {"type": "disabled"}
        auto = str(self._setting("ai_model", "auto") or "auto") == "auto"
        switched = False
        while True:
            try:
                data = self._request(c, "POST", "/chat/completions", body, timeout=90)
                if not data.get("choices") and data.get("error"):
                    error = data["error"] if isinstance(data["error"], dict) else {}
                    code = error.get("code")
                    raise _http_error(c, code if isinstance(code, int) else 500, _payload_error(data))
                break
            except AIError as exc:
                change = self._adapt(c, body, exc, can_switch=auto and not switched)
                if not change:
                    raise
                log.info("%s: retrying the request (%s)", c.name, change)
                switched = switched or change == "model"
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError(_t(c.lang, f"Непонятный ответ от {c.name}", f"Unexpected answer from {c.name}"),
                          code="bad_response") from exc
        content = message.get("content") or ""
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return str(content), str(data.get("model") or body["model"])

    def _adapt(self, c: Conn, body: dict[str, Any], exc: AIError, can_switch: bool) -> str:
        """Change the request after an error the API explains; '' when there is nothing else to try."""
        detail = exc.detail.lower()
        if "thinking" in body and exc.status in (400, 422) and "thinking" in detail:
            body.pop("thinking")
            self._unsupported.add((c.provider, "thinking"))
            return "thinking"
        if "response_format" in body and (
                (exc.status in (400, 422) and ("response_format" in detail or "json" in detail))
                or (exc.status == 404 and "endpoint" in detail and "data policy" not in detail)):
            body.pop("response_format")
            if c.provider != "openrouter":  # there it depends on the model
                self._unsupported.add((c.provider, "response_format"))
            return "response_format"
        if "models" in body and exc.status == 400 and "models" in detail:
            body.pop("models")
            return "models"
        if not can_switch or exc.code not in ("model", "busy"):
            return ""
        if c.provider == "openrouter":
            if body["model"] == FREE_ROUTER:
                return ""
            body["model"] = FREE_ROUTER
            body.pop("models", None)
            return "model"
        self._forget(c)
        try:
            model = self.candidates(c)[0]
        except AIError:
            return ""
        if model == body["model"]:
            return ""
        body["model"] = model
        return "model"

    def _ollama_chat(self, c: Conn, model: str, messages: list[dict[str, str]], json_mode: bool,
                     max_tokens: int, temperature: float) -> tuple[str, str]:
        body: dict[str, Any] = {
            "model": model, "messages": messages, "stream": False, "keep_alive": "30m",
            # the command list does not fit into Ollama's default context
            "options": {"num_ctx": 8192, "temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"
        try:
            data = self._request(c, "POST", "/api/chat", body, timeout=240, base=c.root)
        except AIError as exc:
            if exc.code == "model":
                self._forget(c)
            raise
        message = data.get("message") or {}
        return str(message.get("content") or ""), str(data.get("model") or model)

    # --- settings page ----------------------------------------------------------------------
    def test(self, provider: str | None = None, key: str | None = None, url: str | None = None) -> dict[str, Any]:
        """Check the provider for real: the key, the balance and one small request."""
        c = self.conn(provider, key, url)
        result: dict[str, Any] = {"provider": c.provider, "name": c.name}
        try:
            if c.needs_key and not c.key:
                raise _no_key(c)
            if c.provider == "deepseek":
                result.update(self._deepseek_account(c))
            elif c.provider == "openrouter":
                result.update(self._openrouter_account(c))
            try:
                result["models"] = self.list_models(c)
            except AIError as exc:
                if c.provider == "ollama" or exc.code in ("auth", "offline", "timeout", "url"):
                    raise
                result["models"] = []
            if c.provider == "ollama" and not result["models"]:
                raise _no_local_models(c)
            ping = [{"role": "user",
                     "content": _t(c.lang, "Ответь одним словом: готов.", "Reply with one word: ready.")}]
            _, used = self.complete(c, ping, max_tokens=300, temperature=0)
            result.update(ok=True, model=used)
        except AIError as exc:
            result.update(ok=False, error=str(exc), hint=exc.hint, code=exc.code)
        return result

    def _deepseek_account(self, c: Conn) -> dict[str, Any]:
        try:
            data = self._request(c, "GET", "/user/balance", timeout=15)
        except AIError as exc:
            if exc.code in ("auth", "offline", "timeout"):
                raise
            log.info("DeepSeek balance is unavailable: %s", exc)
            return {}
        balance, positive = _balance_text(data)
        if data.get("is_available") is False or (data.get("balance_infos") and not positive):
            raise AIError(_t(c.lang, f"Ключ верный, но на балансе DeepSeek {balance or '0'}",
                             f"The key is valid, but the DeepSeek balance is {balance or '0'}"),
                          hint=deepseek_paid_hint(c.lang), code="no_balance")
        return {"balance": balance} if balance else {}

    def _openrouter_account(self, c: Conn) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for path in ("/key", "/auth/key"):
            try:
                data = self._request(c, "GET", path, timeout=15)
                break
            except AIError as exc:
                if exc.code in ("auth", "offline", "timeout"):
                    raise
                log.info("OpenRouter %s: %s", path, exc)
        info = data.get("data") or {}
        paid = info.get("is_free_tier") is False
        return {"free_per_day": OPENROUTER_FREE_PER_DAY[1] if paid else OPENROUTER_FREE_PER_DAY[0]}


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


class AIAssistant:
    """Builds prompts with the user's commands and validates what the model proposes."""

    def __init__(self, client: AIClient, store):
        self.client = client
        self.store = store
        self._history: deque[dict[str, str]] = deque(maxlen=8)

    @property
    def available(self) -> bool:
        return self.client.configured

    def _persona(self, lang: str) -> str:
        now = datetime.now()
        tv = time_vars(lang, now)
        if lang == "en":
            return (f"You are J.A.R.V.I.S., a polite, witty voice assistant on the user's Windows PC. "
                    f"Address the user as 'sir'. Now: {tv['weekday']}, {tv['date']} {now.year}, {tv['time']}. "
                    "Answers are spoken aloud: be brief (1-3 sentences), no markdown, no lists, no emoji.")
        return (f"Ты — Д.Ж.А.Р.В.И.С., вежливый голосовой ассистент с лёгкой иронией на компьютере пользователя "
                f"(Windows). Обращайся «сэр». Сейчас {tv['weekday']}, {tv['date']} {now.year} года, {tv['time']}. "
                "Ответ будет озвучен голосом: отвечай кратко (1–3 предложения), без markdown, списков и эмодзи.")

    def ask(self, prompt: str, lang: str = "ru") -> str:
        """Free-form question -> short spoken answer."""
        messages = [{"role": "system", "content": self._persona(lang)}, *self._history,
                    {"role": "user", "content": prompt}]
        answer = self.client.chat(messages, max_tokens=500)
        answer = re.sub(r"[*_#`]+", "", answer).strip()
        self._remember(prompt, answer)
        return answer

    def plan(self, text: str, lang: str = "ru") -> dict[str, Any]:
        """Unknown phrase -> {"reply": str, "actions": [...]} limited to safe actions."""
        commands = self.store.entries() if self.store is not None else []
        lines = []
        for entry in commands[:180]:
            sample = ", ".join(f"«{t.raw}»" for t in entry.triggers[:2])
            lines.append(f"- {entry.path[:-5]}: {sample}")
        connected = self.store.connected_apps() if self.store is not None else {}
        apps = ", ".join(f"{a['id']} ({catalog.app_name(a, lang)})" for a in catalog.APPS
                         if a["kind"] != "pack")
        if lang == "en":
            instructions = (
                "The user gave a voice command that matched none of the saved commands. Decide what to do and "
                'answer ONLY with JSON: {"reply": "<short phrase to speak>", "actions": [...]}.\n'
                "Allowed actions:\n")
        else:
            instructions = (
                "Пользователь дал голосовую команду, для которой не нашлось сохранённой команды. Реши, что "
                'сделать, и ответь СТРОГО в формате JSON: {"reply": "<короткая фраза для озвучивания>", '
                '"actions": [...]}.\nДопустимые действия:\n')
        instructions += (
            '- {"type":"run_command","path":"<путь команды из списка>"}\n'
            '- {"type":"open_app","app":"<id из списка приложений или название программы>"}\n'
            '- {"type":"close_app","app":"<id или название>"}\n'
            '- {"type":"open_url","url":"https://..."}\n'
            '- {"type":"search_web","query":"...","engine":"google|yandex|youtube"}\n'
            '- {"type":"hotkey","keys":"ctrl+t"}\n'
            '- {"type":"type_text","text":"..."}\n'
            '- {"type":"media","key":"play_pause|next|prev|volume_up|volume_down|mute"}\n'
            '- {"type":"system_volume","level":0-100}\n'
            '- {"type":"wait","seconds":1}\n'
        )
        if lang == "en":
            instructions += ("If it's a question or small talk, answer in \"reply\" and return an empty \"actions\" "
                             "list. Never shut down or restart the computer. Never invent commands.\n")
        else:
            instructions += ("Если это вопрос или разговор — ответь в \"reply\" и верни пустой \"actions\". "
                             "Никогда не выключай и не перезагружай компьютер. Не выдумывай команды.\n")
        context = (f"{instructions}\nКоманды пользователя:\n" + "\n".join(lines)
                   + f"\n\nИзвестные приложения: {apps}\nПодключены: {', '.join(connected) or '—'}")
        messages = [{"role": "system", "content": self._persona(lang) + "\n\n" + context}, *self._history,
                    {"role": "user", "content": text}]
        raw = self.client.chat(messages, json_mode=True, max_tokens=700, temperature=0.3)
        try:
            data = _extract_json(raw)
        except ValueError:
            data = {"reply": raw, "actions": []}
        if not isinstance(data, dict):
            data = {"reply": raw, "actions": []}
        reply = re.sub(r"[*_#`]+", "", str(data.get("reply") or "")).strip()
        actions = self._sanitize(data.get("actions") or [], {e.path for e in commands})
        self._remember(text, reply)
        return {"reply": reply, "actions": actions}

    @staticmethod
    def _sanitize(actions: Any, known_paths: set[str]) -> list[dict[str, Any]]:
        safe = []
        if not isinstance(actions, list):
            return safe
        for action in actions[:10]:
            if not isinstance(action, dict) or action.get("type") not in AI_SAFE_ACTIONS:
                continue
            if action["type"] == "run_command":
                path = str(action.get("path") or "")
                if not path.endswith(".json"):
                    path += ".json"
                if path not in known_paths:
                    continue
                action = {"type": "run_command", "path": path}
            if action["type"] == "open_url":
                url = str(action.get("url") or "")
                if not url.lower().startswith(("http://", "https://")):
                    continue
            if action["type"] == "wait":
                try:
                    seconds = float(action.get("seconds") or 1)
                except (TypeError, ValueError):
                    seconds = 1.0
                action = {"type": "wait", "seconds": max(0, min(10, seconds))}
            if action["type"] == "jarvis" and action.get("op") not in (
                    "silent_on", "silent_off", "theme_dark", "theme_light", "volume"):
                continue
            safe.append(action)
        return safe

    def _remember(self, user: str, assistant: str) -> None:
        self._history.append({"role": "user", "content": user})
        if assistant:
            self._history.append({"role": "assistant", "content": assistant})
