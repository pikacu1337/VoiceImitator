"""Окно как в ZapretLauncher (WPF WindowChrome: CaptionHeight=0, ResizeBorderThickness=6).

Окно без системного заголовка, но с системной рамкой растягивания (WS_THICKFRAME):
в Windows 10/11 она невидима и лежит снаружи видимого края — как у обычных окон.
Значит растягивание, курсоры у края, Aero Snap, Win+стрелки и разворачивание — всё
системное. Перенос — тоже: нажатие на полосе заголовка отдаётся Windows
(WM_NCLBUTTONDOWN + HTCAPTION). Тень и скруглённые углы рисует Windows 11.

Верхний край такой рамки Windows рисует цветом заголовка — красим его в цвет верха
фона (set_top_color), и он сливается с окном.

Сейчас этим окном пользуется только мастер установки (фиксированного размера);
окно программы — на Qt (app/qtui).

Как в лаунчере: окно не меньше MIN_SIZE, открывается таким, каким его оставили,
в развёрнутом виде не вылезает за экран (это делает сама рамка).
"""

import ctypes
import tkinter as tk
from ctypes import wintypes

MIN_SIZE = (1060, 720)      # MinWidth × MinHeight лаунчера
DEFAULT_SIZE = (1152, 826)  # Width × Height лаунчера

WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2
SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 3, 6, 9
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_THICKFRAME = 0x00040000
WS_MAXIMIZEBOX = 0x00010000
WS_MINIMIZEBOX = 0x00020000
WS_SYSMENU = 0x00080000
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
SWP_FRAMECHANGED = 0x0020
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_CAPTION_COLOR = 35
DWMWCP_ROUND = 2
VK_LBUTTON = 0x01

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
_GetLong = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
_SetLong = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
_GetLong.restype = ctypes.c_ssize_t
_SetLong.restype = ctypes.c_ssize_t
_SetLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def _dwm_int(hwnd, attr, value):
    v = ctypes.c_int(value)
    try:
        dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


