"""Speech-to-text through the Google Web Speech API (via the SpeechRecognition package).

In "auto" mode the phrase is recognised as Russian and English in parallel and the variant that
contains the wake word (or has higher confidence) wins.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ..matcher import find_wake_word

log = logging.getLogger("jarvis.stt")

LANG_CODES = {"ru": "ru-RU", "en": "en-US"}
ENDPOINT = "https://www.google.com/speech-api/v2/recognize"


class STTError(RuntimeError):
    pass


@dataclass
class Candidate:
    text: str
    lang: str
    confidence: float


class GoogleSTT:
    def __init__(self, timeout: float = 8.0):
        try:
            import speech_recognition as sr  # type: ignore
        except Exception as exc:
            raise STTError(f"Модуль SpeechRecognition не установлен: {exc}") from exc
        self._sr = sr
        self._recognizer = sr.Recognizer()
        self._recognizer.operation_timeout = timeout
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="stt")

    def _recognize_one(self, audio, lang: str) -> list[Candidate]:
        sr = self._sr
        try:
            result = self._recognizer.recognize_google(audio, language=LANG_CODES[lang], show_all=True,
                                                       endpoint=ENDPOINT)
        except sr.UnknownValueError:
            return []
        except TypeError:  # older SpeechRecognition without `endpoint`
            try:
                result = self._recognizer.recognize_google(audio, language=LANG_CODES[lang], show_all=True)
            except sr.UnknownValueError:
                return []
        if not isinstance(result, dict):
            return []
        alternatives = result.get("alternative") or []
        out = []
        for i, alt in enumerate(alternatives):
            text = (alt.get("transcript") or "").strip()
            if text:
                conf = float(alt.get("confidence", 0.0 if i else 0.5))
                out.append(Candidate(text, lang, conf))
        return out

    def recognize(self, pcm: bytes, rate: int, mode: str = "auto", wake_word: str = "",
                  prefer: str = "ru") -> list[Candidate]:
        """Candidates ordered from the most to the least likely."""
        audio = self._sr.AudioData(pcm, rate, 2)
        langs = ["ru", "en"] if mode == "auto" else [mode if mode in LANG_CODES else "ru"]
        futures = {lang: self._pool.submit(self._recognize_one, audio, lang) for lang in langs}
        results: dict[str, list[Candidate]] = {}
        errors = []
        for lang, fut in futures.items():
            try:
                results[lang] = fut.result(timeout=15)
            except Exception as exc:
                errors.append(exc)
                results[lang] = []
        if errors and not any(results.values()):
            if len(errors) == len(langs):
                raise STTError(f"Сервис распознавания речи недоступен: {errors[0]}")
        if len(langs) == 1:
            return results[langs[0]]

        def rank(lang: str) -> tuple:
            cands = results.get(lang) or []
            if not cands:
                return (0, 0, 0.0, 0)
            top = cands[0]
            has_wake = bool(wake_word) and find_wake_word(top.text, wake_word)[0]
            return (1, int(has_wake), top.confidence, int(lang == prefer))

        order = sorted(langs, key=rank, reverse=True)
        return [c for lang in order for c in results.get(lang, [])]

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
