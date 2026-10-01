"""End-to-end check of the Windows automation on a real desktop (used in CI).

1. Opens Notepad, types Cyrillic text with SendInput, copies it with Ctrl+A/Ctrl+C and compares
   the clipboard — keyboard emulation, window focus and hotkeys.
2. Opens a test page in Chrome (or Edge) and presses the "Перемешать все" button through UI
   Automation — the same mechanism the "включи музыку в вк" command uses on vk.com/audio.
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis import winapi  # noqa: E402
from jarvis.apps import AppResolver  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetClipboardData.restype = wintypes.HANDLE
user32.OpenClipboard.argtypes = (wintypes.HWND,)
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)


def clipboard_text() -> str:
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.1)
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def wait_window(process_names, title_part="", timeout=15.0) -> int:
    end = time.time() + timeout
    names = {n.lower() for n in process_names}
    while time.time() < end:
        for w in winapi.list_windows():
            if w["exe"] in names and title_part.lower() in w["title"].lower():
                return w["hwnd"]
        time.sleep(0.25)
    return 0


def title_of(hwnd: int) -> str:
    for w in winapi.list_windows():
        if w["hwnd"] == hwnd:
            return w["title"]
    return ""


def check_typing() -> None:
    subprocess.Popen(["notepad.exe"])
    hwnd = wait_window(["notepad.exe"])
    assert hwnd, "Notepad window did not appear"
    print("notepad window:", title_of(hwnd))
    time.sleep(1.0)
    assert winapi.focus_window(hwnd), "could not focus Notepad"
    text = "Привет, Jarvis 123"
    winapi.type_text(text)
    time.sleep(0.3)
    winapi.send_hotkey("ctrl+a ctrl+c")
    time.sleep(0.3)
    got = clipboard_text().strip()
    print("clipboard:", repr(got))
    assert got == text, f"typed text mismatch: {got!r}"
    winapi.kill_processes(["notepad.exe"], force=True)
    print("TYPING OK")


def check_click_in_browser() -> None:
    resolver = AppResolver()
    target = resolver.resolve("chrome", allow_web=False) or resolver.resolve("edge", allow_web=False)
    assert target and target.kind == "exe", "no Chrome/Edge found"
    page = Path(tempfile.mkdtemp()) / "uia-test.html"
    page.write_text(
        "<!doctype html><meta charset='utf-8'><title>Jarvis UIA test</title>"
        "<h1>Музыка</h1><button onclick=\"document.title='CLICKED'\">Перемешать все</button>",
        encoding="utf-8")
    profile = tempfile.mkdtemp()
    proc = subprocess.Popen([target.value, "--no-first-run", "--no-default-browser-check",
                             f"--user-data-dir={profile}", page.as_uri()])
    try:
        hwnd = wait_window(target.process, "Jarvis UIA test", timeout=30)
        assert hwnd, "browser window with the test page did not appear"
        print("browser:", target.app_id, title_of(hwnd))
        winapi.focus_window(hwnd)
        pressed = winapi.click_element(["Перемешать все", "Слушать"], hwnd=hwnd, timeout=20)
        print("pressed:", pressed)
        assert pressed == "Перемешать все", "button not found through UI Automation"
        end = time.time() + 10
        while time.time() < end and "CLICKED" not in title_of(hwnd):
            time.sleep(0.25)
        print("title after click:", title_of(hwnd))
        assert "CLICKED" in title_of(hwnd), "the button did not react"
        print("BROWSER CLICK OK")
    finally:
        proc.kill()
        winapi.kill_processes(target.process, force=True)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    check_typing()
    check_click_in_browser()
    print("ACTIONS SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
