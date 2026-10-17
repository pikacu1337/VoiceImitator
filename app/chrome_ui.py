"""Рамка окна в стиле ZapretLauncher: заголовок 44px с вкладками по центру и
кнопками окна справа, общая чёрточка под открытой вкладкой (переезжает за 0.36 с,
CubicEase InOut, без растяжения) и строка версии внизу — сообщения проявляются
под ней, версия поднимается на 10px, через 8 с всё возвращается."""

import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageTk

from app import __version__, theme
from app.glass import GLYPH_FONT, Clear, Text, blend, scale_of

TITLE_H = 44
FOOTER_H = 52
BAR = (18, 3)          # чёрточка под вкладкой
BAR_MOVE_MS = 360      # переезд чёрточки
BAR_FADE_MS = 350      # первое появление
MSG_IN_MS = 280
MSG_OUT_MS = 220
MSG_HOLD_MS = 8000
VERSION_ALPHA = 0.30   # строка версии почти прозрачная


def cubic_in_out(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def cubic_out(t):
    return 1 - (1 - t) ** 3


def animate(widget, ms, step, ease=cubic_out, done=None, token=None):
    """Простая анимация на after(): step(k) получает долю 0..1 после сглаживания."""
    import time

    start = time.perf_counter()
    owner = token if token is not None else widget
    owner._anim_id = getattr(owner, "_anim_id", 0) + 1
    my_id = owner._anim_id

    def tick():
        if owner._anim_id != my_id or not widget.winfo_exists():
            return
        t = min(1.0, (time.perf_counter() - start) * 1000 / ms)
        step(ease(t))
        if t < 1.0:
            widget.after(15, tick)
        elif done:
            done()

    tick()


def _rounded(w, h, r, rgba):
    ss = 3
    img = Image.new("RGBA", (max(1, w) * ss, max(1, h) * ss), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=rgba)
    return img.resize((max(1, w), max(1, h)), Image.LANCZOS)


class TitleButton(Clear):
    """Кнопка окна: значок Segoe MDL2 36×30, под курсором — подсветка #1FFFFFFF со скруглением 8."""

    def __init__(self, master, glyph, command):
        s = scale_of(master)
        w, h = round(36 * s), round(30 * s)
        super().__init__(master, width=w, height=h, cursor="hand2")
        self.command = command
        self._wash_ref = ImageTk.PhotoImage(_rounded(w, h, round(8 * s), (255, 255, 255, 0x1F)))
        self._wash = self.create_image(0, 0, anchor="nw", image=self._wash_ref, state="hidden")
        self._glyph = self.create_text(w / 2, h / 2, text=glyph, fill=theme.MUTED,
                                       font=(GLYPH_FONT, -round(10 * s)))
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))
        self.bind("<ButtonRelease-1>", self._click)

    def _hover(self, on):
        self.itemconfigure(self._wash, state="normal" if on else "hidden")
        self.itemconfigure(self._glyph, fill=theme.TEXT if on else theme.MUTED)

    def _click(self, e):
        if 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height():
            self.command()

    def set_glyph(self, glyph):
        self.itemconfigure(self._glyph, text=glyph)


class TitleBar(Clear):
    """Полоса заголовка: тянет окно, двойной щелчок разворачивает; справа кнопки окна."""

    def __init__(self, master, app, maximizable: bool = True, caption: str | None = None):
        s = scale_of(master)
        super().__init__(master, height=round(TITLE_H * s))
        btns = Clear(self)
        btns.place(relx=1.0, x=-round(12 * s), rely=0.5, anchor="e")
        TitleButton(btns, "", app.chrome.minimize).grid(row=0, column=0)
        if maximizable:
            self.max_btn = TitleButton(btns, "", app.chrome.toggle_maximize)
            self.max_btn.grid(row=0, column=1)
            app.chrome.on_state = lambda maximized: self.max_btn.set_glyph("" if maximized else "")
        TitleButton(btns, "", app.on_close).grid(row=0, column=2)
        if caption:
            # как wordmark мастера ZapretLauncher: название 600 цвета text, пояснение faint
            mark = Clear(self)
            mark.place(x=round(20 * s), rely=0.5, anchor="w")
            Text(mark, "VoiceImitator", (15, "bold"), theme.TEXT).grid(row=0, column=0)
            Text(mark, caption, (15, "normal"), theme.FAINT).grid(row=0, column=1)
            app.chrome.attach(mark, drag=True)
        app.chrome.attach(self, drag=True)


