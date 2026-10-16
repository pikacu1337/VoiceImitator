import json
import queue
import shutil
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from app import audio, cable_install, theme
from app.chrome_ui import Footer, TabStrip, TitleBar
from app.glass import Clear, Dropdown, GlassPanel, GlassView, Text, scale_of
from app.paths import DATA_DIR, SETTINGS_PATH
from app.picker import AccentPicker
from app.slider import Slider
from app.tts import PRESETS, VOICES, TTSEngine, download_model
from app.window import Chrome

APP_NAME = "VoiceImitator"
HISTORY_SIZE = 30
PAD = 24   # space-8: поля окна
GAP = 14   # space-4: промежуток между панелями
COL_TEXT = 380  # ширина переноса подписей в панели половинной ширины

DEFAULT_SETTINGS = {
    "voice": "Евгений (мужской)",
    "speed": 1.08,
    "pitch": -2.0,
    "volume": 1.0,
    "accent": theme.DEFAULT_ACCENT,
    "accent_hue": None,
    "bg_mode": "picture",     # picture / custom / sky
    "bg_custom": "",
    "bg_brightness": 50,      # яркость картинки-фона, %
    "bg_blur": 0,             # размытие картинки-фона, %
    "glass_blur": 60,         # размытие стекла, %
    "cable": "",
    "monitor_on": True,
    "monitor": "",
    "mic_on": False,
    "mic": "",
    "mic_volume": 1.0,
    "history": [],
}


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULT_SETTINGS, **{k: v for k, v in data.items() if k in DEFAULT_SETTINGS}}


def save_settings(data: dict) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# ======================================================================
# Контролы в стиле Night Glass. Цвета углов и фона подставит стекло (glass.tint).
# ======================================================================

class Kit:
    def __init__(self, app):
        self.app = app

    def label(self, master, text, spec=theme.F_LABEL, color=theme.TEXT, **kw):
        return Text(master, text, spec, color, **kw)

    def solid(self, master, text, cmd, width=140, height=38):
        return ctk.CTkButton(master, text=text, command=cmd, width=width, height=height,
                             corner_radius=theme.R_PILL, fg_color=theme.SOLID,
                             hover_color=theme.SOLID_HOVER, text_color=theme.ON_SOLID,
                             text_color_disabled="#5a5a5a", font=self.app.font(theme.F_BUTTON))

    def ghost(self, master, text, cmd, width=110, height=34):
        b = ctk.CTkButton(master, text=text, command=cmd, width=width, height=height,
                          corner_radius=theme.R_PILL, fg_color="transparent", border_width=1,
                          border_color=theme.EDGE, text_color=theme.TEXT,
                          font=self.app.font(theme.F_BUTTON))
        b.ng_kind = "ghost"
        return b

    def menu(self, master, values, cmd):
        return Dropdown(master, values=values, command=cmd, height=34,
                        corner_radius=theme.R_PILL, text_color=theme.TEXT,
                        font=self.app.font(theme.F_BUTTON), dynamic_resizing=False,
                        dropdown_fg_color=theme.GLASS_2, dropdown_hover_color=theme.WASH,
                        dropdown_text_color=theme.TEXT, dropdown_font=self.app.font(theme.F_BUTTON))

    def switch(self, master, text, cmd, on, accent_list):
        """Переключатель 40×22 и подпись справа, нарисованная на стекле."""
        row = Clear(master)
        sw = ctk.CTkSwitch(row, text="", command=cmd, width=40, switch_width=40, switch_height=22,
                           progress_color=theme.accent_soft(self.app.accent),
                           button_color=theme.SWITCH_KNOB, button_hover_color=theme.SWITCH_KNOB)
        try:
            sw._text_label.grid_forget()
        except Exception:
            pass
        if on:
            sw.select()
        sw.grid(row=0, column=0)
        lbl = Text(row, text, theme.F_BODY, theme.MUTED)
        lbl.grid(row=0, column=1, padx=(10, 0))
        lbl.configure(cursor="hand2")
        lbl.bind("<Button-1>", lambda _e: sw.toggle())
        accent_list.append(("switch", sw))
        return row, sw


# ======================================================================
# Экран загрузки
# ======================================================================

