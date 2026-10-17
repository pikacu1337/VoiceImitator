"""Сборка через PyInstaller: программа и установщик, оба — одним файлом в корне проекта.

    .venv\\Scripts\\python -m pip install pyinstaller
    .venv\\Scripts\\python tools\\build_exe.py            # оба
    .venv\\Scripts\\python tools\\build_exe.py app        # только VoiceImitator.exe
    .venv\\Scripts\\python tools\\build_exe.py setup      # только VoiceImitatorSetup.exe

VoiceImitator.exe (внутри PyTorch и Qt) — сама программа; голосовая модель (~40 МБ)
не вшивается, программа скачает её при первом запуске.
VoiceImitatorSetup.exe (небольшой) — мастер установки: скачивает последнюю версию
программы с GitHub, ставит её, создаёт ярлыки и запись в «Приложениях».
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "app" / "assets"

TARGETS = {
    "app": dict(
        name="VoiceImitator",
        entry=ROOT / "app" / "__main__.py",
        extra=["--collect-data", "num2words", "--collect-submodules", "num2words",
               "--hidden-import", "app.qtui.main",
               # оригинальный пакет VB-CABLE и картинка фона — как app/assets (без изменений)
               "--add-data", f"{ASSETS}{os.pathsep}app/assets",
               # интерфейс — QML-файлы рядом с программой
               "--add-data", f"{ROOT / 'app' / 'qtui' / 'qml'}{os.pathsep}app/qtui/qml",
               # окно — на Qt; Tk нужен только установщику
               *[x for m in ("tkinter", "customtkinter") for x in ("--exclude-module", m)]],
    ),
    "setup": dict(
        name="VoiceImitatorSetup",
        entry=ROOT / "app" / "setup_main.py",
        # установщику не нужны ни голос, ни звук — без них он в разы меньше
        extra=["--collect-all", "customtkinter",
               "--add-data", f"{ASSETS / 'Images'}{os.pathsep}app/assets/Images",
               *[x for m in ("PySide6", "shiboken6", "torch", "pedalboard", "sounddevice", "num2words",
                             "_sounddevice_data", "app.qtui", "app.tts", "app.audio", "app.cable_install")
                 for x in ("--exclude-module", m)]],
    ),
}


def build(target: str) -> None:
    t = TARGETS[target]
    work = Path(tempfile.mkdtemp(prefix="voiceimitator_build_"))  # build/ и .spec — не в папке проекта
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--workpath", str(work / "build"),
        "--specpath", str(work),
        "--distpath", str(ROOT),  # exe — прямо в корне проекта
        "--name", t["name"],
        "--windowed",
        "--onefile",
        *t["extra"],
        str(t["entry"]),
    ]
    print("PyInstaller:", " ".join(args))
    try:
        subprocess.check_call(args, cwd=ROOT)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"\nГотово: {t['name']}.exe")


def main() -> None:
    # консоль Windows (и раннер GitHub) может быть в cp1252 — без этого русский вывод падает
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    targets = sys.argv[1:] or list(TARGETS)
    for target in targets:
        build(target)


if __name__ == "__main__":
    main()
