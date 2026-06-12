from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class UpdateInfo:
    available: bool
    message: str
    latest_version: str | None = None
    notes: str = ""
    asset_url: str | None = None
    asset_name: str | None = None


def parse_version(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lstrip("vV")
    parts = []
    for part in cleaned.split("."):
        number = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(number or 0))
    return tuple(parts or [0])


class GitHubUpdater:
    def __init__(self, config: dict, logger: logging.Logger | None = None):
        self.config = config
        self.logger = logger or logging.getLogger("voice1c.updater")

    def check_latest(self) -> UpdateInfo:
        owner = self.config.get("github_owner")
        repo = self.config.get("github_repo")
        asset_name = self.config.get("release_asset_name", "Voice1CSetup.exe")
        current = self.config.get("version", "0.0.0")
        if not owner or not repo:
            return UpdateInfo(False, "GitHub updater отключён: owner/repo не заполнены.")

        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        try:
            with urllib.request.urlopen(api_url, timeout=10) as response:
                release = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                self.logger.info("[UPDATER] no releases found")
                return UpdateInfo(False, "Релизы пока не опубликованы.")
            return UpdateInfo(False, f"Не удалось проверить обновления: HTTP {exc.code}")
        except Exception as exc:
            return UpdateInfo(False, f"Не удалось проверить обновления: {exc}")

        tag = release.get("tag_name") or release.get("name") or "0.0.0"
        latest = tag.lstrip("vV")
        if parse_version(latest) <= parse_version(current):
            return UpdateInfo(False, f"Установлена актуальная версия {current}.", latest)

        asset_url = None
        for asset in release.get("assets", []):
            if asset.get("name") == asset_name:
                asset_url = asset.get("browser_download_url")
                break
        if not asset_url:
            return UpdateInfo(False, f"В релизе {tag} не найден asset {asset_name}.", latest)

        return UpdateInfo(
            True,
            f"Доступна версия {latest}.",
            latest_version=latest,
            notes=release.get("body") or "",
            asset_url=asset_url,
            asset_name=asset_name,
        )

    def download_and_run(self, info: UpdateInfo) -> str:
        if not info.asset_url or not info.asset_name:
            raise ValueError("Нет ссылки на установщик обновления.")
        target = Path(tempfile.gettempdir()) / info.asset_name
        urllib.request.urlretrieve(info.asset_url, target)
        if target.stat().st_size <= 0:
            raise RuntimeError("Скачанный установщик пустой.")

        checksum_url = info.asset_url + ".sha256"
        try:
            checksum_path = Path(tempfile.gettempdir()) / f"{info.asset_name}.sha256"
            urllib.request.urlretrieve(checksum_url, checksum_path)
            expected = checksum_path.read_text(encoding="utf-8").split()[0].lower()
            actual = hashlib.sha256(target.read_bytes()).hexdigest().lower()
            if expected and expected != actual:
                raise RuntimeError("SHA256 скачанного установщика не совпадает.")
        except urllib.error.HTTPError:
            pass

        subprocess.Popen([str(target)], close_fds=True)
        os._exit(0)
