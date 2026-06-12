from __future__ import annotations

from .base import SpeechEngineBase


class AzureSpeechEngine(SpeechEngineBase):
    name = "azure"

    def start(self) -> None:
        self._on_error("Azure Speech пока не настроен. Нужны ключ и регион Azure.")

    def stop(self) -> None:
        return None

    def is_available(self) -> bool:
        return False
