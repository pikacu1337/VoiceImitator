"""Окно без системного заголовка, как в ZapretLauncher: вкладки и кнопки окна
живут в собственной полосе сверху. Окно остаётся на панели задач, сворачивается,
разворачивается, перетаскивается за заголовок и меняет размер за края; углы
скругляет сама Windows 11 (DWM), она же рисует тень."""

import ctypes
import tkinter as tk
from ctypes import wintypes

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
WS_MINIMIZEBOX = 0x00020000
SW_MINIMIZE = 6
DWMWA_NCRENDERING_POLICY = 2
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2
EDGE = 6  # ширина зоны изменения размера у края окна, px

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
_GetLong = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
_SetLong = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
_GetLong.restype = ctypes.c_ssize_t
_SetLong.restype = ctypes.c_ssize_t
_SetLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]


class MARGINS(ctypes.Structure):
    _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


CURSORS = {"n": "size_ns", "s": "size_ns", "e": "size_we", "w": "size_we",
           "ne": "size_ne_sw", "sw": "size_ne_sw", "nw": "size_nw_se", "se": "size_nw_se"}


class Chrome:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.maximized = False
        self._normal = None
        self._drag = None
        self._resize = None
        self.on_state = lambda maximized: None
        self.on_close = root.destroy
        root.overrideredirect(True)
        root.after(10, self._setup)
        root.bind("<Map>", self._on_map, add="+")

    # ---------- окно ----------

    @property
    def hwnd(self) -> int:
        return user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()

    def _setup(self):
        hwnd = self.hwnd
        ex = _GetLong(hwnd, GWL_EXSTYLE)
        _SetLong(hwnd, GWL_EXSTYLE, (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)  # на панели задач
        st = _GetLong(hwnd, GWL_STYLE)
        _SetLong(hwnd, GWL_STYLE, st | WS_MINIMIZEBOX)                          # сворачивание
        try:
            pref = ctypes.c_int(DWMWCP_ROUND)
            dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                         ctypes.byref(pref), ctypes.sizeof(pref))
            policy = ctypes.c_int(2)
            dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_NCRENDERING_POLICY,
                                         ctypes.byref(policy), ctypes.sizeof(policy))
            dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(1, 1, 1, 1)))  # тень
        except Exception:
            pass
        self.root.withdraw()
        self.root.after(10, self.root.deiconify)

    def _on_map(self, _e=None):
        # после разворачивания с панели задач Tk иногда снимает флаг — возвращаем
        if not self.root.overrideredirect():
            self.root.overrideredirect(True)

    def center(self, w: int, h: int):
        left, top, right, bottom = self._work_area()
        x = left + (right - left - w) // 2
        y = top + (bottom - top - h) // 2
        tk.Wm.wm_geometry(self.root, f"{w}x{h}+{max(left, x)}+{max(top, y)}")

    def _work_area(self):
        mon = user32.MonitorFromWindow(self.hwnd, 2)
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        user32.GetMonitorInfoW(mon, ctypes.byref(info))
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom

    def minimize(self):
        user32.ShowWindow(self.hwnd, SW_MINIMIZE)

    def toggle_maximize(self):
        if self.maximized:
            tk.Wm.wm_geometry(self.root, self._normal)
            self.maximized = False
        else:
            self._normal = tk.Wm.wm_geometry(self.root)
            left, top, right, bottom = self._work_area()
            tk.Wm.wm_geometry(self.root, f"{right - left}x{bottom - top}+{left}+{top}")
            self.maximized = True
        self.on_state(self.maximized)

    def close(self):
        self.on_close()

    # ---------- перетаскивание и изменение размера ----------

    def attach(self, widget, drag: bool = True, drag_height: int | None = None):
        """Виджет становится «заголовком» (тянет окно) и/или краем (меняет размер)."""
        widget.bind("<Motion>", lambda e: self._hover(widget, e), add="+")
        widget.bind("<ButtonPress-1>", lambda e: self._press(e, drag, drag_height), add="+")
        widget.bind("<B1-Motion>", self._motion, add="+")
        widget.bind("<ButtonRelease-1>", self._release, add="+")
        if drag:
            widget.bind("<Double-Button-1>", lambda e: self._dbl(e, drag_height), add="+")

    def _edge(self, e):
        if self.maximized:
            return ""
        x, y = e.x_root - self.root.winfo_rootx(), e.y_root - self.root.winfo_rooty()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        side = ("n" if y < EDGE else "s" if y >= h - EDGE else "") + \
               ("w" if x < EDGE else "e" if x >= w - EDGE else "")
        return side

    def _hover(self, widget, e):
        if self._resize or self._drag:
            return
        side = self._edge(e)
        widget.configure(cursor=CURSORS.get(side, ""))

    def _in_drag_zone(self, e, drag_height):
        if drag_height is None:
            return True
        return e.y_root - self.root.winfo_rooty() < drag_height

    def _press(self, e, drag, drag_height):
        side = self._edge(e)
        if side:
            self._resize = (side, e.x_root, e.y_root, self.root.winfo_rootx(), self.root.winfo_rooty(),
                            self.root.winfo_width(), self.root.winfo_height())
        elif drag and self._in_drag_zone(e, drag_height):
            if self.maximized:  # тянем развёрнутое окно — сначала вернуть обычный размер под курсор
                nw = int(self._normal.split("x")[0])
                self.toggle_maximize()
                tk.Wm.wm_geometry(self.root, f"+{e.x_root - nw // 2}+{e.y_root - 20}")
                self.root.update_idletasks()
            self._drag = (e.x_root - self.root.winfo_rootx(), e.y_root - self.root.winfo_rooty())

    def _motion(self, e):
        if self._drag:
            dx, dy = self._drag
            tk.Wm.wm_geometry(self.root, f"+{e.x_root - dx}+{e.y_root - dy}")
        elif self._resize:
            side, sx, sy, x, y, w, h = self._resize
            mw, mh = tk.Wm.wm_minsize(self.root)  # без пересчёта масштаба CTk — в пикселях экрана
            ddx, ddy = e.x_root - sx, e.y_root - sy
            if "e" in side:
                w = max(mw, w + ddx)
            if "s" in side:
                h = max(mh, h + ddy)
            if "w" in side:
                nw = max(mw, w - ddx)
                x, w = x + (w - nw), nw
            if "n" in side:
                nh = max(mh, h - ddy)
                y, h = y + (h - nh), nh
            tk.Wm.wm_geometry(self.root, f"{w}x{h}+{x}+{y}")

    def _release(self, _e):
        self._drag = None
        self._resize = None

    def _dbl(self, e, drag_height):
        if not self._edge(e) and self._in_drag_zone(e, drag_height):
            self.toggle_maximize()
