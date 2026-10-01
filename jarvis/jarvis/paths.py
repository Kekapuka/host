"""Locations of bundled resources and user data."""
from __future__ import annotations

import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def resource_root() -> Path:
    """Folder with web/ and assets/ (PyInstaller unpacks them into sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent.parent


WEB_DIR = resource_root() / "web"
ASSETS_DIR = resource_root() / "assets"


def data_root() -> Path:
    """Per-user data folder: %APPDATA%\\Jarvis on Windows, ~/.config/jarvis elsewhere.

    JARVIS_HOME overrides it (used by tests and portable setups).
    """
    env = os.environ.get("JARVIS_HOME")
    if env:
        root = Path(env)
    elif IS_WINDOWS:
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Jarvis"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "jarvis"
    root.mkdir(parents=True, exist_ok=True)
    return root


def commands_dir() -> Path:
    path = data_root() / "commands"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = data_root() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return data_root() / "settings.json"


def history_file() -> Path:
    return data_root() / "history.json"


def log_file() -> Path:
    return data_root() / "jarvis.log"
