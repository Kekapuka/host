import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from jarvis import ai
from jarvis.ai import (AIAssistant, AIClient, AIError, _extract_json, api_base, ollama_root, pick_any_model,
                       pick_local_model, pick_model, rank_free_models)
from jarvis.settings import Settings

FREE = {"prompt": "0", "completion": "0"}
OPENROUTER_MODELS = [
    {"id": "openai/gpt-4o", "pricing": {"prompt": "0.0000025", "completion": "0.00001"}, "context_length": 128000},
    {"id": "deepseek/deepseek-r1-0528:free", "pricing": FREE, "context_length": 163840},
    {"id": "meta-llama/llama-3.2-3b-instruct:free", "pricing": FREE, "context_length": 131072},
    {"id": "meta-llama/llama-3.3-70b-instruct:free", "pricing": FREE, "context_length": 65536},
    {"id": "deepseek/deepseek-chat-v3-0324:free", "pricing": FREE, "context_length": 163840},
    {"id": "google/gemini-2.5-flash-image:free", "pricing": FREE,
     "architecture": {"output_modalities": ["image", "text"]}},
    {"id": "qwen/qwen3-235b-a22b:free", "pricing": FREE, "context_length": 40960},
    {"id": "openrouter/free", "pricing": FREE},
    {"id": "openrouter/auto", "pricing": {"prompt": "-1", "completion": "-1"}},
]
PLAN = json.dumps({"reply": "Открываю почту, сэр", "actions": [
    {"type": "open_url", "url": "https://mail.yandex.ru"}, {"type": "run", "command": "x"}]})


def test_pick_model_prefers_newest_flash():
    assert pick_model(["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4.1-flash"]) == "deepseek-v4.1-flash"
    assert pick_model(["deepseek-chat", "deepseek-reasoner"]) == "deepseek-chat"
    assert pick_model(["deepseek-v4.1-flash-expires-on-0910", "deepseek-v4-flash"]) == "deepseek-v4-flash"
    assert pick_model([]) == ai.FALLBACK_MODEL


def test_rank_free_models():
    assert rank_free_models(OPENROUTER_MODELS) == [
        "deepseek/deepseek-chat-v3-0324:free",  # known fast chat models first
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-235b-a22b:free",
        "deepseek/deepseek-r1-0528:free",  # "thinking" models are slow for voice
    ]  # paid, tiny, image and router models are left out


def test_pick_local_and_any_models():
    assert pick_local_model(["nomic-embed-text:latest", "deepseek-r1:8b", "qwen2.5:7b"]) == "qwen2.5:7b"
    assert pick_local_model(["deepseek-r1:8b"]) == "deepseek-r1:8b"
    assert pick_any_model(["whisper-large-v3", "llama-3.3-70b-versatile"]) == "llama-3.3-70b-versatile"


def test_addresses():
    assert ollama_root("") == "http://localhost:11434"
    assert ollama_root("127.0.0.1:11434/v1/") == "http://127.0.0.1:11434"
    assert api_base("api.groq.com/openai/v1/chat/completions") == "https://api.groq.com/openai/v1"
    assert api_base("localhost:1234/v1/") == "http://localhost:1234/v1"
    assert api_base("") == ""


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


