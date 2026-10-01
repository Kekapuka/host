"""Small shared helpers."""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis")

_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        log.warning("Cannot read %s: %s", path, exc)
        return default


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON through a temp file so a crash never leaves a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def detect_lang(text: str, default: str = "ru") -> str:
    """'ru' when the text contains Cyrillic, 'en' for Latin text, default otherwise."""
    if not text:
        return default
    if _CYRILLIC.search(text):
        return "ru"
    if re.search(r"[a-z]", text, re.IGNORECASE):
        return "en"
    return default


RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
             "сентября", "октября", "ноября", "декабря"]
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]
RU_WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
EN_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def time_vars(lang: str, now: datetime | None = None) -> dict[str, str]:
    """Variables available in responses: {time}, {date}, {weekday}, {year}."""
    now = now or datetime.now()
    if lang == "en":
        date = f"{EN_MONTHS[now.month - 1]} {now.day}"
        weekday = EN_WEEKDAYS[now.weekday()]
    else:
        date = f"{now.day} {RU_MONTHS[now.month - 1]}"
        weekday = RU_WEEKDAYS[now.weekday()]
    return {
        "time": now.strftime("%H:%M"),
        "date": date,
        "weekday": weekday,
        "year": str(now.year),
    }


class SafeDict(dict):
    """dict for str.format_map that leaves unknown {placeholders} untouched."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_template(template: str, variables: dict[str, Any]) -> str:
    if not template or "{" not in template:
        return template or ""
    try:
        return template.format_map(SafeDict({k: v for k, v in variables.items() if v is not None}))
    except (ValueError, IndexError):
        return template


def start_thread(target, name: str, *args, **kwargs) -> threading.Thread:
    thread = threading.Thread(target=target, name=name, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread
