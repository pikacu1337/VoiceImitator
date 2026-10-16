"""Выбор акцента, как AccentPicker в ZapretLauncher: квадрат насыщенности и яркости,
полоса оттенков, восемь готовых цветов сеткой 4×2 и поле #RRGGBB. Цвет применяется
ко всему окну сразу, пока его тянут. Оттенок хранится отдельно от цвета — если
провести метку через серый или чёрный, оттенок не теряется."""

import colorsys
import re

import customtkinter as ctk
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageTk

from app import theme
from app.glass import Clear, masks, scale_of

SV_H = 104        # высота квадрата и полосы оттенков
HUE_W = 14        # ширина полосы оттенков
HUE_MARK = (20, 5)
SWATCH = 26       # кружок 16px, кольцо выбора 26px
HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def _hex_to_hsv(color: str):
    r, g, b = (int(color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)


def _hsv_to_hex(h, s, v) -> str:
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _shadowed(shape: Image.Image, pad: int) -> Image.Image:
    """Белая метка с мягкой тенью (DropShadowEffect BlurRadius 4)."""
    w, h = shape.size
    out = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 230), (pad, pad), shape.split()[3])
    out = Image.alpha_composite(out, shadow.filter(ImageFilter.GaussianBlur(pad / 2)))
    out.alpha_composite(shape, (pad, pad))
    return out