class LoadingView(GlassView):
    def __init__(self, master, app):
        super().__init__(master, app)
        k = Kit(app)
        self.grid_columnconfigure(0, weight=1)
        TitleBar(self, app).grid(row=0, column=0, sticky="ew")
        panel = GlassPanel(self)
        panel.place(relx=0.5, rely=0.5, anchor="center")
        k.label(panel, "VoiceImitator", theme.F_STATUS).grid(row=0, column=0, padx=56, pady=(40, 14))
        self.status = k.label(panel, "Запуск…", theme.F_BODY, theme.MUTED)
        self.status.grid(row=1, column=0, pady=6)
        self.bar = ctk.CTkProgressBar(panel, width=360, progress_color=app.accent)
        self.bar.set(0)
        self.bar.grid(row=2, column=0, padx=56, pady=(8, 44))
        self.bar.configure(mode="indeterminate")
        self.bar.start()
        threading.Thread(target=self._prepare, daemon=True).start()

    def _set(self, text):
        self.app.after(0, lambda: self.status.configure(text=text))

    def _progress(self, frac):
        def upd():
            self.bar.configure(mode="determinate")
            self.bar.set(frac)
        self.app.after(0, upd)

    def _prepare(self):
        engine = self.app.engine
        if not engine.model_present:
            self._set("Скачиваю голосовую модель (~40 МБ), это один раз…")
            try:
                download_model(self._progress)
            except Exception as e:
                self._set(f"Не удалось скачать модель: {e}")
                return
        self._set("Загружаю голос…")
        try:
            engine.load()
        except Exception as e:
            self._set(f"Ошибка загрузки модели: {e}")
            return
        self.app.after(0, self.app.show_main)


# ======================================================================
# Главный экран
# ======================================================================

