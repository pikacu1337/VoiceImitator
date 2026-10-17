"""Ползунок прямо на стекле: без подложки, дорожка со скруглёнными концами,
метка — вертикальная скруглённая плашка. Рисуется картинкой со сглаживанием."""

from PIL import Image, ImageDraw, ImageTk

from app import theme
from app.glass import Clear, scale_of

TRACK = 4          # толщина дорожки
THUMB = (10, 13)   # метка: ширина × высота
THUMB_HOVER = (10, 15)
THUMB_R = 3        # скругление метки
HEIGHT = 24
SS = 3             # рисуем в 3x и уменьшаем — так края гладкие


def _rgba(color: str, alpha: int = 255):
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha


class Slider(Clear):
    def __init__(self, master, from_=0.0, to=1.0, number_of_steps=None, command=None,
                 progress_color=theme.DEFAULT_ACCENT, button_color=None, button_hover_color=None, **_):
        self.s = scale_of(master)
        super().__init__(master, height=round(HEIGHT * self.s), width=40, cursor="hand2")
        self.lo, self.hi = float(from_), float(to)
        self.steps = number_of_steps
        self.command = command
        self.accent = progress_color
        self.value = self.lo
        self.state = "normal"
        self.hover = False
        self._ref = None
        self._top = self.create_image(0, 0, anchor="nw")
        self.bind("<Configure>", lambda _e: self._draw(), add="+")
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))

    # ---------- API как у CTkSlider ----------

    def get(self) -> float:
        return self.value

    def set(self, value: float):
        self.value = min(self.hi, max(self.lo, float(value)))
        self._draw()

    def configure(self, cnf=None, **kw):
        changed = False
        for key in ("progress_color", "button_color"):
            if key in kw:
                self.accent = kw.pop(key)
                changed = True
        kw.pop("button_hover_color", None)
        if "state" in kw:
            self.state = kw.pop("state")
            super().configure(cursor="hand2" if self.state == "normal" else "")
            changed = True
        if changed:
            self._draw()
        if kw or cnf:
            return super().configure(cnf, **kw)

    config = configure

    # ---------- ввод ----------

    def _pad(self):
        return THUMB_HOVER[0] * self.s / 2 + TRACK * self.s / 2 + 1

    def _drag(self, e):
        if self.state != "normal":
            return
        w = self.winfo_width()
        pad = self._pad()
        frac = min(1.0, max(0.0, (e.x - pad) / max(1.0, w - 2 * pad)))
        if self.steps:
            frac = round(frac * self.steps) / self.steps
        value = self.lo + frac * (self.hi - self.lo)
        if value != self.value:
            self.value = value
            self._draw()
            if self.command:
                self.command(value)

    def _set_hover(self, on):
        self.hover = on and self.state == "normal"
        self._draw()

    # ---------- рисование ----------

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 4:
            return
        s, ss = self.s, SS
        alpha = 255 if self.state == "normal" else 102   # opacity-disabled 0.4
        img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        pad = self._pad()
        cy = h / 2
        t = TRACK * s
        frac = (self.value - self.lo) / ((self.hi - self.lo) or 1)
        x0, x1 = pad, w - pad
        xv = x0 + frac * (x1 - x0)

        def bar(a, b, color):  # отрезок дорожки с круглыми концами
            if b - a < 0.5:
                return
            d.rounded_rectangle(((a - t / 2) * ss, (cy - t / 2) * ss, (b + t / 2) * ss, (cy + t / 2) * ss),
                                radius=t / 2 * ss, fill=color)

        bar(x0, x1, (255, 255, 255, round(0x1f * alpha / 255)))       # track-off #ffffff1f
        bar(x0, xv, _rgba(self.accent, alpha))                          # пройденная часть — акцент
        tw, th = (THUMB_HOVER if self.hover else THUMB)
        tw, th = tw * s, th * s
        d.rounded_rectangle(((xv - tw / 2) * ss, (cy - th / 2) * ss, (xv + tw / 2) * ss, (cy + th / 2) * ss),
                            radius=THUMB_R * s * ss, fill=_rgba(self.accent, alpha))
        self._ref = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))
        self.itemconfigure(self._top, image=self._ref)
        self.tag_raise(self._top)
