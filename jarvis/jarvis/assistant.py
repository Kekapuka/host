"""The assistant: microphone -> recognition -> wake word -> commands -> actions -> spoken reply."""
from __future__ import annotations

import logging
import queue
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .actions import ActionError, ExecContext, Executor
from .matcher import Matcher, PlanStep, find_wake_word, match_word_list
from .util import detect_lang, render_template, time_vars

log = logging.getLogger("jarvis.assistant")

AWAKE_SECONDS = 8.0
CONFIRM_SECONDS = 15.0

PHRASES = {
    "ru": {
        "unknown": ["Не знаю такой команды: «{text}». Добавьте её в редакторе команд.",
                    "Команда «{text}» мне не знакома, сэр."],
        "unknown_short": "Не понял команду",
        "confirm": "Подтвердите: {names}. Скажите «{yes}» или «{no}».",
        "confirm_again": "Скажите «{yes}» или «{no}».",
        "cancelled": "Отменено",
        "done": "Готово",
        "nothing": "Нечего отменять",
        "failed": "Не получилось: {error}",
        "ai_error": "ИИ недоступен: {error}",
        "stt_error": "Нет связи с сервисом распознавания речи",
    },
    "en": {
        "unknown": ["I don't know the command “{text}”. You can add it in the command editor.",
                    "“{text}” is not a command I know, sir."],
        "unknown_short": "I didn't understand",
        "confirm": "Please confirm: {names}. Say “{yes}” or “{no}”.",
        "confirm_again": "Say “{yes}” or “{no}”.",
        "cancelled": "Cancelled",
        "done": "Done",
        "nothing": "Nothing to cancel",
        "failed": "That didn't work: {error}",
        "ai_error": "AI is unavailable: {error}",
        "stt_error": "The speech recognition service is unreachable",
    },
}


def phrase(lang: str, key: str, **kw: Any) -> str:
    value = PHRASES.get(lang, PHRASES["ru"])[key]
    if isinstance(value, list):
        value = random.choice(value)
    return value.format(**kw)


@dataclass
class Step:
    text: str
    kind: str  # command | ai | unknown
    match: Any = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    reply: str = ""

    @property
    def needs_confirm(self) -> bool:
        return self.kind == "command" and bool(self.match.command.data.get("confirm"))

    @property
    def label(self) -> str:
        if self.kind == "command":
            return self.match.command.path[:-5].replace("/", " › ")
        return self.kind


