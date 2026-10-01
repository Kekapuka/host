"""DeepSeek integration: answering questions and turning unknown phrases into actions."""
from __future__ import annotations

import json
import logging
import re
import threading
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime
from typing import Any, Callable

from . import catalog
from .actions import AI_SAFE_ACTIONS
from .util import time_vars

log = logging.getLogger("jarvis.ai")

BASE_URL = "https://api.deepseek.com"
FALLBACK_MODEL = "deepseek-v4-flash"


class AIError(RuntimeError):
    pass


def _version_key(model_id: str) -> tuple:
    nums = re.findall(r"\d+", model_id)
    return tuple(int(n) for n in nums)


def pick_model(models: list[str]) -> str:
    """Prefer the newest fast chat model: deepseek-v4.1-flash > deepseek-v4-flash > deepseek-chat."""
    usable = [m for m in models if "expire" not in m and "embed" not in m]
    flash = sorted((m for m in usable if "flash" in m), key=_version_key, reverse=True)
    if flash:
        return flash[0]
    if "deepseek-chat" in usable:
        return "deepseek-chat"
    plain = [m for m in usable if "reason" not in m and "think" not in m]
    return (plain or usable or [FALLBACK_MODEL])[0]


class DeepSeekClient:
    def __init__(self, key_getter: Callable[[], str], model_getter: Callable[[], str]):
        self._key = key_getter
        self._model_setting = model_getter
        self._resolved: str | None = None
        self._resolved_for_key: str | None = None
        self._thinking_param = True
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._key())

    def _request(self, method: str, path: str, body: dict | None = None, timeout: float = 30,
                 key: str | None = None) -> dict:
        key = key if key is not None else self._key()
        if not key:
            raise AIError("Не указан API-ключ DeepSeek (Настройки → ИИ-провайдер)")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(BASE_URL + path, data=data, method=method, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                detail = (payload.get("error") or {}).get("message") or ""
            except Exception:
                pass
            raise AIError(_http_message(exc.code, detail)) from exc
        except urllib.error.URLError as exc:
            raise AIError(f"Нет соединения с DeepSeek: {exc.reason}") from exc
        except TimeoutError as exc:
            raise AIError("DeepSeek не ответил вовремя") from exc

    def models(self, key: str | None = None) -> list[str]:
        data = self._request("GET", "/models", key=key, timeout=15)
        return [m.get("id") for m in data.get("data", []) if m.get("id")]

    def model(self) -> str:
        chosen = (self._model_setting() or "auto").strip()
        if chosen and chosen != "auto":
            return chosen
        key = self._key()
        with self._lock:
            if self._resolved and self._resolved_for_key == key:
                return self._resolved
        try:
            resolved = pick_model(self.models())
        except AIError as exc:
            log.warning("Cannot list DeepSeek models: %s", exc)
            resolved = FALLBACK_MODEL
        with self._lock:
            self._resolved, self._resolved_for_key = resolved, key
        return resolved

    def chat(self, messages: list[dict[str, str]], json_mode: bool = False, max_tokens: int = 700,
             temperature: float = 0.5) -> str:
        body: dict[str, Any] = {
            "model": self.model(),
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self._thinking_param:
            body["thinking"] = {"type": "disabled"}
        try:
            data = self._request("POST", "/chat/completions", body)
        except AIError as exc:
            text = str(exc).lower()
            if "thinking" in text and self._thinking_param:
                self._thinking_param = False
                body.pop("thinking", None)
                data = self._request("POST", "/chat/completions", body)
            elif "model" in text and (self._model_setting() or "auto") == "auto":
                with self._lock:
                    self._resolved = None
                body["model"] = self.model()
                data = self._request("POST", "/chat/completions", body)
            else:
                raise
        try:
            return (data["choices"][0]["message"].get("content") or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError("Неожиданный ответ DeepSeek") from exc

    def test(self, key: str | None = None) -> dict[str, Any]:
        models = self.models(key=key)
        return {"ok": True, "models": models, "model": pick_model(models)}


def _http_message(code: int, detail: str) -> str:
    messages = {
        400: "DeepSeek отклонил запрос",
        401: "Неверный API-ключ DeepSeek",
        402: "Недостаточно средств на балансе DeepSeek",
        403: "Доступ к DeepSeek запрещён",
        404: "Модель DeepSeek не найдена",
        422: "DeepSeek не принял параметры запроса",
        429: "Слишком много запросов к DeepSeek, попробуйте позже",
        500: "Ошибка на стороне DeepSeek",
        503: "DeepSeek перегружен, попробуйте позже",
    }
    base = messages.get(code, f"Ошибка DeepSeek ({code})")
    return f"{base}: {detail}" if detail else base


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

    def __init__(self, client: DeepSeekClient, store):
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
                action = {"type": "wait", "seconds": max(0, min(10, float(action.get("seconds") or 1)))}
            if action["type"] == "jarvis" and action.get("op") not in (
                    "silent_on", "silent_off", "theme_dark", "theme_light", "volume"):
                continue
            safe.append(action)
        return safe

    def _remember(self, user: str, assistant: str) -> None:
        self._history.append({"role": "user", "content": user})
        if assistant:
            self._history.append({"role": "assistant", "content": assistant})
