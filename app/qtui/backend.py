"""Мост между окном (QML) и тем, что делает работу: озвучка, звук, настройки.

Окно хранит у себя состояние для отрисовки и сообщает каждое изменение сюда через
set(); отсюда в окно идут сигналы. Тяжёлое (синтез, загрузка модели, установка
кабеля) — в потоках; сигналы Qt сами доставляют результат в поток окна."""

import queue
import shutil
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from app import __version__, audio, backdrop, cable_install, stt, theme
from app.paths import DATA_DIR
from app.settings import DEFAULT_SETTINGS, HISTORY_SIZE, load_settings, save_settings
from app.tts import PRESETS, VOICES, TTSEngine, download_model, download_piper, piper_present

NOT_CHOSEN = "Не выбрано"
SKY_PATH = DATA_DIR / "sky.png"


class Backend(QObject):
    flash = Signal(str)                 # сообщение внизу окна
    busy = Signal(bool)                 # идёт озвучка
    loading = Signal(str, float)        # экран загрузки: текст и доля (-1 — без шкалы)
    ready = Signal()                    # модель загружена — главный экран
    devices = Signal("QVariant")        # списки устройств и выбранные
    cable = Signal("QVariant")          # подсказка про кабель и кнопка установки
    history = Signal("QVariant")
    background = Signal(str)            # адрес картинки фона
    changed = Signal(str, "QVariant")   # настройку поменял не пользователь, а программа
    voiceStatus = Signal(str, float)    # голосовой ввод: что происходит и доля (-1 — без шкалы, -2 — ошибка)
    heard = Signal(str)                 # голосовой ввод: распознанная фраза
    _later = Signal(object)             # выполнить функцию в потоке окна (из любого потока)

    def __init__(self):
        super().__init__()
        self.s = load_settings()
        self.engine = TTSEngine()
        self.router = audio.AudioRouter(on_error=self.flash.emit)
        self.jobs: queue.Queue = queue.Queue()
        self.out_devices: list = []
        self.in_devices: list = []
        self.audio_ok = True
        self._save_timer = QTimer(self, singleShot=True, interval=400, timeout=self._save_now)
        self._later.connect(self._run)   # слот объекта — значит, в его потоке, а не в потоке сигнала
        self.voice = stt.VoiceInput(on_text=self._heard, on_status=self.voiceStatus.emit)
        if not self.s["stt_mode"]:
            self.s["stt_mode"] = stt.default_mode()
        threading.Thread(target=self._worker, daemon=True).start()

    @Slot(object)
    def _run(self, fn):
        fn()

    # ---------- что окно читает при старте ----------

    @Slot(result="QVariant")
    def settings(self):
        return dict(self.s)

    @Slot(result="QVariant")
    def info(self):
        return {
            "version": __version__,
            "voices": list(VOICES),
            "presets": list(PRESETS),
            "accents": [theme.ACCENTS[k] for k in theme.ACCENT_ORDER],
            "credit": cable_install.CREDIT,
            "nvidia": stt.has_nvidia(),
        }

    # ---------- настройки ----------

    @Slot(str, "QVariant")
    def set(self, key, value):
        if key not in DEFAULT_SETTINGS or self.s.get(key) == value:
            return
        self.s[key] = value
        if key == "volume":
            self.router.set_volume(float(value))
        elif key == "cable":
            self._cable_hint()
            self.router.set_cable(self._dev(self.out_devices, value))
            self.router.set_volume(self.s["volume"])
        elif key in ("monitor", "monitor_on"):
            self.router.set_monitor(self._dev(self.out_devices, self.s["monitor"]) if self.s["monitor_on"] else None)
            self.router.set_volume(self.s["volume"])
        elif key in ("mic", "mic_on"):
            self.router.set_mic(self._dev(self.in_devices, self.s["mic"]) if self.s["mic_on"] else None)
            self.router.mic_volume = self.s["mic_volume"]
        elif key in ("bg_mode", "bg_custom"):
            self.background.emit(self.background_url())
        elif key == "stt_on":
            if value and self.s["mic_on"]:
                # голосовой ввод заменяет живой голос: друзья слышат только озвучку
                self.s["mic_on"] = False
                self.router.set_mic(None)
                self.changed.emit("mic_on", False)
                self.flash.emit("Пропуск микрофона в кабель выключен — друзья слышат только озвучку")
            self._voice_apply()
        elif key in ("stt_mic", "stt_mode"):
            self._voice_apply()
        self._save_timer.start()   # ползунки шлют значения часто — пишем на диск с паузой

    def _save_now(self):
        save_settings(self.s)

    @Slot(int, int)
    def saveWindow(self, w, h):
        self.s["window"] = [w, h]
        self._save_now()

    @Slot(str, result="QVariant")
    def preset(self, name):
        voice, speed, pitch = PRESETS[name]
        return {"voice": voice, "speed": speed, "pitch": pitch}

    # ---------- фон ----------

    @Slot(result=str)
    def background_url(self):
        mode = self.s["bg_mode"]
        if mode == "custom" and self.s["bg_custom"] and Path(self.s["bg_custom"]).exists():
            path = Path(self.s["bg_custom"])
        elif mode == "sky":
            if not SKY_PATH.exists():
                backdrop._sky(2560, 1440, 1.6).save(SKY_PATH)
            path = SKY_PATH
        else:
            path = backdrop.backdrop_path()
        return QUrl.fromLocalFile(str(path)).toString()

    @Slot()
    def chooseBackground(self):
        path, _ = QFileDialog.getOpenFileName(None, "Картинка для фона", "",
                                              "Картинки (*.jpg *.jpeg *.png *.bmp *.webp);;Все файлы (*.*)")
        if not path:
            return
        dst = DATA_DIR / ("custom_backdrop" + Path(path).suffix.lower())
        try:
            for old in DATA_DIR.glob("custom_backdrop.*"):
                if old != dst:
                    old.unlink(missing_ok=True)
            shutil.copyfile(path, dst)
        except OSError as e:
            self.flash.emit(f"Не удалось взять картинку: {e}")
            return
        self.s["bg_custom"] = str(dst)
        self.s["bg_mode"] = "custom"
        self._save_now()
        self.background.emit(self.background_url())
        self.flash.emit(f"Фон: {Path(path).name}")

    # ---------- загрузка модели ----------

    @Slot()
    def start(self):
        threading.Thread(target=self._prepare, daemon=True).start()

    def _prepare(self):
        if not self.engine.model_present:
            self.loading.emit("Скачиваю голосовую модель (~40 МБ), это один раз…", 0.0)
            try:
                download_model(lambda frac: self.loading.emit("Скачиваю голосовую модель (~40 МБ), это один раз…", frac))
            except Exception as e:
                self.loading.emit(f"Не удалось скачать модель: {e}", -1)
                return
        self.loading.emit("Загружаю голос…", -1)
        try:
            self.engine.load()
        except Exception as e:
            self.loading.emit(f"Ошибка загрузки модели: {e}", -1)
            return
        self.ready.emit()
        self._later.emit(self._voice_apply)

    # ---------- голосовой ввод ----------

    def _voice_apply(self):
        if not self.s["stt_on"]:
            self.voice.stop()
            self.voiceStatus.emit("", -1)
            return
        if self.engine.model is None:
            return   # включится, когда загрузится голос
        dev = self._dev(self.in_devices, self.s["stt_mic"]) or audio.default_device("input", self.in_devices)
        self.voice.start(dev.index if dev else None, self.s["stt_mode"])

    def _heard(self, text):
        """Из потока распознавания: фраза — в историю и на озвучку, как набранная."""
        self.heard.emit(text)
        self._later.emit(lambda: self.speak(text, False))

    # ---------- устройства ----------

    @Slot()
    def refreshDevices(self):
        self.audio_ok = audio.windows_audio_ok()
        self.out_devices = audio.list_devices("output")
        self.in_devices = audio.list_devices("input")
        outs = [d.name for d in self.out_devices]
        ins = [d.name for d in self.in_devices]
        cable = audio.find_cable(self.out_devices)
        mon = audio.default_device("output", self.out_devices)
        mic = audio.default_device("input", self.in_devices)
        self.s["cable"] = self.s["cable"] if self.s["cable"] in outs else (cable.name if cable else "")
        self.s["monitor"] = self.s["monitor"] if self.s["monitor"] in outs else (mon.name if mon else "")
        self.s["mic"] = self.s["mic"] if self.s["mic"] in ins else (mic.name if mic else "")
        self.devices.emit({
            "outs": outs, "ins": ins,
            "cable": self.s["cable"] or NOT_CHOSEN,
            "monitor": self.s["monitor"] or NOT_CHOSEN,
            "mic": self.s["mic"] or NOT_CHOSEN,
        })
        self._cable_hint()
        self._apply_audio()

    def _dev(self, devices, name):
        return next((d for d in devices if d.name == name), None)

    def _apply_audio(self):
        self.router.set_cable(self._dev(self.out_devices, self.s["cable"]))
        self.router.set_monitor(self._dev(self.out_devices, self.s["monitor"]) if self.s["monitor_on"] else None)
        self.router.set_mic(self._dev(self.in_devices, self.s["mic"]) if self.s["mic_on"] else None)
        self.router.set_volume(self.s["volume"])
        self.router.mic_volume = self.s["mic_volume"]

    def _cable_hint(self, text=None, button=None):
        name = self.s["cable"]
        found = bool(name and audio.is_cable(name))
        missing = not audio.find_cable(self.out_devices) and self.audio_ok
        if text is None:
            if not self.audio_ok:
                text = ("Служба звука Windows не отвечает — устройства не видны. Перезагрузите компьютер "
                        "или запустите службу «Windows Audio», затем нажмите «Обновить устройства»")
            elif found:
                text = "Кабель найден. В Discord выберите CABLE Output как устройство ввода"
            elif missing:
                text = ("Виртуальный кабель не найден. Нажмите «Установить кабель» — откроется окно "
                        "VB-CABLE, там нажмите «Install Driver»")
            else:
                text = "Выбранное устройство не похоже на кабель — Discord не услышит озвучку"
        self.cable.emit({
            "text": text,
            "install": missing and not found,
            "button": button or "Установить кабель",
            "enabled": button is None,
        })

    @Slot()
    def rescan(self):
        # всё — в потоке устройств, по очереди: закрыть, перечитать, затем обновить окно
        self.router.close_streams()
        self.router.call(audio.rescan_devices)
        self.router.call(lambda: self._later.emit(self._after_rescan))

    def _after_rescan(self):
        self.refreshDevices()
        self.flash.emit("Список устройств обновлён" if self.audio_ok else
                        "Служба звука Windows не отвечает — перезагрузите компьютер")

    # ---------- установка кабеля ----------

    @Slot()
    def installCable(self):
        self._cable_hint("Подтвердите запрос прав Windows, затем нажмите «Install Driver»", "Открываю установщик…")

        def work():
            started, msg = cable_install.open_installer()
            if not started:
                self._cable_hint(msg)
                return
            self._cable_hint(msg, "Жду установки…")
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                time.sleep(2)
                done = threading.Event()
                self.router.close_streams()
                self.router.call(audio.rescan_devices)
                self.router.call(done.set)
                done.wait(10)
                if audio.find_cable(audio.list_devices("output")):
                    self._later.emit(self._after_install)
                    return
            self.out_devices = audio.list_devices("output")
            self._cable_hint("Пока не вижу кабель. Если ставили — иногда нужна перезагрузка, "
                             "после неё нажмите «Обновить устройства»")
            self._later.emit(self._apply_audio)

        threading.Thread(target=work, daemon=True).start()

    def _after_install(self):
        self.s["cable"] = ""
        self.refreshDevices()
        self._save_now()

    # ---------- озвучка ----------

    @Slot(str, bool)
    def speak(self, text, from_history=False):
        text = text.strip()
        if not text:
            return
        # Фраза, нажатая в истории, просто проигрывается — порядок истории не меняется.
        # Наверх поднимается только текст, заново введённый в поле.
        if not from_history:
            h = self.s["history"]
            if text in h:
                h.remove(text)
            h.insert(0, text)
            del h[HISTORY_SIZE:]
            self.history.emit(list(h))
            self._save_now()
        self.jobs.put(text)

    @Slot()
    def stop(self):
        self.router.stop()

    def _worker(self):
        while True:
            text = self.jobs.get()
            self.busy.emit(True)
            # озвучка звучит в наушниках — микрофон может её услышать: пока она идёт, не слушаем
            listen_pause = self.s["monitor_on"]
            self.voice.paused = listen_pause
            try:
                voice = self.s["voice"]
                engine, name = VOICES.get(voice, ("silero", ""))
                if engine == "piper" and not piper_present(name):
                    self.flash.emit(f"Скачиваю голос «{voice.split(' (')[0]}» (~60 МБ), это один раз…")
                    download_piper(name)
                data = self.engine.synthesize(text, voice, float(self.s["speed"]), float(self.s["pitch"]))
                self.router.play(data)
                if listen_pause:
                    deadline = time.monotonic() + len(data) / 48000 + 2
                    while self.router.playing and time.monotonic() < deadline:
                        time.sleep(0.05)
                    time.sleep(0.25)   # хвост эха
            except Exception as e:
                self.flash.emit(f"Ошибка: {e}")
            finally:
                self.voice.paused = False
                self.busy.emit(False)

    @Slot()
    def close(self):
        self._save_now()
        self.voice.stop()
        self.router.close()
