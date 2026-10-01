"""Application wiring: creates the services and runs the window (pywebview) or the browser bridge."""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import webbrowser
from typing import Any

from . import APP_NAME, paths
from .actions import Executor
from .ai import AIAssistant, DeepSeekClient
from .api import Api
from .apps import AppResolver
from .assistant import Assistant
from .events import EventBus
from .history import History
from .settings import Settings
from .store import CommandStore

log = logging.getLogger("jarvis.app")

WINDOW_TITLE = "Jarvis"


def _mic_factory(**kwargs):
    from .voice.mic import MicListener

    return MicListener(**kwargs)


def _stt_factory():
    from .voice.stt import GoogleSTT

    return GoogleSTT()


class JarvisApp:
    def __init__(self, mode: str = "window", port: int = 0, open_browser: bool = True, debug: bool = False,
                 voice: bool = True):
        self.mode = mode
        self.port = port
        self.open_browser = open_browser
        self.debug = debug
        self.window = None
        self.frontend_ready = threading.Event()
        self.ready_event_id = 0

        self.settings = Settings()
        self.bus = EventBus()
        self.store = CommandStore(paths.commands_dir())
        self.store.ensure_seeded(self.settings.get("language"))
        self.history = History()
        self.resolver = AppResolver(self.store)
        self.ai_client = DeepSeekClient(lambda: self.settings.get("ai_api_key"),
                                        lambda: self.settings.get("ai_model"))
        self.ai = AIAssistant(self.ai_client, self.store)
        if voice:
            from .voice.tts import Speaker

            self.speaker = Speaker(self.settings)
        else:
            self.speaker = _SilentSpeaker()
        self.executor = Executor(self.resolver, self.store,
                                 ask_ai=lambda prompt, lang: self.ai.ask(prompt, lang),
                                 jarvis_op=lambda op, value: self.assistant.jarvis_op(op, value))
        self.assistant = Assistant(self.settings, self.store, self.history, self.bus, self.executor,
                                   self.speaker, ai=self.ai,
                                   stt_factory=_stt_factory if voice else None,
                                   mic_factory=_mic_factory if voice else None)
        self.api = Api(self)
        self.settings.on_change(self._on_settings_changed)

    # --- settings side effects --------------------------------------------------------------
    def _on_settings_changed(self, changed: dict[str, Any]) -> None:
        self.bus.emit("settings", self.settings.all())
        if "theme" in changed:
            self._apply_title_bar()
        if "mic_device" in changed:
            threading.Thread(target=self.assistant.restart_mic, daemon=True).start()

    def _apply_title_bar(self) -> None:
        if not paths.IS_WINDOWS or self.window is None:
            return
        try:
            from . import winapi

            hwnd = winapi.find_own_window(WINDOW_TITLE)
            winapi.set_dark_title_bar(hwnd, self.settings.get("theme") == "dark")
        except Exception as exc:
            log.debug("Title bar theme: %s", exc)

    def _after_start(self) -> None:
        """Runs once the UI is up: auto-start the microphone if enabled."""
        self.frontend_ready.wait(30)
        self._apply_title_bar()
        if self.settings.get("mic_autostart"):
            self.assistant.set_mic(True)

    # --- run --------------------------------------------------------------------------------
    def run(self) -> None:
        try:
            if self.mode == "browser":
                self._run_browser()
            else:
                try:
                    import webview  # noqa: F401  # type: ignore
                except Exception as exc:
                    log.warning("pywebview is unavailable (%s), falling back to the browser mode", exc)
                    self.mode = "browser"
                    self._run_browser()
                    return
                self._run_window()
        finally:
            self.shutdown()

    def _run_browser(self) -> None:
        from .bridge import BridgeServer

        server = BridgeServer(self.api, self.bus, self.port)
        url = server.url
        print(f"{APP_NAME}: интерфейс доступен по адресу {url}", flush=True)
        log.info("Browser mode at %s", url)
        threading.Thread(target=self._after_start, daemon=True).start()
        if self.open_browser:
            threading.Timer(0.6, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()

    def _run_window(self) -> None:
        import webview  # type: ignore

        dark = self.settings.get("theme") == "dark"
        self.window = webview.create_window(
            WINDOW_TITLE,
            url=str(paths.WEB_DIR / "index.html"),
            js_api=self.api,
            width=1240,
            height=820,
            min_size=(980, 660),
            background_color="#000000" if dark else "#FFFFFF",
            text_select=True,
        )
        pusher = _EventPusher(self)
        self.bus.subscribe(pusher.push)
        threading.Thread(target=pusher.run, name="ui-events", daemon=True).start()
        icon = paths.ASSETS_DIR / "icon.ico"
        webview.start(
            self._after_start,
            http_server=True,
            private_mode=False,
            storage_path=str(paths.data_root() / "webview"),
            debug=self.debug,
            icon=str(icon) if icon.exists() else None,
        )

    def shutdown(self) -> None:
        try:
            self.assistant.shutdown()
        except Exception:
            log.exception("assistant shutdown")
        try:
            self.speaker.shutdown()
        except Exception:
            pass


class _EventPusher:
    """Delivers bus events to the window in batches (the UI thread is never blocked by audio)."""

    def __init__(self, app: JarvisApp):
        self.app = app
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue()

    def push(self, event: dict[str, Any]) -> None:
        self.queue.put(event)

    def run(self) -> None:
        self.app.frontend_ready.wait()
        while True:
            batch = [self.queue.get()]
            time.sleep(0.03)
            while True:
                try:
                    batch.append(self.queue.get_nowait())
                except queue.Empty:
                    break
            # events from before the UI asked for its initial state are already reflected in it
            batch = [e for e in batch if e["id"] > self.app.ready_event_id]
            # keep only the newest level value
            levels = [e for e in batch if e["type"] == "level"]
            batch = [e for e in batch if e["type"] != "level"] + levels[-1:]
            window = self.app.window
            if window is None or not batch:
                continue
            try:
                payload = json.dumps(batch, ensure_ascii=False)
                window.run_js(f"window.__jarvis && window.__jarvis.dispatch({payload})")
            except Exception as exc:
                log.debug("UI push failed: %s", exc)


class _SilentSpeaker:
    speaking = False
    on_start = None
    on_end = None

    def say(self, text: str, lang: str = "ru"):
        log.info("[voice] %s", text)
        done = threading.Event()
        done.set()
        return done

    def stop(self) -> None:
        pass

    def chime(self) -> None:
        pass

    def shutdown(self) -> None:
        pass
