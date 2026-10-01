"""Windows helpers on top of ctypes: keyboard input, windows, processes, DPAPI, DWM, UI Automation.

Every public function is safe to call on other platforms: it returns a neutral value or raises
NotSupported, so the rest of the app can be developed and tested on Linux/macOS.
"""
from __future__ import annotations

import ctypes
import logging
import os
import re
import subprocess
import time

from .paths import IS_WINDOWS

log = logging.getLogger("jarvis.winapi")


class NotSupported(RuntimeError):
    pass


CREATE_NO_WINDOW = 0x08000000

if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = (
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        )

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        )

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = (
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        )

    class _INPUTUNION(ctypes.Union):
        _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = (("type", wintypes.DWORD), ("u", _INPUTUNION))

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
    user32.MapVirtualKeyW.restype = wintypes.UINT
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.BringWindowToTop.argtypes = (wintypes.HWND,)
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT)
    user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
    user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                                    wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel32.LocalFree.restype = ctypes.c_void_p

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = (EnumWindowsProc, wintypes.LPARAM)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

# --- keyboard -------------------------------------------------------------------------------

VK: dict[str, int] = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D, "shift": 0x10,
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "pause": 0x13, "capslock": 0x14,
    "esc": 0x1B, "escape": 0x1B, "space": 0x20, "pageup": 0x21, "pgup": 0x21,
    "pagedown": 0x22, "pgdn": 0x22, "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26,
    "right": 0x27, "down": 0x28, "printscreen": 0x2C, "prtsc": 0x2C, "insert": 0x2D,
    "delete": 0x2E, "del": 0x2E, "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C, "menu": 0x5D,
    "multiply": 0x6A, "add": 0x6B, "subtract": 0x6D, "decimal": 0x6E, "divide": 0x6F,
    "numlock": 0x90, "scrolllock": 0x91,
    "browser_back": 0xA6, "browser_forward": 0xA7, "browser_refresh": 0xA8,
    "browser_home": 0xAC,
    "volume_mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF,
    "media_next": 0xB0, "media_prev": 0xB1, "media_stop": 0xB2, "media_play_pause": 0xB3,
    ";": 0xBA, "=": 0xBB, "plus": 0xBB, ",": 0xBC, "comma": 0xBC, "-": 0xBD, "minus": 0xBD,
    ".": 0xBE, "period": 0xBE, "/": 0xBF, "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD,
    "'": 0xDE,
}
VK.update({f"f{i}": 0x6F + i for i in range(1, 25)})
VK.update({f"num{i}": 0x60 + i for i in range(10)})
VK.update({chr(c): c - 32 for c in range(ord("a"), ord("z") + 1)})
VK.update({str(d): 0x30 + d for d in range(10)})

KEY_ALIASES = {
    "cmd": "win", "super": "win", "windows": "win", "option": "alt", "ctl": "ctrl",
    "arrowleft": "left", "arrowright": "right", "arrowup": "up", "arrowdown": "down",
    "play": "media_play_pause", "playpause": "media_play_pause", "next": "media_next",
    "prev": "media_prev", "previous": "media_prev", "mute": "volume_mute",
    "volumeup": "volume_up", "volumedown": "volume_down", "ins": "insert",
}

_EXTENDED = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D,
    0x6F, 0x90, 0xA6, 0xA7, 0xA8, 0xAC, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3,
}
MODIFIERS = {"ctrl", "control", "shift", "alt", "win", "lwin", "rwin"}


def split_combos(text: str) -> list[str]:
    """'ctrl + k, ctrl+c' -> ['ctrl+k', 'ctrl+c']"""
    text = re.sub(r"\s*\+\s*", "+", (text or "").strip())
    return [p for p in re.split(r"[\s,;]+", text) if p]


def parse_combo(combo: str) -> list[str]:
    """'Ctrl+Shift+T' -> ['ctrl', 'shift', 't']; raises ValueError on unknown keys."""
    keys = []
    for raw in combo.replace(" ", "").lower().split("+"):
        if not raw:
            continue
        key = KEY_ALIASES.get(raw, raw)
        if key not in VK:
            raise ValueError(f"Неизвестная клавиша: {raw}")
        keys.append(key)
    if not keys:
        raise ValueError("Пустое сочетание клавиш")
    return keys


def _key_input(vk: int, up: bool) -> "INPUT":
    flags = KEYEVENTF_KEYUP if up else 0
    if vk in _EXTENDED:
        flags |= KEYEVENTF_EXTENDEDKEY
    scan = user32.MapVirtualKeyW(vk, 0) & 0xFF
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0))


def _send(inputs: list) -> None:
    if not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise OSError(f"SendInput: отправлено {sent} из {len(inputs)} событий "
                      f"(ошибка {ctypes.get_last_error()})")


def send_hotkey(combo: str) -> None:
    """Press a key combination. Several combos may be separated by spaces or commas:
    'ctrl+t', 'ctrl+shift+esc', 'alt+tab', 'media_play_pause', 'ctrl+k ctrl+c'."""
    if not IS_WINDOWS:
        raise NotSupported("Эмуляция клавиш доступна только в Windows")
    for part in split_combos(combo):
        keys = parse_combo(part)
        codes = [VK[k] for k in keys]
        inputs = [_key_input(c, False) for c in codes] + [_key_input(c, True) for c in reversed(codes)]
        _send(inputs)
        time.sleep(0.05)