class Assistant:
    def __init__(self, settings, store, history, bus, executor: Executor, speaker, ai=None,
                 stt_factory: Callable[[], Any] | None = None, mic_factory: Callable[..., Any] | None = None):
        self.settings = settings
        self.store = store
        self.history = history
        self.bus = bus
        self.executor = executor
        self.speaker = speaker
        self.ai = ai
        self._stt_factory = stt_factory
        self._mic_factory = mic_factory
        self._stt = None
        self.mic = None
        self.phase = "off"
        self._mic_error = ""
        self._jobs: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._audio: queue.Queue[tuple[bytes, int] | None] = queue.Queue(maxsize=8)
        self._pending: dict[str, Any] | None = None
        self._awake_until = 0.0
        self._cancel = threading.Event()
        self._busy = False
        self._last_stt_error = 0.0
        self._running = True
        if speaker is not None:
            speaker.on_start = self._on_speech_start
            speaker.on_end = self._on_speech_end
        threading.Thread(target=self._job_loop, name="assistant", daemon=True).start()
        threading.Thread(target=self._stt_loop, name="stt-worker", daemon=True).start()

    # --- state ------------------------------------------------------------------------------
    def state(self) -> dict[str, Any]:
        return {"mic": bool(self.mic and self.mic.running), "phase": self.phase,
                "error": self._mic_error, "pending": (self._pending or {}).get("entry")}

    def _set_phase(self, phase: str) -> None:
        if phase != self.phase:
            self.phase = phase
            self.bus.emit("state", self.state())

    def _idle_phase(self) -> str:
        if self._pending:
            return "confirm"
        if self.mic and self.mic.running:
            return "awake" if time.time() < self._awake_until else "listening"
        return "off"

    def _lang(self, text: str = "") -> str:
        ui = self.settings.get("language")
        stt = self.settings.get("stt_language")
        default = stt if stt in ("ru", "en") else ui
        return detect_lang(text, default) if text else default

    # --- microphone -------------------------------------------------------------------------
    def set_mic(self, on: bool) -> dict[str, Any]:
        if on:
            if not (self.mic and self.mic.running):
                self._mic_error = ""
                try:
                    if self._mic_factory is None:
                        raise RuntimeError("Микрофон недоступен")
                    self.mic = self._mic_factory(
                        on_phrase=self._on_phrase, on_level=lambda v: self.bus.emit("level", round(v, 3)),
                        device=self.settings.get("mic_device"))
                    self.mic.start()
                except Exception as exc:
                    log.warning("Microphone error: %s", exc)
                    self.mic = None
                    self._mic_error = str(exc)
                    self.bus.emit("toast", {"kind": "error", "text": str(exc)})
        else:
            if self.mic:
                self.mic.stop()
            self.mic = None
            self._awake_until = 0.0
        self._set_phase(self._idle_phase())
        self.bus.emit("state", self.state())
        return self.state()

    def restart_mic(self) -> None:
        if self.mic and self.mic.running:
            self.set_mic(False)
            self.set_mic(True)

    def _on_phrase(self, pcm: bytes, rate: int) -> None:
        if self.speaker is not None and self.speaker.speaking:
            return
        try:
            self._audio.put_nowait((pcm, rate))
        except queue.Full:
            log.warning("Recognition queue is full, phrase dropped")

    def _on_speech_start(self) -> None:
        if self.mic:
            self.mic.pause()
        self._set_phase("speaking")

    def _on_speech_end(self) -> None:
        if self.mic:
            self.mic.resume(0.35)
        self._set_phase(self._idle_phase())

    # --- recognition ------------------------------------------------------------------------
    def _stt_loop(self) -> None:
        while self._running:
            item = self._audio.get()
            if item is None:
                return
            pcm, rate = item
            if self.phase in ("listening", "awake", "confirm"):
                self._set_phase("recognizing" if self.phase != "confirm" else "confirm")
            try:
                if self._stt is None:
                    if self._stt_factory is None:
                        raise RuntimeError("распознавание речи недоступно")
                    self._stt = self._stt_factory()
                candidates = self._stt.recognize(pcm, rate, mode=self.settings.get("stt_language"),
                                                 wake_word=self.settings.get("wake_word"),
                                                 prefer=self.settings.get("language"))
            except Exception as exc:
                log.warning("Recognition failed: %s", exc)
                if time.time() - self._last_stt_error > 30:
                    self._last_stt_error = time.time()
                    self.bus.emit("toast", {"kind": "error", "text": phrase(self._lang(), "stt_error")
                                            + f" ({exc})"})
                candidates = []
            if self.phase == "recognizing":
                self._set_phase(self._idle_phase())
            if candidates:
                self._jobs.put(("voice", candidates))

    # --- public entry points ----------------------------------------------------------------
    def submit_text(self, text: str, source: str = "text") -> None:
        text = (text or "").strip()
        if text:
            self._jobs.put(("text", (text, source)))

    def confirm(self, entry_id: str | None, yes: bool) -> None:
        self._jobs.put(("confirm", (entry_id, yes)))

    def stop_speaking(self) -> None:
        if self.speaker is not None:
            self.speaker.stop()

    def cancel(self) -> None:
        self._cancel.set()
        self.stop_speaking()

    def shutdown(self) -> None:
        self._running = False
        self.set_mic(False)
        self._cancel.set()
        self._jobs.put(("quit", None))
        try:
            self._audio.put_nowait(None)
        except queue.Full:
            pass
        if self._stt is not None and hasattr(self._stt, "close"):
            self._stt.close()

    # --- job loop ---------------------------------------------------------------------------
    def _job_loop(self) -> None:
        while True:
            try:
                kind, payload = self._jobs.get(timeout=0.5)
            except queue.Empty:
                self._tick()
                continue
            if kind == "quit":
                return
            try:
                if kind == "voice":
                    self._handle_voice(payload)
                elif kind == "text":
                    text, source = payload
                    self._handle_text(text, source)
                elif kind == "confirm":
                    entry_id, yes = payload
                    if self._pending and (entry_id in (None, self._pending["entry"])):
                        self._resolve_pending(yes)
            except Exception:
                log.exception("Job %s failed", kind)
            finally:
                self._tick()

    def _tick(self) -> None:
        now = time.time()
        if self._pending and now > self._pending["expires"]:
            entry = self._pending["entry"]
            self._pending = None
            updated = self.history.update(entry, status="cancelled",
                                          reply=phrase(self._lang(), "cancelled"))
            if updated:
                self.bus.emit("history_update", updated)
        if self.phase in ("awake", "confirm", "listening", "off") and not self._busy:
            if self.speaker is None or not self.speaker.speaking:
                self._set_phase(self._idle_phase())

    def _speak(self, text: str, lang: str) -> None:
        if text and self.speaker is not None and not self.settings.get("silent"):
            self.speaker.say(text, lang)

    # --- voice ------------------------------------------------------------------------------
    def _handle_voice(self, candidates: list) -> None:
        wake = self.settings.get("wake_word")
        chosen = None
        for cand in candidates[:6]:
            found, rest = find_wake_word(cand.text, wake)
            if found:
                chosen = (cand, rest, True)
                break
        expecting = self._pending is not None or time.time() < self._awake_until
        if chosen is None and expecting:
            chosen = (candidates[0], candidates[0].text, False)
        if chosen is None:
            self.bus.emit("heard", {"text": candidates[0].text, "addressed": False})
            return
        cand, rest, had_wake = chosen
        self.bus.emit("heard", {"text": cand.text, "addressed": True})
        lang = self._lang(cand.text)
        if self._pending:
            if self._answer_pending(rest or cand.text, strict=False):
                return
            if not had_wake or not rest:
                self._speak(phrase(lang, "confirm_again", yes=self._yes(), no=self._no()), lang)
                return
            self._resolve_pending(False, quiet=True)
        if not rest:
            self._awake_until = time.time() + AWAKE_SECONDS
            self._set_phase("awake")
            if not self.settings.get("silent") and self.speaker is not None:
                self.speaker.chime()
            return
        self._awake_until = 0.0
        alternatives = []
        for other in candidates[1:4]:
            found, other_rest = find_wake_word(other.text, wake)
            if found and other_rest:
                alternatives.append(other_rest)
            elif not had_wake and other.text:
                alternatives.append(other.text)
        self._run(rest, heard=cand.text, source="voice", lang=lang, alternatives=alternatives)

    def _handle_text(self, text: str, source: str) -> None:
        found, rest = find_wake_word(text, self.settings.get("wake_word"))
        if found:
            text = rest
        if not text:
            return
        if self._pending and self._answer_pending(text, strict=False):
            return
        if self._pending:
            self._resolve_pending(False, quiet=True)
        self._run(text, heard=text, source=source, lang=self._lang(text))

    def _yes(self) -> str:
        words = self.settings.get("confirm_words")
        return words[0] if words else "да"

    def _no(self) -> str:
        words = self.settings.get("cancel_words")
        return words[0] if words else "нет"

    def _answer_pending(self, text: str, strict: bool) -> bool:
        if match_word_list(text, self.settings.get("cancel_words"), strict=strict):
            self._resolve_pending(False)
            return True
        if match_word_list(text, self.settings.get("confirm_words"), strict=strict):
            self._resolve_pending(True)
            return True
        return False

    # --- planning & execution ---------------------------------------------------------------
    def _plan(self, text: str, alternatives: list[str]) -> tuple[str, list[Step]]:
        matcher = Matcher(self.store.entries())
        chain = self.settings.get("chain_words")
        best_text, best_plan = text, matcher.plan(text, chain)

        def quality(plan: list[PlanStep]) -> tuple:
            matched = [s for s in plan if s.match]
            return (len(matched) == len(plan), len(matched), sum(s.match.score for s in matched))

        for alt in alternatives:
            if all(s.match for s in best_plan):
                break
            plan = matcher.plan(alt, chain)
            if quality(plan) > quality(best_plan):
                best_text, best_plan = alt, plan
        steps = [Step(s.text, "command", match=s.match) if s.match else Step(s.text, "unknown")
                 for s in best_plan]
        return best_text, steps

    def _run(self, text: str, heard: str, source: str, lang: str, alternatives: list[str] | None = None) -> None:
        self._busy = True
        self._set_phase("processing")
        entry = self.history.add(source=source, heard=heard, text=text, status="processing")
        self.bus.emit("history_add", entry)
        try:
            if match_word_list(text, self.settings.get("cancel_words"), strict=True):
                self.cancel()
                reply = phrase(lang, "cancelled")
                self._finish(entry["id"], [], reply, "cancelled", lang)
                return
            text, steps = self._plan(text, alternatives or [])
            if text != entry["text"]:
                self.history.update(entry["id"], text=text)
            self._fill_ai(steps, lang)
            if any(s.needs_confirm for s in steps):
                names = ", ".join(s.match.command.name for s in steps if s.needs_confirm)
                prompt = phrase(lang, "confirm", names=names, yes=self._yes(), no=self._no())
                self._pending = {"entry": entry["id"], "steps": steps, "lang": lang,
                                 "expires": time.time() + CONFIRM_SECONDS}
                updated = self.history.update(entry["id"], status="confirm", reply=prompt,
                                              steps=[self._step_info(s, "pending") for s in steps])
                self.bus.emit("history_update", updated)
                self._set_phase("confirm")
                self._speak(prompt, lang)
                return
            self._execute(entry["id"], steps, lang)
        finally:
            self._busy = False
            if not (self.speaker and self.speaker.speaking):
                self._set_phase(self._idle_phase())

    def _fill_ai(self, steps: list[Step], lang: str) -> None:
        if not self.ai or not self.ai.available:
            return
        for step in steps:
            if step.kind != "unknown":
                continue
            try:
                result = self.ai.plan(step.text, lang)
                step.kind = "ai"
                step.actions = result["actions"]
                step.reply = result["reply"]
            except Exception as exc:
                log.warning("AI planning failed: %s", exc)
                step.reply = phrase(lang, "ai_error", error=exc)

    def _resolve_pending(self, yes: bool, quiet: bool = False) -> None:
        pending, self._pending = self._pending, None
        if not pending:
            return
        lang = pending["lang"]
        if yes:
            self._busy = True
            self._set_phase("processing")
            try:
                self._execute(pending["entry"], pending["steps"], lang)
            finally:
                self._busy = False
                self._set_phase(self._idle_phase())
        else:
            reply = phrase(lang, "cancelled")
            self._finish(pending["entry"], [self._step_info(s, "cancelled") for s in pending["steps"]],
                         reply, "cancelled", lang, speak=not quiet)

    @staticmethod
    def _step_info(step: Step, status: str, error: str = "") -> dict[str, Any]:
        info = {"text": step.text, "kind": step.kind, "status": status, "label": step.label}
        if step.kind == "command":
            info["path"] = step.match.command.path
        if error:
            info["error"] = error
        return info

    def _execute(self, entry_id: str, steps: list[Step], lang: str) -> None:
        self._cancel.clear()
        replies: list[str] = []
        infos: list[dict[str, Any]] = []
        for step in steps:
            if self._cancel.is_set():
                infos.append(self._step_info(step, "cancelled"))
                continue
            if step.kind == "unknown":
                infos.append(self._step_info(step, "unknown"))
                replies.append(step.reply or phrase(lang, "unknown", text=step.text))
                continue
            if step.kind == "command":
                data = step.match.command.data
                variables = {**time_vars(lang), **step.match.captures, "_text": step.text}
                ctx = ExecContext(variables, data.get("folder_meta") or {}, lang, self._cancel)
                actions = data.get("actions", [])
                response_tpl = data.get("response", "")
            else:
                ctx = ExecContext({**time_vars(lang), "_text": step.text}, {}, lang, self._cancel)
                actions = step.actions
                response_tpl = step.reply
            try:
                self.executor.run(actions, ctx)
                status, error = "ok", ""
            except ActionError as exc:
                status, error = "error", str(exc)
            response = render_template(response_tpl, ctx.vars) if response_tpl else ""
            if status == "ok":
                if response:
                    replies.append(response)
                replies.extend(ctx.messages)
            else:
                replies.append(error if self._cancel.is_set() else phrase(lang, "failed", error=error))
            infos.append(self._step_info(step, status, error))
        statuses = {i["status"] for i in infos}
        if statuses <= {"ok"}:
            overall = "ok"
        elif "ok" in statuses:
            overall = "partial"
        elif statuses <= {"cancelled"}:
            overall = "cancelled"
        else:
            overall = "error"
        reply = _join(replies)
        self._finish(entry_id, infos, reply, overall, lang)

    def _finish(self, entry_id: str, infos: list[dict[str, Any]], reply: str, status: str, lang: str,
                speak: bool = True) -> None:
        updated = self.history.update(entry_id, steps=infos, reply=reply, status=status)
        if updated:
            self.bus.emit("history_update", updated)
        if speak:
            self._speak(reply, lang)

    # --- hooks for "jarvis" actions ---------------------------------------------------------
    def jarvis_op(self, op: str, value: Any = None) -> None:
        if op == "silent_on":
            self.settings.update({"silent": True})
        elif op == "silent_off":
            self.settings.update({"silent": False})
        elif op == "theme_dark":
            self.settings.update({"theme": "dark"})
        elif op == "theme_light":
            self.settings.update({"theme": "light"})
        elif op == "volume" and value is not None:
            from .textproc import parse_number

            level = parse_number(value)
            if level is not None:
                self.settings.update({"volume": level})
        elif op == "mic_off":
            threading.Timer(1.5, lambda: self.set_mic(False)).start()
        elif op == "stop":
            self.stop_speaking()
            if self._pending:
                self._resolve_pending(False, quiet=True)
        elif op in ("open_settings", "open_editor", "open_home"):
            self.bus.emit("navigate", op.replace("open_", ""))


def _join(parts: list[str]) -> str:
    out = []
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        if p[-1] not in ".!?…":
            p += "."
        out.append(p)
    return " ".join(out)