class MainView(GlassView):
    TABS = ["Озвучка", "Настройки", "Оформление"]

    def __init__(self, master, app):
        super().__init__(master, app)
        self.k = Kit(app)
        self.s = app.settings
        self.engine: TTSEngine = app.engine
        self.router = audio.AudioRouter()
        self.jobs: queue.Queue = queue.Queue()
        self.results: queue.Queue = queue.Queue()
        self.out_devices = []
        self.in_devices = []
        self.accent_widgets = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self.areas = {
            "Озвучка": self._build_speak_area(),
            "Настройки": self._build_settings_area(),
            "Оформление": self._build_look_area(),
        }

        # внизу — только строка версии, сообщения проявляются под ней
        self.footer = Footer(self, app)
        self.footer.grid(row=2, column=0, sticky="ew", padx=PAD, pady=(0, round(8 * scale_of(self))))

        self.refresh_devices()
        self.apply_audio_settings()
        self.apply_accent()
        self.switch_tab("Озвучка")

        threading.Thread(target=self._worker, daemon=True).start()
        self.after(60, self._poll)

    # ---------- заголовок с вкладками ----------

    def _build_header(self):
        # вместо системного заголовка: вкладки по центру, кнопки окна справа, прямо на фоне
        bar = TitleBar(self, self.app)
        bar.grid(row=0, column=0, sticky="ew")
        self.tabs = TabStrip(bar, self.TABS, self.switch_tab, self.app)
        self.tabs.place(relx=0.5, rely=0.5, anchor="center")

    def _two_columns(self):
        area = Clear(self)
        area.grid_columnconfigure((0, 1), weight=1, uniform="cols")
        cols = Clear(area), Clear(area)
        cols[0].grid(row=0, column=0, sticky="new", padx=(0, GAP // 2))
        cols[1].grid(row=0, column=1, sticky="new", padx=(GAP // 2, 0))
        for c in cols:
            c.grid_columnconfigure(0, weight=1)
        return area, cols

    def _section(self, col, row, title):
        p = GlassPanel(col)
        p.grid(row=row, column=0, sticky="ew", pady=(0 if row == 0 else GAP, 0))
        p.grid_columnconfigure(0, weight=1)
        self.k.label(p, title, theme.F_PANEL).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 8))
        return p

    # ---------- вкладка «Озвучка» ----------

    def _build_speak_area(self):
        area = Clear(self)
        area.grid_columnconfigure(0, weight=3)
        area.grid_columnconfigure(1, weight=2)

        p = GlassPanel(area)
        p.grid(row=0, column=0, sticky="new", padx=(0, GAP // 2))
        p.grid_columnconfigure(0, weight=1)
        self.k.label(p, "Текст", theme.F_PANEL).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 8))
        self.text = ctk.CTkTextbox(p, height=120, wrap="word", text_color=theme.TEXT,
                                   border_color=theme.EDGE, border_width=1,
                                   corner_radius=theme.R_PILL, font=self.app.font(theme.F_LABEL))
        self.text.grid(row=1, column=0, sticky="ew", padx=20)
        self.text.bind("<Control-Return>", lambda _e: (self.speak(), "break")[1])

        btns = Clear(p)
        btns.grid(row=2, column=0, sticky="ew", padx=20, pady=12)
        btns.grid_columnconfigure(0, weight=1)
        self.speak_btn = self.k.solid(btns, "Озвучить   Ctrl+Enter", self.speak, height=42)
        self.speak_btn.configure(font=self.app.font(theme.F_LABEL))
        self.speak_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.k.ghost(btns, "Стоп", self.stop, width=96, height=42).grid(row=0, column=1)

        self.k.label(p, "История — нажмите, чтобы повторить", theme.F_CAPTION, theme.FAINT)\
            .grid(row=3, column=0, sticky="w", padx=20, pady=(0, 6))
        self.history_box = ctk.CTkScrollableFrame(p, height=120, corner_radius=theme.R_ROW,
                                                  scrollbar_button_color=theme.EDGE)
        self.history_box._parent_frame.ng_kind = "scroll"
        self.history_box._parent_frame.ng_scroll = self.history_box
        self.history_box.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 20))
        self.render_history()

        v = GlassPanel(area)
        v.grid(row=0, column=1, sticky="new", padx=(GAP // 2, 0))
        v.grid_columnconfigure(0, weight=1)
        self.k.label(v, "Голос", theme.F_PANEL).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 8))
        self.preset = self.k.menu(v, list(PRESETS.keys()), self.apply_preset)
        self.preset.set("Пресеты…")
        self.preset.grid(row=1, column=0, sticky="ew", padx=20, pady=4)
        self.voice = self.k.menu(v, list(VOICES.keys()), lambda _v: self.save())
        self.voice.set(self.s["voice"])
        self.voice.grid(row=2, column=0, sticky="ew", padx=20, pady=4)
        self.speed_lbl, self.speed = self._slider(v, 3, "Скорость", 0.5, 1.5, self.s["speed"], "x")
        self.pitch_lbl, self.pitch = self._slider(v, 5, "Тон", -12, 12, self.s["pitch"], " пт")
        self.vol_lbl, self.vol = self._slider(v, 7, "Громкость", 0.0, 1.0, self.s["volume"], "%",
                                              pct=True, cmd=self.on_volume)
        Clear(v, height=14).grid(row=9, column=0)
        return area

    # ---------- вкладка «Настройки»: звук ----------

    def _build_settings_area(self):
        area, (col0, col1) = self._two_columns()

        p = self._section(col0, 0, "Микрофон для Discord")
        self.cable = self.k.menu(p, [""], self.on_cable_change)
        self.cable.grid(row=1, column=0, sticky="ew", padx=20, pady=4)
        self.cable_warn = self.k.label(p, "", theme.F_CAPTION, theme.MUTED, wraplength=COL_TEXT)
        self.cable_warn.grid(row=2, column=0, sticky="w", padx=20, pady=(6, 0))
        self.cable_btn = self.k.solid(p, "Установить кабель", self.install_cable, width=170, height=34)
        self.cable_credit = self.k.label(p, cable_install.CREDIT, theme.F_SMALL, theme.FAINT, wraplength=COL_TEXT)
        Clear(p, height=16).grid(row=9, column=0)

        p = self._section(col1, 0, "Слышать озвучку в наушниках")
        row, self.monitor_sw = self.k.switch(p, "Включено", self.on_monitor_toggle, self.s["monitor_on"],
                                             self.accent_widgets)
        row.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 10))
        self.monitor = self.k.menu(p, [""], self.on_monitor_change)
        self.monitor.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))

        p = self._section(col1, 1, "Пускать мой микрофон в кабель")
        self.k.label(p, "Друзья услышат и озвучку, и ваш живой голос", theme.F_CAPTION, theme.MUTED,
                     wraplength=COL_TEXT).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 10))
        row, self.mic_sw = self.k.switch(p, "Включено", self.on_mic_toggle, self.s["mic_on"], self.accent_widgets)
        row.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 10))
        self.mic = self.k.menu(p, [""], self.on_mic_change)
        self.mic.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 20))

        self.k.ghost(col1, "Обновить устройства", self.rescan, width=180)\
            .grid(row=2, column=0, sticky="w", pady=(GAP, 0))
        return area

    # ---------- вкладка «Оформление»: акцент, фон, стекло ----------

    def _build_look_area(self):
        area, (col0, col1) = self._two_columns()

        p = self._section(col0, 0, "Цвет-акцент")
        self.k.label(p, "Красит то, что работает: вкладку, ползунки, переключатели",
                     theme.F_CAPTION, theme.MUTED, wraplength=COL_TEXT)\
            .grid(row=1, column=0, sticky="w", padx=20, pady=(0, 12))
        self.picker = AccentPicker(p, self.app.accent, self.s.get("accent_hue"),
                                   self.on_accent_drag, self.flash)
        self.picker.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))

        p = self._section(col1, 0, "Фон и стекло")
        seg = Clear(p)
        seg.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 6))
        seg.grid_columnconfigure((0, 1, 2), weight=1, uniform="seg")
        self.bg_buttons = {}
        for i, (mode, title) in enumerate((("picture", "Картинка"), ("custom", "Своя картинка…"),
                                           ("sky", "Звёздное небо"))):
            b = self.k.ghost(seg, title, lambda m=mode: self.set_bg_mode(m), width=10, height=32)
            b.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0))
            self.bg_buttons[mode] = b
        self.bg_hint = self.k.label(p, "", theme.F_CAPTION, theme.FAINT, wraplength=COL_TEXT)
        self.bg_hint.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 2))

        self.bright_lbl, self.bright = self._slider(p, 3, "Яркость фона", 0, 100, self.s["bg_brightness"], "%int",
                                                    cmd=lambda: self.on_look("bg_brightness", self.bright),
                                                    steps=100, accent=True)
        self.bgblur_lbl, self.bgblur = self._slider(p, 5, "Размытие фона", 0, 100, self.s["bg_blur"], "%int",
                                                    cmd=lambda: self.on_look("bg_blur", self.bgblur),
                                                    steps=100, accent=True)
        self.glass_lbl, self.glassblur = self._slider(p, 7, "Размытие стекла", 0, 100, self.s["glass_blur"],
                                                      "%int", cmd=lambda: self.on_look("glass_blur", self.glassblur),
                                                      steps=100, accent=True)
        self.k.ghost(p, "Сбросить", self.reset_look, width=110, height=32)\
            .grid(row=9, column=0, sticky="w", padx=20, pady=(16, 20))
        self._sync_bg_buttons()
        return area

    # ---------- общие ----------

    def _slider(self, parent, row, title, lo, hi, value, unit, pct=False, cmd=None, steps=None, accent=True):
        head = Clear(parent)
        head.grid(row=row, column=0, sticky="ew", padx=20, pady=(12, 2))
        head.grid_columnconfigure(0, weight=1)
        self.k.label(head, title).grid(row=0, column=0, sticky="w")
        lbl = self.k.label(head, "", theme.F_CAPTION, theme.MUTED)
        lbl.grid(row=0, column=1, sticky="e")
        sl = Slider(parent, from_=lo, to=hi, number_of_steps=steps, progress_color=self.app.accent,
                    command=lambda _v: (self._fmt(lbl, unit, pct, sl.get()),
                                        (cmd() if cmd else None), self.save()))
        sl.set(value)
        sl.grid(row=row + 1, column=0, sticky="ew", padx=16)
        self._fmt(lbl, unit, pct, value)
        self.accent_widgets.append(("slider", sl))
        return lbl, sl

    @staticmethod
    def _fmt(lbl, unit, pct, value):
        if pct:
            lbl.configure(text=f"{int(round(value * 100))}%")
        elif unit == "%int":
            lbl.configure(text=f"{int(round(value))}%")
        elif unit == " пт":
            lbl.configure(text=f"{value:+.0f} пт")
        else:
            lbl.configure(text=f"{value:.2f}{unit}")

    def apply_preset(self, name):
        voice, speed, pitch = PRESETS[name]
        self.voice.set(voice)
        self.speed.set(speed)
        self.pitch.set(pitch)
        self._fmt(self.speed_lbl, "x", False, speed)
        self._fmt(self.pitch_lbl, " пт", False, pitch)
        self.preset.set("Пресеты…")
        self.save()

    # ---------- вкладки / акцент ----------

    def switch_tab(self, name):
        for area in self.areas.values():
            area.grid_remove()
        self.areas[name].grid(row=1, column=0, sticky="nsew", padx=PAD, pady=(0, GAP))
        self.recompose_later()

    def on_accent_drag(self, color, hue):
        self.app.accent = color
        self.s["accent"] = color
        self.s["accent_hue"] = hue
        self.apply_accent()
        if getattr(self, "_save_job", None):
            self.after_cancel(self._save_job)
        self._save_job = self.after(400, self.save)

    def apply_accent(self):
        a = self.app.accent
        soft = theme.accent_soft(a)
        self.tabs.restyle_accent()
        for kind, w in self.accent_widgets:
            if kind == "slider":
                w.configure(progress_color=a, button_color=a, button_hover_color=a)
            else:
                w.configure(progress_color=soft)
        if hasattr(self, "bg_buttons"):
            self._sync_bg_buttons()

    # ---------- фон и стекло ----------

    def _sync_bg_buttons(self):
        mode = self.s["bg_mode"]
        for m, b in self.bg_buttons.items():
            on = m == mode
            b.ng_selected = self.app.accent if on else None
            b.configure(text_color=theme.TEXT if on else theme.MUTED)
            if on:
                b.configure(border_color=self.app.accent)
            elif hasattr(b, "ng_avg"):
                b.configure(border_color=_edge(b.ng_avg))
        picture = mode != "sky"
        self.bright.configure(state="normal" if picture else "disabled")
        hints = {
            "picture": "Грозовое небо над полем",
            "custom": Path(self.s["bg_custom"]).name or "Своя картинка",
            "sky": "Яркость действует только на картинку",
        }
        self.bg_hint.configure(text=hints[mode])

    def set_bg_mode(self, mode):
        if mode == "custom":
            path = filedialog.askopenfilename(
                title="Картинка для фона",
                filetypes=[("Картинки", "*.jpg *.jpeg *.png *.bmp *.webp"), ("Все файлы", "*.*")])
            if not path:
                return
            dst = DATA_DIR / ("custom_backdrop" + Path(path).suffix.lower())
            try:
                for old in DATA_DIR.glob("custom_backdrop.*"):
                    if old != dst:
                        old.unlink(missing_ok=True)
                shutil.copyfile(path, dst)
            except OSError as e:
                self.flash(f"Не удалось взять картинку: {e}")
                return
            self.s["bg_custom"] = str(dst)
            self.flash(f"Фон: {Path(path).name}")
        self.s["bg_mode"] = mode
        self._sync_bg_buttons()
        self.save()
        self.recompose_later(10)

    def on_look(self, key, slider):
        self.s[key] = int(round(slider.get()))
        self.recompose_later(120)

    def reset_look(self):
        for key, sl, lbl in (("bg_brightness", self.bright, self.bright_lbl),
                             ("bg_blur", self.bgblur, self.bgblur_lbl),
                             ("glass_blur", self.glassblur, self.glass_lbl)):
            self.s[key] = DEFAULT_SETTINGS[key]
            sl.set(self.s[key])
            self._fmt(lbl, "%int", False, self.s[key])
        self.s["bg_mode"] = "picture"
        self._sync_bg_buttons()
        self.save()
        self.recompose_later(10)

    # ---------- устройства ----------

    def refresh_devices(self):
        self.out_devices = audio.list_devices("output")
        self.in_devices = audio.list_devices("input")
        out_names = [d.name for d in self.out_devices] or [""]
        in_names = [d.name for d in self.in_devices] or [""]

        cable = audio.find_cable(self.out_devices)
        chosen = self.s["cable"] if self.s["cable"] in out_names else (cable.name if cable else "")
        self.cable.configure(values=out_names)
        self.cable.set(chosen or "Не выбрано")
        self._update_cable_warning(chosen)

        mon = audio.default_device("output", self.out_devices)
        cm = self.s["monitor"] if self.s["monitor"] in out_names else (mon.name if mon else "")
        self.monitor.configure(values=out_names)
        self.monitor.set(cm or "Не выбрано")

        md = audio.default_device("input", self.in_devices)
        cmic = self.s["mic"] if self.s["mic"] in in_names else (md.name if md else "")
        self.mic.configure(values=in_names)
        self.mic.set(cmic or "Не выбрано")

    def _update_cable_warning(self, name):
        found = bool(name and audio.is_cable(name))
        missing = not audio.find_cable(self.out_devices)
        if found:
            text = "Кабель найден. В Discord выберите CABLE Output как устройство ввода"
        elif missing:
            text = ("Виртуальный кабель не найден. Нажмите «Установить кабель» — откроется окно "
                    "VB-CABLE, там нажмите «Install Driver»")
        else:
            text = "Выбранное устройство не похоже на кабель — Discord не услышит озвучку"
        self.cable_warn.configure(text=text)
        if missing and not found:
            self.cable_btn.grid(row=3, column=0, sticky="w", padx=20, pady=(12, 2))
            self.cable_credit.grid(row=4, column=0, sticky="w", padx=20, pady=(4, 0))
        else:
            self.cable_btn.grid_remove()
            self.cable_credit.grid_remove()
        self.recompose_later()

    def _dev(self, devices, name):
        return next((d for d in devices if d.name == name), None)

    def apply_audio_settings(self):
        self.router.set_cable(self._dev(self.out_devices, self.cable.get()))
        self.router.set_monitor(self._dev(self.out_devices, self.monitor.get())
                                if self.monitor_sw.get() else None)
        self.router.set_mic(self._dev(self.in_devices, self.mic.get()) if self.mic_sw.get() else None)
        self.router.set_volume(self.vol.get())
        self.router.mic_volume = self.s["mic_volume"]

    def rescan(self):
        self.router.close()
        audio.rescan_devices()
        self.refresh_devices()
        self.apply_audio_settings()
        self.flash("Список устройств обновлён")

    def on_cable_change(self, _v):
        self._update_cable_warning(self.cable.get())
        self.router.set_cable(self._dev(self.out_devices, self.cable.get()))
        self.router.set_volume(self.vol.get())
        self.save()

    def on_monitor_toggle(self):
        self.on_monitor_change(None)

    def on_monitor_change(self, _v):
        self.router.set_monitor(self._dev(self.out_devices, self.monitor.get())
                                if self.monitor_sw.get() else None)
        self.router.set_volume(self.vol.get())
        self.save()

    def on_mic_toggle(self):
        self.on_mic_change(None)

    def on_mic_change(self, _v):
        self.router.set_mic(self._dev(self.in_devices, self.mic.get()) if self.mic_sw.get() else None)
        self.router.mic_volume = self.s["mic_volume"]
        self.save()

    def on_volume(self):
        self.router.set_volume(self.vol.get())

    # ---------- установка кабеля ----------

    def install_cable(self):
        self.cable_btn.configure(state="disabled", text="Открываю установщик…")
        self.cable_warn.configure(text="Подтвердите запрос прав Windows, затем нажмите «Install Driver»")

        def work():
            started, msg = cable_install.open_installer()
            self.after(0, lambda: self.cable_warn.configure(text=msg))
            if not started:
                self.after(0, lambda: self.cable_btn.configure(state="normal", text="Установить кабель"))
                return
            self.after(0, lambda: self.cable_btn.configure(text="Жду установки…"))
            ok = cable_install.wait_for_cable()
            self.after(0, lambda: self._after_install(ok))

        threading.Thread(target=work, daemon=True).start()

    def _after_install(self, ok):
        if not ok:
            self.cable_btn.configure(state="normal", text="Установить кабель")
            self.cable_warn.configure(text="Пока не вижу кабель. Если ставили — иногда нужна перезагрузка, "
                                           "после неё нажмите «Обновить устройства»")
            return
        self.router.close()
        self.refresh_devices()
        cable = audio.find_cable(self.out_devices)
        if cable:
            self.cable.set(cable.name)
            self._update_cable_warning(cable.name)
        self.apply_audio_settings()
        self.save()

    # ---------- озвучка ----------

    def speak(self, text=None):
        if text is None:
            text = self.text.get("1.0", "end").strip()
        if not text:
            return
        self.add_history(text)
        self.jobs.put(text)

    def stop(self):
        self.router.stop()

    def _worker(self):
        while True:
            text = self.jobs.get()
            self.results.put(("busy", True))
            try:
                audio_data = self.engine.synthesize(text, VOICES[self.voice.get()],
                                                     self.speed.get(), self.pitch.get())
                self.router.play(audio_data)
            except Exception as e:
                self.results.put(("error", str(e)))
            finally:
                self.results.put(("busy", False))

    def _poll(self):
        try:
            while True:
                kind, value = self.results.get_nowait()
                if kind == "busy":
                    self.speak_btn.configure(text="Озвучиваю…" if value else "Озвучить   Ctrl+Enter",
                                             state="disabled" if value else "normal")
                elif kind == "error":
                    self.flash(f"Ошибка: {value}")
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def flash(self, text):
        self.footer.flash(text)

    # ---------- история ----------

    def add_history(self, text):
        h = self.s["history"]
        if text in h:
            h.remove(text)
        h.insert(0, text)
        del h[HISTORY_SIZE:]
        self.render_history()
        self.save()

    def render_history(self):
        for w in self.history_box.winfo_children():
            w.destroy()
        for item in self.s["history"]:
            preview = item if len(item) <= 52 else item[:51] + "…"
            ctk.CTkButton(self.history_box, text=preview, anchor="w", height=28,
                          corner_radius=theme.R_ROW, fg_color="transparent", hover_color=theme.WASH,
                          text_color=theme.MUTED, font=self.app.font(theme.F_LIST),
                          command=lambda t=item: self.speak(t)).pack(fill="x", pady=1)

    # ---------- сохранение ----------

    def save(self):
        self.s.update({
            "voice": self.voice.get(), "speed": round(self.speed.get(), 3),
            "pitch": round(self.pitch.get(), 1), "volume": round(self.vol.get(), 3),
            "accent": self.app.accent, "cable": self.cable.get(),
            "monitor_on": bool(self.monitor_sw.get()), "monitor": self.monitor.get(),
            "mic_on": bool(self.mic_sw.get()), "mic": self.mic.get(),
        })
        save_settings(self.s)

    def close(self):
        self.save()
        self.router.close()


