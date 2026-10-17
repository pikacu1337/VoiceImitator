"""Фон окна, как в ZapretLauncher:
  - «Картинка» — встроенная фотография (грозовое небо над полем);
  - «Своя картинка» — любая картинка пользователя;
  - «Звёздное небо» — радиальный градиент от space-top к space-bottom и звёзды.
Картинка заполняет окно с сохранением пропорций, затемняется по яркости
(яркость b% = чёрный с прозрачностью (100 − b)%) и может размываться.
"""

import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app import theme

BACKDROP_BLUR_MAX = 20   # размытие фона при 100% (в лаунчере 60px WPF = 20px CSS)


def _assets() -> Path:
    """app/assets — и из исходников, и внутри собранного .exe (PyInstaller кладёт их в app/assets)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app" / "assets"
    return Path(__file__).resolve().parent / "assets"


def backdrop_path() -> Path:
    return _assets() / "Images" / "backdrop.jpg"


def _hex(c: str) -> np.ndarray:
    c = c.lstrip("#")
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


_STARS: list[tuple[float, float, float, int]] = []


def _stars() -> list:
    if not _STARS:
        rng = random.Random(7)  # фиксированные звёзды — не прыгают при перерисовке
        for layer, (count, r0, r1, a0, a1) in enumerate(((140, 0.5, 0.9, 50, 120),
                                                          (45, 0.8, 1.3, 110, 190),
                                                          (12, 1.2, 1.8, 170, 240))):
            for _ in range(count):
                _STARS.append((rng.random(), rng.random(), rng.uniform(r0, r1), rng.randint(a0, a1)))
    return _STARS


def _sky(w: int, h: int, scale: float) -> Image.Image:
    top, bottom = _hex(theme.SKY_TOP), _hex(theme.SKY_BOTTOM)
    fx, fy = 0.5 * w, 0.25 * h
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    dist = np.sqrt((xs - fx) ** 2 + (ys - fy) ** 2)
    dmax = max(np.hypot(cx - fx, cy - fy) for cx, cy in ((0, 0), (w, 0), (0, h), (w, h))) or 1.0
    t = np.clip(dist / dmax, 0, 1)[..., None]
    pic = Image.fromarray((top * (1 - t) + bottom * t).astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(pic, "RGBA")
    for rx, ry, rad, alpha in _stars():
        x, y, r = rx * w, ry * h, rad * scale
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, alpha))
    return pic


def _cover(img: Image.Image, w: int, h: int, fast: bool = False) -> Image.Image:
    """Заполнение с сохранением пропорций (как background-size: cover), обрезка по центру.
    fast — кадр растягивания окна: из уменьшенной копии и попроще, но с той же обрезкой."""
    iw, ih = img.size
    s = max(w / iw, h / ih)
    # обрезка считается в долях исходника — одна и та же у быстрого и полного кадра
    cw, ch = w / s, h / s
    box = (max(0.0, (iw - cw) / 2), max(0.0, (ih - ch) / 2), min(iw, (iw + cw) / 2), min(ih, (ih + ch) / 2))
    if fast:
        small = _small(img)
        k = small.width / iw
        return small.resize((w, h), Image.BILINEAR, box=tuple(v * k for v in box))
    return img.resize((w, h), Image.LANCZOS, box=box)


_small_cache: dict = {}


def _small(img: Image.Image) -> Image.Image:
    """Копия исходника не больше 1000 px — для быстрых кадров."""
    key = id(img)
    if key not in _small_cache:
        _small_cache.clear()
        f = max(1, max(img.size) // 1000)
        _small_cache[key] = (img, img.reduce(f) if f > 1 else img)   # img держим, чтобы id не повторился
    return _small_cache[key][1]


_src_cache: dict = {}


def _load(path: Path) -> Image.Image | None:
    key = (str(path), path.stat().st_mtime if path.exists() else 0)
    if key not in _src_cache:
        _src_cache.clear()
        try:
            _src_cache[key] = Image.open(path).convert("RGB")
        except Exception:
            _src_cache[key] = None
    return _src_cache[key]


def render(w: int, h: int, mode: str = "picture", custom: str = "", brightness: int = 50,
           blur: int = 0, scale: float = 1.0, fast: bool = False) -> Image.Image:
    w, h = max(2, int(w)), max(2, int(h))
    if mode == "sky":
        pic = _sky(w, h, scale)
    else:
        src = _load(Path(custom)) if mode == "custom" and custom else None
        if src is None:
            src = _load(backdrop_path())
        if src is None:
            return _sky(w, h, scale)
        pic = _cover(src, w, h, fast)
        pic = Image.fromarray((np.asarray(pic, dtype=np.float32) * (brightness / 100.0)).astype(np.uint8))
    if blur > 0:
        pic = pic.filter(ImageFilter.GaussianBlur(blur / 100.0 * BACKDROP_BLUR_MAX * scale))
    return pic
