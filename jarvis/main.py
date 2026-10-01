"""Jarvis — голосовой ассистент для ПК.

    python main.py              окно приложения
    python main.py --browser    интерфейс в браузере (если окно не запускается)
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys


def setup_console() -> None:
    """Russian text must not crash printing to a cp1252/cp866 pipe on Windows."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def setup_logging(debug: bool) -> None:
    from jarvis import paths

    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(paths.log_file(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    ]
    if sys.stderr is not None:  # pythonw / frozen windowed apps have no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)
    logging.getLogger("comtypes").setLevel(logging.WARNING)
    logging.getLogger("pywebview").setLevel(logging.INFO if debug else logging.WARNING)


def single_instance() -> bool:
    """Only one Jarvis may listen to the microphone. Returns False if another copy is running."""
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, "Local\\JarvisVoiceAssistant")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        user32 = ctypes.WinDLL("user32")
        hwnd = user32.FindWindowW(None, "Jarvis")
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
        return False
    return True


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description="Jarvis — голосовой ассистент")
    parser.add_argument("--browser", action="store_true", help="открыть интерфейс в браузере")
    parser.add_argument("--port", type=int, default=0, help="порт для режима браузера")
    parser.add_argument("--no-open", action="store_true", help="не открывать браузер автоматически")
    parser.add_argument("--no-voice", action="store_true", help="без микрофона и озвучки (для отладки)")
    parser.add_argument("--debug", action="store_true", help="подробный журнал и инструменты разработчика")
    args = parser.parse_args()

    setup_logging(args.debug)
    if not single_instance():
        return 0

    from jarvis.app import JarvisApp

    app = JarvisApp(mode="browser" if args.browser else "window", port=args.port,
                    open_browser=not args.no_open, debug=args.debug, voice=not args.no_voice)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
