"""Установка виртуального кабеля VB-CABLE.

VB-CABLE © V.Burel (www.vb-cable.com) — бесплатный donationware. Его лицензия
разрешает распространять ОРИГИНАЛЬНЫЙ пакет без изменений, но запрещает молча
встраивать его в установочную процедуру другой программы без согласия автора.
Поэтому программа не ставит драйвер молча: она распаковывает оригинальный пакет
и открывает штатный установщик VB-CABLE, а пользователь сам жмёт «Install Driver».
После установки программа находит устройство и выбирает его.
"""

import ctypes
import os
import sys
import time
import zipfile
from pathlib import Path

from app import audio
from app.paths import DATA_DIR

ASSET_NAME = "VBCABLE_Driver_Pack.zip"
SETUP_EXE = "VBCABLE_Setup_x64.exe"
EXTRACT_DIR = DATA_DIR / "vbcable"

CREDIT = "VB-CABLE © V.Burel — бесплатный, www.vb-cable.com (donationware)"


def assets_dir() -> Path:
    """app/assets — и из исходников, и внутри собранного .exe (PyInstaller кладёт их в app/assets)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app" / "assets"
    return Path(__file__).resolve().parent / "assets"


def bundled_pack() -> Path | None:
    p = assets_dir() / ASSET_NAME
    return p if p.exists() else None


def cable_present() -> bool:
    try:
        return audio.find_cable(audio.list_devices("output")) is not None
    except Exception:
        return False


def _extract() -> Path | None:
    """Распаковывает ОРИГИНАЛЬНЫЙ пакет без изменений, возвращает путь к установщику."""
    pack = bundled_pack()
    if not pack:
        return None
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(pack) as z:
            z.extractall(EXTRACT_DIR)
    except Exception:
        return None
    return next(iter(EXTRACT_DIR.rglob(SETUP_EXE)), None)


def open_installer() -> tuple[bool, str]:
    """Открывает штатный установщик VB-CABLE (его окно) с правами администратора.
    Пользователь сам нажимает «Install Driver». Возвращает (запущен ли, сообщение)."""
    setup = _extract()
    if setup is None:
        try:
            os.startfile(EXTRACT_DIR)  # хотя бы откроем папку, если установщик не нашёлся
        except Exception:
            pass
        return False, "Не удалось подготовить установщик VB-CABLE."
    # "runas" → один запрос UAC, дальше открывается родное окно VB-CABLE с кнопкой Install Driver
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(setup), None, str(setup.parent), 1)
    if int(rc) <= 32:
        try:
            os.startfile(setup.parent)  # UAC отклонён — покажем папку, пусть запустят вручную
        except Exception:
            pass
        return False, "Запрос прав отклонён. Открыл папку — запусти VBCABLE_Setup_x64.exe от администратора."
    return True, "Открылось окно VB-CABLE. Нажми «Install Driver», дождись конца установки."


def wait_for_cable(timeout: float = 120.0) -> bool:
    """Ждёт появления устройства кабеля после установки."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        audio.rescan_devices()
        if cable_present():
            return True
        time.sleep(2.0)
    return False
