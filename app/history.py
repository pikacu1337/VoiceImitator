"""История фраз — один холст вместо списка кнопок.

Раньше каждая строка была CTkButton (два окна Windows на строку) в CTkScrollableFrame:
при растягивании окна они перерисовывались по одной, и на это уходила половина
времени кадра. Теперь поле — картинка (стекло под ним + заливка поля + обводка),
строки — надписи на том же холсте, прокрутка — сдвиг надписей."""

import tkinter.font as tkfont

from PIL import Image, ImageTk

from app import theme
from app.glass import Clear, _hex, _rgb, blend, masks, scale_of

ROW = 30      # шаг строки (высота 28 + промежуток 2)
ROW_H = 28
PAD = 6       # поле вокруг строк
TEXT_X = 11   # отступ текста внутри строки
BAR_W = 6     # полоса прокрутки
WHEEL = 3 * ROW


def _round_rect(x0, y0, x1, y1, r):
    """Точки скруглённого прямоугольника для create_polygon(smooth=True)."""
    return (x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
            x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0)


class HistoryList(Clear):
    def __init__(self, master, on_pick, rows_visible: int = 7, font_spec=theme.F_LIST):
        self.s = scale_of(master)
        s = self.s
        super().__init__(master, height=round((2 * PAD + rows_visible * ROW) * s), cursor="arrow")
        self.on_pick = on_pick
        self.items: list[str] = []
        self.offset = 0.0        # прокрутка, px
        self.hover = None
        self._drag = None
        self._piece = None
        self._field = theme.FIELD
        size, weight = font_spec
        self._font = tkfont.Font(family=theme.FONT_UI, size=-round(size * s), weight=weight)
        self._texts = []
        self._hl = self.create_polygon(0, 0, 0, 0, smooth=True, fill="", outline="", state="hidden")
        # верх и низ поля — куски картинки поверх строк: строки «уходят» под край, как в прокрутке
        self._cap_top = self.create_image(0, 0, anchor="nw")
        self._cap_bot = self.create_image(0, 0, anchor="nw")
        self._caps = (None, None)
        self._bar = self.create_polygon(0, 0, 0, 0, smooth=True, fill="", outline="", state="hidden")
        self.bind("<Configure>", lambda _e: self._layout(), add="+")
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag_bar)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<MouseWheel>", self._wheel)

    # ---------- данные ----------

    def set_items(self, items: list[str]):
        if items == self.items:
            return
        self.items = list(items)
        while len(self._texts) < len(self.items):
            self._texts.append(self.create_text(0, 0, anchor="w", font=self._font, fill=theme.MUTED))
        while len(self._texts) > len(self.items):
            self.delete(self._texts.pop())
        self._clamp()
        self._layout()

    # ---------- геометрия ----------

    def _inner(self):
        s = self.s
        return PAD * s, self.winfo_height() - PAD * s

    def _content_h(self):
        return len(self.items) * ROW * self.s

    def _view_h(self):
        top, bottom = self._inner()
        return max(1.0, bottom - top)

    def _clamp(self):
        self.offset = max(0.0, min(self.offset, self._content_h() - self._view_h()))

    def _row_at(self, y):
        top, bottom = self._inner()
        if not top <= y < bottom:
            return None
        i = int((y - top + self.offset) // (ROW * self.s))
        if 0 <= i < len(self.items) and (y - top + self.offset) - i * ROW * self.s < ROW_H * self.s:
            return i
        return None

    def _fit(self, text, width):
        if self._font.measure(text) <= width:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._font.measure(text[:mid].rstrip() + "…") <= width:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo].rstrip() + "…"

    def _bar_rect(self):
        content, view = self._content_h(), self._view_h()
        if content <= view + 0.5:
            return None
        s = self.s
        top, _ = self._inner()
        x1 = self.winfo_width() - (PAD + 2) * s
        h = max(24 * s, view * view / content)
        y = top + (view - h) * (self.offset / (content - view))
        return x1 - BAR_W * s, y, x1, y + h

    def _layout(self):
        w = self.winfo_width()
        if w < 20:
            return
        s = self.s
        top, _ = self._inner()
        bar = self._bar_rect()
        text_w = w - 2 * PAD * s - 2 * TEXT_X * s - ((BAR_W + 6) * s if bar else 0)
        x = (PAD + TEXT_X) * s
        for i, (t, item) in enumerate(zip(self._texts, self.items)):
            y = top + i * ROW * s - self.offset + ROW_H * s / 2
            self.coords(t, x, y)
            self.itemconfigure(t, text=self._fit(item.replace("\n", " "), text_w))
        if bar:
            self.coords(self._bar, *_round_rect(*bar, BAR_W * s / 2))
            self.itemconfigure(self._bar, state="normal")
        else:
            self.itemconfigure(self._bar, state="hidden")
        self._paint_hover()
        self._stack()

    def _stack(self):
        self.tag_raise(self._cap_top)
        self.tag_raise(self._cap_bot)
        self.tag_raise(self._bar)

    # ---------- картинка ----------

    def show(self, pil, avg=None) -> bool:
        if not super().show(pil, avg):
            return False
        self._render(pil)
        return True

    def _render(self, pil):
        """Поле — то же матовое стекло, что у текстового поля: чуть темнее панели, обводка еле видна."""
        avg = _hex(pil.resize((1, 1), Image.BOX).getpixel((0, 0)))
        w, h = pil.size
        r = min(round(theme.R_ROW * self.s), w // 2, h // 2)
        fill, ring = masks(w, h, r)
        self._field = blend(avg, "#000000", 0.16)
        img = pil.convert("RGB")
        img.paste(_rgb(self._field), (0, 0), fill)
        img.paste(_rgb(blend(avg, "#ffffff", 0.09)), (0, 0), ring)
        self._img = ImageTk.PhotoImage(img)
        self.itemconfigure(self._item, image=self._img)
        top, bottom = self._inner()
        t, b = round(top), round(bottom)
        caps = (ImageTk.PhotoImage(img.crop((0, 0, w, t))), ImageTk.PhotoImage(img.crop((0, b, w, h))))
        self._caps = caps
        self.itemconfigure(self._cap_top, image=caps[0])
        self.coords(self._cap_bot, 0, b)
        self.itemconfigure(self._cap_bot, image=caps[1])
        self.itemconfigure(self._bar, fill=blend(self._field, "#ffffff", 0.16))
        self._paint_hover()
        self._stack()

    # ---------- ввод ----------

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.configure(cursor="hand2" if i is not None else "arrow")
            self._paint_hover()

    def _paint_hover(self):
        for j, t in enumerate(self._texts):
            self.itemconfigure(t, fill=theme.TEXT if j == self.hover else theme.MUTED)
        if self.hover is None or self.hover >= len(self.items):
            self.itemconfigure(self._hl, state="hidden")
            return
        s = self.s
        top, _ = self._inner()
        y0 = top + self.hover * ROW * s - self.offset
        x1 = self.winfo_width() - PAD * s - ((BAR_W + 6) * s if self._bar_rect() else 0)
        self.coords(self._hl, *_round_rect(PAD * s, y0, x1, y0 + ROW_H * s, theme.R_ROW * s))
        self.itemconfigure(self._hl, state="normal", fill=blend(self._field, "#ffffff", 0.07))
        self.tag_lower(self._hl, self._texts[0])
        self._stack()

    def _on_bar(self, e):
        bar = self._bar_rect()
        return bar and bar[0] - 4 * self.s <= e.x <= bar[2] + 4 * self.s

    def _motion(self, e):
        if self._drag is None:
            self._set_hover(None if self._on_bar(e) else self._row_at(e.y))

    def _press(self, e):
        if self._on_bar(e):
            bar = self._bar_rect()
            if not bar[1] <= e.y <= bar[3]:   # щелчок мимо ползунка — прыгнуть к месту
                self._scroll_to_bar(e.y - (bar[3] - bar[1]) / 2)
                bar = self._bar_rect()
            self._drag = e.y - bar[1]

    def _drag_bar(self, e):
        if self._drag is not None:
            self._scroll_to_bar(e.y - self._drag)

    def _scroll_to_bar(self, bar_top):
        content, view = self._content_h(), self._view_h()
        top, _ = self._inner()
        bar = self._bar_rect()
        span = view - (bar[3] - bar[1])
        self.offset = (bar_top - top) / max(1.0, span) * (content - view)
        self._clamp()
        self._layout()

    def _release(self, e):
        if self._drag is not None:
            self._drag = None
            return
        i = self._row_at(e.y)
        if i is not None and i == self.hover:
            self.on_pick(self.items[i])

    def _wheel(self, e):
        self.offset -= e.delta / 120 * WHEEL * self.s
        self._clamp()
        self._layout()
        self._set_hover(self._row_at(e.y))
