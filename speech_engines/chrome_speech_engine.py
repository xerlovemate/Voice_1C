from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from chrome_runtime.chrome_manager import ChromeManager, chrome_profile_dir
from chrome_runtime.local_bridge_server import LocalBridgeServer

from .base import SpeechEngineBase


class ChromeSpeechEngine(SpeechEngineBase):
    name = "chrome"
    display_name = "Chrome Speech Free"

    def __init__(
        self,
        bridge_dir: Path,
        mode: str = "headless",
        port: int = 0,
        logger: logging.Logger | None = None,
    ):
        super().__init__()
        self.bridge_dir = Path(bridge_dir)
        self.mode = (mode or "hidden").lower()
        self.port = int(port or 0)
        self.logger = logger or logging.getLogger("voice1c.chrome_speech")
        self.manager = ChromeManager()
        self.server: LocalBridgeServer | None = None
        self.driver = None
        self.state = "idle"
        self.bridge_url = ""
        self.last_error = ""
        self.capabilities: dict = {}
        self._lock = threading.RLock()

    def is_available(self) -> bool:
        if not self.bridge_dir.exists():
            self.last_error = f"Chrome bridge files not found: {self.bridge_dir}"
            return False
        if not self.manager.find_chrome():
            self.last_error = "Google Chrome не найден"
            return False
        try:
            import selenium  # noqa: F401
        except Exception as exc:
            self.last_error = f"Selenium недоступен: {exc}"
            return False
        return True

    def start(self) -> None:
        with self._lock:
            if self.state in {"starting", "listening"}:
                return
            self.state = "starting"
            self.last_error = ""

        try:
            self._start_server()
            self._start_driver()
            self._start_recognition()
            with self._lock:
                self.state = "listening"
        except Exception as exc:
            if self.mode == "headless":
                self.logger.warning("[CHROME] headless failed; fallback to hidden window: %s", exc)
                self.capabilities["headless_failed"] = True
                self.stop()
                with self._lock:
                    self.state = "starting"
                self.mode = "hidden"
                try:
                    self._start_server()
                    self._start_driver()
                    self._start_recognition()
                    with self._lock:
                        self.state = "listening"
                    return
                except Exception as retry_exc:
                    exc = retry_exc
            self.logger.exception("[CHROME_SPEECH] start failed")
            self.last_error = str(exc)
            self.state = "error"
            self._on_error(str(exc))
            self.stop()
            raise

    def stop(self) -> None:
        with self._lock:
            if self.state == "idle":
                return
            self.state = "stopping"
        try:
            if self.driver:
                try:
                    self.driver.execute_script("window.voice1cStop && window.voice1cStop();")
                except Exception:
                    pass
                try:
                    self.driver.quit()
                except Exception as exc:
                    self.logger.warning("[CHROME] cannot quit driver: %s", exc)
        finally:
            self.driver = None
            if self.server:
                try:
                    self.server.stop()
                except Exception as exc:
                    self.logger.warning("[CHROME] cannot stop bridge server: %s", exc)
            self.server = None
            self._on_level(0.0)
            with self._lock:
                self.state = "idle"
            self.logger.info("[CHROME] stopped")

    def restart(self) -> None:
        self.stop()
        self.start()

    def _start_server(self) -> None:
        self.server = LocalBridgeServer(self.bridge_dir, self._handle_bridge_event, self.logger, self.port)
        self.bridge_url = self.server.start()

    def _start_driver(self) -> None:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        chrome_path = self.manager.find_chrome()
        if not chrome_path:
            raise RuntimeError("Google Chrome не найден")

        requested = self.mode
        actual = requested
        options = Options()
        options.binary_location = str(chrome_path)
        options.add_argument(f"--user-data-dir={chrome_profile_dir()}")
        options.add_argument("--use-fake-ui-for-media-stream")
        options.add_argument("--autoplay-policy=no-user-gesture-required")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--lang=ru-RU")
        options.add_experimental_option(
            "prefs",
            {
                "profile.default_content_setting_values.media_stream_mic": 1,
                "profile.default_content_setting_values.notifications": 2,
            },
        )

        if requested == "headless":
            options.add_argument("--headless=new")
            options.add_argument("--window-size=900,640")
        elif requested == "visible":
            options.add_argument("--window-size=560,420")
        else:
            actual = "hidden"
            options.add_argument("--window-size=520,360")
            options.add_argument("--window-position=-32000,-32000")

        self.logger.info("[CHROME] mode requested: %s", requested)
        self.logger.info("[CHROME] fallback to hidden window: %s", requested not in {"headless", "visible"})
        self.logger.info("[CHROME] chrome path: %s", chrome_path)
        self.logger.info("[CHROME] profile path: %s", chrome_profile_dir())

        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(20)
        self.driver.get(self.bridge_url)
        self.capabilities["chrome_mode_actual"] = actual

    def _start_recognition(self) -> None:
        if not self.driver:
            raise RuntimeError("Chrome driver is not started")

        deadline = time.monotonic() + 15
        capabilities = None
        while time.monotonic() < deadline:
            try:
                capabilities = self.driver.execute_script(
                    "return window.voice1cBridge && window.voice1cBridge.capabilities && window.voice1cBridge.capabilities();"
                )
                if capabilities:
                    break
            except Exception:
                pass
            time.sleep(0.2)

        if not capabilities:
            raise RuntimeError("Chrome speech bridge не загрузился")

        self.capabilities.update(capabilities)
        api_available = bool(capabilities.get("speechApiAvailable"))
        self.logger.info("[CHROME] speech api available: %s", api_available)
        if not api_available:
            raise RuntimeError("Web Speech API недоступен в этом Chrome")

        started = self.driver.execute_script("return window.voice1cStart && window.voice1cStart();")
        if not started:
            raise RuntimeError("Не удалось запустить Web Speech recognition")
        self.logger.info("[CHROME_SPEECH] recognition started")

    def _handle_bridge_event(self, event: str, payload: dict) -> None:
        text = str(payload.get("text") or "").strip()
        if event == "interim" and text:
            self.logger.info("[CHROME_SPEECH] interim: %s", text)
            self._on_partial(text)
        elif event == "final" and text:
            self.logger.info("[CHROME_SPEECH] final: %s", text)
            self._on_final(text)
        elif event == "error":
            error = str(payload.get("error") or "Chrome Speech error")
            self.last_error = error
            self.logger.error("[CHROME_SPEECH] error: %s", error)
            if error in {"no-speech", "aborted"}:
                return
            self._on_error(error)
        elif event == "level":
            try:
                self._on_level(float(payload.get("level") or 0.0))
            except Exception:
                self._on_level(0.0)
        elif event == "state":
            status = str(payload.get("status") or "")
            if status:
                self.capabilities["bridge_state"] = status
                self.logger.info("[CHROME] bridge state: %s", status)

    def get_status(self) -> dict:
        chrome = self.manager.status(include_version=self.state not in {"starting", "listening"})
        return {
            "available": self.is_available(),
            "state": self.state,
            "last_error": self.last_error,
            "bridge_url": self.bridge_url,
            "mode_requested": self.mode,
            "mode_actual": self.capabilities.get("chrome_mode_actual", ""),
            "chrome_found": chrome["found"],
            "chrome_path": chrome["path"],
            "chrome_version": chrome["version"],
            "profile_path": chrome["profile_path"],
            "speech_api_available": bool(self.capabilities.get("speechApiAvailable")),
            "microphone_permission": self.capabilities.get("bridge_state", "unknown"),
            "headless_failed": bool(self.capabilities.get("headless_failed")),
            "selenium_ready": self.driver is not None,
        }