class _FakeAPIs(BaseHTTPRequestHandler):
    """DeepSeek under /ds, OpenRouter under /or, Ollama under /ol, another OpenAI-compatible API under /cu."""
    requests: list = []

    def log_message(self, *args):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _key(self):
        return (self.headers.get("Authorization") or "").removeprefix("Bearer ")

    def _answer(self, body, model=None):
        content = PLAN if body.get("response_format") or "JSON" in body["messages"][0]["content"] else \
            "Чёрная дыра — это **область** пространства."
        self._send(200, {"model": model or body["model"], "choices": [{"message": {"content": content}}]})

    def do_GET(self):
        path, key = self.path, self._key()
        if path == "/or/models":
            self._send(200, {"data": OPENROUTER_MODELS})
        elif path == "/ol/api/tags":
            self._send(200, {"models": [{"name": "nomic-embed-text:latest"}, {"name": "qwen2.5:7b"}]})
        elif path == "/cu/v1/models":
            self._send(200, {"data": [{"id": "whisper-large-v3"}, {"id": "llama-3.3-70b-versatile"}]})
        elif key not in ("good", "empty", "or-good"):
            self._send(401, {"error": {"message": "Authentication Fails (no such user)"}})
        elif path == "/ds/models":
            self._send(200, {"data": [{"id": "deepseek-v4-flash"}, {"id": "deepseek-v4.1-flash"}]})
        elif path == "/ds/user/balance":
            total = "5.00" if key == "good" else "0.00"
            self._send(200, {"is_available": key == "good", "balance_infos": [
                {"currency": "USD", "total_balance": total, "granted_balance": "0.00", "topped_up_balance": total}]})
        elif path == "/or/key":
            self._send(200, {"data": {"label": "sk-or-v1-abc", "is_free_tier": True, "usage": 0}})
        else:
            self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeAPIs.requests.append((self.path, body))
        key = self._key()
        if self.path == "/ds/chat/completions":
            if key == "empty":
                self._send(402, {"error": {"message": "Insufficient Balance", "type": "unknown_error"}})
            elif "thinking" in body:
                self._send(400, {"error": {"message": "unknown field: thinking"}})
            else:
                self._answer(body)
        elif self.path == "/or/chat/completions":
            if key == "or-limit":
                self._send(429, {"error": {"code": 429, "message": "Rate limit exceeded: free-models-per-day. "
                                           "Add 10 credits to unlock 1000 free model requests per day"}})
            elif key == "or-privacy":
                self._send(404, {"error": {"code": 404, "message": "No endpoints found matching your data policy "
                                           "(Free model publication). Configure: https://openrouter.ai/settings/privacy"}})
            elif key == "or-busy" and body["model"] != ai.FREE_ROUTER:
                self._send(429, {"error": {"code": 429, "message": "Provider returned error", "metadata": {
                    "raw": f"{body['model']} is temporarily rate-limited upstream. Please retry shortly"}}})
            elif key == "or-busy":
                self._answer(body, "meta-llama/llama-3.3-70b-instruct:free")
            else:
                self._answer(body, (body.get("models") or [body["model"]])[0])
        elif self.path == "/ol/api/chat":
            content = PLAN if body.get("format") == "json" else "<think>Пользователь просит…</think>Готов, сэр."
            self._send(200, {"model": body["model"], "message": {"role": "assistant", "content": content},
                             "done": True})
        elif self.path == "/cu/v1/chat/completions":
            if body.get("response_format"):
                self._send(400, {"error": {"message": "response_format is not supported by this model"}})
            else:
                self._answer(body)
        else:
            self._send(404, {"error": {"message": "not found"}})


@pytest.fixture
def fake(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAPIs)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setattr(ai, "DEEPSEEK_URL", base + "/ds")
    monkeypatch.setattr(ai, "OPENROUTER_URL", base + "/or")
    _FakeAPIs.requests = []
    yield base
    server.shutdown()


def config(**values):
    return {"language": "ru", "ai_model": "auto", **values}


def test_deepseek_flow(fake, store):
    client = AIClient(config(ai_provider="deepseek", ai_api_key="good"))
    result = client.test()
    assert result["ok"] and result["model"] == "deepseek-v4.1-flash" and result["balance"] == "5.00 USD"
    assistant = AIAssistant(client, store)
    assert assistant.ask("что такое чёрная дыра", "ru") == "Чёрная дыра — это область пространства."
    # the first request carried "thinking" and was retried without it; later requests do not send it
    bodies = [b for _, b in _FakeAPIs.requests]
    assert "thinking" in bodies[0] and all("thinking" not in b for b in bodies[1:])
    assert bodies[-1]["model"] == "deepseek-v4.1-flash"
    plan = assistant.plan("открой мою почту", "ru")
    assert plan == {"reply": "Открываю почту, сэр", "actions": [{"type": "open_url", "url": "https://mail.yandex.ru"}]}


def test_deepseek_without_balance_is_explained(fake):
    client = AIClient(config(ai_provider="deepseek", ai_api_key="empty"))
    result = client.test()
    assert not result["ok"] and result["code"] == "no_balance"
    assert "Ключ верный" in result["error"] and "0.00 USD" in result["error"]
    assert "платный" in result["hint"] and "OpenRouter" in result["hint"]
    assert not _FakeAPIs.requests  # stopped before spending a request
    with pytest.raises(AIError) as err:
        client.chat([{"role": "user", "content": "привет"}])
    assert err.value.code == "no_balance" and "платный" in str(err.value)


def test_key_errors(fake):
    result = AIClient(config(ai_provider="deepseek", ai_api_key="bad")).test()
    assert not result["ok"] and result["code"] == "auth" and result["error"] == "Неверный ключ DeepSeek"
    with pytest.raises(AIError, match="Не указан ключ OpenRouter"):
        AIClient(config(ai_provider="openrouter")).chat([{"role": "user", "content": "hi"}])
    result = AIClient(config(ai_provider="openrouter", openrouter_api_key="bad", language="en")).test()
    assert result["code"] == "auth" and result["error"] == "Invalid OpenRouter API key"


