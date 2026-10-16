"""Сборка программы в один .exe через PyInstaller.

    .venv\\Scripts\\python -m pip install pyinstaller
    .venv\\Scripts\\python tools\\build_exe.py

Готовый файл появится в dist\\VoiceImitator.exe.
Голосовая модель (~40 МБ) НЕ вшивается — при первом запуске программа скачает её сама.
Бот (папка bot) в сборку не входит: он остаётся у тебя как управляющая часть.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
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
    subprocess.check_call(args, cwd=ROOT)
    print("\nГотово: dist\\VoiceImitator.exe")


if __name__ == "__main__":
    main()
