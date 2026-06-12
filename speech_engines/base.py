from __future__ import annotations

from typing import Callable

SpeechCallback = Callable[[str], None]
LevelCallback = Callable[[float], None]


class SpeechEngineBase:
    name = "base"

    def __init__(self):
        self._on_partial: SpeechCallback = lambda text: None
        self._on_final: SpeechCallback = lambda text: None
        self._on_error: SpeechCallback = lambda text: None
        self._on_level: LevelCallback = lambda level: None

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def is_available(self) -> bool:
        return False

    def set_on_partial(self, callback: SpeechCallback) -> None:
        self._on_partial = callback

    def set_on_final(self, callback: SpeechCallback) -> None:
        self._on_final = callback

    def set_on_error(self, callback: SpeechCallback) -> None:
        self._on_error = callback

    def set_on_level(self, callback: LevelCallback) -> None:
        self._on_level = callback
