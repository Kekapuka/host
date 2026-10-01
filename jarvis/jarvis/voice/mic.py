"""Continuous microphone capture with a simple energy-based voice activity detector.

The listener cuts the audio stream into phrases (speech followed by ~0.8 s of silence) and
hands each phrase to `on_phrase(pcm16_bytes, sample_rate)`. It also reports the input level
for the UI meter.
"""
from __future__ import annotations

import array
import collections
import logging
import math
import queue
import threading
import time
from typing import Callable

log = logging.getLogger("jarvis.mic")

FRAME_MS = 30
PREROLL_MS = 300
START_FRAMES = 3          # ~90 ms of voice starts a phrase
END_SILENCE_MS = 800      # silence that ends a phrase
MAX_PHRASE_S = 12
MIN_VOICED_MS = 250
MIN_RMS = 220             # absolute floor for int16 audio


class MicError(RuntimeError):
    pass


def _sd():
    try:
        import sounddevice as sd  # type: ignore
    except Exception as exc:  # ImportError or OSError when PortAudio is missing
        raise MicError(f"Не удалось загрузить звуковую библиотеку: {exc}") from exc
    return sd


def list_input_devices() -> list[dict]:
    """Input devices of the default host API (MME on Windows) to avoid duplicates."""
    sd = _sd()
    try:
        devices = sd.query_devices()
        default_in = sd.default.device[0] if sd.default.device else -1
        host = devices[default_in]["hostapi"] if default_in is not None and default_in >= 0 else None
    except Exception as exc:
        raise MicError(str(exc)) from exc
    out = []
    for idx, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) <= 0:
            continue
        if host is not None and dev.get("hostapi") != host:
            continue
        out.append({"id": dev["name"], "name": dev["name"], "default": idx == default_in})
    return out


def rms_int16(data: bytes) -> float:
    samples = array.array("h")
    samples.frombytes(data[: len(data) - len(data) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


class PhraseDetector:
    """Energy VAD state machine; feed it fixed-size frames."""

    def __init__(self, sample_rate: int, frame_ms: int = FRAME_MS):
        self.rate = sample_rate
        self.frame_ms = frame_ms
        self.noise = None  # running estimate of background RMS
        self.reset()

    def reset(self) -> None:
        self.preroll = collections.deque(maxlen=max(1, PREROLL_MS // self.frame_ms))
        self.active = False
        self.voiced_run = 0
        self.silence_run = 0
        self.voiced_total = 0
        self.frames: list[bytes] = []

    def feed(self, frame: bytes, rms: float | None = None) -> bytes | None:
        if rms is None:
            rms = rms_int16(frame)
        if self.noise is None:
            self.noise = rms
        start_thr = max(MIN_RMS, self.noise * 3.0)
        keep_thr = max(MIN_RMS * 0.75, self.noise * 2.0)
        if not self.active:
            self.preroll.append(frame)
            if rms > start_thr:
                self.voiced_run += 1
                if self.voiced_run >= START_FRAMES:
                    self.active = True
                    self.frames = list(self.preroll)
                    self.voiced_total = self.voiced_run
                    self.silence_run = 0
            else:
                self.voiced_run = 0
                # adapt to the room only while nobody speaks
                self.noise = 0.95 * self.noise + 0.05 * rms
            return None
        self.frames.append(frame)
        if rms > keep_thr:
            self.silence_run = 0
            self.voiced_total += 1
        else:
            self.silence_run += 1
        too_long = len(self.frames) * self.frame_ms >= MAX_PHRASE_S * 1000
        if self.silence_run * self.frame_ms >= END_SILENCE_MS or too_long:
            phrase = b"".join(self.frames)
            voiced_ms = self.voiced_total * self.frame_ms
            self.reset()
            if voiced_ms >= MIN_VOICED_MS:
                return phrase
        return None

    @staticmethod
    def level(rms: float) -> float:
        """0..1 loudness for the UI meter."""
        return max(0.0, min(1.0, math.sqrt(rms / 6000.0)))


class MicListener:
    def __init__(self, on_phrase: Callable[[bytes, int], None],
                 on_level: Callable[[float], None] | None = None,
                 on_error: Callable[[str], None] | None = None,
                 device: str | None = None):
        self.on_phrase = on_phrase
        self.on_level = on_level
        self.on_error = on_error
        self.device = device
        self.rate = 16000
        self._stream = None
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=400)
        self._thread: threading.Thread | None = None
        self._running = False
        self._paused_until = 0.0
        self._paused = False

    @property
    def running(self) -> bool:
        return self._running

    def _device_index(self, sd) -> int | None:
        if not self.device:
            return None
        for idx, dev in enumerate(sd.query_devices()):
            if dev["name"] == self.device and dev.get("max_input_channels", 0) > 0:
                return idx
        log.warning("Microphone %r not found, using the default one", self.device)
        return None

    def start(self) -> None:
        if self._running:
            return
        sd = _sd()
        device = self._device_index(sd)

        def callback(indata, frames, time_info, status):  # PortAudio thread
            try:
                self._queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

        last_exc: Exception | None = None
        for rate in (16000, None):
            try:
                if rate is None:
                    info = sd.query_devices(device if device is not None else sd.default.device[0])
                    rate = int(info["default_samplerate"])
                blocksize = int(rate * FRAME_MS / 1000)
                stream = sd.RawInputStream(samplerate=rate, blocksize=blocksize, device=device,
                                           channels=1, dtype="int16", callback=callback)
                stream.start()
                self._stream, self.rate = stream, rate
                break
            except Exception as exc:
                last_exc = exc
                log.warning("Cannot open the microphone at %s Hz: %s", rate, exc)
        if self._stream is None:
            raise MicError(f"Не удалось открыть микрофон: {last_exc}")
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="mic-vad", daemon=True)
        self._thread.start()
        log.info("Microphone started at %s Hz", self.rate)

    def stop(self) -> None:
        self._running = False
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

    def pause(self) -> None:
        """Ignore the microphone (while Jarvis is speaking)."""
        self._paused = True

    def resume(self, delay: float = 0.3) -> None:
        self._paused_until = time.time() + delay
        self._paused = False

    def _loop(self) -> None:
        detector = PhraseDetector(self.rate)
        frame_bytes = int(self.rate * FRAME_MS / 1000) * 2
        pending = b""
        last_level = 0.0
        peak = 0.0
        while self._running:
            try:
                chunk = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if chunk is None:
                break
            if self._paused or time.time() < self._paused_until:
                detector.reset()
                pending = b""
                continue
            pending += chunk
            while len(pending) >= frame_bytes:
                frame, pending = pending[:frame_bytes], pending[frame_bytes:]
                rms = rms_int16(frame)
                peak = max(peak, detector.level(rms))
                now = time.time()
                if self.on_level and now - last_level >= 0.07:
                    last_level = now
                    try:
                        self.on_level(peak)
                    except Exception:
                        log.exception("level callback failed")
                    peak = 0.0
                phrase = detector.feed(frame, rms)
                if phrase:
                    try:
                        self.on_phrase(phrase, self.rate)
                    except Exception:
                        log.exception("phrase callback failed")
        if self.on_level:
            try:
                self.on_level(0.0)
            except Exception:
                pass