class Chrome:
    def __init__(self, root: tk.Tk, min_size=MIN_SIZE):
        self.root = root
        self.min_size = min_size
        self.resizable = True     # у мастера установки окно фиксированного размера
        self.resizing = False     # пока тянут край, поверх окна превью
        self._hwnd = None
        self._zoomed = False
        self._last_size = None
        self._top_color = None
        self.on_resize_start = lambda: None
        self.on_resize_frame = lambda: None
        self.on_resize_end = lambda: None
        self.on_state = lambda maximized: None
        self.on_close = root.destroy
        root.overrideredirect(True)
        root.attributes("-alpha", 0.0)   # пока стили не выставлены — окно невидимо
        root.after(0, self._setup)
        root.bind("<Configure>", self._on_configure, add="+")
        root.bind("<Map>", self._on_map, add="+")

    # ---------- окно ----------

    @property
    def hwnd(self) -> int:
        return self._hwnd or user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()

    @property
    def maximized(self) -> bool:
        return bool(user32.IsZoomed(self.hwnd))

    def scale(self) -> float:
        try:
            return user32.GetDpiForWindow(self.hwnd) / 96
        except Exception:
            return 1.0

    def _setup(self):
        self.root.update_idletasks()
        self._hwnd = hwnd = user32.GetParent(self.root.winfo_id())
        ex = _GetLong(hwnd, GWL_EXSTYLE)
        _SetLong(hwnd, GWL_EXSTYLE, (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)   # на панели задач
        st = _GetLong(hwnd, GWL_STYLE) | WS_MINIMIZEBOX | WS_SYSMENU
        if self.resizable:
            st |= WS_THICKFRAME | WS_MAXIMIZEBOX   # невидимая системная рамка растягивания
        _SetLong(hwnd, GWL_STYLE, st)
        _dwm_int(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
        _dwm_int(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
        if self._top_color is not None:
            _dwm_int(hwnd, DWMWA_CAPTION_COLOR, self._top_color)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | SWP_FRAMECHANGED)
        s = self.scale()
        tk.Wm.wm_minsize(self.root, round(self.min_size[0] * s), round(self.min_size[1] * s))
        if self._pending_rect:
            self._place(*self._pending_rect)
        self.root.withdraw()             # чтобы панель задач заметила новое окно
        self.root.after(10, self._show)

    def _show(self):
        self.root.deiconify()
        self.root.after(30, self._opaque)

    def _opaque(self):
        """Окно было прозрачным на время настройки; прозрачность делает его «слоёным»
        (WS_EX_LAYERED), а такие окна дёргаются при переносе — снимаем флаг совсем."""
        self.root.attributes("-alpha", 1.0)
        ex = _GetLong(self.hwnd, GWL_EXSTYLE)
        if ex & WS_EX_LAYERED:
            _SetLong(self.hwnd, GWL_EXSTYLE, ex & ~WS_EX_LAYERED)
            user32.SetWindowPos(self.hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | SWP_FRAMECHANGED)

    def _on_map(self, _e=None):
        # после разворачивания с панели задач Tk иногда снимает флаг — возвращаем
        if not self.root.overrideredirect():
            self.root.overrideredirect(True)

    _pending_rect = None

    def _frame(self) -> tuple[int, int, int, int]:
        """Толщина невидимой рамки слева, сверху, справа, снизу — разница окна и клиентской области."""
        r, c, pt = wintypes.RECT(), wintypes.RECT(), wintypes.POINT(0, 0)
        user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        user32.GetClientRect(self.hwnd, ctypes.byref(c))
        user32.ClientToScreen(self.hwnd, ctypes.byref(pt))
        return pt.x - r.left, pt.y - r.top, r.right - pt.x - c.right, r.bottom - pt.y - c.bottom

    def _work_area(self, hwnd=None):
        mon = user32.MonitorFromWindow(hwnd or self.hwnd, 2)
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        user32.GetMonitorInfoW(mon, ctypes.byref(info))
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom

    def _place(self, x, y, w, h):
        """Клиентская область w×h в точке x,y — рамка добавляется снаружи."""
        fl, ft, fr, fb = self._frame()
        user32.SetWindowPos(self.hwnd, 0, x - fl, y - ft, w + fl + fr, h + ft + fb, 0x0004 | 0x0010)

    def center(self, w: int, h: int):
        """Размер в пикселях экрана; не больше рабочей области минус 20 (как в лаунчере)."""
        left, top, right, bottom = self._work_area(user32.GetDesktopWindow())
        w, h = min(w, right - left - 20), min(h, bottom - top - 20)
        rect = (left + (right - left - w) // 2, top + (bottom - top - h) // 2, w, h)
        if self._hwnd:
            self._place(*rect)
        else:
            self._pending_rect = rect
            tk.Wm.wm_geometry(self.root, f"{w}x{h}+{rect[0]}+{rect[1]}")

    def size(self) -> tuple[int, int]:
        """Размер видимого окна (клиентской области) — чтобы открыть его таким же в следующий раз."""
        c = wintypes.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(c))
        return c.right, c.bottom

    def set_top_color(self, hex_color: str):
        """Верхний край рамки Windows рисует цветом заголовка — делаем его цветом верха фона."""
        h = hex_color.lstrip("#")
        colorref = int(h[4:6], 16) << 16 | int(h[2:4], 16) << 8 | int(h[0:2], 16)
        if colorref != self._top_color:
            self._top_color = colorref
            if self._hwnd:
                _dwm_int(self._hwnd, DWMWA_CAPTION_COLOR, colorref)

    def minimize(self):
        user32.ShowWindow(self.hwnd, SW_MINIMIZE)

    def toggle_maximize(self):
        if not self.resizable:
            return
        self.on_resize_start()   # превью закрывает перекладку интерфейса
        user32.ShowWindow(self.hwnd, SW_RESTORE if self.maximized else SW_MAXIMIZE)
        self.root.update_idletasks()
        self.on_resize_frame()
        self.root.after(60, self.on_resize_end)

    def close(self):
        self.on_close()

    # ---------- изменение размера ----------

    def _on_configure(self, e):
        if e.widget is not self.root:
            return
        zoomed = self.maximized
        if zoomed != self._zoomed:
            self._zoomed = zoomed
            self.on_state(zoomed)
        size = (e.width, e.height)
        if size == self._last_size:
            return
        first = self._last_size is None
        self._last_size = size
        # Размер меняется, пока зажата кнопка мыши, — значит тянут край системной рамки:
        # ставим превью (снимок ещё со старой раскладкой — Tk её больше не трогает).
        if not first and not self.resizing and user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
            self.resizing = True
            self.on_resize_start()
            self.root.after(15, self._tick)
        elif self.resizing:
            self.on_resize_frame()

    def _tick(self):
        """Пока край тянут — ждём; отпустили кнопку — собрать интерфейс начисто."""
        if user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
            self.root.after(15, self._tick)
            return
        self.resizing = False
        self.on_resize_end()

    # ---------- заголовок ----------

    def attach(self, widget, drag: bool = True, drag_height: int | None = None):
        """Виджет — «заголовок»: тянет окно (системно) и разворачивает его двойным щелчком."""
        if not drag:
            return   # края — системная рамка, ловить их не нужно
        widget.bind("<ButtonPress-1>", lambda e: self._press(e, drag_height), add="+")
        widget.bind("<Double-Button-1>", lambda e: self._dbl(e, drag_height), add="+")

    def _in_drag_zone(self, e, drag_height):
        return drag_height is None or e.y_root - self.root.winfo_rooty() < drag_height

    def _press(self, e, drag_height):
        if self._in_drag_zone(e, drag_height):
            # перенос — системный: с Aero Snap и восстановлением из развёрнутого
            user32.ReleaseCapture()
            user32.PostMessageW(self.hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)

    def _dbl(self, e, drag_height):
        if self._in_drag_zone(e, drag_height):
            self.toggle_maximize()
