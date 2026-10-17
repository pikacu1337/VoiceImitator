"""Голосовой ввод: микрофон → фразы → текст (Whisper) → озвучка выбранным голосом.

Фразы режутся по паузам: уровень сигнала сравнивается с плавающим уровнем шума,
фраза кончается после 0.7 с тишины (или через 20 с). Каждая фраза распознаётся
faster-whisper в отдельном потоке, микрофон тем временем слушает дальше.

Два режима:
  - «gpu» — видеокарта NVIDIA, модель large-v3-turbo: точно и быстро (~0.3 с на фразу).
    Нужны библиотеки cuBLAS — при первом включении скачиваются из пакета NVIDIA
    на PyPI (~530 МБ), из него берутся две DLL. Сама модель ~1.6 ГБ.
  - «cpu» — процессор, модель small (~480 МБ): ~2–3 с на фразу, точность пониже.
Всё скачивается один раз в %APPDATA%\\VoiceImitator\\models.

Пока звучит озвучка, микрофон не слушается — чтобы не распознать её саму."""

import ctypes
import os
import queue
import re
import threading
import zipfile
from pathlib import Path

import numpy as np

from app.audio import resample
from app.net import download
from app.paths import MODELS_DIR

RATE = 16000
FRAME = 0.03                 # 30 мс
START_FRAMES = 3             # столько громких кадров подряд — начало речи
END_SILENCE = 0.7            # столько тишины — конец фразы
MAX_PHRASE = 20.0
MIN_SPEECH = 0.35
PREROLL = 0.3

WHISPER_DIR = MODELS_DIR / "whisper"
CUDA_DIR = MODELS_DIR / "cuda"
CUBLAS_WHEEL = ("https://files.pythonhosted.org/packages/20/e2/fc9a0e985249d873150276d5afb02e39a66817fedbf1a385724393e505ed/"
                "nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl")
CUBLAS_DLLS = ("cublas64_12.dll", "cublasLt64_12.dll")

MODES = {
    # режим: (модель, устройство, вычисления, примерный размер модели в МБ)
    "gpu": ("large-v3-turbo", "cuda", "int8_float16", 1620),
    "cpu": ("small", "cpu", "int8", 484),
}

# что Whisper «слышит» в тишине и шуме — такие фразы не озвучиваем
HALLUCINATIONS = ("субтитр", "продолжение следует", "спасибо за просмотр", "подписывайтесь",
                  "редактор", "корректор", "dimatorzok", "благодарю за внимание", "ставьте лайк")


def has_nvidia() -> bool:
    try:
        ctypes.WinDLL("nvcuda.dll")
        return True
    except OSError:
        return False


def default_mode() -> str:
    return "gpu" if has_nvidia() else "cpu"


def cuda_ready() -> bool:
    return all((CUDA_DIR / n).exists() for n in CUBLAS_DLLS)


def model_ready(mode: str) -> bool:
    name = MODES[mode][0]
    return any((WHISPER_DIR / d).is_dir() and any((WHISPER_DIR / d).rglob("model.bin"))
               for d in os.listdir(WHISPER_DIR) if name in d) if WHISPER_DIR.exists() else False


