from __future__ import annotations

from contextlib import contextmanager

from pynput.keyboard import Controller, Key

try:
    from utils import is_russian_layout
except Exception:
    is_russian_layout = lambda: False

keyboard = Controller()


def press_and_release(key) -> None:
    keyboard.press(key)
    keyboard.release(key)


@contextmanager
def pressed(key):
    keyboard.press(key)
    try:
        yield
    finally:
        keyboard.release(key)


def enter() -> None:
    press_and_release(Key.enter)


def tab() -> None:
    press_and_release(Key.tab)


def delete_word() -> None:
    with pressed(Key.ctrl):
        press_and_release(Key.backspace)


def delete_line() -> None:
    with pressed(Key.shift):
        press_and_release(Key.end)
    press_and_release(Key.backspace)


def semicolon_enter() -> None:
    press_and_release(";")
    press_and_release(Key.enter)


def ctrl_combo(en_key: str, ru_key: str | None = None) -> None:
    key = ru_key if ru_key and is_russian_layout() else en_key
    with pressed(Key.ctrl):
        press_and_release(key)


def copy() -> None:
    ctrl_combo("c", "с")


def paste() -> None:
    ctrl_combo("v", "м")


def cut() -> None:
    ctrl_combo("x", "ч")


def search() -> None:
    ctrl_combo("f", "а")


def undo() -> None:
    ctrl_combo("z", "я")
