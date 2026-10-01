"""Backend -> UI event bus.

Subscribers get every event synchronously (the pywebview pusher). The HTTP bridge long-polls
the ring buffer. Frequent 'level' events are coalesced so they never flood the buffer.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any, Callable

log = logging.getLogger("jarvis.events")

COALESCE = {"level"}


class EventBus:
    def __init__(self, size: int = 400):
        self._cond = threading.Condition()
        self._seq = 0
        self._buffer: deque[dict[str, Any]] = deque(maxlen=size)
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._subscribers.append(callback)

    def emit(self, type_: str, data: Any = None) -> None:
        with self._cond:
            self._seq += 1
            event = {"id": self._seq, "type": type_, "data": data}
            if type_ in COALESCE and self._buffer and self._buffer[-1]["type"] == type_:
                self._buffer[-1] = event
            else:
                self._buffer.append(event)
            self._cond.notify_all()
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception:
                log.exception("event subscriber failed")

    @property
    def last_id(self) -> int:
        with self._cond:
            return self._seq

    def wait(self, after: int, timeout: float = 25.0) -> list[dict[str, Any]]:
        """Events with id > after; blocks up to `timeout` seconds when there are none."""
        with self._cond:
            if self._seq <= after:
                self._cond.wait(timeout)
            return [e for e in self._buffer if e["id"] > after]
