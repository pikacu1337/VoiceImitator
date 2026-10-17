"""Превью растягивания окна: панели подстраиваются под размер сразу, без рывков.

Tk перекладывает и перерисовывает ~100 виджетов на каждый шаг мыши — это 100–150 мс,
поэтому «живая» перекладка идёт рывками. Здесь, пока край тянут:
  - настоящий интерфейс замирает в прежнем размере (Tk ничего не перекладывает);
  - поверх окна — холст, на котором каждый кадр собирается одной картинкой:
    свежий фон под новый размер, стеклянные панели на новых местах и контролы,
    сдвинутые и растянутые так, как их расставит сетка Tk;
  - где окажется каждый виджет, считает модель сетки (Grid): прибавку ширины
    колонки делят по весам, виджет едет или тянется по своему sticky;
  - контролы берутся со снимка окна в виде «разницы с фоном» (снимок минус
    стекло под ним), поэтому на новом месте ложатся на новое стекло — без
    остатков старой картинки вокруг подписей.
Край отпустили — интерфейс перекладывается по-настоящему один раз, стекло
собирается начисто, и только потом холст убирается."""

import ctypes
import tkinter as tk
from ctypes import wintypes

import customtkinter as ctk
import numpy as np
from PIL import Image, ImageTk

from app.glass import EDGE_ALPHA, Clear, GlassPanel, GlassView, masks, scale_of

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
PW_CLIENTONLY = 1
PW_RENDERFULLCONTENT = 2
CAP = 24   # край контрола, который при растягивании не тянется (шеврон, полоса прокрутки, угол)


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


# ---------------------------------------------------------------- модель сетки

_ANCHOR_X = {"w": 0.0, "nw": 0.0, "sw": 0.0, "e": 1.0, "ne": 1.0, "se": 1.0}
_ANCHOR_Y = {"n": 0.0, "nw": 0.0, "ne": 0.0, "s": 1.0, "sw": 1.0, "se": 1.0}


class Node:
    """Виджет на снимке: где был, как его кладёт родитель и что внутри."""

    def __init__(self, widget, rect):
        self.widget = widget
        self.rect = rect                 # x, y, w, h относительно экрана
        self.kind = "leaf"               # leaf — рисуется; box — контейнер; panel — стеклянная панель
        self.children: list[Node] = []
        self.cols = self.rows = None     # (ширина, вес) колонок / строк сетки внутри
        self.manager = ""
        self.info = {}
        self.sprite = None               # int16: снимок минус стекло под ним
        self.center = False              # содержимое по центру (кнопка) — растягиваем поля по бокам
        self.scale = getattr(widget, "ng_stretch", "") == "scale"   # градиент — масштабировать целиком


def _float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _tracks(widget, count, axis):
    """Ширины колонок (или высоты строк) сетки внутри виджета и их веса."""
    out = []
    for i in range(count):
        conf = widget.grid_columnconfigure(i) if axis == 0 else widget.grid_rowconfigure(i)
        bbox = widget.grid_bbox(i, 0) if axis == 0 else widget.grid_bbox(0, i)
        out.append((bbox[2] if axis == 0 else bbox[3], int(_float(conf.get("weight"), 0))))
    return out


def _gather(widget, ox, oy) -> Node:
    x, y = widget.winfo_rootx() - ox, widget.winfo_rooty() - oy
    node = Node(widget, (x, y, widget.winfo_width(), widget.winfo_height()))
    node.manager = widget.winfo_manager()
    try:
        if node.manager == "grid":
            node.info = widget.grid_info()
        elif node.manager == "place":
            node.info = widget.place_info()
    except tk.TclError:
        pass
    if isinstance(widget, ctk.CTkBaseClass) or not isinstance(widget, (Clear, GlassView)):
        node.center = getattr(widget, "_anchor", "w") == "center" and isinstance(widget, ctk.CTkButton)
        return node                                     # контрол CTk — целиком, внутрь не смотрим
    kids = [c for c in widget.winfo_children() if c.winfo_ismapped()]
    if not kids:
        return node                                     # подпись, ползунок, история — рисуются сами
    node.kind = "panel" if isinstance(widget, GlassPanel) else "box"
    ncols, nrows = widget.grid_size()
    if ncols or nrows:
        node.cols = _tracks(widget, ncols, 0)
        node.rows = _tracks(widget, nrows, 1)
    node.children = [_gather(c, ox, oy) for c in kids]
    return node


def _growth(tracks, delta, hook=None, new_size=None):
    """На сколько вырастет каждая колонка: прибавку Tk делит по весам (uniform — так же)."""
    if hook is not None:
        return [n - o for n, (o, _) in zip(hook(new_size), tracks)]
    total = sum(w for _, w in tracks)
    return [delta * w / total if total else 0.0 for _, w in tracks]


