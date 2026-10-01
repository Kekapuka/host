import json
import threading
import time
import urllib.request

import pytest

from jarvis import actions
from jarvis.actions import ActionError, ExecContext, Executor, normalize_site
from jarvis.apps import AppResolver, Target
from jarvis.events import EventBus


@pytest.mark.parametrize("raw,url", [
    ("habr.com", "https://habr.com"),
    ("хабр точка ком", "https://www.google.com/search?q=%D1%85%D0%B0%D0%B1%D1%80+%D1%82%D0%BE%D1%87%D0%BA%D0%B0+%D0%BA%D0%BE%D0%BC"),
    ("github", "https://github.com"),
    ("vk ru", "https://vk.ru"),
    ("https://example.org/x", "https://example.org/x"),
])
def test_normalize_site(raw, url):
    assert normalize_site(raw) == url


class FakeResolver(AppResolver):
    def __init__(self):
        super().__init__(None)
        self.launched = []

    def launch(self, target):
        self.launched.append(target)

    def resolve(self, app_id, meta=None, allow_web=True, deep=True):
        if app_id == "chrome":
            return Target("exe", "C:/chrome.exe", [], "Google Chrome", "chrome", ["chrome.exe"])
        return super().resolve(app_id, meta, allow_web, deep)


def test_open_url_uses_browser_opened_before(monkeypatch):
    opened = []
    monkeypatch.setattr(actions, "open_uri", opened.append)
    resolver = FakeResolver()
    ex = Executor(resolver)
    ctx = ExecContext({"query": "кошки & собаки"})
    ex.run([{"type": "open_url", "url": "https://vk.com/audio?q={query}"}], ctx)
    assert opened == ["https://vk.com/audio?q=%D0%BA%D0%BE%D1%88%D0%BA%D0%B8%20%26%20%D1%81%D0%BE%D0%B1%D0%B0%D0%BA%D0%B8"]
    ex.run([{"type": "open_app", "app": "chrome"}], ctx)
    assert ctx.vars["app_name"] == "Google Chrome" and ex.last_browser == "chrome"
    ex.run([{"type": "search_web", "query": "{query}", "engine": "youtube"}], ctx)
    last = resolver.launched[-1]
    assert last.value == "C:/chrome.exe"
    assert last.args == ["https://www.youtube.com/results?search_query=%D0%BA%D0%BE%D1%88%D0%BA%D0%B8+%26+%D1%81%D0%BE%D0%B1%D0%B0%D0%BA%D0%B8"]


def test_unknown_app_and_optional_actions():
    ex = Executor(FakeResolver())
    ctx = ExecContext({"app": "абракадабра"})
    with pytest.raises(ActionError, match="Не нашёл приложение"):
        ex.run([{"type": "open_app", "app": "{app}"}], ctx)
    ex.run([{"type": "open_app", "app": "{app}", "optional": True}], ctx)  # no exception


def test_wait_is_cancellable():
    ex = Executor(FakeResolver())
    ctx = ExecContext({})
    threading.Timer(0.1, ctx.cancel.set).start()
    start = time.time()
    with pytest.raises(ActionError):
        ex.run([{"type": "wait", "seconds": 5}], ctx)
    assert time.time() - start < 1


def test_say_and_ask_ai_messages():
    ex = Executor(FakeResolver(), ask_ai=lambda prompt, lang: f"ответ на «{prompt}»")
    ctx = ExecContext({"_text": "что такое бозон"})
    ex.run([{"type": "say", "text": "Сейчас {time}"}, {"type": "ask_ai"}], ctx)
    assert ctx.messages == ["Сейчас {time}", "ответ на «что такое бозон»"]


class DummyApi:
    def echo(self, value):
        return {"echo": value}

    def boom(self):
        raise ValueError("ошибка")


def _post(url, payload, token=None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"X-Jarvis-Token": token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_bridge_requires_token_and_serves_ui():
    from jarvis.bridge import BridgeServer

    bus = EventBus()
    server = BridgeServer(DummyApi(), bus, 0)
    server.start_background()
    base = server.url
    try:
        html = urllib.request.urlopen(base, timeout=5).read().decode()
        assert server.token in html and "css/app.css" in html
        assert _post(base + "api/echo", {"args": [1]})[0] == 403
        assert _post(base + "api/echo", {"args": [1]}, server.token) == (200, {"ok": True, "result": {"echo": 1}})
        assert _post(base + "api/boom", {}, server.token)[1] == {"ok": False, "error": "ошибка"}
        assert _post(base + "api/_private", {}, server.token)[0] == 404
        bus.emit("toast", {"text": "hi"})
        with urllib.request.urlopen(f"{base}api/events?after=0&token={server.token}", timeout=5) as resp:
            data = json.loads(resp.read())
        assert data["events"][0]["type"] == "toast"
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "../jarvis/settings.py", timeout=5)
    finally:
        server.shutdown()
        server.server_close()
