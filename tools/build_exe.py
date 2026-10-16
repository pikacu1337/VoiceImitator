"""Сборка программы в один .exe через PyInstaller.

    .venv\\Scripts\\python -m pip install pyinstaller
    .venv\\Scripts\\python tools\\build_exe.py

Готовый VoiceImitator.exe появится прямо в корне проекта.
Голосовая модель (~40 МБ) НЕ вшивается — при первом запуске программа скачает её сама.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="voiceimitator_build_"))  # build/ и .spec — не в папке проекта
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--workpath", str(work / "build"),
        "--specpath", str(work),
        "--distpath", str(ROOT),  # exe — прямо в корне проекта
        "--name", "VoiceImitator",
        "--windowed",
        "--onefile",
        "--collect-all", "customtkinter",
        "--collect-data", "num2words",
        "--collect-submodules", "num2words",
        "--hidden-import", "app.gui",
        # Оригинальный пакет VB-CABLE кладётся рядом как app/assets (без изменений)
        "--add-data", f"{ROOT / 'app' / 'assets'}{os.pathsep}app/assets",
        str(ROOT / "app" / "__main__.py"),
    ]
    print("PyInstaller:", " ".join(args))
    try:
        subprocess.check_call(args, cwd=ROOT)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("\nГотово: VoiceImitator.exe")


if __name__ == "__main__":
    main()
