"""Executing command actions (open apps and sites, press keys, media, system...)."""
from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable

from . import catalog, winapi
from .apps import AppResolver, Target, expand, open_uri
from .paths import IS_WINDOWS
from .textproc import parse_number
from .util import render_template

log = logging.getLogger("jarvis.actions")

SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={q}",
    "yandex": "https://yandex.ru/search/?text={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "bing": "https://www.bing.com/search?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "vk": "https://vk.com/search?c%5Bq%5D={q}",
}

MEDIA_KEYS = {
    "play_pause": "media_play_pause", "next": "media_next", "prev": "media_prev",
    "stop": "media_stop", "volume_up": "volume_up", "volume_down": "volume_down", "mute": "volume_mute",
}

SYSTEM_OPS = ("lock", "shutdown", "restart", "sleep", "logoff", "screenshot", "show_desktop",
              "empty_recycle_bin", "task_manager")

# Action types the AI planner may use (no shell commands, no power operations).
AI_SAFE_ACTIONS = {"open_app", "close_app", "focus_app", "open_url", "search_web", "hotkey", "type_text",
                   "media", "system_volume", "wait", "run_command", "jarvis", "say"}


class ActionError(Exception):
    """A user-facing error message ("Chrome не запущен")."""


@dataclass
class ExecContext:
    vars: dict[str, Any]
    folder_meta: dict[str, Any] = field(default_factory=dict)
    lang: str = "ru"
    cancel: threading.Event = field(default_factory=threading.Event)
    depth: int = 0
    messages: list[str] = field(default_factory=list)


def _msg(lang: str, ru: str, en: str) -> str:
    return en if lang == "en" else ru


def normalize_site(text: str) -> str:
    """'хабр ру' -> 'https://habr.ru', 'github' -> 'https://github.com', 'vk.com' -> 'https://vk.com'."""
    raw = (text or "").strip()
    if re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.I):
        return raw
    s = raw.lower()
    s = re.sub(r"\s+(точка|dot)\s+", ".", s)
    s = re.sub(r"\s+(ру|ru)$", ".ru", s)
    s = re.sub(r"\s+(ком|com)$", ".com", s)
    s = re.sub(r"\s+(рф)$", ".рф", s)
    s = re.sub(r"\s+(нет|net)$", ".net", s)
    s = re.sub(r"\s+(орг|org)$", ".org", s)
    s = s.replace(" ", "")
    if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}(/.*)?", s) or re.fullmatch(r"[а-я0-9.-]+\.рф", s):
        return "https://" + s
    if re.fullmatch(r"[a-z0-9-]+", s):
        return f"https://{s}.com"
    return SEARCH_ENGINES["google"].format(q=urllib.parse.quote_plus(raw))


