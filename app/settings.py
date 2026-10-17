"""Настройки программы: %APPDATA%\\VoiceImitator\\settings.json."""

import json

from app import theme
from app.paths import SETTINGS_PATH

HISTORY_SIZE = 30

DEFAULT_SETTINGS = {
    "voice": "Евгений (мужской)",
    "speed": 1.08,
    "pitch": -2.0,
    "volume": 1.0,
    "accent": theme.DEFAULT_ACCENT,
    "accent_hue": None,
    "bg_mode": "picture",     # picture / custom / sky
    "bg_custom": "",
    "bg_brightness": 50,      # яркость картинки-фона, %
    "bg_blur": 0,             # размытие картинки-фона, %
    "glass_blur": 60,         # размытие стекла, %
    "cable": "",
    "monitor_on": True,
    "monitor": "",
    "mic_on": False,
    "mic": "",
    "mic_volume": 1.0,
    "history": [],
    "window": None,           # [ширина, высота] обычного окна — открываться таким же
}


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULT_SETTINGS, **{k: v for k, v in data.items() if k in DEFAULT_SETTINGS}}


def save_settings(data: dict) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
