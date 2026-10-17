"""Синтез речи локально, без интернета: Silero TTS и Piper, скорость и тон — через pedalboard.

Голоса Piper — отдельные модели (~60 МБ каждая), скачиваются при первом выборе голоса."""

import re
import threading
from typing import Callable

import numpy as np

from app.net import download
from app.paths import MODELS_DIR

MODEL_URL = "https://models.silero.ai/models/tts/ru/v4_ru.pt"
MODEL_PATH = MODELS_DIR / "v4_ru.pt"
SAMPLE_RATE = 48000
MAX_CHUNK = 800  # Silero не любит слишком длинные куски текста

# голос: (движок, имя голоса у движка)
VOICES = {
    "Айдар (мужской)": ("silero", "aidar"),
    "Евгений (мужской)": ("silero", "eugene"),
    "Денис (мужской)": ("piper", "denis"),
    "Дмитрий (мужской)": ("piper", "dmitri"),
    "Руслан (мужской)": ("piper", "ruslan"),
    "Бая (женский)": ("silero", "baya"),
    "Ксения (женский)": ("silero", "kseniya"),
    "Ксения 2 (женский)": ("silero", "xenia"),
    "Ирина (женский)": ("piper", "irina"),
}
PIPER_DIR = MODELS_DIR / "piper"
PIPER_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/{0}/medium/ru_RU-{0}-medium.{1}"

# Пресеты: голос, скорость, тон в полутонах
PRESETS = {
    "Обычный": ("Айдар (мужской)", 1.0, 0),
    "Диктор дорам": ("Евгений (мужской)", 1.08, -2),
    "Дорама (она)": ("Ксения (женский)", 1.05, 1),
    "Бурундук": ("Бая (женский)", 1.25, 7),
    "Великан": ("Айдар (мужской)", 0.85, -7),
    "Робот": ("Дмитрий (мужской)", 1.0, -4),
    "Злодей": ("Руслан (мужской)", 0.9, -5),
    "Аниме": ("Ирина (женский)", 1.1, 5),
}

LATIN = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "х",
    "i": "и", "j": "дж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п",
    "q": "к", "r": "р", "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "кс",
    "y": "й", "z": "з",
}
LATIN_COMBOS = {"sh": "ш", "ch": "ч", "zh": "ж", "th": "т", "ph": "ф", "oo": "у", "ee": "и", "kh": "х"}


def _transliterate(word: str) -> str:
    out, i, low = [], 0, word.lower()
    while i < len(low):
        pair = low[i:i + 2]
        if pair in LATIN_COMBOS:
            out.append(LATIN_COMBOS[pair])
            i += 2
        else:
            out.append(LATIN.get(low[i], low[i]))
            i += 1
    return "".join(out)


def normalize_text(text: str) -> str:
    """Silero читает только кириллицу: числа превращаем в слова, латиницу — в транслит."""
    from num2words import num2words

    text = text.replace("\n", " ").strip()
    text = re.sub(r"\d+([.,]\d+)?", lambda m: num2words(float(m.group().replace(",", "."))
                                                        if m.group(1) else int(m.group()), lang="ru"), text)
    text = re.sub(r"[A-Za-z]+", lambda m: _transliterate(m.group()), text)
    text = re.sub(r"[^\w\s.,!?…:;\-—()«»\"']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_text(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    chunks, current = [], ""
    for s in sentences:
        while len(s) > MAX_CHUNK:  # очень длинное предложение без точек
            cut = s.rfind(" ", 0, MAX_CHUNK)
            cut = cut if cut > 0 else MAX_CHUNK
            chunks.append(s[:cut])
            s = s[cut:].strip()
        if len(current) + len(s) + 1 > MAX_CHUNK:
            chunks.append(current)
            current = s
        else:
            current = f"{current} {s}".strip()
    if current:
        chunks.append(current)
    return [c for c in chunks if re.search(r"\w", c)]


def download_model(progress: Callable[[float], None]) -> None:
    download(MODEL_URL, MODEL_PATH, progress)


def piper_path(name: str):
    return PIPER_DIR / f"ru_RU-{name}-medium.onnx"


def piper_present(name: str) -> bool:
    return piper_path(name).exists() and piper_path(name).with_suffix(".onnx.json").exists()


def download_piper(name: str, progress: Callable[[float], None] = lambda _f: None) -> None:
    download(PIPER_URL.format(name, "onnx.json"), piper_path(name).with_suffix(".onnx.json"))
    download(PIPER_URL.format(name, "onnx"), piper_path(name), progress)


class TTSEngine:
    def __init__(self):
        self.model = None
        self._piper = {}
        self._lock = threading.Lock()

    @property
    def model_present(self) -> bool:
        return MODEL_PATH.exists()

    def load(self) -> None:
        import torch

        torch.set_num_threads(max(1, min(4, (__import__("os").cpu_count() or 2) // 2)))
        self.model = torch.package.PackageImporter(str(MODEL_PATH)).load_pickle("tts_models", "model")
        self.synthesize("Привет", "Айдар (мужской)", 1.0, 0)  # прогрев, чтобы первая фраза не тормозила

    def _piper_voice(self, name: str):
        if name not in self._piper:
            from piper import PiperVoice

            self._piper[name] = PiperVoice.load(str(piper_path(name)))
        return self._piper[name]

    def synthesize(self, text: str, voice: str, speed: float, pitch: float) -> np.ndarray:
        """voice — название из VOICES. Возвращает моно float32 с частотой SAMPLE_RATE."""
        from pedalboard import time_stretch

        from app.audio import resample

        engine, name = VOICES.get(voice, VOICES["Айдар (мужской)"])
        parts = []
        with self._lock:
            for chunk in split_text(normalize_text(text)):
                if engine == "piper":
                    pieces = list(self._piper_voice(name).synthesize(chunk))
                    if not pieces:
                        continue
                    audio = resample(np.concatenate([c.audio_float_array for c in pieces]).astype(np.float32),
                                     pieces[0].sample_rate, SAMPLE_RATE)
                else:
                    audio = self.model.apply_tts(text=chunk, speaker=name, sample_rate=SAMPLE_RATE,
                                                 put_accent=True, put_yo=True).numpy()
                parts.append(audio.astype(np.float32))
                parts.append(np.zeros(int(SAMPLE_RATE * 0.15), dtype=np.float32))
        if not parts:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(parts)
        if abs(speed - 1.0) > 0.01 or abs(pitch) > 0.05:
            audio = time_stretch(audio[None, :], SAMPLE_RATE, stretch_factor=speed,
                                 pitch_shift_in_semitones=pitch)[0].astype(np.float32)
        return audio
