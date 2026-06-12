from __future__ import annotations

import json
import logging
import shutil
import threading
import time
import webbrowser
from datetime import datetime

from app_config import default_config
from chrome_runtime.chrome_manager import CHROME_DOWNLOAD_URL, ChromeManager, chrome_profile_dir
from input import hotkeys
from input.text_inserter import TextInserter
from speech_engines.chrome_speech_engine import ChromeSpeechEngine
from speech_engines.microphones import list_microphones, normalize_device_id, test_microphone_level
from speech_engines.vosk_engine import VoskSpeechEngine
from updater.github_updater import GitHubUpdater, UpdateInfo
from voice_actions.command_router import CommandRouter
from voice_actions.formatter_1c import format_1c
from voice_actions.formatter_default import format_default

from .logging_setup import open_log_file
from .resource_paths import frontend_path, log_file_path, resource_path, user_config_path


ENGINE_AUTO = "auto"
ENGINE_CHROME = "chrome speech free"
ENGINE_VOSK = "vosk offline"
LEGACY_ENGINES = {"windows", "windows speech", "azure", "azure online"}


class AppController:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.lock = threading.RLock()
        self.config = self._load_config()
        self.status = "Пауза"
        self.status_kind = "paused"
        self.listening = False
        self.engine_running = False
        self.partial_text = ""
        self.mic_level = 0.0
        self.mic_test_running = False
        self.mic_test_result = ""
        self.last_phrase = ""
        self.last_result = ""
        self.last_error = ""
        self.update_message = "Готово к проверке обновлений."
        self.pending_update: UpdateInfo | None = None
        self.recent_phrases: list[dict] = []
        self.replacements = self._load_replacements()
        self.chrome_manager = ChromeManager()
        self.inserter = TextInserter(
            method=self.config.get("input_method", "clipboard"),
            insert_delay_ms=int(self.config.get("insert_delay_ms", 300)),
            restore_clipboard=bool(self.config.get("restore_clipboard", True)),
            restore_delay_ms=int(self.config.get("restore_clipboard_delay_ms", 250)),
            logger=self.logger,
        )
        self.command_router = CommandRouter(resource_path("command_config.json"), logger=self.logger)
        self.engine = None
        self._select_engine(self.config.get("speech_engine", "auto"))
        if self.config.get("update_check_on_start", True):
            threading.Thread(target=self._check_updates_on_start, name="Voice1CUpdateCheck", daemon=True).start()

    def _normalize_engine_name(self, engine_name: str | None) -> str:
        normalized = " ".join((engine_name or ENGINE_AUTO).strip().lower().split())
        if normalized in LEGACY_ENGINES:
            self.logger.warning("[VOICE] legacy engine '%s' is disabled; using Auto", engine_name)
            return ENGINE_AUTO
        if normalized in {"chrome", "chrome speech", "chrome speech free", "web speech"}:
            return ENGINE_CHROME
        if normalized in {"vosk", "vosk offline", "offline"}:
            return ENGINE_VOSK
        return ENGINE_AUTO

    def _make_chrome_engine(self) -> ChromeSpeechEngine:
        return ChromeSpeechEngine(
            frontend_path("chrome_bridge"),
            mode=str(self.config.get("chrome_mode", "headless")),
            port=int(self.config.get("chrome_bridge_port", 0) or 0),
            logger=self.logger,
        )

    def _make_vosk_engine(self) -> VoskSpeechEngine:
        return VoskSpeechEngine(
            resource_path("model"),
            logger=self.logger,
            device_id=self.config.get("selected_microphone_id"),
        )

    def _check_updates_on_start(self) -> None:
        try:
            time.sleep(1.2)
            self.check_updates()
        except Exception:
            self.logger.exception("[UPDATE] startup check failed")

    def _load_config(self) -> dict:
        config = default_config()
        path = user_config_path()
        if path.exists():
            try:
                config.update(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                self.logger.warning("cannot load user config: %s", exc)
        config["version"] = default_config().get("version")
        config["app_name"] = default_config().get("app_name")
        config["github_owner"] = config.get("github_owner") or default_config().get("github_owner")
        config["github_repo"] = config.get("github_repo") or default_config().get("github_repo")
        config["release_asset_name"] = config.get("release_asset_name") or default_config().get("release_asset_name")
        return config

    def _save_config(self) -> None:
        user_config_path().write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_replacements(self) -> dict[str, str]:
        path = resource_path("replacements.json")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.logger.warning("cannot load replacements: %s", exc)
            return {}
        replacements: dict[str, str] = {}
        for item in data:
            patterns = item.get("patterns", "")
            replacement = item.get("replacement", "")
            for pattern in patterns.split(","):
                normalized = pattern.strip().lower()
                if normalized:
                    replacements[normalized] = replacement
        return replacements

    def _select_engine(self, engine_name: str) -> None:
        normalized = self._normalize_engine_name(engine_name)
        if self.engine:
            self.engine.stop()
            self.engine_running = False

        if normalized == ENGINE_CHROME:
            engine = self._make_chrome_engine()
            self.config["speech_engine"] = ENGINE_CHROME
        elif normalized == ENGINE_VOSK:
            engine = self._make_vosk_engine()
            self.config["speech_engine"] = ENGINE_VOSK
        else:
            chrome = self._make_chrome_engine()
            if chrome.is_available():
                engine = chrome
                self.logger.info("[VOICE] Auto selected Chrome Speech Free")
            else:
                self.logger.warning("[VOICE] Chrome unavailable in Auto: %s; fallback to Vosk Offline", chrome.last_error)
                engine = self._make_vosk_engine()
            self.config["speech_engine"] = ENGINE_AUTO

        engine.set_on_partial(self._on_partial)
        engine.set_on_final(self._on_final)
        engine.set_on_error(self._on_error)
        engine.set_on_level(self._on_level)
        self.engine = engine
        self.logger.info("speech engine selected: %s", self.engine.name)

    def ensure_engine_started(self) -> bool:
        if self.engine_running:
            return True
        if not self.engine or not self.engine.is_available():
            if self.config.get("speech_engine") == ENGINE_AUTO and not isinstance(self.engine, VoskSpeechEngine):
                self.logger.warning("[VOICE] active Auto engine unavailable; fallback to Vosk Offline")
                self._select_engine(ENGINE_VOSK)
                self.config["speech_engine"] = ENGINE_AUTO
            if not self.engine or not self.engine.is_available():
                self._on_error("\u0412\u044b\u0431\u0440\u0430\u043d\u043d\u044b\u0439 \u0434\u0432\u0438\u0436\u043e\u043a \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0432\u0430\u043d\u0438\u044f \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 Chrome, \u043c\u043e\u0434\u0435\u043b\u044c Vosk \u0438\u043b\u0438 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d\u0430.")
                return False
        try:
            self.logger.info("[VOICE] starting engine: %s", self.engine.name)
            self.engine.start()
        except Exception as exc:
            self.logger.exception("[VOICE] engine start failed: %s", self.engine.name if self.engine else "")
            if self.config.get("speech_engine") == ENGINE_AUTO and not isinstance(self.engine, VoskSpeechEngine):
                self.logger.warning("[VOICE] Chrome failed in Auto; fallback to Vosk Offline")
                self._select_engine(ENGINE_VOSK)
                self.config["speech_engine"] = ENGINE_AUTO
                if not self.engine or not self.engine.is_available():
                    self._on_error(f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c Chrome Speech \u0438 Vosk \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d: {exc}")
                    return False
                try:
                    self.engine.start()
                except Exception as fallback_exc:
                    self.logger.exception("[VOICE] Vosk fallback failed")
                    self._on_error(f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c fallback Vosk: {fallback_exc}")
                    return False
            else:
                self._on_error(str(exc))
                return False
        if getattr(self.engine, "state", "") == "error":
            self._on_error(getattr(self.engine, "last_error", "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0432\u0430\u043d\u0438\u0435."))
            return False
        self.engine_running = True
        self.last_error = ""
        return True

    def toggle_listening(self) -> dict:
        with self.lock:
            self.logger.info("[API] toggle_listening received")
            if self.listening or self.status_kind == "error":
                if self.engine:
                    self.engine.stop()
                self.listening = False
                self.engine_running = False
                self.status = "Пауза"
                self.status_kind = "paused"
                self.partial_text = ""
                self.mic_level = 0.0
                self.logger.info("listening changed: %s", self.listening)
                return self.get_status()
            if not self.listening and not self.ensure_engine_started():
                return self.get_status()
            self.listening = True
            self.status = "Слушаю" if self.listening else "Пауза"
            self.status_kind = "listening" if self.listening else "paused"
            self.logger.info("listening changed: %s", self.listening)
            return self.get_status()

    def set_listening(self, value: bool) -> None:
        with self.lock:
            if value:
                if not self.ensure_engine_started():
                    return
            self.listening = value
            self.status = "Слушаю" if value else "Пауза"
            self.status_kind = "listening" if value else "paused"

    def _on_partial(self, text: str) -> None:
        with self.lock:
            self.partial_text = text

    def _on_level(self, level: float) -> None:
        with self.lock:
            self.mic_level = max(0.0, min(1.0, float(level or 0.0)))

    def _on_final(self, text: str) -> None:
        try:
            self.handle_phrase(text)
        except Exception as exc:
            self.logger.exception("cannot handle phrase")
            self._on_error(str(exc))

    def _on_error(self, message: str) -> None:
        with self.lock:
            self.last_error = message
            self.status = "Ошибка"
            self.status_kind = "error"
            self.listening = False
            self.engine_running = False
            self.mic_level = 0.0
            self.logger.error(message)

    def handle_phrase(self, text: str) -> None:
        normalized = " ".join((text or "").strip().lower().split())
        if not normalized:
            return
        self.logger.info("[PIPELINE] received text from %s: %s", getattr(self.engine, "name", "unknown"), normalized)

        command = self.command_router.match(normalized)
        if command.handled:
            self.logger.info("[COMMAND] handled=true input=%s action=%s", normalized, command.action)
            self._execute_command(command.action or "", command.dangerous)
            self._add_history(text, f"Команда: {command.action}", "command")
            return

        if not self.listening:
            self.logger.info("phrase ignored while paused: %s", text)
            return

        self.logger.info("[COMMAND] handled=false input=%s", normalized)
        mode = self.config.get("mode", "1c")
        result = format_1c(normalized, self.replacements) if mode == "1c" else format_default(normalized, self.replacements)
        self.logger.info("[FORMAT] mode=%s input=%s output=%s", mode, normalized, result)
        try:
            self.inserter.insert_text(result)
            self.logger.info("[INSERT] method=%s success=true", self.config.get("input_method", "clipboard"))
        except Exception as exc:
            self.logger.exception("[INSERT] failed")
            self._on_error(f"Не удалось вставить текст: {exc}")
            return

        with self.lock:
            self.last_phrase = text
            self.last_result = result
            self.last_error = ""
            self.partial_text = ""
            self._add_history(text, result, "1С-код" if mode == "1c" else "Текст")

    def _execute_command(self, action: str, dangerous: bool) -> None:
        if dangerous and self.config.get("confirm_dangerous_commands", True):
            self.last_result = f"Команда '{action}' требует подтверждения. Подтверждение будет добавлено в следующем шаге."
            self.logger.info("dangerous command skipped pending confirmation: %s", action)
            return

        actions = {
            "start": lambda: self.set_listening(True),
            "stop": lambda: self.set_listening(False),
            "enter": hotkeys.enter,
            "tab": hotkeys.tab,
            "delete_word": hotkeys.delete_word,
            "delete_line": hotkeys.delete_line,
            "copy": hotkeys.copy,
            "paste": hotkeys.paste,
            "cut": hotkeys.cut,
            "search": hotkeys.search,
            "newline": hotkeys.semicolon_enter,
            "undo": self.inserter.undo_last_insert,
        }
        handler = actions.get(action)
        if handler:
            handler()
            self.last_result = f"Выполнена команда: {action}"
            self.last_error = ""
            self.logger.info("command executed: %s", action)

    def _add_history(self, phrase: str, result: str, kind: str) -> None:
        item = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "phrase": phrase,
            "result": result,
            "kind": kind,
        }
        self.recent_phrases.insert(0, item)
        del self.recent_phrases[20:]

    def set_mode(self, mode: str) -> dict:
        self.config["mode"] = "1c" if mode in {"1c", "code"} else "text"
        self._save_config()
        return self.get_status()

    def set_engine(self, engine: str) -> dict:
        was_listening = self.listening
        self.listening = False
        self._select_engine(engine)
        self._save_config()
        if was_listening:
            self.set_listening(True)
        return self.get_status()

    def set_chrome_mode(self, mode: str) -> dict:
        normalized = str(mode or "headless").lower()
        if normalized not in {"hidden", "visible", "headless"}:
            normalized = "headless"
        was_listening = self.listening
        self.config["chrome_mode"] = normalized
        if isinstance(self.engine, ChromeSpeechEngine):
            self.listening = False
            self.engine.stop()
            self.engine_running = False
            self._select_engine(self.config.get("speech_engine", ENGINE_AUTO))
        self._save_config()
        if was_listening:
            self.set_listening(True)
        return self.get_status()

    def get_chrome_status(self) -> dict:
        if isinstance(self.engine, ChromeSpeechEngine):
            return self.engine.get_status()
        status = self.chrome_manager.status()
        bridge_dir = frontend_path("chrome_bridge")
        status.update(
            {
                "available": bool(status.get("found")) and bridge_dir.exists(),
                "state": "idle",
                "last_error": "" if bridge_dir.exists() else f"Chrome bridge files not found: {bridge_dir}",
                "bridge_url": "",
                "mode_requested": self.config.get("chrome_mode", "headless"),
                "mode_actual": "",
                "speech_api_available": False,
                "microphone_permission": "unknown",
                "selenium_ready": False,
            }
        )
        return status

    def test_chrome_speech(self) -> dict:
        self.logger.info("[CHROME] test requested")
        engine = self.engine if isinstance(self.engine, ChromeSpeechEngine) else self._make_chrome_engine()
        if not engine.is_available():
            return {"ok": False, "message": engine.last_error or "Chrome Speech Free is not available", "status": self.get_status()}
        started_temp = False
        try:
            if engine is self.engine and self.engine_running:
                return {"ok": True, "message": "Chrome Speech Free is already running", "chrome_status": engine.get_status(), "status": self.get_status()}
            engine.start()
            started_temp = True
            time.sleep(0.8)
            return {"ok": True, "message": "Chrome Speech Free started successfully", "chrome_status": engine.get_status(), "status": self.get_status()}
        except Exception as exc:
            self.logger.exception("[CHROME] test failed")
            return {"ok": False, "message": str(exc), "chrome_status": engine.get_status(), "status": self.get_status()}
        finally:
            if started_temp:
                engine.stop()
                if engine is self.engine:
                    self.engine_running = False
                    self.listening = False

    def restart_chrome_speech(self) -> dict:
        self.logger.info("[CHROME] restart requested")
        if not isinstance(self.engine, ChromeSpeechEngine):
            self._select_engine(ENGINE_CHROME)
        if not self.engine:
            return self.get_status()
        try:
            self.engine.stop()
            self.engine_running = False
            self.listening = False
            self.engine.start()
            self.engine_running = True
            self.listening = True
            self.status = "Слушаю"
            self.status_kind = "listening"
            self.last_error = ""
        except Exception as exc:
            self.logger.exception("[CHROME] restart failed")
            self._on_error(str(exc))
        return self.get_status()

    def open_chrome_window(self) -> dict:
        self.config["chrome_mode"] = "visible"
        self._save_config()
        was_listening = self.listening
        if not isinstance(self.engine, ChromeSpeechEngine):
            self._select_engine(ENGINE_CHROME)
        elif self.engine_running:
            self.engine.stop()
            self.engine_running = False
            self.listening = False
            self._select_engine(ENGINE_CHROME)
        if was_listening or not self.engine_running:
            self.set_listening(True)
        return self.get_status()

    def reset_chrome_permission(self) -> dict:
        self.logger.info("[CHROME] permission/profile reset requested")
        if isinstance(self.engine, ChromeSpeechEngine):
            self.engine.stop()
            self.engine_running = False
            self.listening = False
        profile = chrome_profile_dir()
        try:
            if profile.exists():
                shutil.rmtree(profile)
            profile.mkdir(parents=True, exist_ok=True)
            self.last_result = "Профиль Chrome Speech сброшен. При следующем запуске разрешение микрофона будет выдано заново."
            self.last_error = ""
        except Exception as exc:
            self.logger.exception("[CHROME] profile reset failed")
            self._on_error(f"Не удалось сбросить профиль Chrome: {exc}")
        return self.get_status()

    def open_chrome_download(self) -> dict:
        try:
            webbrowser.open(CHROME_DOWNLOAD_URL)
            self.last_result = "Открыта официальная страница установки Google Chrome."
        except Exception as exc:
            self.logger.exception("[CHROME] cannot open download page")
            self._on_error(f"Не удалось открыть страницу Chrome: {exc}")
        return self.get_status()

    def set_input_method(self, method: str) -> dict:
        normalized = "keyboard" if method in {"keyboard", "slow"} else "clipboard"
        self.config["input_method"] = normalized
        self.inserter.configure(method=normalized)
        self._save_config()
        return self.get_status()

    def get_microphones(self) -> list[dict]:
        try:
            devices = list_microphones()
            self.logger.info("[MIC] devices listed: %s", len(devices))
            if not devices:
                self._on_error("Микрофоны не найдены.")
            return devices
        except Exception as exc:
            self.logger.exception("[MIC] cannot list devices")
            self._on_error(f"Не удалось получить список микрофонов: {exc}")
            return []

    def set_microphone(self, device_id: int | str | None) -> dict:
        normalized = normalize_device_id(device_id)
        self.logger.info("[MIC] selected in config: %s", normalized if normalized is not None else "default")
        was_listening = self.listening
        if self.engine:
            self.engine.stop()
        self.engine_running = False
        self.listening = False
        self.config["selected_microphone_id"] = normalized
        if isinstance(self.engine, VoskSpeechEngine):
            self.engine.set_device(normalized)
        self._save_config()
        if was_listening:
            self.set_listening(True)
        return self.get_status()

    def get_selected_microphone(self):
        return self.config.get("selected_microphone_id")

    def test_microphone(self) -> dict:
        with self.lock:
            if self.engine_running:
                self.mic_test_result = "Диктовка уже слушает микрофон; уровень отображается в индикаторе."
                return {"ok": True, "message": self.mic_test_result}
            if self.mic_test_running:
                return {"ok": False, "message": "Тест микрофона уже идёт."}
            self.mic_test_running = True
            self.mic_test_result = "Тест микрофона запущен."

        def worker() -> None:
            try:
                self.logger.info("[MIC] test started")
                result = test_microphone_level(
                    self.config.get("selected_microphone_id"),
                    5.0,
                    self._on_level,
                )
                message = f"Тест завершён: {result['device_name']}, пик {int(result['peak'] * 100)}%."
                if result.get("fallback"):
                    message += " Выбранный микрофон недоступен, использован default."
                self.logger.info("[MIC] test finished: %s", result)
                with self.lock:
                    self.mic_test_result = message
                    self.last_result = message
            except Exception as exc:
                self.logger.exception("[MIC] test failed")
                self._on_error(f"Ошибка теста микрофона: {exc}")
                with self.lock:
                    self.mic_test_result = f"Ошибка теста микрофона: {exc}"
            finally:
                with self.lock:
                    self.mic_test_running = False
                    self.mic_level = 0.0

        threading.Thread(target=worker, name="Voice1CMicrophoneTest", daemon=True).start()
        return {"ok": True, "message": "Говорите в микрофон 5 секунд."}

    def test_insert(self) -> dict:
        text = "Тест Voice 1C"
        try:
            self.logger.info("[INSERT] test requested")
            self.inserter.insert_text(text)
            self.last_result = f"Тест вставки выполнен: {text}"
            self._add_history("тест вставки", text, "Тест")
            return self.get_status()
        except Exception as exc:
            self.logger.exception("[INSERT] test failed")
            self._on_error(f"Не удалось выполнить тест вставки: {exc}")
            return self.get_status()

    def save_settings(self, settings: dict) -> dict:
        self.config.update(settings or {})
        self.inserter.configure(
            method=self.config.get("input_method", "clipboard"),
            insert_delay_ms=int(self.config.get("insert_delay_ms", 300)),
            restore_clipboard=bool(self.config.get("restore_clipboard", True)),
            restore_delay_ms=int(self.config.get("restore_clipboard_delay_ms", 250)),
        )
        self._save_config()
        return self.get_status()

    def test_formatting(self, text: str) -> str:
        mode = self.config.get("mode", "1c")
        normalized = " ".join((text or "").strip().lower().split())
        return format_1c(normalized, self.replacements) if mode == "1c" else format_default(normalized, self.replacements)

    def undo_last_insert(self) -> dict:
        self.inserter.undo_last_insert()
        self.last_result = "Отмена последнего действия отправлена в активное окно."
        return self.get_status()

    def check_updates(self) -> dict:
        updater = GitHubUpdater(self.config, logger=self.logger)
        info = updater.check_latest()
        self.pending_update = info if info.available else None
        self.update_message = info.message
        return {
            "available": info.available,
            "message": info.message,
            "latest_version": info.latest_version,
            "notes": info.notes,
            "asset_name": info.asset_name,
        }

    def install_pending_update(self) -> dict:
        if not self.pending_update:
            return {"ok": False, "message": "Нет подготовленного обновления."}
        GitHubUpdater(self.config, logger=self.logger).download_and_run(self.pending_update)
        return {"ok": True, "message": "Установщик обновления запущен."}

    def open_logs(self) -> dict:
        try:
            open_log_file()
            return {"ok": True, "message": str(log_file_path())}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def get_status(self) -> dict:
        with self.lock:
            return {
                "app_name": self.config.get("app_name"),
                "version": self.config.get("version"),
                "listening": self.listening,
                "engine_running": self.engine_running,
                "status": self.status,
                "status_kind": self.status_kind,
                "mode": self.config.get("mode", "1c"),
                "speech_engine": self.config.get("speech_engine", "auto"),
                "active_engine": getattr(self.engine, "name", ""),
                "active_engine_display": getattr(self.engine, "display_name", getattr(self.engine, "name", "")),
                "chrome_mode": self.config.get("chrome_mode", "headless"),
                "chrome_status": self.get_chrome_status(),
                "input_method": self.config.get("input_method", "clipboard"),
                "restore_clipboard": self.config.get("restore_clipboard", True),
                "confirm_dangerous_commands": self.config.get("confirm_dangerous_commands", True),
                "sound_enabled": self.config.get("sound_enabled", True),
                "update_check_on_start": self.config.get("update_check_on_start", True),
                "large_ui_mode": self.config.get("large_ui_mode", True),
                "selected_microphone_id": self.config.get("selected_microphone_id"),
                "mic_level": self.mic_level,
                "mic_test_running": self.mic_test_running,
                "mic_test_result": self.mic_test_result,
                "partial_text": self.partial_text,
                "last_phrase": self.last_phrase,
                "last_result": self.last_result,
                "last_error": self.last_error,
                "phrases_count": len([item for item in self.recent_phrases if item["kind"] != "command"]),
                "recent_phrases": list(self.recent_phrases[:8]),
                "update_message": self.update_message,
                "github_owner": self.config.get("github_owner"),
                "github_repo": self.config.get("github_repo"),
                "release_asset_name": self.config.get("release_asset_name"),
                "log_file": str(log_file_path()),
                "log_tail": self.read_log_tail(),
            }

    def get_recent_phrases(self) -> list[dict]:
        return self.get_status()["recent_phrases"]

    def log_event(self, message: str) -> bool:
        self.logger.info(str(message))
        return True

    def read_log_tail(self, max_lines: int = 80) -> str:
        path = log_file_path()
        try:
            if not path.exists():
                return ""
            return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:])
        except Exception as exc:
            return f"Не удалось прочитать лог: {exc}"

    def shutdown(self, *args) -> None:
        self.logger.info("application shutdown")
        if self.engine:
            self.engine.stop()
            self.engine_running = False


