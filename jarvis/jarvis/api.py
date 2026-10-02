"""Methods the UI calls (exposed to JavaScript by pywebview or by the HTTP bridge).

Every public method returns JSON-serialisable data and raises an exception with a
user-readable message on failure.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from typing import Any

from . import __version__, catalog, paths
from .actions import ExecContext
from .util import time_vars

log = logging.getLogger("jarvis.api")


class Api:
    def __init__(self, app):
        self._app = app

    # --- bootstrap --------------------------------------------------------------------------
    def ready(self) -> dict[str, Any]:
        """Called by the UI once it is loaded: returns everything needed for the first render."""
        app = self._app
        app.ready_event_id = app.bus.last_id
        app.frontend_ready.set()
        log.info("UI connected (%s mode)", app.mode)
        return {
            "last_event": app.ready_event_id,
            "version": __version__,
            "platform": sys.platform,
            "mode": app.mode,
            "settings": app.settings.all(),
            "state": app.assistant.state(),
            "history": app.history.all()[-150:],
            "data_dir": str(paths.data_root()),
        }

    # --- settings ---------------------------------------------------------------------------
    def get_settings(self) -> dict[str, Any]:
        return self._app.settings.all()

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        self._app.settings.update(patch or {})
        return self._app.settings.all()

    # --- assistant --------------------------------------------------------------------------
    def set_mic(self, on: bool) -> dict[str, Any]:
        return self._app.assistant.set_mic(bool(on))

    def get_state(self) -> dict[str, Any]:
        return self._app.assistant.state()

    def send_text(self, text: str) -> bool:
        self._app.assistant.submit_text(str(text or ""), "text")
        return True

    def confirm(self, entry_id: str | None, yes: bool) -> bool:
        self._app.assistant.confirm(entry_id, bool(yes))
        return True

    def stop_speaking(self) -> bool:
        self._app.assistant.cancel()
        return True

    def get_history(self) -> list[dict[str, Any]]:
        return self._app.history.all()

    def clear_history(self) -> bool:
        self._app.history.clear()
        self._app.bus.emit("history_clear")
        return True

    def repeat(self, entry_id: str) -> bool:
        entry = self._app.history.get(entry_id)
        if not entry:
            raise ValueError("Запись не найдена")
        self._app.assistant.submit_text(entry.get("text") or entry.get("heard") or "", "repeat")
        return True

    # --- command editor ---------------------------------------------------------------------
    def tree(self) -> list[dict[str, Any]]:
        return self._app.store.tree()

    def read_item(self, path: str) -> dict[str, Any]:
        return self._app.store.read(path)

    def create_folder(self, parent: str, name: str) -> str:
        path = self._app.store.create_folder(parent or "", name)
        self._changed()
        return path

    def create_command(self, parent: str, name: str) -> str:
        path = self._app.store.create_command(parent or "", name)
        self._changed()
        return path

    def rename_item(self, path: str, name: str) -> str:
        new = self._app.store.rename(path, name)
        self._changed()
        return new

    def delete_item(self, path: str) -> bool:
        self._app.store.delete(path)
        self._changed()
        return True

    def move_item(self, path: str, parent: str) -> str:
        new = self._app.store.move(path, parent or "")
        self._changed()
        return new

    def duplicate_item(self, path: str) -> str:
        suffix = "copy" if self._app.settings.get("language") == "en" else "копия"
        new = self._app.store.duplicate(path, suffix)
        self._changed()
        return new

    def save_command(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        result = self._app.store.save_command(path, data)
        self._changed()
        return result

    def save_folder(self, path: str, meta: dict[str, Any]) -> dict[str, Any]:
        result = self._app.store.save_folder(path, meta)
        self._changed()
        return result

    def test_command(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a command right now (from the editor) and return the reply."""
        app = self._app
        item = app.store.read(path)
        if item.get("type") != "command":
            raise ValueError("Это не команда")
        payload = data or item["data"]
        lang = app.settings.get("language")
        ctx = ExecContext({**time_vars(lang), "_text": item["name"]}, item.get("folder") or {}, lang)
        from .actions import ActionError
        from .util import render_template

        try:
            app.executor.run(payload.get("actions", []), ctx)
        except ActionError as exc:
            return {"ok": False, "error": str(exc)}
        reply = render_template(payload.get("response", ""), ctx.vars)
        parts = [p for p in [reply, *ctx.messages] if p]
        text = " ".join(parts)
        if text and not app.settings.get("silent"):
            app.speaker.say(text, lang)
        return {"ok": True, "reply": text}

    def match_phrase(self, text: str) -> dict[str, Any]:
        """Which commands would run for a phrase (for the editor's test field)."""
        from .matcher import Matcher

        plan = Matcher(self._app.store.entries()).plan(text, self._app.settings.get("chain_words"))
        return {"steps": [{"text": s.text, "path": s.match.command.path if s.match else None,
                           "score": round(s.match.score, 3) if s.match else 0,
                           "captures": s.match.captures if s.match else {}} for s in plan]}

    def _changed(self) -> None:
        self._app.bus.emit("tree_changed")

    # --- apps catalog -----------------------------------------------------------------------
    def catalog(self) -> dict[str, Any]:
        app = self._app
        data = catalog.catalog_for_ui(app.settings.get("language"))
        data["connected"] = app.store.connected_apps()
        data["status"] = app.resolver.cached_statuses()
        return data

    def detect_apps(self) -> bool:
        """Scan the PC for installed apps in the background; result arrives as 'apps_status'."""
        def work():
            try:
                statuses = self._app.resolver.statuses()
                self._app.bus.emit("apps_status", statuses)
            except Exception:
                log.exception("App detection failed")

        threading.Thread(target=work, name="detect-apps", daemon=True).start()
        return True

    def connect_app(self, app_id: str) -> str:
        path = self._app.store.connect_app(app_id, self._app.settings.get("language"))
        self._changed()
        return path

    def disconnect_app(self, app_id: str) -> bool:
        removed = self._app.store.disconnect_app(app_id)
        self._changed()
        return removed

    def reset_defaults(self) -> bool:
        self._app.store.reset_defaults(self._app.settings.get("language"))
        self._changed()
        return True

    # --- settings helpers -------------------------------------------------------------------
    def list_microphones(self) -> list[dict[str, Any]]:
        from .voice.mic import MicError, list_input_devices

        try:
            return list_input_devices()
        except MicError as exc:
            raise RuntimeError(str(exc)) from exc

    def test_voice(self) -> bool:
        lang = self._app.settings.get("language")
        text = ("Все системы в норме, сэр. Так звучит мой голос." if lang != "en"
                else "All systems nominal, sir. This is how I sound.")
        self._app.speaker.say(text, lang)
        return True

    def ai_test(self, provider: str | None = None, key: str | None = None, url: str | None = None) -> dict[str, Any]:
        """Check the AI provider with the values typed in the settings (a real request)."""
        return self._app.ai_client.test(provider or None, key if key else None, url if url else None)

    def ai_models(self, provider: str | None = None) -> list[str]:
        """Models for the settings list (OpenRouter's free models are public, no key needed)."""
        from .ai import AIError

        client = self._app.ai_client
        try:
            return client.list_models(client.conn(provider or None))
        except AIError as exc:
            log.info("Cannot list AI models: %s", exc)
            return []

    def open_link(self, url: str) -> bool:
        url = str(url or "")
        if not url.lower().startswith(("https://", "http://")):
            raise ValueError("Можно открывать только веб-ссылки")
        from .apps import open_uri

        open_uri(url)
        return True

    def pick_file(self) -> str | None:
        window = getattr(self._app, "window", None)
        if window is None:
            raise RuntimeError("Выбор файла доступен только в окне приложения. Вставьте путь вручную.")
        import webview  # type: ignore

        dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None)
        if dialog is None:
            dialog = getattr(webview, "OPEN_DIALOG", 10)
        result = window.create_file_dialog(dialog, allow_multiple=False,
                                           file_types=("Программы (*.exe;*.lnk;*.bat;*.cmd)", "Все файлы (*.*)"))
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else str(result)

    def open_data_folder(self) -> bool:
        folder = str(paths.data_root())
        if paths.IS_WINDOWS:
            os.startfile(folder)  # type: ignore[attr-defined]
        elif paths.IS_MAC:
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
        return True
