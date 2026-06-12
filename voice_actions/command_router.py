from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz, process


@dataclass
class CommandMatch:
    handled: bool
    action: str | None = None
    phrase: str | None = None
    score: float = 0
    dangerous: bool = False


class CommandRouter:
    def __init__(self, config_path: Path, logger: logging.Logger | None = None):
        self.config_path = config_path
        self.logger = logger or logging.getLogger("voice1c.commands")
        self.threshold = 86
        self.commands: list[dict] = []
        self.load()

    def load(self) -> None:
        with open(self.config_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        self.threshold = int(data.get("threshold", self.threshold))
        self.commands = list(data.get("commands", []))

    def match(self, text: str) -> CommandMatch:
        normalized = " ".join((text or "").strip().lower().split())
        if len(normalized) < 3:
            return CommandMatch(False)

        best: CommandMatch | None = None
        for command in self.commands:
            phrases = command.get("phrases", [])
            if normalized in phrases:
                return CommandMatch(
                    True,
                    action=command.get("action"),
                    phrase=normalized,
                    score=100,
                    dangerous=bool(command.get("dangerous", False)),
                )

            result = process.extractOne(
                normalized,
                phrases,
                scorer=fuzz.WRatio,
                score_cutoff=self.threshold,
            )
            if not result:
                continue
            phrase, score, _ = result
            if best is None or score > best.score:
                best = CommandMatch(
                    True,
                    action=command.get("action"),
                    phrase=phrase,
                    score=score,
                    dangerous=bool(command.get("dangerous", False)),
                )

        return best or CommandMatch(False)