def _layout(node, new, out):
    """new — новое место узла (x, y, w, h); раскладывает детей по модели их менеджера."""
    out[node] = new
    if not node.children:
        return
    x, y, w, h = node.rect
    nx, ny, nw, nh = new
    dw, dh = nw - w, nh - h
    hook = getattr(node.widget, "predict_columns", None)
    gx = _growth(node.cols, dw, hook, nw) if node.cols else []
    gy = _growth(node.rows, dh) if node.rows else []
    for ch in node.children:
        cx, cy, cw, chh = ch.rect
        ddx = ddy = ddw = ddh = 0.0
        if ch.manager == "grid" and gx:
            c, r = int(ch.info.get("column", 0)), int(ch.info.get("row", 0))
            cs, rs = int(ch.info.get("columnspan", 1)), int(ch.info.get("rowspan", 1))
            st = str(ch.info.get("sticky", ""))
            off, cell = sum(gx[:c]), sum(gx[c:c + cs])
            ddx, ddw = _stick(off, cell, "w" in st, "e" in st)
            off, cell = sum(gy[:r]), sum(gy[r:r + rs])
            ddy, ddh = _stick(off, cell, "n" in st, "s" in st)
        elif ch.manager == "place":
            rw, rh = _float(ch.info.get("relwidth")), _float(ch.info.get("relheight"))
            ddw, ddh = rw * dw, rh * dh
            anchor = str(ch.info.get("anchor", "nw"))
            ddx = _float(ch.info.get("relx")) * dw - _ANCHOR_X.get(anchor, 0.5) * ddw
            ddy = _float(ch.info.get("rely")) * dh - _ANCHOR_Y.get(anchor, 0.5) * ddh
        _layout(ch, (cx + (nx - x) + ddx, cy + (ny - y) + ddy, cw + ddw, chh + ddh), out)


def _stick(off, cell, lo, hi):
    """Сдвиг и прибавка размера виджета в ячейке, выросшей на cell (sticky по одной оси)."""
    if lo and hi:
        return off, cell
    if hi:
        return off + cell, 0.0
    if lo:
        return off, 0.0
    return off + cell / 2, 0.0


# ---------------------------------------------------------------- растягивание контролов

