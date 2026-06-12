from __future__ import annotations

import os
import locale
import shutil
import subprocess
import winreg
from pathlib import Path

from backend.resource_paths import user_data_dir


CHROME_DOWNLOAD_URL = "https://www.google.com/chrome/"


def chrome_profile_dir() -> Path:
    path = user_data_dir() / "chrome_profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


class ChromeManager:
    def __init__(self):
        self._cached_path: Path | None = None
        self._cached_version: str | None = None

    def find_chrome(self) -> Path | None:
        if self._cached_path and self._cached_path.exists():
            return self._cached_path

        candidates = [
            os.environ.get("VOICE1C_CHROME_PATH"),
            str(Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
            str(Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
            shutil.which("chrome.exe"),
            shutil.which("chrome"),
        ]
        candidates.extend(self._registry_candidates())

        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.exists():
                self._cached_path = path
                return path
        return None

    def _registry_candidates(self) -> list[str]:
        values: list[str] = []
        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
        ]
        for root, subkey in keys:
            try:
                with winreg.OpenKey(root, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, None)
                    if value:
                        values.append(value)
            except OSError:
                pass
        return values

    def chrome_version(self) -> str:
        if self._cached_version is not None:
            return self._cached_version
        path = self.find_chrome()
        if not path:
            return ""
        try:
            result = subprocess.run(
                [str(path), "--version"],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            data = result.stdout or result.stderr or b""
            decoded = ""
            for encoding in ("utf-8", locale.getpreferredencoding(False), "cp866", "cp1251"):
                try:
                    decoded = data.decode(encoding).strip()
                    if decoded:
                        break
                except UnicodeDecodeError:
                    continue
            self._cached_version = decoded or data.decode("utf-8", errors="replace").strip()
            if "chrome" not in self._cached_version.lower():
                self._cached_version = ""
            return self._cached_version
        except Exception:
            return ""

    def status(self) -> dict:
        path = self.find_chrome()
        return {
            "found": bool(path),
            "path": str(path) if path else "",
            "version": self.chrome_version() if path else "",
            "profile_path": str(chrome_profile_dir()),
            "download_url": CHROME_DOWNLOAD_URL,
        }
