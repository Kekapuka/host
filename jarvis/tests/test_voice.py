import math
import queue
import random
import struct
import threading
import time

import pytest

from jarvis.voice.mic import FRAME_MS, MicListener, PhraseDetector
from jarvis.voice.stt import Candidate

RATE = 16000
FRAME = RATE * FRAME_MS // 1000


def frames(kind: str, seconds: float):
    """int16 mono frames: background noise or a voiced (harmonic) sound."""
    out = []
    n = int(seconds * 1000 / FRAME_MS)
    for f in range(n):
        samples = []
        for i in range(FRAME):
            t = (f * FRAME + i) / RATE
            if kind == "voice":
                v = 5000 * math.sin(2 * math.pi * 220 * t) + 2500 * math.sin(2 * math.pi * 660 * t)
            else:
                v = random.gauss(0, 60)
            samples.append(int(max(-32768, min(32767, v))))
        out.append(struct.pack(f"<{FRAME}h", *samples))
    return out


def test_detector_cuts_a_phrase():
    det = PhraseDetector(RATE)
    stream = frames("noise", 1.0) + frames("voice", 1.2) + frames("noise", 1.2)
    phrases = [p for p in (det.feed(fr) for fr in stream) if p]
    assert len(phrases) == 1
    seconds = len(phrases[0]) / 2 / RATE
    assert 1.6 <= seconds <= 2.6  # preroll + speech + trailing silence


def test_detector_ignores_clicks():
    det = PhraseDetector(RATE)
    stream = frames("noise", 1.0) + frames("voice", 0.12) + frames("noise", 1.5)
    assert not [p for p in (det.feed(fr) for fr in stream) if p]


def test_listener_loop_and_pause():
    got = []
    levels = []
    mic = MicListener(on_phrase=lambda pcm, rate: got.append(len(pcm)), on_level=levels.append)
    mic.rate = RATE
    mic._running = True
    thread = threading.Thread(target=mic._loop, daemon=True)
    thread.start()
    for fr in frames("noise", 0.6) + frames("voice", 1.0) + frames("noise", 1.0):
        mic._queue.put(fr)
    assert _wait(lambda: len(got) == 1)
    assert levels  # throttled to ~14 updates per second in real time
    mic.pause()
    for fr in frames("voice", 1.0) + frames("noise", 1.0):
        mic._queue.put(fr)
    time.sleep(0.3)
    assert len(got) == 1  # paused while Jarvis speaks
    mic._running = False
    mic._queue.put(None)
    thread.join(2)


def _wait(pred, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_auto_language_prefers_transcript_with_wake_word(monkeypatch):
    pytest.importorskip("speech_recognition")
    from jarvis.voice.stt import GoogleSTT

    stt = GoogleSTT()
    answers = {
        "ru": [Candidate("джарвис опен хром", "ru", 0.62)],
        "en": [Candidate("Jarvis open Chrome", "en", 0.91), Candidate("Jarvis open chrom", "en", 0.0)],
    }
    monkeypatch.setattr(stt, "_recognize_one", lambda audio, lang: answers[lang])
    result = stt.recognize(b"\0\0" * 1600, RATE, mode="auto", wake_word="джарвис")
    assert [c.lang for c in result] == ["en", "en", "ru"]
    answers["en"] = [Candidate("Java's open", "en", 0.95)]
    result = stt.recognize(b"\0\0" * 1600, RATE, mode="auto", wake_word="джарвис")
    assert result[0].lang == "ru"  # only the Russian variant contains the wake word
    assert [c.lang for c in stt.recognize(b"\0\0" * 1600, RATE, mode="ru")] == ["ru"]
    stt.close()


class _Settings:
    def __init__(self, **values):
        self.values = {"volume": 70, "voice_engine": "neural", **values}

    def get(self, key):
        return self.values[key]


def test_speaker_falls_back_and_reports_start_end(monkeypatch):
    from jarvis.voice import tts

    events = []
    speaker = tts.Speaker(_Settings(), on_start=lambda: events.append("start"), on_end=lambda: events.append("end"))
    monkeypatch.setattr(speaker, "_neural", lambda text, lang: (_ for _ in ()).throw(OSError("offline")))
    spoken = []
    monkeypatch.setattr(speaker, "_system", lambda text, lang: spoken.append(text))
    done = speaker.say("Проверка связи", "ru")
    assert done.wait(5)
    assert spoken == ["Проверка связи"]
    assert _wait(lambda: events == ["start", "end"])
    speaker.shutdown()


def test_chime_pcm_shape():
    from jarvis.voice.tts import _chime_pcm

    pcm = _chime_pcm(44100, 2, 0.5)
    assert len(pcm) == (int(44100 * 0.07) + int(44100 * 0.09)) * 2 * 2
