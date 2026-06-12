from __future__ import annotations

from .base import SpeechEngineBase


class WindowsSpeechEngine(SpeechEngineBase):
    name = "windows"

    def start(self) -> None:
        self._on_error("Windows Speech engine пока доступен как архитектурная заглушка.")

    def stop(self) -> None:
        return None

    def is_available(self) -> bool:
        return False
