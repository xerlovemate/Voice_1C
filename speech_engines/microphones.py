from __future__ import annotations

import math
import struct
import time
from collections.abc import Callable


LevelCallback = Callable[[float], None]


def _import_pyaudio():
    import pyaudio

    return pyaudio


def list_microphones() -> list[dict]:
    pyaudio = _import_pyaudio()
    audio = pyaudio.PyAudio()
    devices: list[dict] = []
    default_index = None
    try:
        try:
            default_index = int(audio.get_default_input_device_info().get("index"))
        except Exception:
            default_index = None

        for index in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(index)
            channels = int(info.get("maxInputChannels") or 0)
            if channels <= 0:
                continue
            devices.append(
                {
                    "id": int(info.get("index", index)),
                    "name": str(info.get("name") or f"Input device {index}"),
                    "channels": channels,
                    "default": int(info.get("index", index)) == default_index,
                    "sample_rate": int(float(info.get("defaultSampleRate") or 16000)),
                }
            )
    finally:
        audio.terminate()
    return devices


def default_microphone_id() -> int | None:
    devices = list_microphones()
    for device in devices:
        if device.get("default"):
            return int(device["id"])
    if devices:
        return int(devices[0]["id"])
    return None


def normalize_device_id(device_id: int | str | None) -> int | None:
    if device_id in (None, "", "default", "auto"):
        return None
    try:
        return int(device_id)
    except (TypeError, ValueError):
        return None


def select_device_or_default(device_id: int | str | None) -> tuple[int | None, dict | None, bool]:
    requested = normalize_device_id(device_id)
    devices = list_microphones()
    if requested is not None:
        for device in devices:
            if int(device["id"]) == requested:
                return requested, device, False

    for device in devices:
        if device.get("default"):
            return int(device["id"]), device, requested is not None

    if devices:
        return int(devices[0]["id"]), devices[0], requested is not None
    return None, None, requested is not None


def calculate_level(data: bytes) -> float:
    if not data:
        return 0.0
    sample_count = len(data) // 2
    if sample_count <= 0:
        return 0.0
    samples = struct.unpack(f"<{sample_count}h", data[: sample_count * 2])
    if not samples:
        return 0.0
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    return max(0.0, min(1.0, rms / 32768.0 * 6.0))


def open_input_stream(audio, pyaudio, device_index: int | None, preferred_rate: int) -> tuple[object, int, int]:
    rates = []
    for rate in (preferred_rate, 16000, 44100, 48000, 8000):
        if rate and rate not in rates:
            rates.append(int(rate))

    last_error: Exception | None = None
    for rate in rates:
        frames = max(1024, int(rate / 10))
        try:
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=frames,
            )
            return stream, rate, frames
        except Exception as exc:
            last_error = exc

    if last_error:
        raise last_error
    raise RuntimeError("Cannot open input stream")


def test_microphone_level(
    device_id: int | str | None,
    duration_seconds: float,
    on_level: LevelCallback,
    preferred_rate: int = 16000,
) -> dict:
    pyaudio = _import_pyaudio()
    device_index, device, fallback = select_device_or_default(device_id)
    if device is None:
        raise RuntimeError("Микрофоны не найдены")

    audio = pyaudio.PyAudio()
    stream = None
    peak = 0.0
    try:
        stream, rate, frames = open_input_stream(audio, pyaudio, device_index, preferred_rate)
        stream.start_stream()
        deadline = time.monotonic() + max(duration_seconds, 0.1)
        while time.monotonic() < deadline:
            data = stream.read(frames, exception_on_overflow=False)
            level = calculate_level(data)
            peak = max(peak, level)
            on_level(level)
        return {
            "ok": True,
            "device_id": device_index,
            "device_name": device["name"],
            "fallback": fallback,
            "sample_rate": rate,
            "peak": round(peak, 3),
        }
    finally:
        on_level(0.0)
        if stream is not None:
            try:
                if stream.is_active():
                    stream.stop_stream()
                stream.close()
            except Exception:
                pass
        audio.terminate()