def test_openrouter_free_models(fake, store):
    client = AIClient(config(ai_provider="openrouter", openrouter_api_key="or-good"))
    assert client.configured
    result = client.test()
    assert result["ok"] and result["free_per_day"] == 50
    assert result["model"] == "deepseek/deepseek-chat-v3-0324:free"
    assert result["models"] == rank_free_models(OPENROUTER_MODELS)
    _, body = _FakeAPIs.requests[-1]
    assert body["models"] == ["deepseek/deepseek-chat-v3-0324:free", "meta-llama/llama-3.3-70b-instruct:free",
                              ai.FREE_ROUTER]  # OpenRouter moves on when a free model is busy
    assert "thinking" not in body and body["max_tokens"] >= 1500
    plan = AIAssistant(client, store).plan("открой мою почту", "ru")
    assert plan["actions"] == [{"type": "open_url", "url": "https://mail.yandex.ru"}]


def test_openrouter_limits_are_explained(fake):
    def error(key):
        with pytest.raises(AIError) as err:
            AIClient(config(ai_provider="openrouter", openrouter_api_key=key)).chat([{"role": "user", "content": "hi"}])
        return err.value

    limit = error("or-limit")
    assert limit.code == "daily_limit" and "закончились" in str(limit) and "50" in limit.hint
    privacy = error("or-privacy")
    assert privacy.code == "privacy" and "openrouter.ai/settings/privacy" in privacy.hint
    # a busy free model: the request is repeated through OpenRouter's free router
    client = AIClient(config(ai_provider="openrouter", openrouter_api_key="or-busy",
                             ai_model="qwen/qwen3-235b-a22b:free"))
    with pytest.raises(AIError) as err:  # a model chosen by hand is not replaced
        client.chat([{"role": "user", "content": "hi"}])
    assert err.value.code == "busy"
    client = AIClient(config(ai_provider="openrouter", openrouter_api_key="or-busy"))
    text, used = client.complete(client.conn(), [{"role": "user", "content": "hi"}])
    assert used == "meta-llama/llama-3.3-70b-instruct:free" and text
    assert _FakeAPIs.requests[-1][1]["model"] == ai.FREE_ROUTER


def test_ollama_runs_locally(fake, store):
    client = AIClient(config(ai_provider="ollama", ollama_url=fake.removeprefix("http://") + "/ol/"))
    result = client.test()
    assert result["ok"] and result["model"] == "qwen2.5:7b"
    assert result["models"] == ["nomic-embed-text:latest", "qwen2.5:7b"]
    assert AIAssistant(client, store).ask("ты готов?", "ru") == "Готов, сэр."  # the "thinking" part is dropped
    plan = AIAssistant(client, store).plan("открой мою почту", "ru")
    assert plan["reply"] == "Открываю почту, сэр"
    path, body = _FakeAPIs.requests[-1]
    assert path == "/ol/api/chat" and body["format"] == "json" and body["options"]["num_ctx"] >= 8192


def test_ollama_not_running():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    result = AIClient(config(ai_provider="ollama", ollama_url=f"http://127.0.0.1:{port}")).test()
    assert not result["ok"] and result["code"] == "offline"
    assert "Ollama не запущена" in result["error"] and "ollama pull" in result["hint"]


def test_custom_openai_compatible_api(fake, store):
    client = AIClient(config(ai_provider="custom", custom_url=fake + "/cu/v1/chat/completions"))
    assert client.configured
    result = client.test()
    assert result["ok"] and result["model"] == "llama-3.3-70b-versatile"
    plan = AIAssistant(client, store).plan("открой мою почту", "ru")  # retried without response_format
    assert plan["actions"] == [{"type": "open_url", "url": "https://mail.yandex.ru"}]
    assert not AIClient(config(ai_provider="custom")).configured


def test_provider_settings(jarvis_home):
    s = Settings()
    assert s.get("ai_provider") == "openrouter" and s.get("ollama_url") == "http://localhost:11434"
    s.update({"ai_provider": "deepseek", "ai_model": "deepseek-v4-flash"})
    assert s.get("ai_model") == "deepseek-v4-flash"
    s.update({"ai_provider": "ollama"})
    assert s.get("ai_model") == "auto"  # models differ between providers
    s.update({"openrouter_api_key": " sk-or-v1-x ", "custom_api_key": "abc"})
    again = Settings()
    assert again.get("openrouter_api_key") == "sk-or-v1-x" and again.get("custom_api_key") == "abc"
    with pytest.raises(ValueError):
        s.update({"ai_provider": "gpt"})