class TabStrip(Clear):
    """Вкладки: текст muted, открытая и под курсором — text; под открытой — чёрточка-акцент."""

    def __init__(self, master, tabs, on_change, app):
        super().__init__(master)
        self.app = app
        self.s = scale_of(master)
        self.on_change = on_change
        self.active = tabs[0]
        self.cells = {}
        self.bar_x = None
        self._bar_alpha = 0.0
        self._bar_ref = None
        self._bar = self.create_image(0, 0, anchor="center")
        s = self.s
        for i, name in enumerate(tabs):
            txt = Text(self, name, (13.5, "normal"), theme.MUTED)
            # отступы как у вкладки ZapretLauncher: 8 снаружи, 12 по бокам, 9 сверху, 12 снизу
            txt.grid(row=0, column=i, padx=round(20 * s), pady=(round(9 * s), round(12 * s)))
            txt.configure(cursor="hand2")
            txt.bind("<Button-1>", lambda _e, n=name: self.select(n))
            txt.bind("<Enter>", lambda _e, t=txt: t.configure(text_color=theme.TEXT))
            txt.bind("<Leave>", lambda _e, n=name, t=txt: t.configure(
                text_color=theme.TEXT if n == self.active else theme.MUTED))
            self.cells[name] = txt
        app.chrome.attach(self, drag=True)
        self.bind("<Configure>", lambda _e: self._snap(), add="+")
        self.after(80, lambda: self.select(self.active, fire=False))

    def _target(self):
        txt = self.cells[self.active]
        return txt.winfo_x() + txt.winfo_width() / 2

    def _bar_y(self):
        return self.winfo_height() - round(4 * self.s) - BAR[1] * self.s / 2

    def _render_bar(self):
        w, h = round(BAR[0] * self.s), max(2, round(BAR[1] * self.s))
        c = self.app.accent.lstrip("#")
        rgba = (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), round(255 * self._bar_alpha))
        self._bar_ref = ImageTk.PhotoImage(_rounded(w, h, round(2 * self.s), rgba))
        self.itemconfigure(self._bar, image=self._bar_ref)
        self.tag_raise(self._bar)

    def _snap(self):
        if self.bar_x is not None and not getattr(self, "_moving", False):
            self.bar_x = self._target()
            self.coords(self._bar, self.bar_x, self._bar_y())

    def select(self, name, fire=True):
        self.active = name
        for n, txt in self.cells.items():
            txt.configure(text_color=theme.TEXT if n == name else theme.MUTED)
        self.update_idletasks()
        target = self._target()
        if self.bar_x is None:  # первое появление — проявляется на месте
            self.bar_x = target
            self.coords(self._bar, target, self._bar_y())

            def fade(k):
                self._bar_alpha = k
                self._render_bar()
            animate(self, BAR_FADE_MS, fade)
        else:
            start = self.bar_x
            self._moving = True

            def move(k):
                self.bar_x = start + (target - start) * k
                self.coords(self._bar, self.bar_x, self._bar_y())

            def end():
                self._moving = False
            animate(self, BAR_MOVE_MS, move, ease=cubic_in_out, done=end)
        if fire:
            self.on_change(name)

    def restyle_accent(self):
        self._render_bar()

    def show(self, pil, avg=None):
        changed = super().show(pil, avg)
        self.tag_raise(self._bar)
        return changed


class Footer(Clear):
    """Строка версии внизу; сообщения проявляются под ней и уходят через 8 с."""

    def __init__(self, master, app):
        self.s = scale_of(master)
        super().__init__(master, height=round(FOOTER_H * self.s))
        font = tkfont.Font(family=theme.FONT_UI, size=-round(12 * self.s))
        self._avg = theme.WINDOW
        self.shift = 0.0
        self.msg_alpha = 0.0
        self._hold = None
        self.version = self.create_text(0, 0, anchor="w", font=font,
                                        text=f"VoiceImitator {__version__}")
        self.msg = self.create_text(0, 0, anchor="w", font=font, text="")
        self.bind("<Configure>", lambda _e: self._layout(), add="+")

    def _layout(self):
        cy = self.winfo_height() / 2
        self.coords(self.version, 0, cy + self.shift)
        self.coords(self.msg, 0, cy + self.shift + round(19 * self.s))
        self.itemconfigure(self.version, fill=blend(self._avg, theme.TEXT, VERSION_ALPHA))
        self.itemconfigure(self.msg, fill=blend(self._avg, theme.MUTED, self.msg_alpha),
                           state="normal" if self.msg_alpha > 0.01 else "hidden")

    def show(self, pil, avg=None):
        if not super().show(pil, avg):
            return False
        self._avg = avg or "#%02x%02x%02x" % pil.resize((1, 1), Image.BOX).getpixel((0, 0))[:3]
        self._layout()
        return True

    def flash(self, text):
        self.itemconfigure(self.msg, text=text)
        if self._hold:
            self.after_cancel(self._hold)
        s0, a0 = self.shift, self.msg_alpha

        def step(k):
            self.shift = s0 + (-10 * self.s - s0) * k
            self.msg_alpha = a0 + (1 - a0) * k
            self._layout()
        animate(self, MSG_IN_MS, step)
        self._hold = self.after(MSG_HOLD_MS, self._hide)

    def _hide(self):
        self._hold = None
        s0, a0 = self.shift, self.msg_alpha

        def step(k):
            self.shift = s0 * (1 - k)
            self.msg_alpha = a0 * (1 - k)
            self._layout()
        animate(self, MSG_OUT_MS, step)
