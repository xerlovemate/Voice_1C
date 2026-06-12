# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import vosk
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path.cwd()
VOSK_DIR = Path(vosk.__file__).resolve().parent
SELENIUM_DATAS = collect_data_files("selenium", include_py_files=False)
SELENIUM_HIDDENIMPORTS = collect_submodules("selenium")

datas = [
    (str(ROOT / "frontend"), "frontend"),
    (str(ROOT / "resources"), "resources"),
    (str(ROOT / "voice_actions" / "command_config.json"), "voice_actions"),
    (str(VOSK_DIR), "vosk"),
] + SELENIUM_DATAS

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "webview",
        "webview.platforms.winforms",
        "pythonnet",
        "clr_loader",
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "keyboard",
        "pyperclip",
        "vosk",
        "pyaudio",
        "selenium",
        "trio",
        "trio_websocket",
        "websocket",
        "wsproto",
        *SELENIUM_HIDDENIMPORTS,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PySide6"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Voice1C",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "resources" / "icon.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Voice1C",
)
