"""Smoke test of the Windows integration (run on Windows: python scripts/smoke_windows.py).

Checks DPAPI, window/process enumeration, app discovery, SAPI voices and UI Automation without
pressing keys or launching programs.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis import apps, catalog, winapi  # noqa: E402


def main() -> int:
    assert sys.platform == "win32", "run this on Windows"
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    secret = "sk-проверка".encode("utf-8")
    assert winapi.dpapi_unprotect(winapi.dpapi_protect(secret)) == secret
    print("DPAPI: ok")
    print("windows:", len(winapi.list_windows()), "processes:", len(winapi.running_processes()))
    assert winapi.parse_combo("Ctrl+Shift+Esc") == ["ctrl", "shift", "esc"]
    assert winapi.split_combos("win + down, win+down") == ["win+down", "win+down"]
    print("foreground window:", winapi.foreground_window())

    resolver = apps.AppResolver()
    print("App Paths msedge.exe:", resolver.app_paths("msedge.exe"))
    for app_id in ("edge", "notepad", "calc", "explorer", "cmd", "powershell", "settings"):
        print(f"resolve {app_id}:", resolver.resolve(app_id))
    print("start menu apps:", len(resolver.start_apps()), "shortcuts:", len(resolver.shortcuts()))
    print("default browser:", resolver.default_browser())
    statuses = resolver.statuses()
    installed = sorted(k for k, v in statuses.items() if v == "installed")
    print("installed catalog apps:", installed)
    assert len(statuses) == len(catalog.APPS)
    target, name = resolver.find_by_name("блокнот")
    print("find 'блокнот':", target, name)
    assert target is not None

    import comtypes.client

    voice = comtypes.client.CreateObject("SAPI.SpVoice")
    tokens = voice.GetVoices()
    print("SAPI voices:", [tokens.Item(i).GetDescription() for i in range(tokens.Count)])

    _uia_module, uia = winapi._uia()
    print("UI Automation root:", bool(uia.GetRootElement()))
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