def prepare_cuda(progress) -> None:
    if cuda_ready():
        return
    wheel = CUDA_DIR / "cublas.whl"
    download(CUBLAS_WHEEL, wheel, progress)
    with zipfile.ZipFile(wheel) as z:
        for info in z.infolist():
            if Path(info.filename).name in CUBLAS_DLLS:
                (CUDA_DIR / Path(info.filename).name).write_bytes(z.read(info))
    wheel.unlink(missing_ok=True)


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def load_model(mode: str, status):
    """Скачивает что нужно и загружает модель. status(текст, доля 0..1 или -1)."""
    name, device, compute, size_mb = MODES[mode]
    if mode == "gpu":
        if not cuda_ready():
            prepare_cuda(lambda f: status("Скачиваю библиотеки видеокарты (~530 МБ), это один раз…", f))
        os.add_dll_directory(str(CUDA_DIR))
        os.environ["PATH"] = str(CUDA_DIR) + os.pathsep + os.environ.get("PATH", "")
    from faster_whisper import WhisperModel, download_model

    if not model_ready(mode):
        text = f"Скачиваю модель распознавания (~{size_mb // 100 / 10:g} ГБ), это один раз…" if size_mb >= 1000 \
            else f"Скачиваю модель распознавания (~{size_mb} МБ), это один раз…"
        start = _dir_size(WHISPER_DIR)
        done = threading.Event()

        def watch():   # у загрузчика Hugging Face нет своего отчёта — смотрим, сколько уже легло на диск
            while not done.wait(0.5):
                status(text, min(0.99, (_dir_size(WHISPER_DIR) - start) / (size_mb * 1024 * 1024)))

        threading.Thread(target=watch, daemon=True).start()
        try:
            download_model(name, cache_dir=str(WHISPER_DIR))
        finally:
            done.set()
    status("Загружаю модель распознавания…", -1)
    model = WhisperModel(name, device=device, compute_type=compute, download_root=str(WHISPER_DIR),
                         cpu_threads=max(2, min(8, (os.cpu_count() or 4) // 2)))
    # прогрев: первая фраза на видеокарте иначе ждёт секунды
    list(model.transcribe(np.zeros(RATE, dtype=np.float32), language="ru", beam_size=1)[0])
    return model


def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    low = text.lower()
    if not re.search(r"[0-9a-zа-яё]", low) or any(h in low for h in HALLUCINATIONS):
        return ""
    return text


class VoiceInput:
    """Слушает микрофон, отдаёт распознанные фразы в on_text(текст) (из своего потока).
    on_status(текст, доля) — что происходит: загрузка, «Слушаю…», «Распознаю…»."""

    def __init__(self, on_text, on_status):
        self.on_text = on_text
        self.on_status = on_status
        self.paused = False          # звучит озвучка — не слушать
        self._model = None
        self._mode = None
        self._stream = None
        self._run = False
        self._frames: queue.Queue = queue.Queue()
        self._phrases: queue.Queue = queue.Queue()
        self._gen = 0                # номер запуска — старые потоки по нему понимают, что пора выходить

    @property
    def active(self) -> bool:
        return self._run

    def start(self, device_index: int | None, mode: str) -> None:
        self.stop()
        self._run = True
        self._gen += 1
        gen = self._gen
        threading.Thread(target=self._prepare, args=(gen, device_index, mode), daemon=True).start()

    def stop(self) -> None:
        self._run = False
        self._gen += 1
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    # ---------- подготовка ----------

    def _prepare(self, gen, device_index, mode):
        try:
            if self._model is None or self._mode != mode:
                self._model = None
                self._model = load_model(mode, self.on_status)
                self._mode = mode
        except Exception as e:
            if gen == self._gen:
                self._run = False
                self.on_status(f"Не удалось подготовить распознавание: {e}", -2)
            return
        if gen != self._gen:
            return
        try:
            import sounddevice as sd

            info = sd.query_devices(device_index, "input") if device_index is not None else sd.query_devices(kind="input")
            rate = int(info["default_samplerate"])
            self._stream = sd.InputStream(device=device_index, samplerate=rate, channels=1, dtype="float32",
                                          blocksize=int(rate * FRAME), callback=self._callback)
            self._stream.start()
        except Exception as e:
            self._run = False
            self.on_status(f"Микрофон не открылся: {e}", -2)
            return
        threading.Thread(target=self._segment, args=(gen, rate), daemon=True).start()
        threading.Thread(target=self._recognize, args=(gen,), daemon=True).start()
        self.on_status("Слушаю…", -1)

    def _callback(self, indata, _frames, _time, _status):
        self._frames.put(indata[:, 0].copy())

    # ---------- нарезка на фразы ----------

    def _segment(self, gen, rate):
        floor = 0.004                # плавающий уровень шума
        pre: list = []               # последние кадры до начала речи
        phrase: list = []
        loud = quiet = 0
        speech = 0.0
        while gen == self._gen:
            try:
                block = self._frames.get(timeout=0.3)
            except queue.Empty:
                continue
            if self.paused:
                pre, phrase, loud, quiet, speech = [], [], 0, 0, 0.0
                continue
            frame = resample(block, rate, RATE)
            rms = float(np.sqrt(np.mean(frame ** 2))) if len(frame) else 0.0
            thr = max(0.012, floor * 3.5)
            if not phrase:
                floor = floor * 0.97 + rms * 0.03 if rms < thr else floor
                pre.append(frame)
                pre = pre[-int(PREROLL / FRAME):]
                loud = loud + 1 if rms > thr else 0
                if loud >= START_FRAMES:
                    phrase, quiet, speech = list(pre), 0, loud * FRAME
                continue
            phrase.append(frame)
            if rms > thr * 0.7:
                quiet = 0
                speech += FRAME
            else:
                quiet += 1
            length = len(phrase) * FRAME
            if quiet * FRAME >= END_SILENCE or length >= MAX_PHRASE:
                if speech >= MIN_SPEECH:
                    self._phrases.put(np.concatenate(phrase))
                phrase, pre, loud = [], [], 0

    # ---------- распознавание ----------

    def _recognize(self, gen):
        while gen == self._gen:
            try:
                audio = self._phrases.get(timeout=0.3)
            except queue.Empty:
                continue
            self.on_status("Распознаю…", -1)
            try:
                segs, _ = self._model.transcribe(audio, language="ru", beam_size=1, vad_filter=True,
                                                 condition_on_previous_text=False, without_timestamps=True)
                text = clean(" ".join(s.text for s in segs if s.no_speech_prob < 0.6))
            except Exception as e:
                text = ""
                self.on_status(f"Ошибка распознавания: {e}", -2)
            if gen != self._gen:
                return
            if text:
                self.on_text(text)
            self.on_status("Слушаю…", -1)
