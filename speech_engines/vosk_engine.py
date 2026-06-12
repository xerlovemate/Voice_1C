from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from .base import SpeechEngineBase
from .microphones import calculate_level, open_input_stream, select_device_or_default


class VoskSpeechEngine(SpeechEngineBase):
    name = "vosk"

    def __init__(
        self,
        model_path: Path,
        logger: logging.Logger | None = None,
        device_id: int | str | None = None,
    ):
        super().__init__()
        self.model_path = self._resolve_model_path(Path(model_path))
        self.logger = logger or logging.getLogger("voice1c.speech.vosk")
        self.device_id = device_id
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self.sample_rate = self._read_sample_rate(self.model_path) or 16000

    @staticmethod
    def _is_model_dir(path: Path) -> bool:
        return (path / "am").exists() and (path / "conf").exists() and (path / "graph").exists()

    @classmethod
    def _resolve_model_path(cls, path: Path) -> Path:
        if cls._is_model_dir(path):
            nested = sorted(path.glob("vosk-model-*"))
            for candidate in nested:
                if cls._is_model_dir(candidate) and cls._read_sample_rate(candidate) == 16000:
                    return candidate
            return path
        for candidate in sorted(path.glob("vosk-model-*")):
            if cls._is_model_dir(candidate):
                return candidate
        return path

    @staticmethod
    def _read_sample_rate(path: Path) -> int | None:
        mfcc = path / "conf" / "mfcc.conf"
        if not mfcc.exists():
            return None
        for line in mfcc.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "--sample-frequency=" in line:
                try:
                    return int(float(line.split("=", 1)[1].strip()))
                except ValueError:
                    return None
        return None

    def set_device(self, device_id: int | str | None) -> None:
        self.device_id = device_id

    def is_available(self) -> bool:
        return self._is_model_dir(self.model_path)

    def start(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="VoskSpeechEngine", daemon=True)
        self._thread.start()
        self._running = True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._running = False

    def _run(self) -> None:
        stream = None
        audio = None
        try:
            import pyaudio
            from vosk import KaldiRecognizer, Model

            if not self.is_available():
                raise FileNotFoundError(f"Vosk model not found: {self.model_path}")

            self.logger.info("[VOSK] model loading: %s", self.model_path)
            model = Model(str(self.model_path))
            self.logger.info("[VOSK] model loaded")
            if self._stop_event.is_set():
                return

            device_index, device, fallback = select_device_or_default(self.device_id)
            if device is None:
                raise RuntimeError("Микрофоны не найдены")
            if fallback:
                self.logger.warning("[MIC] selected device unavailable, fallback to: %s", device["name"])
            self.logger.info("[MIC] selected device: %s (%s)", device["name"], device_index)

            audio = pyaudio.PyAudio()
            if self._stop_event.is_set():
                return
            stream, rate, frames = open_input_stream(audio, pyaudio, device_index, self.sample_rate)
            recognizer = KaldiRecognizer(model, rate)
            stream.start_stream()
            self.logger.info("[MIC] stream opened: rate=%s frames=%s", rate, frames)

            last_partial = ""
            while not self._stop_event.is_set():
                data = stream.read(frames, exception_on_overflow=False)
                self._on_level(calculate_level(data))
                if recognizer.AcceptWaveform(data):
                    answer = json.loads(recognizer.Result())
                    text = answer.get("text", "").strip()
                    if text:
                        self.logger.info("[VOSK] final: %s", text)
                        self._on_final(text)
                    last_partial = ""
                else:
                    partial = json.loads(recognizer.PartialResult()).get("partial", "").strip()
                    if partial and partial != last_partial:
                        last_partial = partial
                        self.logger.info("[VOSK] partial: %s", partial)
                        self._on_partial(partial)
                time.sleep(0.01)
        except Exception as exc:
            self.logger.exception("[VOSK] engine failed")
            self._on_error(str(exc))
        finally:
            self._on_level(0.0)
            try:
                if stream is not None:
                    if stream.is_active():
                        stream.stop_stream()
                    stream.close()
            except Exception as exc:
                self.logger.warning("cannot close audio stream: %s", exc)
            try:
                if audio is not None:
                    audio.terminate()
            except Exception as exc:
                self.logger.warning("cannot terminate PyAudio: %s", exc)
            self._running = False
            self.logger.info("[MIC] stream stopped")
