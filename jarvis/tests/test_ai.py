import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from jarvis import ai
from jarvis.ai import AIAssistant, AIError, DeepSeekClient, _extract_json, pick_model


def test_pick_model_prefers_newest_flash():
    assert pick_model(["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4.1-flash"]) == "deepseek-v4.1-flash"
    assert pick_model(["deepseek-chat", "deepseek-reasoner"]) == "deepseek-chat"
    assert pick_model(["deepseek-v4.1-flash-expires-on-0910", "deepseek-v4-flash"]) == "deepseek-v4-flash"
    assert pick_model([]) == ai.FALLBACK_MODEL


def test_extract_json():
    assert _extract_json('{"reply": "ok", "actions": []}')["reply"] == "ok"
    assert _extract_json('```json\n{"reply": "x"}\n```')["reply"] == "x"
    assert _extract_json('Вот ответ: {"reply": "y"} — готово')["reply"] == "y"


def test_sanitize_drops_dangerous_actions():
    known = {"Система/Скриншот.json"}
    actions = [
        {"type": "run", "command": "format c:"},
        {"type": "system", "op": "shutdown"},
        {"type": "open_url", "url": "file:///C:/Windows"},
        {"type": "open_url", "url": "https://vk.com"},
        {"type": "run_command", "path": "Система/Скриншот"},
        {"type": "run_command", "path": "Нет/Такой"},
        {"type": "wait", "seconds": 999},
        {"type": "jarvis", "op": "mic_off"},
        {"type": "media", "key": "next"},
    ]
    safe = AIAssistant._sanitize(actions, known)
    assert safe == [
        {"type": "open_url", "url": "https://vk.com"},
        {"type": "run_command", "path": "Система/Скриншот.json"},
        {"type": "wait", "seconds": 10},
        {"type": "media", "key": "next"},
    ]


class _FakeDeepSeek(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *args):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer good":
            self._send(401, {"error": {"message": "invalid key"}})
            return
        self._send(200, {"data": [{"id": "deepseek-v4-flash"}, {"id": "deepseek-v4.1-flash"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeDeepSeek.requests.append(body)
        if "thinking" in body:
            self._send(400, {"error": {"message": "unknown field: thinking"}})
            return
        if body.get("response_format"):
            content = json.dumps({"reply": "Открываю почту, сэр", "actions": [
                {"type": "open_url", "url": "https://mail.yandex.ru"}, {"type": "run", "command": "x"}]})
        else:
            content = "Чёрная дыра — это **область** пространства."
        self._send(200, {"choices": [{"message": {"content": content}}]})


@pytest.fixture
def fake_api(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeDeepSeek)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(ai, "BASE_URL", f"http://127.0.0.1:{server.server_address[1]}")
    _FakeDeepSeek.requests = []
    yield server
    server.shutdown()


def test_client_flow(fake_api, store):
    client = DeepSeekClient(lambda: "good", lambda: "auto")
    assert client.test()["model"] == "deepseek-v4.1-flash"
    assistant = AIAssistant(client, store)
    answer = assistant.ask("что такое чёрная дыра", "ru")
    assert answer == "Чёрная дыра — это область пространства."
    # the first request carried "thinking" and was retried without it
    assert "thinking" in _FakeDeepSeek.requests[0] and "thinking" not in _FakeDeepSeek.requests[1]
    assert _FakeDeepSeek.requests[1]["model"] == "deepseek-v4.1-flash"
    plan = assistant.plan("открой мою почту", "ru")
    assert plan["reply"] == "Открываю почту, сэр"
    assert plan["actions"] == [{"type": "open_url", "url": "https://mail.yandex.ru"}]


def test_client_errors(fake_api):
    bad = DeepSeekClient(lambda: "bad", lambda: "auto")
    with pytest.raises(AIError, match="Неверный API-ключ"):
        bad.models()
    empty = DeepSeekClient(lambda: "", lambda: "auto")
    with pytest.raises(AIError, match="Не указан"):
        empty.chat([{"role": "user", "content": "hi"}])
