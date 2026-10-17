"""Матовое стекло Night Glass поверх фона.

Tk не умеет полупрозрачные виджеты, поэтому стекло собирается картинкой:
  - экран (GlassView) — холст, на котором нарисован фон (картинка или звёздное небо);
  - под каждой панелью (GlassPanel) в эту картинку вклеивается тот же фон,
    размытый, затемнённый (glass-dim) и высветленный вуалью (veil), со
    скруглёнными углами и обводкой 1px (edge) — как слой Frost в оригинале;
  - прозрачные контейнеры (Clear) и подписи (Text) показывают ровно тот кусок
    картинки, что под ними;
  - под каждый контрол (кнопку, поле, ползунок) подкладывается его кусок картинки,
    поэтому скруглённые углы ложатся на настоящее стекло, без прямоугольников.
"""

import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFilter, ImageTk

from app import backdrop, theme

GLASS_BLUR_MAX = 40   # размытие стекла при 100% (в лаунчере 120px WPF = 40px CSS)
GLASS_DIM = 0.28      # стекло темнее фона: 64% чёрного против 50% у картинки
VEIL = 0.07           # #ffffff12 — то, что делает стекло стеклом
EDGE_ALPHA = 36       # #ffffff24 — обводка 1px
GLYPH_FONT = "Segoe MDL2 Assets"


def _rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(v) for v in rgb[:3])


def blend(a: str, b: str, t: float) -> str:
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(round(x + (y - x) * t) for x, y in zip(ra, rb)))


def scale_of(widget) -> float:
    try:
        return ctk.ScalingTracker.get_widget_scaling(widget)
    except Exception:
        return 1.0


_mask_cache: dict = {}


def _draw_masks(w: int, h: int, r: int):
    """Скруглённая маска заливки и кольцо обводки 1px, со сглаживанием (рисуем в 3x)."""
    ss = 3
    fill = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(fill).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=255)
    ring = fill.copy()
    ImageDraw.Draw(ring).rounded_rectangle((ss, ss, w * ss - 1 - ss, h * ss - 1 - ss),
                                           max(0, (r - 1) * ss), fill=0)
    return fill.resize((w, h), Image.LANCZOS), ring.resize((w, h), Image.LANCZOS)


_corner_cache: dict = {}


def masks(w: int, h: int, r: int):
    """Маска и кольцо любого размера — из готовых уголков радиуса r и прямых краёв между ними.
    Рисовать заново на каждый размер дорого, а при растягивании окна размер каждый кадр новый."""
    key = (w, h, r)
    if key in _mask_cache:
        return _mask_cache[key]
    if w < 2 * r + 2 or h < 2 * r + 2 or r < 1:
        res = _draw_masks(w, h, r)
    else:
        if r not in _corner_cache:
            n = 2 * r + 8
            _corner_cache[r] = (n, *_draw_masks(n, n, r))
        n, ref_fill, ref_ring = _corner_cache[r]
        res = []
        for ref, inside in ((ref_fill, 255), (ref_ring, 0)):
            m = Image.new("L", (w, h), inside)
            for (cx, cy), (px, py) in (((0, 0), (0, 0)), ((n - r, 0), (w - r, 0)),
                                       ((0, n - r), (0, h - r)), ((n - r, n - r), (w - r, h - r))):
                m.paste(ref.crop((cx, cy, cx + r, cy + r)), (px, py))
            # прямые края — срез референса посередине, растянутый вдоль края
            m.paste(ref.crop((r, 0, r + 1, r)).resize((w - 2 * r, r)), (r, 0))
            m.paste(ref.crop((r, n - r, r + 1, n)).resize((w - 2 * r, r)), (r, h - r))
            m.paste(ref.crop((0, r, r, r + 1)).resize((r, h - 2 * r)), (0, r))
            m.paste(ref.crop((n - r, r, n, r + 1)).resize((r, h - 2 * r)), (w - r, r))
            res.append(m)
        res = tuple(res)
    if len(_mask_cache) > 96:
        _mask_cache.clear()
    _mask_cache[key] = res
    return res


def find_view(widget):
    w = widget
    while w is not None and not isinstance(w, GlassView):
        w = getattr(w, "master", None)
    return w


