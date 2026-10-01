"""Finding and launching installed applications.

Lookup order for a catalog app: path from the folder settings -> known install paths ->
"App Paths" registry -> PATH -> Start menu apps (Get-StartApps, covers Store apps) ->
Start menu shortcuts -> URI scheme -> web version.
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import catalog
from .paths import IS_MAC, IS_WINDOWS
from .textproc import normalize, phrase_phonetic_sim, phrase_score, words
from .winapi import CREATE_NO_WINDOW

log = logging.getLogger("jarvis.apps")

CACHE_TTL = 600  # seconds

# Known folders that can be opened with "открой загрузки" etc.
SHELL_FOLDERS = {
    "загрузки": "Downloads", "папку загрузки": "Downloads", "downloads": "Downloads",
    "документы": "Personal", "мои документы": "Personal", "documents": "Personal",
    "рабочий стол": "Desktop", "desktop": "Desktop",
    "изображения": "My Pictures", "картинки": "My Pictures", "фотографии": "My Pictures",
    "pictures": "My Pictures",
    "корзину": "RecycleBinFolder", "корзина": "RecycleBinFolder", "recycle bin": "RecycleBinFolder",
}

BROWSER_PROGIDS = {
    "chromehtml": "chrome", "msedgehtm": "edge", "firefoxurl": "firefox", "yandexhtml": "yandex",
    "bravehtml": "brave", "operastable": "opera", "opera gxstable": "operagx",
}


@dataclass
class Target:
    kind: str  # exe | startapp | shortcut | uri | web | shell
    value: str
    args: list[str] = field(default_factory=list)
    name: str = ""
    app_id: str | None = None
    process: list[str] = field(default_factory=list)

    def describe(self) -> str:
        return {"exe": "программа", "startapp": "меню «Пуск»", "shortcut": "ярлык",
                "uri": "протокол", "web": "веб-версия", "shell": "папка"}.get(self.kind, self.kind)


def _split_args(args: Any) -> list[str]:
    if not args:
        return []
    if isinstance(args, (list, tuple)):
        return [str(a) for a in args]
    try:
        return shlex.split(str(args), posix=not IS_WINDOWS)
    except ValueError:
        return str(args).split()


def expand(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(str(path).strip().strip('"')))


class AppResolver:
    def __init__(self, store=None):
        self.store = store
        self._lock = threading.Lock()
        self._start_apps: list[tuple[str, str]] | None = None
        self._start_time = 0.0
        self._shortcuts: list[tuple[str, str]] | None = None
        self._shortcut_time = 0.0
        self._status: dict[str, str] = {}
        self._status_time = 0.0

    # --- Windows discovery ------------------------------------------------------------------
    def start_apps(self) -> list[tuple[str, str]]:
        """(name, AppID) of everything in the Start menu, Store apps included."""
        if not IS_WINDOWS:
            return []
        with self._lock:
            if self._start_apps is not None and time.time() - self._start_time < CACHE_TTL:
                return self._start_apps
        script = ("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
                  "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress")
        apps: list[tuple[str, str]] = []
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True, timeout=30, creationflags=CREATE_NO_WINDOW)
            data = json.loads(res.stdout.decode("utf-8", errors="replace") or "[]")
            if isinstance(data, dict):
                data = [data]
            apps = [(d.get("Name") or "", d.get("AppID") or "") for d in data if d.get("AppID")]
        except Exception as exc:
            log.warning("Get-StartApps failed: %s", exc)
        with self._lock:
            self._start_apps, self._start_time = apps, time.time()
        return apps

    def shortcuts(self) -> list[tuple[str, str]]:
        if not IS_WINDOWS:
            return []
        with self._lock:
            if self._shortcuts is not None and time.time() - self._shortcut_time < CACHE_TTL:
                return self._shortcuts
        found = []
        roots = [os.environ.get("ProgramData", r"C:\ProgramData"), os.environ.get("APPDATA", "")]
        for root in roots:
            base = Path(root) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if not base.is_dir():
                continue
            for lnk in base.rglob("*.lnk"):
                low = lnk.stem.lower()
                if any(w in low for w in ("uninstall", "удал", "деинстал", "readme", "help", "справка")):
                    continue
                found.append((lnk.stem, str(lnk)))
        with self._lock:
            self._shortcuts, self._shortcut_time = found, time.time()
        return found

    @staticmethod
    def app_paths(exe: str) -> str | None:
        if not IS_WINDOWS:
            return None
        import winreg

        sub = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for flag in (0, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | flag) as key:
                        value, _ = winreg.QueryValueEx(key, None)
                        value = expand(value)
                        if os.path.isfile(value):
                            return value
                except OSError:
                    continue
        return None

    @staticmethod
    def uri_registered(scheme: str) -> bool:
        if not IS_WINDOWS:
            return False
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, scheme) as key:
                winreg.QueryValueEx(key, "URL Protocol")
                return True
        except OSError:
            return False

    @staticmethod
    def default_browser() -> str | None:
        """Catalog id of the default browser (chrome, edge, yandex...)."""
        if not IS_WINDOWS:
            return None
        import winreg

        sub = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as key:
                progid, _ = winreg.QueryValueEx(key, "ProgId")
        except OSError:
            return None
        progid = str(progid).lower()
        for prefix, app_id in BROWSER_PROGIDS.items():
            if progid.startswith(prefix):
                return app_id
        return None

    def _find_named(self, items: list[tuple[str, str]], names: list[str]) -> str | None:
        """Exact (case-insensitive) name first, then "starts with" (PyCharm 2025.2 ...)."""
        lowered = [(n.lower(), v) for n, v in items]
        for name in names:
            name = name.lower()
            for n, v in lowered:
                if n == name:
                    return v
        for name in names:
            name = name.lower()
            for n, v in lowered:
                if n.startswith(name + " ") or n.startswith(name + "("):
                    return v
        return None

    # --- resolution -------------------------------------------------------------------------
    def resolve(self, app_id: str, meta: dict[str, Any] | None = None, allow_web: bool = True,
                deep: bool = True) -> Target | None:
        app = catalog.APPS_BY_ID.get(app_id)
        meta = meta or {}
        if meta.get("path") and meta.get("app") in (None, app_id):
            path = expand(meta["path"])
            if os.path.exists(path):
                return Target("exe", path, _split_args(meta.get("args")) or list((app or {}).get("args", [])),
                              name=catalog.app_name(app) if app else Path(path).stem, app_id=app_id,
                              process=[meta["process"]] if meta.get("process") else [Path(path).name])
        if app is None:
            return None
        name = catalog.app_name(app)
        args = list(app.get("args", []))
        process = list(app.get("process", []))
        if app["kind"] == "web":
            return Target("web", app["web"], name=name, app_id=app_id) if allow_web else None
        for raw in app.get("paths", []):
            path = expand(raw)
            if os.path.isfile(path):
                return Target("exe", path, args, name, app_id, process)
        for exe in app.get("exe", []):
            path = self.app_paths(exe)
            if path:
                return Target("exe", path, args, name, app_id, process)
        for exe in app.get("exe", []):
            path = shutil.which(exe) if IS_WINDOWS else None
            if path:
                return Target("exe", path, args, name, app_id, process)
        if deep and app.get("start"):
            appid = self._find_named(self.start_apps(), app["start"])
            if appid:
                return Target("startapp", appid, [], name, app_id, process)
            lnk = self._find_named(self.shortcuts(), app["start"])
            if lnk:
                return Target("shortcut", lnk, [], name, app_id, process)
        if app.get("uri") and (not app.get("scheme") or self.uri_registered(app["scheme"])):
            return Target("uri", app["uri"], [], name, app_id, process)
        if allow_web and app.get("web"):
            return Target("web", app["web"], [], name, app_id, process)
        return None

    def find_by_name(self, spoken: str) -> tuple[Target | None, str]:
        """Resolve a spoken app name: 'телеграм', 'гугл хром', 'фотошоп', 'загрузки'."""
        query = normalize(spoken)
        if not query:
            return None, spoken
        for key, folder in SHELL_FOLDERS.items():
            if query == key:
                return Target("shell", folder, name=spoken), spoken
        # user folders with their own executable or aliases
        if self.store is not None:
            for item in self.store.custom_apps():
                names = [item["name"], *item.get("aliases", [])]
                if self._name_score(query, names) >= 0.85:
                    target = self.resolve(item.get("app") or "", item) if item.get("app") else None
                    if target is None and item.get("path"):
                        path = expand(item["path"])
                        target = Target("exe", path, _split_args(item.get("args")), item["name"],
                                        process=[item.get("process") or Path(path).name])
                    if target:
                        return target, item["name"]
        # catalog
        best_app, best_score = None, 0.0
        for app in catalog.APPS:
            if app["kind"] == "pack":
                continue
            score = self._name_score(query, catalog.all_names(app))
            if score > best_score:
                best_app, best_score = app, score
        if best_app and best_score >= 0.82:
            target = self.resolve(best_app["id"])
            if target:
                return target, catalog.app_name(best_app)
        # anything else in the Start menu
        for items, kind in ((self.start_apps(), "startapp"), (self.shortcuts(), "shortcut")):
            best, score_best = None, 0.0
            for name, value in items:
                score = self._name_score(query, [name])
                if score > score_best:
                    best, score_best = (name, value), score
            if best and score_best >= 0.85:
                return Target(kind, best[1], name=best[0]), best[0]
        return None, spoken

    @staticmethod
    def _name_score(query: str, names: list[str]) -> float:
        qw = words(query)
        best = 0.0
        for name in names:
            nn = normalize(name)
            if not nn:
                continue
            if nn == query:
                return 1.0
            nw = words(nn)
            score, coverage = phrase_score(qw, nw)
            if coverage >= 0.95 and len(qw) <= len(nw) + 1:
                best = max(best, score)
            best = max(best, phrase_phonetic_sim(query, nn) - 0.05)
        return best

    def process_names(self, app: str, meta: dict[str, Any] | None = None) -> tuple[list[str], str]:
        """Executable names to close/focus an app given by id or spoken name."""
        meta = meta or {}
        if app in catalog.APPS_BY_ID:
            data = catalog.APPS_BY_ID[app]
            names = list(data.get("process", []))
            if meta.get("process") and meta.get("app") in (None, app):
                names.insert(0, meta["process"])
            return names, catalog.app_name(data)
        if not app and (meta.get("process") or meta.get("path")):
            return [meta.get("process") or Path(expand(meta["path"])).name], meta.get("app") or ""
        target, name = self.find_by_name(app)
        if target and target.process:
            return target.process, name
        if target and target.kind == "exe":
            return [Path(target.value).name], name
        return [], name

    # --- launching --------------------------------------------------------------------------
    def launch(self, target: Target) -> None:
        log.info("launch %s %s %s", target.kind, target.value, target.args)
        if target.kind == "exe":
            _shell_execute(target.value, target.args)
        elif target.kind == "startapp":
            if not IS_WINDOWS:
                raise RuntimeError("Запуск из меню «Пуск» доступен только в Windows")
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{target.value}"], creationflags=CREATE_NO_WINDOW)
        elif target.kind == "shortcut":
            _start_file(target.value)
        elif target.kind == "shell":
            if not IS_WINDOWS:
                raise RuntimeError("Системные папки открываются только в Windows")
            subprocess.Popen(["explorer.exe", f"shell:{target.value}"], creationflags=CREATE_NO_WINDOW)
        elif target.kind in ("uri", "web"):
            open_uri(target.value)
        else:
            raise RuntimeError(f"Неизвестный способ запуска: {target.kind}")

    # --- status for the Apps tab ------------------------------------------------------------
    def statuses(self, refresh: bool = False) -> dict[str, str]:
        with self._lock:
            fresh = time.time() - self._status_time < 120
            if self._status and fresh and not refresh:
                return dict(self._status)
        result: dict[str, str] = {}
        for app in catalog.APPS:
            if app["kind"] == "pack":
                result[app["id"]] = "builtin"
                continue
            target = self.resolve(app["id"], allow_web=False)
            if target:
                result[app["id"]] = "installed"
            elif app.get("web"):
                result[app["id"]] = "web"
            else:
                result[app["id"]] = "missing"
        with self._lock:
            self._status, self._status_time = result, time.time()
        return dict(result)

    def cached_statuses(self) -> dict[str, str]:
        with self._lock:
            return dict(self._status)


def _start_file(path: str) -> None:
    if IS_WINDOWS:
        os.startfile(path)  # type: ignore[attr-defined]
    elif IS_MAC:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _shell_execute(path: str, args: list[str]) -> None:
    """ShellExecute handles elevation prompts and working directories like Explorer does."""
    if IS_WINDOWS:
        import ctypes

        params = subprocess.list2cmdline(args) if args else None
        workdir = os.path.dirname(path) or None
        shell_execute = ctypes.windll.shell32.ShellExecuteW
        shell_execute.restype = ctypes.c_void_p
        rc = shell_execute(None, "open", path, params, workdir, 1) or 0
        if rc <= 32:
            raise RuntimeError(f"Не удалось запустить {Path(path).name} (код {rc})")
    else:
        subprocess.Popen([path, *args], start_new_session=True)


def open_uri(uri: str) -> None:
    """Open a web page in the default browser or hand a custom URI (steam://, tg://) to the OS."""
    if IS_WINDOWS or IS_MAC:
        if IS_WINDOWS and uri.lower().startswith(("http://", "https://")):
            webbrowser.open(uri)
        else:
            _start_file(uri)
        return
    # Linux: never block on console browsers that webbrowser may pick
    if shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    else:
        threading.Thread(target=webbrowser.open, args=(uri,), daemon=True).start()
