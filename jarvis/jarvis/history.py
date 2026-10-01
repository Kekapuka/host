"""Command history shown on the home screen."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from . import paths
from .util import read_json, write_json_atomic

MAX_ENTRIES = 300


class History:
    def __init__(self, path=None):
        self._path = path or paths.history_file()
        self._lock = threading.RLock()
        data = read_json(self._path, [])
        self._items: list[dict[str, Any]] = data if isinstance(data, list) else []

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._items]

    def add(self, **fields: Any) -> dict[str, Any]:
        entry = {
            "id": uuid.uuid4().hex[:12],
            "ts": time.time(),
            "source": "voice",
            "heard": "",
            "text": "",
            "steps": [],
            "reply": "",
            "status": "pending",
        }
        entry.update(fields)
        with self._lock:
            self._items.append(entry)
            del self._items[:-MAX_ENTRIES]
            self._save()
        return dict(entry)

    def update(self, entry_id: str, **fields: Any) -> dict[str, Any] | None:
        with self._lock:
            for item in self._items:
                if item["id"] == entry_id:
                    item.update(fields)
                    self._save()
                    return dict(item)
        return None

    def get(self, entry_id: str) -> dict[str, Any] | None:
        with self._lock:
            for item in self._items:
                if item["id"] == entry_id:
                    return dict(item)
        return None

    def clear(self) -> None:
        with self._lock:
            self._items = []
            self._save()

    def _save(self) -> None:
        write_json_atomic(self._path, self._items)