class _Layer(Clear):
    """Прозрачный холст с картинкой поверх стекла."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._top = self.create_image(0, 0, anchor="nw")
        self._mark = self.create_image(0, 0, anchor="center")
        self._refs = {}

    def set_top(self, pil, x=0, y=0):
        self._refs["top"] = ImageTk.PhotoImage(pil)
        self.itemconfigure(self._top, image=self._refs["top"])
        self.coords(self._top, x, y)

    def set_mark(self, pil):
        self._refs["mark"] = ImageTk.PhotoImage(pil)
        self.itemconfigure(self._mark, image=self._refs["mark"])

    def move_mark(self, x, y):
        self.coords(self._mark, x, y)
        self.tag_raise(self._mark)


class AccentPicker(Clear):
    def __init__(self, master, color: str, hue: float | None, on_change, on_error):
        super().__init__(master)
        self.on_change = on_change
        self.on_error = on_error
        self.s = scale_of(self)
        h, s, v = _hex_to_hsv(color)
        self.h = hue if hue is not None else h
        self.sat, self.val = s, v
        self.color = color
        self.hover = None

        self.grid_columnconfigure(0, weight=1)
        # квадрат насыщенности/яркости
        self.sv = _Layer(self, height=round(SV_H * self.s), cursor="hand2")
        self.sv.grid(row=0, column=0, sticky="ew")
        # полоса оттенков (холст шире полосы на 3px с каждой стороны — под метку 20×5)
        self.hue = _Layer(self, width=round(HUE_MARK[0] * self.s), height=round(SV_H * self.s), cursor="hand2")
        self.hue.grid(row=0, column=1, padx=(round(9), round(17)))
        # готовые цвета 4×2 и поле #RRGGBB
        right = Clear(self)
        right.grid(row=0, column=2, sticky="ns")
        cell = round(SWATCH * self.s)
        self.sw = _Layer(right, width=cell * 4 + 6 * 3, height=cell * 2 + round(4 * self.s), cursor="hand2")
        self.sw.grid(row=0, column=0)
        self.entry = ctk.CTkEntry(right, width=SWATCH * 4 + 6 * 3, height=30, corner_radius=theme.R_PILL,
                                  border_width=1, border_color=theme.EDGE, text_color=theme.TEXT,
                                  font=ctk.CTkFont(family=theme.FONT_UI, size=13), justify="center")
        self.entry.grid(row=1, column=0, pady=(8, 0))
        self.entry.bind("<Return>", lambda _e: self._apply_hex())
        self.entry.bind("<FocusOut>", lambda _e: self._apply_hex())

        self._prepare_marks()
        for layer, down, move in ((self.sv, self._sv_down, self._sv_down),
                                  (self.hue, self._hue_down, self._hue_down)):
            layer.bind("<Button-1>", down)
            layer.bind("<B1-Motion>", move)
            layer.bind("<Configure>", lambda _e: self._render(), add="+")
        self.sw.bind("<Button-1>", self._sw_click)
        self.sw.bind("<Motion>", self._sw_hover)
        self.sw.bind("<Leave>", lambda _e: self._set_hover(None))
        self.after_idle(self._render)

    # ---------- отрисовка ----------

    def _prepare_marks(self):
        s = self.s
        d = round(14 * s)
        ring = Image.new("RGBA", (d * 3, d * 3), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((2, 2, d * 3 - 3, d * 3 - 3), outline=(255, 255, 255, 255), width=round(2 * s * 3))
        self.sv.set_mark(_shadowed(ring.resize((d, d), Image.LANCZOS), round(4 * s)))
        mw, mh = round(HUE_MARK[0] * s), round(HUE_MARK[1] * s)
        bar = Image.new("RGBA", (mw * 3, mh * 3), (0, 0, 0, 0))
        ImageDraw.Draw(bar).rounded_rectangle((0, 0, mw * 3 - 1, mh * 3 - 1), mh * 3 // 2, fill=(255, 255, 255, 255))
        self.hue.set_mark(_shadowed(bar.resize((mw, mh), Image.LANCZOS), round(4 * s)))

    def _render(self):
        self._render_sv()
        self._render_hue()
        self._render_swatches()
        self._place_marks()
        self.entry.delete(0, "end")
        self.entry.insert(0, self.color.upper())

    def _render_sv(self):
        w, h = self.sv.winfo_width(), self.sv.winfo_height()
        if w < 4 or h < 4:
            return
        hue = np.array(colorsys.hsv_to_rgb(self.h, 1, 1), dtype=np.float32) * 255
        sx = np.linspace(0, 1, w, dtype=np.float32)[None, :, None]
        vy = np.linspace(1, 0, h, dtype=np.float32)[:, None, None]
        rgb = (255 * (1 - sx) + hue * sx) * vy
        img = Image.fromarray(rgb.astype(np.uint8), "RGB").convert("RGBA")
        fill, ring = masks(w, h, round(theme.R_PILL * self.s))
        img.putalpha(fill)
        img.paste((255, 255, 255, 255), (0, 0), ring.point(lambda v: v * 36 // 255))
        self.sv.set_top(img)

    def _render_hue(self):
        w, h = self.hue.winfo_width(), self.hue.winfo_height()
        sw = round(HUE_W * self.s)
        if h < 4:
            return
        ys = np.linspace(0, 1, h, dtype=np.float32)
        col = np.array([colorsys.hsv_to_rgb(float(y) % 1.0, 1, 1) for y in ys], dtype=np.float32) * 255
        img = Image.fromarray(np.repeat(col[:, None, :], sw, axis=1).astype(np.uint8), "RGB").convert("RGBA")
        fill, _ = masks(sw, h, round(7 * self.s))
        img.putalpha(fill)
        self.hue.set_top(img, (w - sw) // 2, 0)

    def _render_swatches(self):
        s, ss = self.s, 3
        cell = round(SWATCH * s)
        gap = 6
        w, h = cell * 4 + gap * 3, cell * 2 + round(4 * s)
        big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        self._cells = []
        for i, key in enumerate(theme.ACCENT_ORDER):
            color = theme.ACCENTS[key]
            cx = (i % 4) * (cell + gap) + cell / 2
            cy = (i // 4) * (cell + round(4 * s)) + cell / 2
            self._cells.append((cx, cy, color))
            r_dot = 8 * s
            d.ellipse([(cx - r_dot) * ss, (cy - r_dot) * ss, (cx + r_dot) * ss, (cy + r_dot) * ss], fill=color)
            selected = color.lower() == self.color.lower()
            if selected or self.hover == i:
                rgb = tuple(int(color[j:j + 2], 16) for j in (1, 3, 5))
                alpha = 255 if selected else 115
                r_ring = (cell / 2 - 1)
                d.ellipse([(cx - r_ring) * ss, (cy - r_ring) * ss, (cx + r_ring) * ss, (cy + r_ring) * ss],
                          outline=rgb + (alpha,), width=round(1.5 * s * ss))
        self.sw.set_top(big.resize((w, h), Image.LANCZOS))

    def _place_marks(self):
        w, h = self.sv.winfo_width(), self.sv.winfo_height()
        self.sv.move_mark(self.sat * (w - 1), (1 - self.val) * (h - 1))
        hw, hh = self.hue.winfo_width(), self.hue.winfo_height()
        self.hue.move_mark(hw / 2, self.h * (hh - 1))

    # ---------- ввод ----------

    def _emit(self):
        self.color = _hsv_to_hex(self.h, self.sat, self.val)
        self._render_swatches()
        self._place_marks()
        self.entry.delete(0, "end")
        self.entry.insert(0, self.color.upper())
        self.on_change(self.color, self.h)

    def _sv_down(self, e):
        w, h = self.sv.winfo_width(), self.sv.winfo_height()
        self.sat = min(1, max(0, e.x / max(1, w - 1)))
        self.val = 1 - min(1, max(0, e.y / max(1, h - 1)))
        self._emit()

    def _hue_down(self, e):
        h = self.hue.winfo_height()
        self.h = min(0.9999, max(0, e.y / max(1, h - 1)))
        self._render_sv()
        self._emit()

    def _hit(self, e):
        cell = SWATCH * self.s
        for i, (cx, cy, _) in enumerate(self._cells):
            if abs(e.x - cx) <= cell / 2 and abs(e.y - cy) <= cell / 2:
                return i
        return None

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self._render_swatches()

    def _sw_hover(self, e):
        self._set_hover(self._hit(e))

    def _sw_click(self, e):
        i = self._hit(e)
        if i is not None:
            self.set_color(self._cells[i][2])

    def set_color(self, color: str):
        color = color.lower()
        h, s, v = _hex_to_hsv(color)
        if s > 0.02 and v > 0.02:
            self.h = h  # у белого/серого/чёрного оттенка нет — оставляем прежний
        self.sat, self.val, self.color = s, v, color
        self._render_sv()
        self._render_swatches()
        self._place_marks()
        self.entry.delete(0, "end")
        self.entry.insert(0, color.upper())
        self.on_change(color, self.h)

    def _apply_hex(self):
        text = self.entry.get().strip()
        m = HEX_RE.match(text)
        if not m:
            self.entry.delete(0, "end")
            self.entry.insert(0, self.color.upper())
            if text.upper() != self.color.upper():
                self.on_error("Свой цвет: шесть шестнадцатеричных цифр, например #7AB8FF, и Enter")
            return
        color = "#" + m.group(1).lower()
        if color != self.color.lower():
            self.set_color(color)
