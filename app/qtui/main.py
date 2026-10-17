"""Запуск окна на Qt Quick: интерфейс — app/qtui/qml, работа — app/qtui/backend.py."""

import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from app.qtui.backend import Backend

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2
DEFAULT_SIZE = (1152, 826)
MIN_SIZE = (1060, 720)


def qml_dir() -> Path:
    """app/qtui/qml — и из исходников, и внутри собранного .exe."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app" / "qtui" / "qml"
    return Path(__file__).resolve().parent / "qml"


def icon_path() -> Path:
    base = Path(sys._MEIPASS) / "app" if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return base / "assets" / "app.ico"


def _dwm(hwnd: int):
    """Тёмная рамка и скруглённые углы Windows 11 (с тенью) для окна без системного заголовка."""
    for attr, value in ((DWMWA_USE_IMMERSIVE_DARK_MODE, 1), (DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)):
        v = ctypes.c_int(value)
        try:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
        except Exception:
            pass


def run():
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QApplication(sys.argv)
    app.setApplicationName("VoiceImitator")
    app.setFont(QFont("Segoe UI Variable Text", 10))
    if icon_path().exists():
        app.setWindowIcon(QIcon(str(icon_path())))

    backend = Backend()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(qml_dir() / "Main.qml")))
    if not engine.rootObjects():
        sys.exit(1)
    win = engine.rootObjects()[0]

    # открывается таким, каким его оставили (как в лаунчере), но не меньше минимума и не больше экрана
    w, h = backend.s.get("window") or DEFAULT_SIZE
    screen = win.screen().availableGeometry()
    w = min(max(w, MIN_SIZE[0]), screen.width() - 20)
    h = min(max(h, MIN_SIZE[1]), screen.height() - 20)
    win.setGeometry(screen.x() + (screen.width() - w) // 2, screen.y() + (screen.height() - h) // 2, w, h)
    _dwm(int(win.winId()))
    win.show()
    sys.exit(app.exec())
