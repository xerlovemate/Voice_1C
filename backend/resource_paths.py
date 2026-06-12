from __future__ import annotations

import os
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    root = app_root()
    candidates = [
        root.joinpath("resources", *parts),
        root.joinpath(*parts),
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass).joinpath("resources", *parts))
        candidates.insert(1, Path(meipass).joinpath(*parts))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def frontend_index() -> Path:
    root = app_root()
    candidates = [root / "frontend" / "index.html"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "frontend" / "index.html")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def frontend_path(*parts: str) -> Path:
    root = frontend_index().parent
    return root.joinpath(*parts)


def user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(base) / "Voice1C"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_config_path() -> Path:
    return user_data_dir() / "config.json"


def log_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file_path() -> Path:
    return log_dir() / "app.log"