class AppApi:
    def __init__(self, controller: AppController):
        self.controller = controller

    def toggle_listening(self):
        return self.controller.toggle_listening()

    def set_mode(self, mode):
        return self.controller.set_mode(mode)

    def set_engine(self, engine):
        return self.controller.set_engine(engine)

    def set_chrome_mode(self, mode):
        return self.controller.set_chrome_mode(mode)

    def get_chrome_status(self):
        return self.controller.get_chrome_status()

    def test_chrome_speech(self):
        return self.controller.test_chrome_speech()

    def restart_chrome_speech(self):
        return self.controller.restart_chrome_speech()

    def open_chrome_window(self):
        return self.controller.open_chrome_window()

    def reset_chrome_permission(self):
        return self.controller.reset_chrome_permission()

    def open_chrome_download(self):
        return self.controller.open_chrome_download()

    def set_input_method(self, method):
        return self.controller.set_input_method(method)

    def get_status(self):
        return self.controller.get_status()

    def get_recent_phrases(self):
        return self.controller.get_recent_phrases()

    def check_updates(self):
        return self.controller.check_updates()

    def open_logs(self):
        return self.controller.open_logs()

    def save_settings(self, settings):
        return self.controller.save_settings(settings)

    def test_formatting(self, text):
        return self.controller.test_formatting(text)

    def undo_last_insert(self):
        return self.controller.undo_last_insert()

    def install_pending_update(self):
        return self.controller.install_pending_update()

    def get_microphones(self):
        return self.controller.get_microphones()

    def set_microphone(self, device_id):
        return self.controller.set_microphone(device_id)

    def get_selected_microphone(self):
        return self.controller.get_selected_microphone()

    def test_microphone(self):
        return self.controller.test_microphone()

    def test_insert(self):
        return self.controller.test_insert()

    def read_log_tail(self):
        return self.controller.read_log_tail()

    def log_event(self, message):
        return self.controller.log_event(message)
