"""Вывод звука: в виртуальный кабель (его Discord видит как микрофон), себе в наушники,
плюс опционально пропуск живого микрофона в тот же кабель, чтобы можно было говорить
и своим голосом, не переключая микрофон в Discord."""

import collections
import queue
import threading
import time
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

from app.tts import SAMPLE_RATE

# Части названий виртуальных кабелей: VB-Audio Cable, VoiceMeeter и аналоги
CABLE_HINTS = ("cable input", "vb-audio", "voicemeeter input", "voicemeeter vaio", "virtual audio")
CABLE_DOWNLOAD_URL = "https://vb-audio.com/Cable/"
MIC_MAX_BUFFER = int(SAMPLE_RATE * 0.12)  # больше 120 мс задержки микрофона не копим


@dataclass
class Device:
    index: int
    name: str
    default_rate: int


def _wasapi_index() -> int | None:
    for i, api in enumerate(sd.query_hostapis()):
        if "WASAPI" in api["name"]:
            return i
    return None


def rescan_devices() -> None:
    """Перечитывает список устройств (например, после установки кабеля).
    Все открытые потоки при этом умирают — перед вызовом закрой AudioRouter."""
    sd._terminate()
    sd._initialize()


def windows_audio_ok() -> bool:
    """Служба «Windows Audio» отвечает: у WASAPI есть устройства. Когда служба остановлена,
    PortAudio видит только WDM-KS, а открытие устройств через WASAPI зависает."""
    api = _wasapi_index()
    return api is not None and len(sd.query_hostapis(api)["devices"]) > 0


def list_devices(kind: str) -> list[Device]:
    """kind = 'output' или 'input'. Берём только WASAPI — без дублей и с низкой задержкой."""
    api = _wasapi_index()
    key = "max_output_channels" if kind == "output" else "max_input_channels"
    return [
        Device(i, d["name"], int(d["default_samplerate"]))
        for i, d in enumerate(sd.query_devices())
        if d[key] > 0 and (api is None or d["hostapi"] == api)
    ]


def is_cable(name: str) -> bool:
    low = name.lower()
    return any(h in low for h in CABLE_HINTS)


def find_cable(devices: list[Device]) -> Device | None:
    return next((d for d in devices if is_cable(d.name)), None)


def default_device(kind: str, devices: list[Device]) -> Device | None:
    """Устройство Windows по умолчанию (в его WASAPI-варианте), но не кабель."""
    try:
        idx = sd.default.device[1 if kind == "output" else 0]
        name = sd.query_devices(idx)["name"] if idx >= 0 else ""
    except Exception:
        name = ""
    real = [d for d in devices if not is_cable(d.name)]
    for d in real:
        if name and (d.name.startswith(name) or name.startswith(d.name[:31])):
            return d
    return real[0] if real else None


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or len(x) == 0:
        return x
    n = int(round(len(x) * dst / src))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


class _Sink:
    """Один выход (кабель или наушники) со своим курсором воспроизведения."""

    def __init__(self, device: Device, router: "AudioRouter", with_mic: bool):
        self.router = router
        self.with_mic = with_mic
        self.data = np.zeros(0, dtype=np.float32)
        self.pos = 0
        self.volume = 1.0
        info = sd.query_devices(device.index)
        self.channels = min(2, info["max_output_channels"])
        try:
            self.rate = SAMPLE_RATE
            self.stream = sd.OutputStream(
                device=device.index, samplerate=self.rate, channels=self.channels, dtype="float32",
                callback=self._callback, latency="low",
                extra_settings=sd.WasapiSettings(auto_convert=True),
            )
        except Exception:
            self.rate = device.default_rate
            self.stream = sd.OutputStream(
                device=device.index, samplerate=self.rate, channels=self.channels, dtype="float32",
                callback=self._callback, latency="low",
            )
        self.stream.start()

    @property
    def playing(self) -> bool:
        return self.pos < len(self.data)

    def play(self, audio: np.ndarray) -> None:
        self.data = resample(audio, SAMPLE_RATE, self.rate)
        self.pos = 0

    def stop(self) -> None:
        self.pos = len(self.data)

    def _callback(self, outdata, frames, _time, _status):
        chunk = self.data[self.pos:self.pos + frames]
        self.pos += len(chunk)
        out = np.zeros(frames, dtype=np.float32)
        out[:len(chunk)] = chunk * self.volume
        if self.with_mic:
            out += self.router.pull_mic(frames, self.rate)
        np.clip(out, -1.0, 1.0, out=out)
        outdata[:] = out[:, None]

    def close(self) -> None:
        self.stream.stop()
        self.stream.close()


def _human_error(name: str, e: Exception) -> str:
    """Ошибка PortAudio — одной понятной фразой: что случилось и что делать."""
    text = str(e)
    if "Invalid device" in text or "-9996" in text:
        return f"{name}: устройство недоступно — выберите другое в «Настройках» и нажмите «Обновить устройства»"
    if "Unanticipated host error" in text or "-9999" in text:
        return f"{name}: устройство занято другой программой или отключено"
    if "Invalid sample rate" in text or "-9997" in text:
        return f"{name}: устройство не поддерживает нужную частоту — выберите другое"
    return f"{name}: не удалось открыть устройство ({text})"