class Clear(tk.Canvas):
    """Прозрачный контейнер: показывает ту часть фона/стекла, что под ним."""

    def __init__(self, master, **kw):
        super().__init__(master, bd=0, highlightthickness=0, bg=theme.WINDOW, **kw)
        self._img = None
        self._sig = None
        # Подложка — прямоугольник среднего цвета участка: если контейнер вырос раньше, чем
        # пересобралось стекло, в новой полосе виден близкий тон, а не чёрный. Цвет меняем через
        # itemconfigure: configure(bg=…) у холста сбросил бы его размер к умолчанию.
        self._bgrect = self.create_rectangle(0, 0, 10000, 10000, fill=theme.WINDOW, outline="")
        self._item = self.create_image(0, 0, anchor="nw")
        self.tag_lower(self._item)
        self.tag_lower(self._bgrect)
        self.bind("<Configure>", self._changed, add="+")

    def _changed(self, _e=None):
        view = find_view(self.master)
        if view:
            view._on_size()

    def show(self, pil, avg: str | None = None) -> bool:
        """Ставит кусок картинки. Если он не изменился — ничего не перерисовывает.
        avg — средний цвет куска, если его уже посчитали (это дешевле, чем считать здесь)."""
        sig = (pil.size, hash(pil.tobytes()))
        if sig == self._sig:
            return False
        self._sig = sig
        self._img = ImageTk.PhotoImage(pil)
        self.itemconfigure(self._item, image=self._img)
        self.itemconfigure(self._bgrect, fill=avg or _hex(pil.resize((1, 1), Image.BOX).getpixel((0, 0))))
        self.tag_lower(self._item)
        self.tag_lower(self._bgrect)
        return True

