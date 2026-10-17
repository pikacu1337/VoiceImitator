"""Мастер установки и удаления в стиле Night Glass — по образцу визарда ZapretLauncher:
Добро пожаловать → Параметры → Установка → Готово; удаление — своей страницей."""

import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from app import __version__, installer, theme
from app.chrome_ui import Footer, TitleBar
from app.glass import Clear, GlassPanel, GlassView, Text, scale_of
from app.window import Chrome

W, H = 760, 540
WRAP = 600

LOOK_DEFAULTS = {"accent": theme.DEFAULT_ACCENT, "bg_mode": "picture", "bg_custom": "",
                 "bg_brightness": 50, "bg_blur": 0, "glass_blur": 60}


def _look() -> dict:
    """Оформление берём из настроек программы, если она уже стояла — мастер выглядит так же."""
    path = Path(os.environ.get("APPDATA", Path.home())) / "VoiceImitator" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {k: data.get(k, v) for k, v in LOOK_DEFAULTS.items()}


class Wizard(GlassView):
    def __init__(self, master, app, mode: str, remove_dir: Path | None):
        super().__init__(master, app)
        self.mode = mode
        self.remove_dir = remove_dir
        self.failed = False
        self.installed_exe = None
        s = scale_of(self)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        caption = " · установка" if mode == "install" else " · удаление"
        TitleBar(self, app, maximizable=False, caption=caption).grid(row=0, column=0, sticky="ew")

        self.card = GlassPanel(self)
        self.card.grid(row=1, column=0, sticky="nsew", padx=24, pady=(4, 0))
        self.card.grid_columnconfigure(0, weight=1)
        self.card.grid_rowconfigure(0, weight=1)
        self.page = Clear(self.card)
        self.page.grid(row=0, column=0, sticky="nsew", padx=36, pady=(30, 0))
        self.page.grid_columnconfigure(0, weight=1)

        nav = Clear(self.card)
        nav.grid(row=1, column=0, sticky="ew", padx=36, pady=(0, 26))
        nav.grid_columnconfigure(0, weight=1)
        self.step = Text(nav, "", theme.F_CAPTION, theme.FAINT)
        self.step.grid(row=0, column=0, sticky="w")
        self.back = self._ghost(nav, "Назад", self.on_back)
        self.next = self._solid(nav, "Далее", self.on_next)
        self.footer = Footer(self, app)
        self.footer.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, round(4 * s)))

        self.desktop = True
        self.launch = True
        self.keep = True
        self._inbox = queue.Queue()
        self.after(40, self._drain)
        self.dir = installer.existing_dir() or installer.default_dir()
        self.go("welcome" if mode == "install" else "remove")

    # ---------- контролы ----------

    def _solid(self, m, text, cmd):
        return ctk.CTkButton(m, text=text, command=cmd, width=130, height=38, corner_radius=theme.R_PILL,
                             fg_color=theme.SOLID, hover_color=theme.SOLID_HOVER, text_color=theme.ON_SOLID,
                             font=self.app.font(theme.F_BUTTON))

    def _ghost(self, m, text, cmd, width=110):
        b = ctk.CTkButton(m, text=text, command=cmd, width=width, height=38, corner_radius=theme.R_PILL,
                          fg_color="transparent", border_width=1, border_color=theme.EDGE,
                          text_color=theme.TEXT, font=self.app.font(theme.F_BUTTON))
        b.ng_kind = "ghost"
        return b

    def _switch(self, master, row, text, attr):
        line = Clear(master)
        line.grid(row=row, column=0, sticky="w", pady=(10, 0))
        sw = ctk.CTkSwitch(line, text="", width=40, switch_width=40, switch_height=22,
                           progress_color=theme.accent_soft(self.app.accent),
                           button_color=theme.SWITCH_KNOB, button_hover_color=theme.SWITCH_KNOB,
                           command=lambda: setattr(self, attr, bool(sw.get())))
        try:
            sw._text_label.grid_forget()
        except Exception:
            pass
        if getattr(self, attr):
            sw.select()
        sw.grid(row=0, column=0)
        lbl = Text(line, text, theme.F_LABEL, theme.TEXT)
        lbl.grid(row=0, column=1, padx=(12, 0))
        lbl.configure(cursor="hand2")
        lbl.bind("<Button-1>", lambda _e: sw.toggle())
        return sw

    def _clear_page(self):
        for w in self.page.winfo_children():
            w.destroy()

    def _title(self, text, row=0):
        Text(self.page, text, (24, "bold"), theme.TEXT).grid(row=row, column=0, sticky="w")

    def _body(self, text, row, pady=(14, 0), color=theme.MUTED):
        t = Text(self.page, text, (14, "normal"), color, wraplength=WRAP)
        t.grid(row=row, column=0, sticky="w", pady=pady)
        return t

    # ---------- страницы ----------

    def go(self, page):
        self.current = page
        self._clear_page()
        back = nxt = None
        step = ""
        if page == "welcome":
            self._title("Установка VoiceImitator")
            self._body("Озвучивает введённый текст нейроголосом прямо в микрофон Discord — "
                       "друзья в голосовом канале слышат озвучку", 1)
            self._body("Установщик скачает с GitHub последнюю версию программы (около 180 МБ), "
                       "создаст ярлыки и запись в «Приложениях» Windows. Права администратора не нужны", 2)
            nxt, step = "Далее", "Шаг 1 из 4"
        elif page == "options":
            self._title("Параметры")
            Text(self.page, "Папка", theme.F_LABEL, theme.TEXT).grid(row=1, column=0, sticky="w", pady=(18, 6))
            row = Clear(self.page)
            row.grid(row=2, column=0, sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            self.path = ctk.CTkEntry(row, height=36, corner_radius=theme.R_PILL, border_width=1,
                                     border_color=theme.EDGE, text_color=theme.TEXT,
                                     font=self.app.font(theme.F_BODY))
            self.path.insert(0, str(self.dir))
            self.path.grid(row=0, column=0, sticky="ew", padx=(0, 8))
            self._ghost(row, "Выбрать…", self.browse, width=110).grid(row=0, column=1)
            self.path_error = Text(self.page, " ", theme.F_CAPTION, theme.MUTED, wraplength=WRAP)
            self.path_error.grid(row=3, column=0, sticky="w", pady=(4, 6))
            self._switch(self.page, 4, "Ярлык на рабочем столе", "desktop")
            back, nxt, step = "Назад", "Установить", "Шаг 2 из 4"
        elif page == "working":
            self.doing = Text(self.page, "Установка…", (24, "bold"), theme.TEXT)
            self.doing.grid(row=0, column=0, sticky="w")
            self.status = self._body("Проверяю последнюю версию на GitHub", 1)
            self.bar = ctk.CTkProgressBar(self.page, height=6, progress_color=self.app.accent)
            self.bar.grid(row=2, column=0, sticky="ew", pady=(22, 0))
            self.bar.configure(mode="indeterminate")
            self.bar.start()
            self.detail = Text(self.page, " ", theme.F_CAPTION, theme.FAINT)
            self.detail.grid(row=3, column=0, sticky="w", pady=(8, 0))
            step = "Шаг 3 из 4" if self.mode == "install" else ""
        elif page == "done":
            self._title(self.done_title)
            self._body(self.done_text, 1)
            if self.mode == "install" and not self.failed:
                self._switch(self.page, 2, "Запустить VoiceImitator", "launch")
            nxt = "Готово" if self.mode == "install" and not self.failed else "Закрыть"
            step = "Шаг 4 из 4" if self.mode == "install" else ""
        elif page == "remove":
            self._title("Удаление VoiceImitator")
            self._body("Будут удалены программа, ярлыки и запись в «Приложениях» Windows", 1)
            self._switch(self.page, 2, "Сохранить настройки и голосовую модель", "keep")
            self._body("Тогда при повторной установке всё подхватится само и модель не придётся "
                       "скачивать заново", 3, pady=(6, 0), color=theme.FAINT)
            back, nxt = "Отмена", "Удалить"

        self.step.configure(text=step)
        if back:
            self.back.configure(text=back)
            self.back.grid(row=0, column=1, padx=(0, 8))
        else:
            self.back.grid_remove()
        if nxt:
            self.next.configure(text=nxt)
            self.next.grid(row=0, column=2)
        else:
            self.next.grid_remove()
        self.recompose_later(10)

    def on_back(self):
        if self.current == "options":
            self.go("welcome")
        elif self.current == "remove":
            self.app.on_close()

    def on_next(self):
        if self.current == "welcome":
            self.go("options")
        elif self.current == "options":
            self.run_install()
        elif self.current == "remove":
            self.run_uninstall()
        elif self.current == "done":
            if self.mode == "install" and not self.failed and self.launch and self.installed_exe \
                    and not installer.TEST:
                subprocess.Popen([str(self.installed_exe)], cwd=str(self.installed_exe.parent), close_fds=True)
            self.app.on_close()

    def browse(self):
        picked = filedialog.askdirectory(title="Папка, в которую установить VoiceImitator",
                                         initialdir=str(self.dir.parent if self.dir.parent.exists() else Path.home()))
        if not picked:
            return
        d = Path(picked)
        if d.name.lower() != installer.APP_NAME.lower():
            d = d / installer.APP_NAME
        self.path.delete(0, "end")
        self.path.insert(0, str(d))
        self.path_error.configure(text=" ")

    # ---------- работа ----------

    def _ui(self, fn):
        """Из рабочего потока — в очередь; окно разбирает её само (Tk трогаем только из своего потока)."""
        self._inbox.put(fn)

    def _drain(self):
        try:
            while True:
                self._inbox.get_nowait()()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(40, self._drain)

    def _set_status(self, text, detail=None):
        self._ui(lambda: (self.status.configure(text=text),
                          detail is not None and self.detail.configure(text=detail)))

    def _progress(self, done, total):
        def upd():
            if total:
                if str(self.bar.cget("mode")) != "determinate":
                    self.bar.stop()
                    self.bar.configure(mode="determinate")
                self.bar.set(done / total)
                self.detail.configure(text=f"{done / 1048576:.0f} из {total / 1048576:.0f} МБ")
        self._ui(upd)

    def run_install(self):
        raw = self.path.get().strip().strip('"')
        d = Path(raw) if raw else None
        if not d or not d.is_absolute():
            self.path_error.configure(text=f"Укажите полный путь к папке, например {installer.default_dir()}")
            return
        self.dir = d
        self.app.busy = True
        self.go("working")

        def work():
            try:
                release = installer.latest_release()
                self._set_status(f"Скачиваю VoiceImitator {release.version}", " ")
                tmp = d / (installer.EXE + ".download")
                installer.download(release.url, tmp, self._progress)
                self._set_status("Копирую файлы и создаю ярлыки", " ")
                self._ui(lambda: (self.bar.configure(mode="indeterminate"), self.bar.start()))
                self.installed_exe = installer.install(d, tmp, release.version, self.desktop)
                self.done_title = "Установлено"
                self.done_text = (f"VoiceImitator {release.version} установлен в папку {d}. "
                                  "Ярлык — в меню «Пуск»" + (" и на рабочем столе" if self.desktop else ""))
            except Exception as e:
                self.failed = True
                self.done_title = "Не удалось установить"
                self.done_text = str(e)
            self.app.busy = False
            self._ui(lambda: self.go("done"))

        threading.Thread(target=work, daemon=True).start()

    def run_uninstall(self):
        self.app.busy = True
        self.go("working")
        self.doing.configure(text="Удаление…")
        self.status.configure(text="Закрываю программу и удаляю файлы")

        def work():
            try:
                installer.uninstall(self.remove_dir or installer.existing_dir(), self.keep)
                self.done_title = "Удалено"
                self.done_text = "VoiceImitator удалён с компьютера." + (
                    " Настройки и голосовая модель сохранены — при повторной установке подхватятся сами"
                    if self.keep else "")
            except Exception as e:
                self.failed = True
                self.done_title = "Не удалось удалить"
                self.done_text = str(e)
            self.app.self_delete = True
            self.app.busy = False
            self._ui(lambda: self.go("done"))

        threading.Thread(target=work, daemon=True).start()


class SetupApp(ctk.CTk):
    def __init__(self, mode: str, remove_dir: Path | None):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("Установка VoiceImitator" if mode == "install" else "Удаление VoiceImitator")
        self.configure(fg_color=theme.WINDOW)
        self.settings = _look()
        self.accent = self.settings["accent"]
        self._fonts = {}
        self.busy = False
        self.self_delete = False
        self.chrome = Chrome(self)
        self.chrome.resizable = False
        self.chrome.on_close = self.on_close
        s = ctk.ScalingTracker.get_window_scaling(self)
        self.chrome.center(round(W * s), round(H * s))
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.view = Wizard(self, self, mode, remove_dir)
        self.view.grid(row=0, column=0, sticky="nsew")

    def font(self, spec):
        if spec not in self._fonts:
            size, weight = spec
            self._fonts[spec] = ctk.CTkFont(family=theme.FONT_UI, size=size, weight=weight)
        return self._fonts[spec]

    def on_close(self):
        if self.busy:   # посреди установки не закрываемся — файлы останутся половинчатыми
            self.view.footer.flash("Подождите, пока закончится установка — иначе файлы останутся недокачанными")
            return
        if self.self_delete:
            installer.schedule_self_delete()
        self.destroy()