def _stretch(a, n, axis, center, cap):
    """Тянет картинку до длины n вдоль оси: края по cap не меняются, тянется середина
    (повтором пикселей у края). center — содержимое посередине остаётся посередине."""
    n0 = a.shape[axis]
    if n == n0 or n0 < 3 or n < 1:
        return a if n == n0 else np.take(a, np.linspace(0, n0 - 1, max(1, n)).astype(int), axis=axis)
    cap = max(1, min(cap, n0 // 3, n // 3 if n >= 3 else 1))

    def part(lo, hi):
        return np.take(a, np.arange(lo, hi), axis=axis)

    def rep(i, k):
        return np.repeat(part(i, i + 1), k, axis=axis) if k > 0 else part(0, 0)

    if center:
        mid, m = part(cap, n0 - cap), n - 2 * cap
        if m >= mid.shape[axis]:
            pad = m - mid.shape[axis]
            mid = np.concatenate([rep(cap, pad // 2), mid, rep(n0 - cap - 1, pad - pad // 2)], axis=axis)
        else:
            cut = (mid.shape[axis] - m) // 2
            mid = np.take(mid, np.arange(cut, cut + m), axis=axis)
        return np.concatenate([part(0, cap), mid, part(n0 - cap, n0)], axis=axis)
    head, m = part(0, n0 - cap), n - cap
    if m >= head.shape[axis]:
        head = np.concatenate([head, rep(n0 - cap - 1, m - head.shape[axis])], axis=axis)
    else:
        head = np.take(head, np.arange(0, m), axis=axis)
    return np.concatenate([head, part(n0 - cap, n0)], axis=axis)


# ---------------------------------------------------------------- превью

class Preview:
    def __init__(self, app):
        self.app = app
        self.active = False
        self.canvas = None
        self._item = None
        self._ref = None
        self._job = None
        self._tree = None
        self._nodes = []
        self._panels = []
        self._view = None
        self._size0 = None

    def start(self):
        view = self.app.view
        if self.active or not isinstance(view, GlassView):
            return
        W0, H0 = view.winfo_width(), view.winfo_height()
        if view._job or view.comp is None or view.comp.size != (W0, H0):
            view.recompose()                    # снимок должен совпасть с последней сборкой стекла
        comp = view.comp
        snap = capture(self.app.chrome.hwnd)
        if comp is None or snap is None or snap.width < W0 or snap.height < H0:
            return
        snap = snap.crop((0, 0, W0, H0))       # окно уже чуть подросло — берём прежнюю область
        diff = np.asarray(snap, np.int16) - np.asarray(comp, np.int16)

        ox, oy = view.winfo_rootx(), view.winfo_rooty()
        tree = _gather(view, ox, oy)
        nodes, panels = [], []

        def walk(node):
            if node.kind == "panel":
                panels.append(node)    # стекло панели собирается заново, со своего снимка не берём
            else:
                x, y, w, h = node.rect
                sprite = diff[max(0, y):y + h, max(0, x):x + w].copy()
                for c in node.children:   # у контейнера — только своё (чёрточка под вкладкой)
                    cx, cy, cw, chh = c.rect
                    sprite[max(0, cy - y):max(0, cy - y + chh), max(0, cx - x):max(0, cx - x + cw)] = 0
                if sprite.size and sprite.any():
                    node.sprite = sprite
                    nodes.append(node)
            for c in node.children:
                walk(c)

        for c in tree.children:
            walk(c)
        self._tree, self._nodes, self._panels = tree, nodes, panels
        self._view, self._size0 = view, (W0, H0)

        # настоящий интерфейс замирает: сетка окна больше не тянет экран за размером окна
        view.grid_propagate(False)
        view.configure(width=W0, height=H0)
        self.app.grid_rowconfigure(0, weight=0)
        self.app.grid_columnconfigure(0, weight=0)
        view.grid_configure(sticky="nw")

        if self.canvas is None:
            self.canvas = tk.Canvas(self.app, bd=0, highlightthickness=0)
            self._item = self.canvas.create_image(0, 0, anchor="nw")
        avg = "#%02x%02x%02x" % comp.resize((1, 1), Image.BOX).getpixel((0, 0))[:3]
        self.canvas.configure(bg=avg)   # окно рванули быстрее кадра — в новой полосе тон фона, не чёрный
        self.active = True
        self._draw()
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        # у Canvas метод lift() поднимает элементы рисунка, а не сам виджет — зовём Tk напрямую
        self.canvas.tk.call("raise", self.canvas._w)

    def frame(self):
        """Окно поменяло размер — новый кадр, не чаще, чем успевает экран."""
        if self.active and self._job is None:
            self._job = self.app.after_idle(self._draw)

    def render(self, W, H) -> Image.Image:
        """Кадр превью для окна W×H."""
        view = self._view
        out = {}
        _layout(self._tree, (0, 0, W, H), out)
        base, frost = view._layers(W, H, fast=True)
        img = base.copy()
        for node in self._panels:
            x, y, w, h = (round(v) for v in out[node])
            if w < 4 or h < 4:
                continue
            r = max(2, round(node.widget.radius * scale_of(node.widget)))
            fill, ring = masks(w, h, min(r, w // 2, h // 2))
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(W, x + w), min(H, y + h)
            if x1 <= x0 or y1 <= y0:
                continue
            piece = view._frost_piece(frost, x0, y0, x1, y1)
            box = (x0 - x, y0 - y, x1 - x, y1 - y)
            img.paste(piece, (x0, y0), fill.crop(box))
            img.paste((255, 255, 255), (x0, y0), ring.crop(box).point(lambda v: v * EDGE_ALPHA // 255))

        arr = np.array(img)
        s = scale_of(view)
        for node in self._nodes:
            sp = node.sprite
            if sp is None or not sp.size:
                continue
            x, y, w, h = (round(v) for v in out[node])
            cap = round(CAP * s)
            if node.scale and (w, h) != (sp.shape[1], sp.shape[0]) and w > 0 and h > 0:
                sp = sp[np.linspace(0, sp.shape[0] - 1, h).astype(int)][:, np.linspace(0, sp.shape[1] - 1, w).astype(int)]
            if w != sp.shape[1]:
                sp = _stretch(sp, w, 1, node.center, cap)
            if h != sp.shape[0]:
                sp = _stretch(sp, h, 0, False, cap)
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(W, x + sp.shape[1]), min(H, y + sp.shape[0])
            if x1 <= x0 or y1 <= y0:
                continue
            region = arr[y0:y1, x0:x1].astype(np.int16)
            region += sp[y0 - y:y1 - y, x0 - x:x1 - x]
            np.clip(region, 0, 255, out=region)
            arr[y0:y1, x0:x1] = region
        return Image.fromarray(arr)

    def _draw(self):
        self._job = None
        if not self.active:
            return
        W, H = self.app.winfo_width(), self.app.winfo_height()
        if W < 10 or H < 10:
            return
        self._ref = ImageTk.PhotoImage(self.render(W, H))
        self.canvas.itemconfigure(self._item, image=self._ref)

    def end(self):
        if not self.active:
            return
        self.active = False
        if self._job:
            self.app.after_cancel(self._job)
            self._job = None
        view = self._view
        # интерфейс снова тянется за окном — одна настоящая перекладка, под холстом превью
        view.grid_configure(sticky="nsew")
        self.app.grid_rowconfigure(0, weight=1)
        self.app.grid_columnconfigure(0, weight=1)
        view.grid_propagate(True)
        if view.winfo_exists():
            if view._job:
                view.after_cancel(view._job)
                view._job = None
            view.recompose()   # стекло начисто, пока превью ещё закрывает окно
        self.app.update_idletasks()
        self.canvas.place_forget()
        self._ref = None
        self._tree, self._nodes, self._panels, self._view = None, [], [], None
