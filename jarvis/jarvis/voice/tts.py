"""Jarvis' voice: Microsoft neural voices (edge-tts, online) with a Windows SAPI fallback.

Speech runs in its own thread. `on_start` / `on_end` let the assistant mute the microphone
while Jarvis talks, so it never hears itself.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import math
import os
import queue
import struct
import tempfile
import threading
import time
from typing import Any, Callable

from .. import paths

log = logging.getLogger("jarvis.tts")

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

NEURAL_VOICES = {"ru": "ru-RU-DmitryNeural", "en": "en-GB-RyanNeural"}
SAPI_LANG_IDS = {"ru": ("419",), "en": ("809", "409")}
CACHE_LIMIT = 400


class Speaker:
    def __init__(self, settings, on_start: Callable[[], None] | None = None,
                 on_end: Callable[[], None] | None = None):
        self.settings = settings
        self.on_start = on_start
        self.on_end = on_end
        self._queue: queue.Queue[tuple[str, str, threading.Event] | None] = queue.Queue()
        self._stop = threading.Event()
        self._speaking = threading.Event()
        self._neural_failures = 0
        self._neural_disabled_until = 0.0
        self._mixer_ok: bool | None = None
        self._thread = threading.Thread(target=self._loop, name="tts", daemon=True)
        self._thread.start()

    # --- public -----------------------------------------------------------------------------
    @property
    def speaking(self) -> bool:
        return self._speaking.is_set()

    def say(self, text: str, lang: str = "ru") -> threading.Event:
        done = threading.Event()
        text = (text or "").strip()
        if not text:
            done.set()
            return done
        self._queue.put((text, lang if lang in NEURAL_VOICES else "ru", done))
        return done

    def stop(self) -> None:
        """Interrupt the current phrase and drop the queue."""
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item:
                item[2].set()
        self._stop.set()

    def shutdown(self) -> None:
        self.stop()
        self._queue.put(None)

    def chime(self) -> None:
        """Short "I'm listening" sound."""
        threading.Thread(target=self._play_chime, name="chime", daemon=True).start()

    # --- worker -----------------------------------------------------------------------------
    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            text, lang, done = item
            self._stop.clear()
            self._speaking.set()
            if self.on_start:
                try:
                    self.on_start()
                except Exception:
                    log.exception("on_start failed")
            try:
                self._speak(text, lang)
            except Exception:
                log.exception("Speech failed")
            finally:
                self._speaking.clear()
                done.set()
                if self.on_end and self._queue.empty():
                    try:
                        self.on_end()
                    except Exception:
                        log.exception("on_end failed")

    def _volume(self) -> float:
        try:
            return max(0.01, min(1.0, int(self.settings.get("volume")) / 100.0))
        except Exception:
            return 0.7

    def _speak(self, text: str, lang: str) -> None:
        engine = self.settings.get("voice_engine")
        if engine == "neural" and time.time() >= self._neural_disabled_until:
            try:
                audio = self._neural(text, lang)
                self._neural_failures = 0
                if self._play_mp3(audio):
                    return
            except Exception as exc:
                self._neural_failures += 1
                log.warning("Neural voice failed (%s), falling back to the system voice", exc)
                if self._neural_failures >= 2:
                    self._neural_disabled_until = time.time() + 600
        self._system(text, lang)

    # --- neural voice -----------------------------------------------------------------------
    def _neural(self, text: str, lang: str) -> bytes:
        voice = NEURAL_VOICES.get(lang, NEURAL_VOICES["ru"])
        key = hashlib.sha1(f"{voice}|{text}".encode("utf-8")).hexdigest()
        cache = paths.cache_dir() / "tts"
        cache.mkdir(parents=True, exist_ok=True)
        cached = cache / f"{key}.mp3"
        if cached.exists():
            return cached.read_bytes()
        import edge_tts  # type: ignore

        async def collect() -> bytes:
            comm = edge_tts.Communicate(text, voice, rate="+4%", pitch="-3Hz",
                                        connect_timeout=6, receive_timeout=20)
            data = bytearray()
            async for chunk in comm.stream():
                if chunk.get("type") == "audio":
                    data.extend(chunk["data"])
            return bytes(data)

        audio = asyncio.run(asyncio.wait_for(collect(), timeout=25))
        if not audio:
            raise RuntimeError("пустой ответ синтезатора")
        if len(text) <= 160:
            try:
                cached.write_bytes(audio)
                files = sorted(cache.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
                for old in files[:-CACHE_LIMIT]:
                    old.unlink(missing_ok=True)
            except OSError:
                pass
        return audio

    def _mixer(self):
        if self._mixer_ok is False:
            return None
        try:
            import pygame  # type: ignore

            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            self._mixer_ok = True
            return pygame
        except Exception as exc:
            log.warning("pygame mixer unavailable: %s", exc)
            self._mixer_ok = False
            return None

    def _play_mp3(self, data: bytes) -> bool:
        pygame = self._mixer()
        if pygame is not None:
            music = pygame.mixer.music
            music.load(io.BytesIO(data), "mp3")
            music.set_volume(self._volume())
            music.play()
            while music.get_busy():
                if self._stop.wait(0.03):
                    music.stop()
                    break
            try:
                music.unload()
            except Exception:
                pass
            return True
        if paths.IS_WINDOWS:
            return self._play_mci(data)
        return False

    def _play_mci(self, data: bytes) -> bool:
        """Windows-only fallback player without extra packages."""
        import ctypes

        winmm = ctypes.windll.winmm
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.write(fd, data)
        os.close(fd)
        alias = f"jarvis{threading.get_ident()}"

        def mci(cmd: str) -> int:
            return winmm.mciSendStringW(cmd, None, 0, None)

        try:
            if mci(f'open "{path}" type mpegvideo alias {alias}') != 0:
                return False
            mci(f"setaudio {alias} volume to {int(self._volume() * 1000)}")
            mci(f"play {alias}")
            buf = ctypes.create_unicode_buffer(64)
            while True:
                winmm.mciSendStringW(f"status {alias} mode", buf, 63, None)
                if buf.value != "playing" or self._stop.wait(0.05):
                    break
            mci(f"close {alias}")
            return True
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    # --- system voice -----------------------------------------------------------------------
    def _system(self, text: str, lang: str) -> None:
        if paths.IS_WINDOWS:
            self._sapi(text, lang)
        else:
            log.info("[voice] %s", text)

    def _sapi(self, text: str, lang: str) -> None:
        import comtypes  # type: ignore
        import comtypes.client  # type: ignore

        try:
            comtypes.CoInitialize()
        except OSError:
            pass
        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        try:
            tokens = voice.GetVoices()
            wanted = SAPI_LANG_IDS.get(lang, ())
            for i in range(tokens.Count):
                token = tokens.Item(i)
                langs = str(token.GetAttribute("Language") or "").lower().split(";")
                if any(w in langs for w in wanted):
                    voice.Voice = token
                    break
        except Exception as exc:
            log.debug("Cannot select a SAPI voice: %s", exc)
        voice.Volume = int(self._volume() * 100)
        voice.Speak(text, 1)  # SVSFlagsAsync
        while not voice.WaitUntilDone(50):
            if self._stop.is_set():
                voice.Speak("", 2)  # SVSFPurgeBeforeSpeak
                break

    # --- chime ------------------------------------------------------------------------------
    def _play_chime(self) -> None:
        volume = self._volume() * 0.55
        pygame = self._mixer()
        if pygame is None:
            return
        try:
            freq, _size, channels = pygame.mixer.get_init()
            sound = pygame.mixer.Sound(buffer=_chime_pcm(freq, channels, volume))
            channel = sound.play()
            # the Sound must stay alive until it finishes, otherwise SDL stops it at once
            deadline = time.time() + 2
            while channel is not None and channel.get_busy() and time.time() < deadline:
                time.sleep(0.02)
        except Exception as exc:
            log.debug("chime failed: %s", exc)


def _chime_pcm(rate: int, channels: int, volume: float) -> bytes:
    """Two quick rising tones, 16-bit PCM."""
    out = bytearray()
    for freq, dur in ((880.0, 0.07), (1318.5, 0.09)):
        n = int(rate * dur)
        for i in range(n):
            env = min(1.0, i / (rate * 0.005)) * min(1.0, (n - i) / (rate * 0.03))
            sample = int(32767 * volume * env * math.sin(2 * math.pi * freq * i / rate))
            out += struct.pack("<h", sample) * channels
    return bytes(out)


def available_engines() -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        import edge_tts  # noqa: F401

        info["neural"] = True
    except Exception:
        info["neural"] = False
    info["system"] = paths.IS_WINDOWS
    return info