class Text(Clear):
    """Подпись, нарисованная прямо на стекле — без прямоугольника вокруг текста."""

    def __init__(self, master, text: str, spec=theme.F_LABEL, color: str = theme.TEXT,
                 wraplength: int | None = None, justify: str = "left", alpha: float | None = None):
        super().__init__(master)
        self.alpha = alpha      # None — сплошной цвет; 0..1 — текст полупрозрачный поверх фона
        self._avg = theme.WINDOW
        size, weight = spec
        # как у CTkFont: отрицательный размер = пиксели, умноженные на масштаб экрана
        self._font = tkfont.Font(family=theme.FONT_UI, size=-round(size * scale_of(self)), weight=weight)
        self._color = color
        self._wrap = round(wraplength * scale_of(self)) if wraplength else None
        self._justify = justify
        self._text_item = self.create_text(0, 0, anchor="nw", font=self._font, fill=color,
                                           justify=justify)
        self._set_text(text)

    def _wrapped(self, text: str) -> str:
        if not self._wrap:
            return text
        out = []
        for para in text.split("\n"):
            line = ""
            for word in para.split(" "):
                probe = f"{line} {word}".strip()
                if line and self._font.measure(probe) > self._wrap:
                    out.append(line)
                    line = word
                else:
                    line = probe
            out.append(line)
        return "\n".join(out)

    def _set_text(self, text: str):
        text = self._wrapped(text or "")
        lines = text.split("\n")
        w = max((self._font.measure(line) for line in lines), default=0) + 2
        h = self._font.metrics("linespace") * max(1, len(lines)) + 2
        x = {"left": 0, "center": w // 2, "right": w}[self._justify]
        anchor = {"left": "nw", "center": "n", "right": "ne"}[self._justify]
        self.coords(self._text_item, x, 0)
        self.itemconfigure(self._text_item, text=text, anchor=anchor)
        super().configure(width=w, height=h)

    def configure(self, cnf=None, **kw):
        if "text" in kw:
            self._set_text(kw.pop("text"))
        if "text_color" in kw:
            self._color = kw.pop("text_color")
            self._apply_color()
        if kw or cnf:
            return super().configure(cnf, **kw)

    config = configure

    def _apply_color(self):
        fill = self._color if self.alpha is None else blend(self._avg, self._color, self.alpha)
        self.itemconfigure(self._text_item, fill=fill)

    def set_alpha(self, alpha: float):
        self.alpha = alpha
        self._apply_color()

    def show(self, pil, avg=None):
        if not super().show(pil, avg):
            return False
        self._avg = avg or _hex(pil.resize((1, 1), Image.BOX).getpixel((0, 0)))
        self._apply_color()
        return True


class GlassPanel(Clear):
    """Панель из матового стекла."""

    def __init__(self, master, radius: int = theme.R_CARD, **kw):
        super().__init__(master, **kw)
        self.radius = radius


class Dropdown(ctk.CTkOptionMenu):
    """Выпадающий список с тонким шевроном (Segoe MDL2, как значки в ZapretLauncher)."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        for w in (self._canvas, self._text_label):
            w.bind("<Enter>", lambda _e: self._arrow_color(theme.TEXT), add="+")
            w.bind("<Leave>", lambda _e: self._arrow_color(theme.MUTED), add="+")

    def _arrow_color(self, color):
        self._canvas.itemconfigure("ng_arrow", fill=color)

    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        cv = self._canvas
        cv.itemconfigure("dropdown_arrow", state="hidden")
        s = scale_of(self)
        x = self._apply_widget_scaling(self._current_width) - round(18 * s)
        y = self._apply_widget_scaling(self._current_height) / 2
        if not cv.find_withtag("ng_arrow"):
            cv.create_text(x, y, text="", font=(GLYPH_FONT, -round(10 * s)),
                           fill=theme.MUTED, anchor="center", tags="ng_arrow")
        cv.coords("ng_arrow", x, y + 1)
        cv.tag_raise("ng_arrow")


class GlassView(tk.Canvas):
    """Экран: фон на всё окно + стеклянные панели, прозрачные контейнеры и контролы на нём."""

    def __init__(self, master, app):
        super().__init__(master, bd=0, highlightthickness=0, bg=theme.WINDOW)
        self.app = app
        self._bgrect = self.create_rectangle(0, 0, 10000, 10000, fill=theme.WINDOW, outline="")
        self._item = self.create_image(0, 0, anchor="nw")
        self._img = None
        self._key = None
        self._base = None
        self._frost = None
        self._job = None
        self._tinted = {}
        self._sig = None
        self._busy = False      # идёт сборка: её update_idletasks не должен запускать вложенную
        self.bind("<Configure>", lambda _e: self._on_size())

    def _on_size(self):
        if self._busy:
            return   # размеры поменялись во время сборки — она их и учтёт
        self.recompose_later()

    def recompose_later(self, delay: int = 50):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(delay, self.recompose)

    def _layers(self, w, h, fast=False):
        s = self.app.settings
        sc = scale_of(self)
        key = (w, h, fast, s["bg_mode"], s["bg_custom"], s["bg_brightness"], s["bg_blur"], s["glass_blur"])
        if self._key != key:
            k = 4 if fast else 1    # быстрый режим (превью растягивания): в четверть размера
            rw, rh = max(2, w // k), max(2, h // k)
            base = backdrop.render(rw, rh, s["bg_mode"], s["bg_custom"], s["bg_brightness"],
                                   s["bg_blur"], sc / k, fast=fast)
            frost = base.filter(ImageFilter.GaussianBlur(s["glass_blur"] / 100 * GLASS_BLUR_MAX * sc / k))
            frost = Image.blend(frost, Image.new("RGB", frost.size, (0, 0, 0)), GLASS_DIM)
            frost = Image.blend(frost, Image.new("RGB", frost.size, (255, 255, 255)), VEIL)
            if k > 1:
                # стекло растягиваем не целиком, а только кусками под панелями (см. _frost_piece)
                base = base.resize((w, h), Image.BILINEAR)
            self._base, self._frost, self._key = base, frost, key
        return self._base, self._frost

    def _frost_piece(self, frost, x0, y0, x1, y1):
        if frost.size == self._base.size:
            return frost.crop((x0, y0, x1, y1))
        k = frost.width / self._base.width
        return frost.resize((x1 - x0, y1 - y0), Image.BILINEAR, box=(x0 * k, y0 * k, x1 * k, y1 * k))

    def _collect(self, widget, clears, leaves):
        for child in widget.winfo_children():
            if not child.winfo_ismapped():
                continue
            if isinstance(child, Clear):
                clears.append(child)
                self._collect(child, clears, leaves)
            elif isinstance(child, (ctk.CTkBaseClass, ctk.CTkFrame)):
                leaves.append(child)

    @staticmethod
    def _rect(w, ox, oy):
        x, y = w.winfo_rootx() - ox, w.winfo_rooty() - oy
        return x, y, x + w.winfo_width(), y + w.winfo_height()

    def recompose(self):
        """Собирает стекло: фон, панели, куски под прозрачными контейнерами и контролами."""
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        if self._busy or not self.winfo_exists():
            return
        self._busy = True
        try:
            self._compose()
        finally:
            self._busy = False
        self.after_recompose()

    def _compose(self):
        self.update_idletasks()
        W, H = self.winfo_width(), self.winfo_height()
        if W < 10 or H < 10:
            return
        base, frost = self._layers(W, H)
        img = base.copy()
        ox, oy = self.winfo_rootx(), self.winfo_rooty()
        clears, leaves = [], []
        self._collect(self, clears, leaves)

        for c in clears:
            if not isinstance(c, GlassPanel):
                continue
            x0, y0, x1, y1 = self._rect(c, ox, oy)
            w, h = x1 - x0, y1 - y0
            if w < 4 or h < 4:
                continue
            r = max(2, round(c.radius * scale_of(c)))
            fill, ring = masks(w, h, min(r, w // 2, h // 2))
            img.paste(self._frost_piece(frost, x0, y0, x1, y1), (x0, y0), fill)
            img.paste((255, 255, 255), (x0, y0), ring.point(lambda v: v * EDGE_ALPHA // 255))

        # средний цвет куска — по уменьшенной в 8 раз картинке: это в десятки раз дешевле
        small = img.reduce(8)

        def avg_of(x0, y0, x1, y1):
            sx0, sy0 = max(0, x0 // 8), max(0, y0 // 8)
            sx1, sy1 = min(small.width, max(sx0 + 1, -(-x1 // 8))), min(small.height, max(sy0 + 1, -(-y1 // 8)))
            if sx1 <= sx0 or sy1 <= sy0:
                return theme.WINDOW
            return _hex(small.crop((sx0, sy0, sx1, sy1)).resize((1, 1), Image.BOX).getpixel((0, 0)))

        sig = (img.size, hash(img.tobytes()))
        if sig != self._sig:
            self._sig = sig
            self._img = ImageTk.PhotoImage(img)
            self.itemconfigure(self._item, image=self._img)
            self.itemconfigure(self._bgrect, fill=avg_of(0, 0, W, H))
            self.tag_lower(self._item)
            self.tag_lower(self._bgrect)
            chrome = getattr(self.app, "chrome", None)
            if chrome is not None and getattr(self.app, "view", None) is self:
                # верхний край системной рамки — цветом верха фона, чтобы с ним сливался
                chrome.set_top_color(avg_of(0, 0, W, 8))

        def crop(x0, y0, x1, y1):
            return img.crop((max(0, x0), max(0, y0), min(W, x1), min(H, y1)))

        for c in clears:
            rect = self._rect(c, ox, oy)
            if rect[2] > rect[0] and rect[3] > rect[1]:
                c.show(crop(*rect), avg_of(*rect))
        for leaf in leaves:
            rect = self._rect(leaf, ox, oy)
            if rect[2] <= rect[0] or rect[3] <= rect[1]:
                continue
            avg = avg_of(*rect)
            if self._tinted.get(id(leaf)) != avg:
                self._tinted[id(leaf)] = avg
                tint(leaf, avg)
            cv = getattr(leaf, "_canvas", None)
            if cv is not None and cv.winfo_ismapped():
                underlay(cv, crop(*self._rect(cv, ox, oy)))

    def after_recompose(self):
        """Хук для экранов: вызывается после каждой пересборки стекла."""


def underlay(cv, piece):
    """Кладёт под рисунок контрола его кусок фона — скруглённые углы ложатся на стекло."""
    sig = (piece.size, hash(piece.tobytes()))
    if getattr(cv, "_ng_sig", None) == sig and cv.find_withtag("ng_under"):
        cv.tag_lower("ng_under")
        return
    cv._ng_sig = sig
    cv._ng_under = ImageTk.PhotoImage(piece)
    cv.delete("ng_under")
    cv.create_image(0, 0, anchor="nw", image=cv._ng_under, tags="ng_under")
    cv.tag_lower("ng_under")


def tint(w, avg: str):
    """Подгоняет цвета контрола под стекло под ним."""
    kind = getattr(w, "ng_kind", None)
    w.ng_avg = avg
    # поля ввода — то же матовое стекло, только плотнее: чуть темнее панели и с еле заметной
    # обводкой, чтобы едва-едва отделялись от фона
    field = blend(avg, "#000000", 0.16)
    field_edge = blend(avg, "#ffffff", 0.09)
    field_hover = blend(avg, "#ffffff", 0.04)
    track = blend(avg, "#ffffff", 0.13)   # track-off #ffffff1f
    hover = blend(avg, "#ffffff", 0.10)   # wash-pill #ffffff1a
    try:
        if kind == "scroll":
            w.ng_scroll.configure(fg_color=field)
            w.configure(bg_color=avg, border_width=1, border_color=field_edge)
        elif isinstance(w, ctk.CTkButton):
            if kind == "ghost":
                sel = getattr(w, "ng_selected", None)
                w.configure(fg_color=avg, bg_color=avg, hover_color=hover,
                            border_color=sel or blend(avg, "#ffffff", 0.16))   # edge #ffffff24
            else:
                w.configure(bg_color=avg)
        elif isinstance(w, ctk.CTkOptionMenu):
            w.configure(bg_color=avg, fg_color=field, button_color=field, button_hover_color=field_hover)
        elif isinstance(w, (ctk.CTkTextbox, ctk.CTkEntry)):
            w.configure(bg_color=avg, fg_color=field, border_color=field_edge)
        elif isinstance(w, (ctk.CTkSlider, ctk.CTkProgressBar, ctk.CTkSwitch)):
            w.configure(bg_color=avg, fg_color=track)
        elif isinstance(w, ctk.CTkFrame):
            if kind == "bar":
                w.configure(bg_color=avg, fg_color=getattr(w, "ng_bar_color", None) or avg)
            else:
                w.configure(bg_color=avg, fg_color=avg)
    except Exception:
        pass