class Executor:
    def __init__(self, resolver: AppResolver, store=None, *,
                 say: Callable[[str, str], None] | None = None,
                 ask_ai: Callable[[str, str], str] | None = None,
                 jarvis_op: Callable[[str, Any], None] | None = None):
        self.resolver = resolver
        self.store = store
        self._say = say
        self._ask_ai = ask_ai
        self._jarvis_op = jarvis_op
        self.last_browser: str | None = None

    # --- public -----------------------------------------------------------------------------
    def run(self, actions: list[dict[str, Any]], ctx: ExecContext) -> ExecContext:
        for action in actions:
            if ctx.cancel.is_set():
                raise ActionError(_msg(ctx.lang, "Выполнение отменено", "Cancelled"))
            kind = action.get("type")
            handler = getattr(self, f"_do_{kind}", None)
            if handler is None:
                raise ActionError(_msg(ctx.lang, f"Неизвестное действие: {kind}", f"Unknown action: {kind}"))
            try:
                handler(action, ctx)
            except ActionError:
                if not action.get("optional"):
                    raise
            except winapi.NotSupported as exc:
                if not action.get("optional"):
                    raise ActionError(str(exc)) from exc
            except Exception as exc:
                log.exception("Action %s failed", kind)
                if not action.get("optional"):
                    raise ActionError(str(exc) or type(exc).__name__) from exc
        return ctx

    # --- helpers ----------------------------------------------------------------------------
    @staticmethod
    def _text(value: Any, ctx: ExecContext) -> str:
        return render_template(str(value if value is not None else ""), ctx.vars).strip()

    @staticmethod
    def _url(value: str, ctx: ExecContext) -> str:
        """Render a URL template: placeholders inside a URL are percent-encoded."""
        template = str(value or "").strip()
        whole = re.fullmatch(r"\{(\w+)\}", template)
        if whole:
            return normalize_site(str(ctx.vars.get(whole.group(1), "")))
        encoded = {k: urllib.parse.quote(str(v), safe="") for k, v in ctx.vars.items() if v is not None}
        return render_template(template, encoded)

    def _browser_target(self, browser: str | None) -> Target | None:
        browser = (browser or "auto").lower()
        if browser in ("default", ""):
            return None
        if browser == "auto":
            candidates = [self.last_browser]
        else:
            candidates = [browser]
        for app_id in candidates:
            if app_id in catalog.BROWSER_IDS:
                target = self.resolver.resolve(app_id, allow_web=False)
                if target and target.kind == "exe":
                    return target
        return None

    def open_in_browser(self, url: str, browser: str | None = "auto") -> None:
        if not url.lower().startswith(("http://", "https://")):
            open_uri(url)
            return
        target = self._browser_target(browser)
        if target:
            self.resolver.launch(Target("exe", target.value, [*target.args, url], target.name, target.app_id))
            self.last_browser = target.app_id
        else:
            open_uri(url)
            default = self.resolver.default_browser()
            if default:
                self.last_browser = default

    def _avoid_own_window(self) -> None:
        """Keys must not land in Jarvis itself: switch to the previous window first."""
        if not IS_WINDOWS:
            return
        fg = winapi.foreground_window()
        windows = winapi.list_windows()
        own = os.getpid()
        if any(w["hwnd"] == fg and w["pid"] == own for w in windows):
            for w in windows:
                if w["pid"] != own:
                    winapi.focus_window(w["hwnd"])
                    break

    def _browser_windows(self) -> list[int]:
        """Browser windows: the foreground one first, then those of the browser Jarvis opened."""
        procs = {p.lower() for b in catalog.BROWSER_IDS for p in catalog.APPS_BY_ID[b]["process"]}
        windows = [w for w in winapi.list_windows() if w["exe"] in procs]
        fg = winapi.foreground_window()
        own = {p.lower() for p in catalog.APPS_BY_ID[self.last_browser]["process"]} if self.last_browser else set()
        windows.sort(key=lambda w: (w["hwnd"] != fg, w["exe"] not in own))
        return [w["hwnd"] for w in windows]

    def _focus_browser(self, ctx: ExecContext) -> None:
        procs = {p.lower() for b in catalog.BROWSER_IDS for p in catalog.APPS_BY_ID[b]["process"]}
        windows = winapi.list_windows()
        fg = winapi.foreground_window()
        if any(w["hwnd"] == fg and w["exe"] in procs for w in windows):
            return
        if self.last_browser:
            if winapi.focus_process(catalog.APPS_BY_ID[self.last_browser]["process"]):
                return
        for w in windows:
            if w["exe"] in procs and winapi.focus_window(w["hwnd"]):
                return
        raise ActionError(_msg(ctx.lang, "Не нашёл открытый браузер", "No open browser window found"))

    # --- actions ----------------------------------------------------------------------------
    def _do_open_app(self, a: dict[str, Any], ctx: ExecContext) -> None:
        app = self._text(a.get("app"), ctx)
        meta = ctx.folder_meta or {}
        target: Target | None = None
        display = app
        if a.get("path"):
            path = expand(self._text(a["path"], ctx))
            target = Target("exe", path, [], os.path.basename(path))
            display = os.path.splitext(os.path.basename(path))[0]
        elif not app:
            app = meta.get("app") or ""
            target = self.resolver.resolve(app, meta) if app else None
            if target is None and meta.get("path"):
                path = expand(meta["path"])
                target = Target("exe", path, [], os.path.basename(path))
        elif app in catalog.APPS_BY_ID:
            target = self.resolver.resolve(app, meta if meta.get("app") in (None, app) else {})
            display = catalog.app_name(catalog.APPS_BY_ID[app], ctx.lang)
        else:
            target, display = self.resolver.find_by_name(app)
        if target is None:
            raise ActionError(_msg(ctx.lang, f"Не нашёл приложение «{display or app}» на компьютере",
                                   f"Couldn't find “{display or app}” on this PC"))
        extra = a.get("args")
        if extra:
            from .apps import _split_args

            target.args = [*target.args, *_split_args(self._text(extra, ctx))]
        ctx.vars["app_name"] = display or target.name
        if target.kind == "web":
            self.open_in_browser(target.value, a.get("browser") or "auto")
        else:
            self.resolver.launch(target)
            if target.app_id in catalog.BROWSER_IDS:
                self.last_browser = target.app_id

    def _do_close_app(self, a: dict[str, Any], ctx: ExecContext) -> None:
        app = self._text(a.get("app"), ctx)
        names, display = self.resolver.process_names(app, ctx.folder_meta)
        ctx.vars["app_name"] = display or app
        if not names:
            raise ActionError(_msg(ctx.lang, f"Не знаю, как закрыть «{display or app}»",
                                   f"I don't know how to close “{display or app}”"))
        if not winapi.kill_processes(names, force=bool(a.get("force"))):
            raise ActionError(_msg(ctx.lang, f"{display or app} не запущен", f"{display or app} is not running"))

    def _do_focus_app(self, a: dict[str, Any], ctx: ExecContext) -> None:
        app = self._text(a.get("app"), ctx)
        if app == "@browser":
            self._focus_browser(ctx)
            return
        names, display = self.resolver.process_names(app, ctx.folder_meta)
        if not names or not winapi.focus_process(names):
            raise ActionError(_msg(ctx.lang, f"Окно «{display or app}» не найдено",
                                   f"Window “{display or app}” not found"))

    def _do_open_url(self, a: dict[str, Any], ctx: ExecContext) -> None:
        url = self._url(a.get("url", ""), ctx)
        if not url:
            raise ActionError(_msg(ctx.lang, "Пустая ссылка", "Empty URL"))
        if not re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I):
            url = normalize_site(url)
        self.open_in_browser(url, a.get("browser") or "auto")

    def _do_search_web(self, a: dict[str, Any], ctx: ExecContext) -> None:
        query = self._text(a.get("query", "{query}"), ctx)
        if not query or query == "{query}":
            raise ActionError(_msg(ctx.lang, "Не расслышал, что искать", "I didn't catch what to search for"))
        engine = SEARCH_ENGINES.get(str(a.get("engine") or "google").lower(), SEARCH_ENGINES["google"])
        self.open_in_browser(engine.format(q=urllib.parse.quote_plus(query)), a.get("browser") or "auto")

    def _do_hotkey(self, a: dict[str, Any], ctx: ExecContext) -> None:
        keys = self._text(a.get("keys"), ctx)
        if not keys:
            raise ActionError(_msg(ctx.lang, "Не указаны клавиши", "No keys specified"))
        for combo in winapi.split_combos(keys):
            winapi.parse_combo(combo)  # validate before pressing anything
        self._avoid_own_window()
        winapi.send_hotkey(keys)

    def _do_type_text(self, a: dict[str, Any], ctx: ExecContext) -> None:
        text = self._text(a.get("text"), ctx)
        if text:
            self._avoid_own_window()
            winapi.type_text(text)

    def _do_media(self, a: dict[str, Any], ctx: ExecContext) -> None:
        key = MEDIA_KEYS.get(str(a.get("key") or "play_pause"))
        if not key:
            raise ActionError(_msg(ctx.lang, "Неизвестная медиаклавиша", "Unknown media key"))
        times = max(1, min(50, int(parse_number(a.get("times", 1)) or 1)))
        winapi.tap_key(key, times, delay=0.02)

    def _do_system_volume(self, a: dict[str, Any], ctx: ExecContext) -> None:
        level = parse_number(self._text(a.get("level"), ctx))
        if level is None:
            raise ActionError(_msg(ctx.lang, "Не расслышал уровень громкости", "I didn't catch the volume level"))
        level = max(0, min(100, level))
        ctx.vars["level"] = level
        winapi.set_system_volume(level)

    def _do_system(self, a: dict[str, Any], ctx: ExecContext) -> None:
        op = a.get("op")
        if op not in SYSTEM_OPS:
            raise ActionError(_msg(ctx.lang, "Неизвестная системная команда", "Unknown system command"))
        if op == "lock":
            winapi.lock_workstation()
        elif op == "sleep":
            winapi.sleep_computer()
        elif op == "empty_recycle_bin":
            winapi.empty_recycle_bin()
        elif op == "screenshot":
            winapi.send_hotkey("win+shift+s")
        elif op == "show_desktop":
            winapi.send_hotkey("win+d")
        elif op == "task_manager":
            winapi.send_hotkey("ctrl+shift+esc")
        else:
            if not IS_WINDOWS:
                raise winapi.NotSupported("Только для Windows")
            flag = {"shutdown": "/s", "restart": "/r", "logoff": "/l"}[op]
            cmd = ["shutdown", flag] + (["/t", "0"] if op != "logoff" else [])
            subprocess.Popen(cmd, creationflags=winapi.CREATE_NO_WINDOW)

    def _do_wait(self, a: dict[str, Any], ctx: ExecContext) -> None:
        seconds = max(0.0, min(60.0, float(a.get("seconds") or 0)))
        end = time.time() + seconds
        while time.time() < end:
            if ctx.cancel.wait(min(0.1, max(0.0, end - time.time()))):
                raise ActionError(_msg(ctx.lang, "Выполнение отменено", "Cancelled"))

    def _do_say(self, a: dict[str, Any], ctx: ExecContext) -> None:
        text = self._text(a.get("text"), ctx)
        if text:
            ctx.messages.append(text)

    def _do_run(self, a: dict[str, Any], ctx: ExecContext) -> None:
        command = self._text(a.get("command"), ctx)
        if not command:
            raise ActionError(_msg(ctx.lang, "Пустая команда", "Empty command"))
        flags = winapi.CREATE_NO_WINDOW if (IS_WINDOWS and a.get("hidden", True)) else 0
        subprocess.Popen(command, shell=True, creationflags=flags)

    def _do_ask_ai(self, a: dict[str, Any], ctx: ExecContext) -> None:
        prompt = self._text(a.get("prompt") or "{_text}", ctx)
        if not self._ask_ai:
            raise ActionError(_msg(ctx.lang, "ИИ не настроен", "AI is not configured"))
        answer = self._ask_ai(prompt, ctx.lang)
        if answer:
            ctx.vars["ai_reply"] = answer
            ctx.messages.append(answer)

    def _do_click_element(self, a: dict[str, Any], ctx: ExecContext) -> None:
        names = a.get("names") or a.get("name") or []
        if isinstance(names, str):
            names = [n.strip() for n in re.split(r"[|\n;]", names) if n.strip()]
        names = [self._text(n, ctx) for n in names]
        if not names:
            raise ActionError(_msg(ctx.lang, "Не указан текст кнопки", "No button text given"))
        app = self._text(a.get("app"), ctx)
        windows = None
        if app == "@browser":
            try:
                self._focus_browser(ctx)
            except ActionError:
                pass  # the page may still be in a background browser window
            windows = self._browser_windows
        elif app:
            proc, _ = self.resolver.process_names(app, ctx.folder_meta)
            windows = lambda: winapi.find_windows(proc)  # noqa: E731
        pressed = winapi.click_element(names, timeout=float(a.get("timeout") or 6), windows=windows)
        if not pressed:
            raise ActionError(_msg(ctx.lang, f"Не нашёл кнопку «{names[0]}»", f"Button “{names[0]}” not found"))

    def _do_run_command(self, a: dict[str, Any], ctx: ExecContext) -> None:
        if ctx.depth >= 3 or self.store is None:
            raise ActionError(_msg(ctx.lang, "Слишком глубокая вложенность команд", "Commands nested too deep"))
        path = str(a.get("path") or "")
        item = self.store.read(path)
        if item.get("type") != "command":
            raise ActionError(_msg(ctx.lang, "Команда не найдена", "Command not found"))
        extra = {k: self._text(v, ctx) for k, v in (a.get("vars") or {}).items()}
        sub = ExecContext({**ctx.vars, **extra}, item.get("folder") or {}, ctx.lang, ctx.cancel, ctx.depth + 1,
                          ctx.messages)
        self.run(item["data"]["actions"], sub)
        response = render_template(item["data"].get("response", ""), sub.vars)
        if response:
            ctx.messages.append(response)

    def _do_jarvis(self, a: dict[str, Any], ctx: ExecContext) -> None:
        if self._jarvis_op:
            value = a.get("value")
            if isinstance(value, str):
                value = self._text(value, ctx)
            self._jarvis_op(str(a.get("op")), value)
