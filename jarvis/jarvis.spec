# PyInstaller spec: pyinstaller --noconfirm --clean jarvis.spec  ->  dist/Jarvis/Jarvis.exe
from pathlib import Path

import speech_recognition

root = Path(SPECPATH)
sr_dir = Path(speech_recognition.__file__).parent

datas = [
    (str(root / "web"), "web"),
    (str(root / "assets"), "assets"),
    # SpeechRecognition reads its version file on import and converts audio with the bundled flac.exe
    (str(sr_dir / "version.txt"), "speech_recognition"),
]
flac = sr_dir / "flac-win32.exe"
if flac.exists():
    datas.append((str(flac), "speech_recognition"))

hiddenimports = [
    "comtypes",
    "comtypes.client",
    "comtypes.stream",
    "speech_recognition",
    "speech_recognition.recognizers.google",
    "sounddevice",
    "edge_tts",
    "pygame",
]

a = Analysis(
    ["main.py"],
    pathex=[str(root)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pocketsphinx", "whisper", "faster_whisper", "torch", "numpy.tests", "PySide6", "PyQt5", "PyQt6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Jarvis",
    icon=str(root / "assets" / "icon.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Jarvis", upx=False)