class AudioRouter:
    """Все открытия и закрытия устройств идут в отдельном потоке по очереди: если драйвер
    или служба звука Windows не отвечает, висит этот поток, а не окно. Если операция
    тянется дольше SLOW_SECONDS, вызывается on_error с понятным текстом."""

    SLOW_SECONDS = 4.0

    def __init__(self, on_error=None):
        self.cable: _Sink | None = None
        self.monitor: _Sink | None = None
        self.mic_stream: sd.InputStream | None = None
        self.mic_rate = SAMPLE_RATE
        self.mic_volume = 1.0
        self.volume = 1.0
        self.on_error = on_error or (lambda msg: None)
        self._mic_buf: collections.deque[np.ndarray] = collections.deque()
        self._mic_len = 0
        self._mic_lock = threading.Lock()
        self._tasks: queue.Queue = queue.Queue()
        self._busy_since = None
        self._warned = False
        self._thread = threading.Thread(target=self._loop, name="audio", daemon=True)
        self._thread.start()
        threading.Thread(target=self._watchdog, name="audio-watchdog", daemon=True).start()

    # --- поток устройств ---

    def _loop(self):
        while True:
            task = self._tasks.get()
            if task is None:
                return
            name, fn = task
            self._busy_since = time.monotonic()
            try:
                fn()
            except Exception as e:
                self.on_error(_human_error(name, e))
            finally:
                self._busy_since = None
                self._warned = False

    def _watchdog(self):
        while self._thread.is_alive():
            time.sleep(0.5)
            since = self._busy_since
            if since and not self._warned and time.monotonic() - since > self.SLOW_SECONDS:
                self._warned = True
                self.on_error("Звуковое устройство не отвечает. Проверьте, что служба «Windows Audio» "
                              "запущена, или перезагрузите компьютер")

    def _submit(self, name, fn):
        self._tasks.put((name, fn))

    def call(self, fn):
        """Выполнить fn в потоке устройств после уже поставленных задач."""
        self._submit("Звук", fn)

    # --- настройка выходов ---

    def set_cable(self, device: Device | None) -> None:
        self._submit("Кабель", lambda: self._set_cable(device))

    def set_monitor(self, device: Device | None) -> None:
        self._submit("Наушники", lambda: self._set_monitor(device))

    def set_mic(self, device: Device | None) -> None:
        self._submit("Микрофон", lambda: self._set_mic(device))

    def _set_cable(self, device):
        old, self.cable = self.cable, None
        if old:
            old.close()
        if device:
            sink = _Sink(device, self, with_mic=True)
            sink.volume = self.volume
            self.cable = sink

    def _set_monitor(self, device):
        old, self.monitor = self.monitor, None
        if old:
            old.close()
        if device:
            sink = _Sink(device, self, with_mic=False)
            sink.volume = self.volume
            self.monitor = sink

    def _set_mic(self, device):
        old, self.mic_stream = self.mic_stream, None
        if old:
            old.stop()
            old.close()
        with self._mic_lock:
            self._mic_buf.clear()
            self._mic_len = 0
        if not device:
            return
        kwargs = dict(device=device.index, channels=1, dtype="float32",
                      callback=self._mic_callback, latency="low")
        try:
            self.mic_rate = SAMPLE_RATE
            stream = sd.InputStream(samplerate=self.mic_rate,
                                    extra_settings=sd.WasapiSettings(auto_convert=True), **kwargs)
        except Exception:
            self.mic_rate = device.default_rate
            stream = sd.InputStream(samplerate=self.mic_rate, **kwargs)
        stream.start()
        self.mic_stream = stream

    def set_volume(self, value: float) -> None:
        self.volume = value
        for sink in (self.cable, self.monitor):
            if sink:
                sink.volume = value

    # --- микрофон ---

    def _mic_callback(self, indata, _frames, _time, _status):
        block = indata[:, 0].copy()
        with self._mic_lock:
            self._mic_buf.append(block)
            self._mic_len += len(block)
            while self._mic_len > MIC_MAX_BUFFER and len(self._mic_buf) > 1:
                self._mic_len -= len(self._mic_buf.popleft())

    def pull_mic(self, frames: int, rate: int) -> np.ndarray:
        need = int(round(frames * self.mic_rate / rate))
        out = np.zeros(need, dtype=np.float32)
        filled = 0
        with self._mic_lock:
            while filled < need and self._mic_buf:
                block = self._mic_buf[0]
                take = min(need - filled, len(block))
                out[filled:filled + take] = block[:take]
                filled += take
                self._mic_len -= take
                if take == len(block):
                    self._mic_buf.popleft()
                else:
                    self._mic_buf[0] = block[take:]
        out = resample(out, self.mic_rate, rate)
        if len(out) < frames:
            out = np.pad(out, (0, frames - len(out)))
        return out[:frames] * self.mic_volume

    # --- воспроизведение ---

    def play(self, audio: np.ndarray, to_cable: bool = True, to_monitor: bool = True) -> None:
        if to_cable and self.cable:
            self.cable.play(audio)
        if to_monitor and self.monitor:
            self.monitor.play(audio)

    def stop(self) -> None:
        for sink in (self.cable, self.monitor):
            if sink:
                sink.stop()

    @property
    def playing(self) -> bool:
        return any(s and s.playing for s in (self.cable, self.monitor))

    def close_streams(self) -> None:
        """Закрыть все устройства (в очереди, не дожидаясь)."""
        self.set_cable(None)
        self.set_monitor(None)
        self.set_mic(None)

    def close(self, timeout: float = 1.5) -> None:
        """При выходе: закрыть устройства и остановить поток, но ждать не дольше timeout."""
        self.close_streams()
        self._tasks.put(None)
        self._thread.join(timeout)