def tap_key(name: str, times: int = 1, delay: float = 0.0) -> None:
    if not IS_WINDOWS:
        raise NotSupported("Эмуляция клавиш доступна только в Windows")
    code = VK[KEY_ALIASES.get(name, name)]
    for _ in range(max(0, times)):
        _send([_key_input(code, False), _key_input(code, True)])
        if delay:
            time.sleep(delay)


def type_text(text: str, chunk: int = 40) -> None:
    """Type arbitrary Unicode text (Cyrillic included) into the focused window."""
    if not IS_WINDOWS:
        raise NotSupported("Ввод текста доступен только в Windows")
    inputs = []
    for ch in text:
        if ch == "\n":
            inputs += [_key_input(0x0D, False), _key_input(0x0D, True)]
            continue
        data = ch.encode("utf-16-le")
        for i in range(0, len(data), 2):
            unit = int.from_bytes(data[i:i + 2], "little")
            for up in (False, True):
                inputs.append(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(
                    wVk=0, wScan=unit,
                    dwFlags=KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0),
                    time=0, dwExtraInfo=0)))
    for i in range(0, len(inputs), chunk * 2):
        _send(inputs[i:i + chunk * 2])
        time.sleep(0.01)


def set_system_volume(level: int) -> None:
    """Approximate the master volume using volume keys (each press is 2%)."""
    level = max(0, min(100, int(level)))
    tap_key("volume_down", 50)
    tap_key("volume_up", round(level / 2))


# --- mouse ----------------------------------------------------------------------------------

def click_at(x: int, y: int, restore: bool = True) -> None:
    if not IS_WINDOWS:
        raise NotSupported("Клик мышью доступен только в Windows")
    old = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(old))
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.03)
    _send([
        INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, 0)),
        INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, 0)),
    ])
    if restore:
        time.sleep(0.05)
        user32.SetCursorPos(old.x, old.y)


# --- processes and windows ------------------------------------------------------------------

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def process_path(pid: int) -> str:
    if not IS_WINDOWS:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def running_processes() -> dict[str, list[int]]:
    """{'chrome.exe': [pid, ...]} for processes we are allowed to query."""
    result: dict[str, list[int]] = {}
    if not IS_WINDOWS:
        return result
    psapi = ctypes.WinDLL("psapi")
    arr = (wintypes.DWORD * 8192)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed)):
        return result
    for pid in arr[: needed.value // ctypes.sizeof(wintypes.DWORD)]:
        if not pid:
            continue
        path = process_path(pid)
        if path:
            result.setdefault(os.path.basename(path).lower(), []).append(pid)
    return result


def is_running(process_names: list[str]) -> bool:
    names = {n.lower() for n in process_names}
    return any(n in names for n in running_processes())


def list_windows() -> list[dict]:
    """Visible top-level application windows: hwnd, pid, title, exe."""
    if not IS_WINDOWS:
        return []
    found = []
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080

    def callback(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
                return True
            if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found.append({"hwnd": hwnd, "pid": pid.value, "title": buf.value,
                          "exe": os.path.basename(process_path(pid.value)).lower()})
        except Exception:  # never let an exception cross the C callback
            pass
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found


def find_windows(process_names: list[str]) -> list[int]:
    names = {n.lower() for n in process_names}
    return [w["hwnd"] for w in list_windows() if w["exe"] in names]


def foreground_window() -> int:
    if not IS_WINDOWS:
        return 0
    return user32.GetForegroundWindow() or 0


def focus_window(hwnd: int) -> bool:
    """Bring a window to the front despite the foreground lock."""
    if not IS_WINDOWS or not hwnd:
        return False
    SW_RESTORE = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    cur_tid = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(fg_tid and fg_tid != cur_tid and user32.AttachThreadInput(cur_tid, fg_tid, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(cur_tid, fg_tid, False)
    if user32.GetForegroundWindow() != hwnd:
        # the classic trick: a synthetic ALT press unlocks SetForegroundWindow
        try:
            _send([_key_input(0x12, False), _key_input(0x12, True)])
        except OSError:
            pass
        user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    return user32.GetForegroundWindow() == hwnd


def focus_process(process_names: list[str]) -> bool:
    for hwnd in find_windows(process_names):
        if focus_window(hwnd):
            return True
    return False


def kill_processes(process_names: list[str], force: bool = False) -> bool:
    """Close applications by executable name (taskkill). Returns True if something was closed."""
    if not IS_WINDOWS:
        raise NotSupported("Закрытие приложений доступно только в Windows")
    closed = False
    for name in process_names:
        args = ["taskkill", "/IM", name, "/T"]
        if force:
            args.append("/F")
        res = subprocess.run(args, capture_output=True, creationflags=CREATE_NO_WINDOW)
        closed = closed or res.returncode == 0
    return closed


# --- system ---------------------------------------------------------------------------------

def lock_workstation() -> None:
    if not IS_WINDOWS:
        raise NotSupported("Только для Windows")
    user32.LockWorkStation()


def sleep_computer() -> None:
    if not IS_WINDOWS:
        raise NotSupported("Только для Windows")
    ctypes.WinDLL("powrprof").SetSuspendState(False, True, False)


def empty_recycle_bin() -> None:
    if not IS_WINDOWS:
        raise NotSupported("Только для Windows")
    shell32 = ctypes.WinDLL("shell32")
    shell32.SHEmptyRecycleBinW(None, None, 0x00000001 | 0x00000002 | 0x00000004)


# --- window appearance ----------------------------------------------------------------------

def find_own_window(title: str) -> int:
    pid = os.getpid()
    for w in list_windows():
        if w["pid"] == pid and w["title"] == title:
            return w["hwnd"]
    for w in list_windows():
        if w["pid"] == pid:
            return w["hwnd"]
    return 0


def set_dark_title_bar(hwnd: int, dark: bool) -> bool:
    """Switch the native title bar of our window between light and dark."""
    if not IS_WINDOWS or not hwnd:
        return False
    dwmapi = ctypes.WinDLL("dwmapi")
    value = ctypes.c_int(1 if dark else 0)
    ok = False
    for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / pre-20H1 builds)
        if dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), attr, ctypes.byref(value), 4) == 0:
            ok = True
            break
    SWP_FLAGS = 0x0002 | 0x0001 | 0x0004 | 0x0020 | 0x0010  # NOMOVE|NOSIZE|NOZORDER|FRAMECHANGED|NOACTIVATE
    user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_FLAGS)
    return ok


