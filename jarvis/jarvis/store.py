"""Commands stored as real folders and JSON files.

    commands/
      Google Chrome/            <- one folder per application (meta in _folder.json)
        _folder.json            {"app": "chrome", "path": "...", "process": "..."}
        Открыть.json            {"triggers": [...], "actions": [...], "response": "..."}
        Вкладки/                <- sub-folders group related actions
          Новая вкладка.json
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Any

from . import catalog
from .matcher import CommandEntry, parse_trigger
from .util import read_json, write_json_atomic

log = logging.getLogger("jarvis.store")

FOLDER_META = "_folder.json"
SEED_MARKER = ".seeded"
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
META_KEYS = {"app", "path", "args", "process", "aliases", "enabled", "browser", "note"}

ACTION_TYPES = {
    "open_app", "close_app", "focus_app", "open_url", "search_web", "hotkey", "type_text", "media",
    "system_volume", "system", "wait", "say", "run", "ask_ai", "click_element", "run_command", "jarvis",
}


class StoreError(Exception):
    pass


def sanitize_name(name: Any) -> str:
    clean = _INVALID.sub(" ", str(name or ""))
    clean = re.sub(r"\s+", " ", clean).strip().strip(".").strip().lstrip("_").strip()[:80].strip()
    if not clean:
        raise StoreError("Имя не может быть пустым")
    if clean.lower() in _RESERVED:
        clean += "_"
    return clean


def normalize_command(data: Any) -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    triggers = []
    for t in data.get("triggers") or []:
        t = " ".join(str(t).split())[:200]
        if t and t not in triggers:
            triggers.append(t)
    actions = []
    for a in data.get("actions") or []:
        if isinstance(a, dict) and a.get("type") in ACTION_TYPES:
            actions.append({k: v for k, v in a.items() if isinstance(k, str)})
    return {
        "triggers": triggers[:100],
        "actions": actions[:50],
        "response": str(data.get("response") or "")[:1000],
        "confirm": bool(data.get("confirm", False)),
        "enabled": bool(data.get("enabled", True)),
    }


def normalize_meta(meta: Any) -> dict[str, Any]:
    meta = meta if isinstance(meta, dict) else {}
    out: dict[str, Any] = {}
    for key in META_KEYS:
        if key not in meta:
            continue
        value = meta[key]
        if key == "aliases":
            if isinstance(value, str):
                value = value.split(",")
            value = [" ".join(str(v).split()) for v in value or [] if str(v).strip()][:20]
        elif key == "enabled":
            value = bool(value)
        elif value is None:
            continue
        else:
            value = str(value).strip()[:500]
            if not value:
                continue
        out[key] = value
    return out


class CommandStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cache_sig: tuple | None = None
        self._cache: list[CommandEntry] = []

    # --- paths ------------------------------------------------------------------------------
    def _abs(self, rel: str | None) -> Path:
        rel = (rel or "").replace("\\", "/").strip("/")
        root = self.root.resolve()
        path = (root / rel).resolve() if rel else root
        if path != root and root not in path.parents:
            raise StoreError("Недопустимый путь")
        return path

    def _rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    @staticmethod
    def _unique(path: Path) -> Path:
        if not path.exists():
            return path
        stem, suffix = (path.stem, path.suffix) if path.suffix == ".json" else (path.name, "")
        for i in range(2, 1000):
            candidate = path.with_name(f"{stem} ({i}){suffix}")
            if not candidate.exists():
                return candidate
        raise StoreError("Слишком много элементов с одинаковым именем")

    # --- seeding ----------------------------------------------------------------------------
    def ensure_seeded(self, lang: str = "ru") -> bool:
        marker = self.root / SEED_MARKER
        if marker.exists():
            return False
        with self._lock:
            for app_id in catalog.DEFAULT_CONNECTED:
                try:
                    self.connect_app(app_id, lang)
                except Exception:
                    log.exception("Cannot create the default pack %s", app_id)
            marker.write_text("1", encoding="utf-8")
        return True

    def reset_defaults(self, lang: str = "ru") -> None:
        """Re-create the default packs (existing folders of those packs are replaced)."""
        with self._lock:
            for app_id in catalog.DEFAULT_CONNECTED:
                self.disconnect_app(app_id)
                self.connect_app(app_id, lang)

    # --- tree -------------------------------------------------------------------------------
    def tree(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._walk(self.root)

    def _walk(self, folder: Path) -> list[dict[str, Any]]:
        nodes = []
        try:
            entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return nodes
        for p in entries:
            if p.name.startswith(".") or p.name == FOLDER_META:
                continue
            if p.is_dir():
                meta = normalize_meta(read_json(p / FOLDER_META, {}))
                nodes.append({"type": "folder", "name": p.name, "path": self._rel(p), "meta": meta,
                              "children": self._walk(p)})
            elif p.suffix.lower() == ".json":
                data = normalize_command(read_json(p, {}))
                nodes.append({"type": "command", "name": p.stem, "path": self._rel(p),
                              "enabled": data["enabled"], "confirm": data["confirm"],
                              "trigger": data["triggers"][0] if data["triggers"] else "",
                              "actions": len(data["actions"])})
        return nodes

    # --- read / write -----------------------------------------------------------------------
    def read(self, rel: str) -> dict[str, Any]:
        path = self._abs(rel)
        if path.is_dir():
            return {"type": "folder", "path": self._rel(path), "name": path.name,
                    "meta": normalize_meta(read_json(path / FOLDER_META, {})),
                    "inherited": self.folder_meta(self._rel(path.parent)) if path != self.root else {}}
        if not path.is_file():
            raise StoreError("Элемент не найден")
        return {"type": "command", "path": self._rel(path), "name": path.stem,
                "data": normalize_command(read_json(path, {})),
                "folder": self.folder_meta(self._rel(path.parent))}

    def save_command(self, rel: str, data: dict[str, Any]) -> dict[str, Any]:
        path = self._abs(rel)
        if path.suffix != ".json" or path.is_dir():
            raise StoreError("Это не команда")
        with self._lock:
            write_json_atomic(path, normalize_command(data))
        return self.read(rel)

    def save_folder(self, rel: str, meta: dict[str, Any]) -> dict[str, Any]:
        path = self._abs(rel)
        if not path.is_dir() or path == self.root.resolve():
            raise StoreError("Папка не найдена")
        with self._lock:
            current = read_json(path / FOLDER_META, {}) or {}
            current.update(meta or {})
            clean = normalize_meta({k: v for k, v in current.items() if v not in ("", None, [])})
            if clean:
                write_json_atomic(path / FOLDER_META, clean)
            elif (path / FOLDER_META).exists():
                (path / FOLDER_META).unlink()
        return self.read(rel)

    def create_folder(self, parent: str, name: str, meta: dict[str, Any] | None = None) -> str:
        with self._lock:
            base = self._abs(parent)
            if not base.is_dir():
                raise StoreError("Родительская папка не найдена")
            path = self._unique(base / sanitize_name(name))
            path.mkdir(parents=True)
            clean = normalize_meta(meta)
            if clean:
                write_json_atomic(path / FOLDER_META, clean)
            return self._rel(path)

    def create_command(self, parent: str, name: str, data: dict[str, Any] | None = None) -> str:
        with self._lock:
            base = self._abs(parent)
            if not base.is_dir():
                raise StoreError("Родительская папка не найдена")
            path = self._unique(base / (sanitize_name(name) + ".json"))
            write_json_atomic(path, normalize_command(data or {}))
            return self._rel(path)

    def rename(self, rel: str, new_name: str) -> str:
        with self._lock:
            path = self._abs(rel)
            if path == self.root.resolve() or not path.exists():
                raise StoreError("Элемент не найден")
            name = sanitize_name(new_name)
            target = path.with_name(name if path.is_dir() else name + ".json")
            if target == path:
                return rel
            if target.exists() and target.name.lower() != path.name.lower():
                raise StoreError("Элемент с таким именем уже существует")
            os.replace(path, target)
            return self._rel(target)

    def delete(self, rel: str) -> None:
        with self._lock:
            path = self._abs(rel)
            if path == self.root.resolve():
                raise StoreError("Нельзя удалить корневую папку")
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()

    def move(self, rel: str, new_parent: str) -> str:
        with self._lock:
            path = self._abs(rel)
            dest_dir = self._abs(new_parent)
            if path == self.root.resolve() or not path.exists():
                raise StoreError("Элемент не найден")
            if not dest_dir.is_dir():
                raise StoreError("Папка назначения не найдена")
            if path.is_dir() and (dest_dir == path or path in dest_dir.parents):
                raise StoreError("Нельзя переместить папку внутрь самой себя")
            if dest_dir == path.parent:
                return rel
            target = self._unique(dest_dir / path.name)
            shutil.move(str(path), str(target))
            return self._rel(target)

    def duplicate(self, rel: str, suffix: str = "копия") -> str:
        with self._lock:
            path = self._abs(rel)
            if path == self.root.resolve() or not path.exists():
                raise StoreError("Элемент не найден")
            if path.is_dir():
                target = self._unique(path.with_name(f"{path.name} ({suffix})"))
                shutil.copytree(path, target)
            else:
                target = self._unique(path.with_name(f"{path.stem} ({suffix}).json"))
                shutil.copy2(path, target)
            return self._rel(target)

    # --- folder metadata / apps -------------------------------------------------------------
    def folder_meta(self, rel: str) -> dict[str, Any]:
        """Metadata inherited from the root down to the folder (children override parents)."""
        path = self._abs(rel)
        if path.is_file():
            path = path.parent
        chain = []
        root = self.root.resolve()
        while path != root and root in path.parents:
            chain.append(path)
            path = path.parent
        merged: dict[str, Any] = {}
        for folder in reversed(chain):
            merged.update(normalize_meta(read_json(folder / FOLDER_META, {})))
        return merged

    def connected_apps(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for p in sorted(self.root.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                app = (read_json(p / FOLDER_META, {}) or {}).get("app")
                if app and app not in found:
                    found[app] = self._rel(p)
        return found

    def custom_apps(self) -> list[dict[str, Any]]:
        """Folders the user bound to an executable path (for "открой {app}")."""
        apps = []
        for p in self.root.rglob(FOLDER_META):
            meta = normalize_meta(read_json(p, {}))
            if meta.get("path") or meta.get("aliases"):
                apps.append({"folder": self._rel(p.parent), "name": p.parent.name, **meta})
        return apps

    def connect_app(self, app_id: str, lang: str = "ru") -> str:
        if app_id not in catalog.APPS_BY_ID:
            raise StoreError("Неизвестное приложение")
        with self._lock:
            existing = self.connected_apps().get(app_id)
            if existing:
                return existing
            return self._write_node(self.root, catalog.build_pack(app_id, lang))

    def disconnect_app(self, app_id: str) -> bool:
        removed = False
        with self._lock:
            for p in list(self.root.iterdir()):
                if p.is_dir() and (read_json(p / FOLDER_META, {}) or {}).get("app") == app_id:
                    shutil.rmtree(p)
                    removed = True
        return removed

    def _write_node(self, parent: Path, node: dict[str, Any]) -> str:
        if node["type"] == "folder":
            path = self._unique(parent / sanitize_name(node["name"]))
            path.mkdir(parents=True)
            meta = normalize_meta(node.get("meta"))
            if meta:
                write_json_atomic(path / FOLDER_META, meta)
            for item in node.get("items", []):
                self._write_node(path, item)
        else:
            path = self._unique(parent / (sanitize_name(node["name"]) + ".json"))
            write_json_atomic(path, normalize_command(node.get("data")))
        return self._rel(path)

    # --- matcher feed -----------------------------------------------------------------------
    def _signature(self) -> tuple:
        sig = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                if name.endswith(".json"):
                    try:
                        st = os.stat(os.path.join(dirpath, name))
                    except OSError:
                        continue
                    sig.append((dirpath, name, st.st_mtime_ns, st.st_size))
        return tuple(sig)

    def entries(self) -> list[CommandEntry]:
        """Enabled commands for the matcher (cached until files change)."""
        with self._lock:
            sig = self._signature()
            if sig == self._cache_sig:
                return self._cache
            entries: list[CommandEntry] = []
            order = 0
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
                folder = Path(dirpath)
                meta = self.folder_meta(self._rel(folder)) if folder != self.root else {}
                if meta.get("enabled") is False:
                    dirnames[:] = []
                    continue
                for name in sorted(filenames):
                    if not name.endswith(".json") or name == FOLDER_META:
                        continue
                    path = folder / name
                    data = normalize_command(read_json(path, {}))
                    if not data["enabled"]:
                        continue
                    triggers = [t for t in (parse_trigger(x) for x in data["triggers"]) if t]
                    if not triggers:
                        continue
                    order += 1
                    rel = self._rel(path)
                    entries.append(CommandEntry(rel, path.stem, triggers,
                                                {**data, "folder_meta": meta, "folder": self._rel(folder) if folder != self.root else ""},
                                                order=order))
            self._cache_sig, self._cache = sig, entries
            return entries

    def display_name(self, rel: str) -> str:
        """'Google Chrome/Вкладки/Новая вкладка.json' -> 'Google Chrome › Вкладки › Новая вкладка'"""
        parts = rel[:-5].split("/") if rel.endswith(".json") else rel.split("/")
        return " › ".join(parts)
