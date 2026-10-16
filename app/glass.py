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


def masks(w: int, h: int, r: int):
    """Скруглённая маска заливки и кольцо обводки, со сглаживанием (рисуем в 3x)."""
    key = (w, h, r)
    if key not in _mask_cache:
        ss = 3
        fill = Image.new("L", (w * ss, h * ss), 0)
        ImageDraw.Draw(fill).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=255)
        ring = fill.copy()
        ImageDraw.Draw(ring).rounded_rectangle((ss, ss, w * ss - 1 - ss, h * ss - 1 - ss),
                                               max(0, (r - 1) * ss), fill=0)
        fill = fill.resize((w, h), Image.LANCZOS)
        ring = ring.resize((w, h), Image.LANCZOS)
        if len(_mask_cache) > 96:
            _mask_cache.clear()
        _mask_cache[key] = (fill, ring)
    return _mask_cache[key]


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
        self._item = self.create_image(0, 0, anchor="nw")
        self.tag_lower(self._item)
        self.bind("<Configure>", self._changed, add="+")

    def _changed(self, _e=None):
        view = find_view(self.master)
        if view:
            view.recompose_later()

    def show(self, pil):
        self._img = ImageTk.PhotoImage(pil)
        self.itemconfigure(self._item, image=self._img)
        self.tag_lower(self._item)


class Text(Clear):
    """Подпись, нарисованная прямо на стекле — без прямоугольника вокруг текста."""

    def __init__(self, master, text: str, spec=theme.F_LABEL, color: str = theme.TEXT,
                 wraplength: int | None = None, justify: str = "left"):
        super().__init__(master)
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
            self.itemconfigure(self._text_item, fill=self._color)
        if kw or cnf:
            return super().configure(cnf, **kw)

    config = configure


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
        self._item = self.create_image(0, 0, anchor="nw")
        self._img = None
        self._key = None
        self._base = None
        self._frost = None
        self._job = None
        self.bind("<Configure>", lambda _e: self.recompose_later())

    def recompose_later(self, delay: int = 50):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(delay, self.recompose)

    def _layers(self, w, h):
        s = self.app.settings
        sc = scale_of(self)
        key = (w, h, s["bg_mode"], s["bg_custom"], s["bg_brightness"], s["bg_blur"], s["glass_blur"])
        if self._key != key:
            base = backdrop.render(w, h, s["bg_mode"], s["bg_custom"], s["bg_brightness"],
                                   s["bg_blur"], sc)
            frost = base.filter(ImageFilter.GaussianBlur(s["glass_blur"] / 100 * GLASS_BLUR_MAX * sc))
            frost = Image.blend(frost, Image.new("RGB", frost.size, (0, 0, 0)), GLASS_DIM)
            frost = Image.blend(frost, Image.new("RGB", frost.size, (255, 255, 255)), VEIL)
            self._base, self._frost, self._key = base, frost, key
        return self._base, self._frost

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
        self._job = None
        if not self.winfo_exists():
            return
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
            img.paste(frost.crop((x0, y0, x1, y1)), (x0, y0), fill)
            img.paste((255, 255, 255), (x0, y0), ring.point(lambda v: v * EDGE_ALPHA // 255))

        self._img = ImageTk.PhotoImage(img)
        self.itemconfigure(self._item, image=self._img)

        def crop(x0, y0, x1, y1):
            return img.crop((max(0, x0), max(0, y0), min(W, x1), min(H, y1)))

        for c in clears:
            x0, y0, x1, y1 = self._rect(c, ox, oy)
            if x1 > x0 and y1 > y0:
                c.show(crop(x0, y0, x1, y1))
        for leaf in leaves:
            x0, y0, x1, y1 = self._rect(leaf, ox, oy)
            if x1 <= x0 or y1 <= y0:
                continue
            piece = crop(x0, y0, x1, y1)
            tint(leaf, _hex(piece.resize((1, 1), Image.BOX).getpixel((0, 0))))
            cv = getattr(leaf, "_canvas", None)
            if cv is not None and cv.winfo_ismapped():
                underlay(cv, crop(*self._rect(cv, ox, oy)))
        self.after_recompose()

    def after_recompose(self):
        """Хук для экранов: вызывается после каждой пересборки стекла."""


def underlay(cv, piece):
    """Кладёт под рисунок контрола его кусок фона — скруглённые углы ложатся на стекло."""
    cv._ng_under = ImageTk.PhotoImage(piece)
    cv.delete("ng_under")
    cv.create_image(0, 0, anchor="nw", image=cv._ng_under, tags="ng_under")
    cv.tag_lower("ng_under")


def tint(w, avg: str):
    """Подгоняет цвета контрола под стекло под ним."""
    kind = getattr(w, "ng_kind", None)
    w.ng_avg = avg
    field = blend(avg, "#ffffff", 0.08)   # field #ffffff14
    track = blend(avg, "#ffffff", 0.13)   # track-off #ffffff1f
    hover = blend(avg, "#ffffff", 0.10)   # wash-pill #ffffff1a
    try:
        if kind == "scroll":
            w.ng_scroll.configure(fg_color=field)
            w.configure(bg_color=avg)
        elif isinstance(w, ctk.CTkButton):
            if kind == "ghost":
                sel = getattr(w, "ng_selected", None)
                w.configure(fg_color=avg, bg_color=avg, hover_color=hover,
                            border_color=sel or blend(avg, "#ffffff", 0.16))   # edge #ffffff24
            else:
                w.configure(bg_color=avg)
        elif isinstance(w, ctk.CTkOptionMenu):
            w.configure(bg_color=avg, fg_color=field, button_color=field, button_hover_color=hover)
        elif isinstance(w, (ctk.CTkTextbox, ctk.CTkEntry)):
            w.configure(bg_color=avg, fg_color=field)
        elif isinstance(w, (ctk.CTkSlider, ctk.CTkProgressBar, ctk.CTkSwitch)):
            w.configure(bg_color=avg, fg_color=track)
        elif isinstance(w, ctk.CTkFrame):
            if kind == "bar":
                w.configure(bg_color=avg, fg_color=getattr(w, "ng_bar_color", None) or avg)
            else:
                w.configure(bg_color=avg, fg_color=avg)
    except Exception:
        pass
