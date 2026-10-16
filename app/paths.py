import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "VoiceImitator"
MODELS_DIR = DATA_DIR / "models"
SETTINGS_PATH = DATA_DIR / "settings.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
