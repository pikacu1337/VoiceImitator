"""«Стоп-кадр» на время растягивания окна.

Tk перекладывает интерфейс медленнее, чем мышь тянет край: между шагами видны
серые заливки, съехавшие панели и шлейфы от кнопок. Поэтому, когда край схвачен,
окно снимает само себя (PrintWindow) и кладёт поверх всего холст: свежий фон
нужного размера + интерфейс со снимка. Настоящая перекладка идёт под ним невидимо;
когда край отпущен, стекло собирается начисто и стоп-кадр убирается."""

import ctypes
import tkinter as tk
from ctypes import wintypes

import numpy as np
from PIL import Image, ImageFilter, ImageTk

from app import backdrop
from app.glass import scale_of

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
PW_CLIENTONLY = 1
PW_RENDERFULLCONTENT = 2


class _BIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def capture(hwnd: int) -> Image.Image | None:
    """Снимок содержимого окна (без невидимой системной рамки), даже если его что-то перекрывает."""
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    w, h = r.right, r.bottom
    if w <= 0 or h <= 0:
        return None
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    try:
        if not user32.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT | PW_CLIENTONLY):
            return None
        bi = _BIH(ctypes.sizeof(_BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    finally:
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(hwnd, hdc)


class Freeze:
    def __init__(self, app):
        self.app = app
        self.active = False
        self.canvas = None
        self._item = None
        self._ref = None
        self._snap = None
        self._mask = None
        self._job = None

    def start(self):
        view = self.app.view
        snap = capture(self.app.chrome.hwnd)
        base = getattr(view, "_base", None)
        if snap is None or base is None:
            return
        if base.size != snap.size:
            # окно уже чуть подросло, а интерфейс на снимке ещё в старой раскладке —
            # берём из снимка ровно старую область (у верхнего левого угла)
            w, h = min(snap.width, base.width), min(snap.height, base.height)
            snap, base = snap.crop((0, 0, w, h)), base.crop((0, 0, w, h))
        # Интерфейс — всё, чем снимок отличается от голого фона: панели, текст, кнопки.
        diff = np.abs(np.asarray(snap, np.int16) - np.asarray(base, np.int16)).max(axis=2)
        keep = diff > 6
        edge = 4   # обводку окна, которую рисует Windows, со снимка не берём — иначе останется рамка
        keep[:edge, :] = keep[-edge:, :] = False
        keep[:, :edge] = keep[:, -edge:] = False
        mask = Image.fromarray((keep * 255).astype(np.uint8), "L").filter(ImageFilter.MaxFilter(3))
        self._snap, self._mask = snap, mask
        avg = "#%02x%02x%02x" % base.resize((1, 1), Image.BOX).getpixel((0, 0))[:3]
        if self.canvas is None:
            self.canvas = tk.Canvas(self.app, bd=0, highlightthickness=0)
            self._item = self.canvas.create_image(0, 0, anchor="nw")
        self.canvas.configure(bg=avg)   # если окно рванули быстрее кадра — виден тон фона, не чёрный
        self.active = True
        self._draw()
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        # у Canvas метод lift() поднимает элементы рисунка, а не сам виджет — зовём Tk напрямую
        self.canvas.tk.call("raise", self.canvas._w)

    def frame(self):
        """Окно поменяло размер — перерисовать стоп-кадр (не чаще, чем успевает экран)."""
        if self.active and self._job is None:
            self._job = self.app.after_idle(self._draw)

    def _draw(self):
        self._job = None
        if not self.active:
            return
        w, h = self.app.winfo_width(), self.app.winfo_height()
        if w < 10 or h < 10:
            return
        s = self.app.settings
        sc = scale_of(self.app)
        # Фон — в половинном размере (быстро) и растянут; обрезка та же, что у настоящего фона,
        # поэтому при отпускании края картинка не прыгает. Если окно рванули быстрее кадра,
        # в новой полосе виден средний тон фона (цвет самого холста).
        bg = backdrop.render(max(2, w // 2), max(2, h // 2), s["bg_mode"], s["bg_custom"], s["bg_brightness"],
                             s["bg_blur"], sc / 2).resize((w, h), Image.BILINEAR)
        bg.paste(self._snap, (0, 0), self._mask)
        self._ref = ImageTk.PhotoImage(bg)
        self.canvas.itemconfigure(self._item, image=self._ref)

    def end(self):
        if not self.active:
            return
        self.active = False
        if self._job:
            self.app.after_cancel(self._job)
            self._job = None
        view = self.app.view
        if view is not None:
            if view._job:
                view.after_cancel(view._job)
                view._job = None
            view.recompose()   # собрать стекло начисто, пока стоп-кадр ещё закрывает окно
        self.app.update_idletasks()
        if self.canvas is not None:
            self.canvas.place_forget()
        self._snap = self._mask = self._ref = None