def _edge(avg):
    from app.glass import blend
    return blend(avg, "#ffffff", 0.16)


# ======================================================================
# Окно
# ======================================================================

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title(APP_NAME)
        self.minsize(900, 640)
        self.configure(fg_color=theme.WINDOW)
        # без системного заголовка — вкладки и кнопки окна в своей полосе сверху
        self.chrome = Chrome(self)
        self.chrome.on_close = self.on_close
        s = ctk.ScalingTracker.get_window_scaling(self)
        self.chrome.center(round(1000 * s), round(700 * s))

        self.settings = load_settings()
        self.accent = self.settings.get("accent", theme.DEFAULT_ACCENT)
        self.engine = TTSEngine()
        self._fonts = {}
        self.view = None

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.start_loading()

    def font(self, spec):
        size, weight = spec
        if spec not in self._fonts:
            self._fonts[spec] = ctk.CTkFont(family=theme.FONT_UI, size=size, weight=weight)
        return self._fonts[spec]

    def show(self, view):
        if isinstance(self.view, MainView):
            self.view.close()
        if self.view is not None:
            self.view.destroy()
        self.view = view
        view.grid(row=0, column=0, sticky="nsew")
        self.chrome.attach(view, drag=False)  # поля окна — за них меняется размер

    def start_loading(self):
        self.show(LoadingView(self, self))

    def show_main(self):
        self.show(MainView(self, self))

    def on_close(self):
        if isinstance(self.view, MainView):
            self.view.close()
        self.destroy()


def run():
    App().mainloop()


if __name__ == "__main__":
    run()