# --- DPAPI (encrypting the API key for the current Windows user) ----------------------------

if IS_WINDOWS:
    class DATA_BLOB(ctypes.Structure):
        _fields_ = (("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char)))


def _blob(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def dpapi_protect(data: bytes) -> bytes:
    if not IS_WINDOWS:
        raise NotSupported("DPAPI доступен только в Windows")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    blob_in, _keep = _blob(data)
    blob_out = DATA_BLOB()
    if not crypt32.CryptProtectData(ctypes.byref(blob_in), "Jarvis", None, None, None, 0x01,
                                    ctypes.byref(blob_out)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def dpapi_unprotect(data: bytes) -> bytes:
    if not IS_WINDOWS:
        raise NotSupported("DPAPI доступен только в Windows")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    blob_in, _keep = _blob(data)
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0x01,
                                      ctypes.byref(blob_out)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


# --- UI Automation: press a button on a web page or in an app by its visible name ------------

UIA_NamePropertyId = 30005
UIA_IsInvokePatternAvailablePropertyId = 30031
UIA_InvokePatternId = 10000
TreeScope_Descendants = 4
PropertyConditionFlags_IgnoreCase = 1
PropertyConditionFlags_MatchSubstring = 2


def _uia():
    import comtypes
    import comtypes.client

    try:
        comtypes.CoInitialize()
    except OSError:
        pass
    try:
        from comtypes.gen import UIAutomationClient as UIA  # type: ignore
    except ImportError:
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA  # type: ignore
    uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
    return UIA, uia


def click_element(names: list[str], hwnd: int | None = None, timeout: float = 6.0) -> str | None:
    """Find a control whose name contains one of `names` inside the window and press it.

    Works for browsers too (Chrome/Edge/Yandex expose page buttons to UI Automation).
    Returns the name that was pressed or None.
    """
    if not IS_WINDOWS:
        raise NotSupported("Нажатие элементов доступно только в Windows")
    try:
        UIA, uia = _uia()
    except Exception as exc:  # comtypes missing or broken
        raise RuntimeError(f"UI Automation недоступен: {exc}") from exc
    hwnd = hwnd or foreground_window()
    if not hwnd:
        return None
    root = uia.ElementFromHandle(wintypes.HWND(hwnd))
    flags = PropertyConditionFlags_IgnoreCase | PropertyConditionFlags_MatchSubstring
    invokable = uia.CreatePropertyCondition(UIA_IsInvokePatternAvailablePropertyId, True)
    deadline = time.time() + max(0.5, timeout)
    while True:
        for strict in (True, False):
            for name in names:
                if not name:
                    continue
                cond = uia.CreatePropertyConditionEx(UIA_NamePropertyId, name, flags)
                if strict:
                    cond = uia.CreateAndCondition(cond, invokable)
                try:
                    element = root.FindFirst(TreeScope_Descendants, cond)
                except Exception:
                    element = None
                if element and _press(UIA, element):
                    return name
        if time.time() >= deadline:
            return None
        time.sleep(0.5)


def _press(UIA, element) -> bool:
    try:
        pattern = element.GetCurrentPattern(UIA_InvokePatternId)
        if pattern:
            pattern.QueryInterface(UIA.IUIAutomationInvokePattern).Invoke()
            return True
    except Exception:
        pass
    try:
        rect = element.CurrentBoundingRectangle
        if rect.right > rect.left and rect.bottom > rect.top:
            click_at((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
            return True
    except Exception:
        pass
    return False
