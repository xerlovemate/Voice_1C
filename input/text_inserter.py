from __future__ import annotations

import logging
import time

import keyboard as kb
import pyperclip

from . import hotkeys


class TextInserter:
    def __init__(
        self,
        method: str = "clipboard",
        insert_delay_ms: int = 300,
        restore_clipboard: bool = True,
        restore_delay_ms: int = 250,
        logger: logging.Logger | None = None,
    ):
        self.method = method
        self.insert_delay_ms = insert_delay_ms
        self.restore_clipboard = restore_clipboard
        self.restore_delay_ms = restore_delay_ms
        self.logger = logger or logging.getLogger("voice1c.input")
        self.last_inserted_text = ""

    def configure(
        self,
        method: str | None = None,
        insert_delay_ms: int | None = None,
        restore_clipboard: bool | None = None,
        restore_delay_ms: int | None = None,
    ) -> None:
        if method:
            self.method = method
        if insert_delay_ms is not None:
            self.insert_delay_ms = insert_delay_ms
        if restore_clipboard is not None:
            self.restore_clipboard = restore_clipboard
        if restore_delay_ms is not None:
            self.restore_delay_ms = restore_delay_ms

    def insert_text(self, text: str) -> None:
        if not text:
            return
        if self.insert_delay_ms > 0:
            time.sleep(self.insert_delay_ms / 1000)
        self.logger.info("[INSERT] method %s, chars=%s", self.method, len(text))
        if self.method == "keyboard":
            self.type_text_slow(text)
        else:
            self.paste_text_fast(text)
        self.last_inserted_text = text

    def type_text_slow(self, text: str) -> None:
        kb.write(text, delay=0.005)
        self.logger.info("[INSERT] keyboard.write success")

    def paste_text_fast(self, text: str) -> None:
        old_clipboard = None
        had_old_clipboard = False
        try:
            old_clipboard = pyperclip.paste()
            had_old_clipboard = True
        except Exception as exc:
            self.logger.warning("cannot read clipboard before paste: %s", exc)

        pyperclip.copy(text)
        time.sleep(0.03)
        hotkeys.paste()
        self.logger.info("[INSERT] clipboard paste success")

        if self.restore_clipboard and had_old_clipboard:
            time.sleep(max(self.restore_delay_ms, 0) / 1000)
            try:
                pyperclip.copy(old_clipboard)
            except Exception as exc:
                self.logger.warning("cannot restore clipboard: %s", exc)

    def undo_last_insert(self) -> None:
        hotkeys.undo()
