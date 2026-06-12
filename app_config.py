from __future__ import annotations

from copy import deepcopy

__version__ = "1.1.0"

DEFAULT_CONFIG = {
    "app_name": "Voice 1C",
    "version": __version__,
    "github_owner": "xerlovemate",
    "github_repo": "Voice_1C",
    "release_asset_name": "Voice1CSetup.exe",
    "update_check_on_start": True,
    "speech_engine": "auto",
    "chrome_mode": "headless",
    "chrome_bridge_port": 0,
    "input_method": "clipboard",
    "selected_microphone_id": None,
    "insert_delay_ms": 300,
    "restore_clipboard": True,
    "restore_clipboard_delay_ms": 250,
    "confirm_dangerous_commands": True,
    "mode": "1c",
    "sound_enabled": True,
    "large_ui_mode": True,
}


def default_config() -> dict:
    return deepcopy(DEFAULT_CONFIG)
