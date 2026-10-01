import threading
import time

import pytest

from jarvis.actions import ActionError
from jarvis.assistant import Assistant
from jarvis.events import EventBus
from jarvis.history import History
from jarvis.settings import Settings
from jarvis.voice.stt import Candidate


class FakeExecutor:
    def __init__(self):
        self.calls = []
        self.fail_types = set()

    def run(self, actions, ctx):
        self.calls.append([a["type"] for a in actions])
        for a in actions:
            if a["type"] in self.fail_types:
                raise ActionError("сломалось")
            if a["type"] == "open_app":
                ctx.vars["app_name"] = "Google Chrome"
        return ctx


class FakeSpeaker:
    def __init__(self):
        self.said = []
        self.chimes = 0
        self.speaking = False
        self.on_start = None
        self.on_end = None

    def say(self, text, lang="ru"):
        self.said.append(text)

    def chime(self):
        self.chimes += 1

    def stop(self):
        pass


@pytest.fixture
def env(store):
    settings = Settings()
    bus = EventBus()
    events = []
    bus.subscribe(events.append)
    executor = FakeExecutor()
    speaker = FakeSpeaker()
    assistant = Assistant(settings, store, History(), bus, executor, speaker)
    yield assistant, executor, speaker, events, settings
    assistant.shutdown()


def wait_for(predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def last_entry(assistant):
    items = assistant.history.all()
    return items[-1] if items else None


def done(assistant):
    e = last_entry(assistant)
    return e is not None and e["status"] not in ("processing",)


def test_text_chain_runs_both_commands(env):
    assistant, executor, speaker, events, _ = env
    assistant.submit_text("открой хром и включи музыку в вк")
    assert wait_for(lambda: done(assistant))
    entry = last_entry(assistant)
    assert entry["status"] == "ok"
    assert [s["path"] for s in entry["steps"]] == ["Google Chrome/Открыть.json",
                                                   "ВКонтакте/Музыка/Включить музыку.json"]
    assert "Открываю Google Chrome" in entry["reply"] and "ВКонтакте" in entry["reply"]
    assert wait_for(lambda: speaker.said)
    assert {e["type"] for e in events} >= {"history_add", "history_update", "state"}


def test_confirmation_yes_and_no(env):
    assistant, executor, speaker, _, _ = env
    assistant.submit_text("выключи компьютер")
    assert wait_for(lambda: last_entry(assistant) and last_entry(assistant)["status"] == "confirm")
    assert executor.calls == []  # nothing ran yet
    assistant.submit_text("да")
    assert wait_for(lambda: last_entry(assistant)["status"] == "ok")
    assert executor.calls == [["system"]]

    assistant.submit_text("перезагрузи компьютер")
    assert wait_for(lambda: last_entry(assistant)["status"] == "confirm")
    assistant.submit_text("отмена")
    assert wait_for(lambda: last_entry(assistant)["status"] == "cancelled")
    assert executor.calls == [["system"]]


def test_confirm_from_ui_button(env):
    assistant, executor, _, _, _ = env
    assistant.submit_text("очисти корзину")
    assert wait_for(lambda: last_entry(assistant) and last_entry(assistant)["status"] == "confirm")
    assistant.confirm(last_entry(assistant)["id"], True)
    assert wait_for(lambda: last_entry(assistant)["status"] == "ok")


def test_unknown_command_without_ai(env):
    assistant, _, speaker, _, _ = env
    assistant.submit_text("свари кофе")
    assert wait_for(lambda: done(assistant))
    entry = last_entry(assistant)
    assert entry["status"] == "error"
    assert entry["steps"][0]["status"] == "unknown"
    assert "свари кофе" in entry["reply"]


def test_failed_action_is_reported(env):
    assistant, executor, _, _, _ = env
    executor.fail_types.add("open_url")
    assistant.submit_text("открой хром и включи музыку в вк")
    assert wait_for(lambda: done(assistant))
    entry = last_entry(assistant)
    assert entry["status"] == "partial"
    assert [s["status"] for s in entry["steps"]] == ["ok", "error"]


def test_silent_mode_does_not_speak(env):
    assistant, _, speaker, _, settings = env
    settings.update({"silent": True})
    assistant.submit_text("который час")
    assert wait_for(lambda: done(assistant))
    time.sleep(0.1)
    assert speaker.said == []
    assert "Сейчас" in last_entry(assistant)["reply"]


def test_voice_requires_wake_word(env):
    assistant, executor, speaker, events, _ = env
    assistant._jobs.put(("voice", [Candidate("открой хром", "ru", 0.9)]))
    assert wait_for(lambda: any(e["type"] == "heard" for e in events))
    assert last_entry(assistant) is None  # not addressed to Jarvis

    assistant._jobs.put(("voice", [Candidate("Джарвис открой хром", "ru", 0.9)]))
    assert wait_for(lambda: done(assistant))
    assert last_entry(assistant)["steps"][0]["path"] == "Google Chrome/Открыть.json"


def test_bare_wake_word_then_command(env):
    assistant, executor, speaker, _, _ = env
    assistant._jobs.put(("voice", [Candidate("Джарвис", "ru", 0.9)]))
    assert wait_for(lambda: speaker.chimes == 1)
    assistant._jobs.put(("voice", [Candidate("который час", "ru", 0.9)]))
    assert wait_for(lambda: done(assistant))
    assert last_entry(assistant)["steps"][0]["path"] == "Основные/Который час.json"


def test_alternative_transcripts_are_used(env):
    assistant, _, _, _, _ = env
    assistant._jobs.put(("voice", [Candidate("Джарвис открой гром и включи музыку в век", "ru", 0.6),
                                   Candidate("Джарвис открой хром и включи музыку в вк", "ru", 0.0)]))
    assert wait_for(lambda: done(assistant))
    entry = last_entry(assistant)
    assert entry["status"] == "ok" and len(entry["steps"]) == 2


def test_jarvis_ops_change_settings(env):
    assistant, _, _, _, settings = env
    assistant.jarvis_op("theme_dark")
    assistant.jarvis_op("volume", "35")
    assistant.jarvis_op("silent_on")
    assert settings.get("theme") == "dark"
    assert settings.get("volume") == 35
    assert settings.get("silent") is True


def test_settings_validation_and_persistence(jarvis_home):
    s = Settings()
    s.update({"volume": 250, "chain_words": "и, затем ,потом, и", "wake_word": "  Пятница "})
    assert s.get("volume") == 100
    assert s.get("chain_words") == ["и", "затем", "потом"]
    assert s.get("wake_word") == "пятница"
    with pytest.raises(ValueError):
        s.update({"theme": "pink"})
    s.update({"ai_api_key": "sk-test"})
    again = Settings()
    assert again.get("volume") == 100 and again.get("ai_api_key") == "sk-test"
