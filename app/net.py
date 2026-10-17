"""Скачивание больших файлов (модели, голоса, библиотеки) с докачкой и повторами:
связь бывает рваной, а файлы — сотни мегабайт."""

import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable


def download(url: str, dest: Path, progress: Callable[[float], None] = lambda _f: None,
             attempts: int = 20) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    last = None
    for attempt in range(attempts):
        have = part.stat().st_size if part.exists() else 0
        req = urllib.request.Request(url, headers={"User-Agent": "VoiceImitator",
                                                   **({"Range": f"bytes={have}-"} if have else {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                if have and r.status != 206:   # сервер не умеет докачку — сначала
                    have = 0
                total = have + int(r.headers.get("Content-Length") or 0)
                with open(part, "ab" if have else "wb") as f:
                    while chunk := r.read(1 << 18):
                        f.write(chunk)
                        have += len(chunk)
                        if total:
                            progress(have / total)
            if not total or have >= total:
                part.replace(dest)
                return
        except urllib.error.HTTPError as e:
            if e.code == 416 and part.exists():   # уже докачано целиком
                part.replace(dest)
                return
            if e.code in (403, 404):
                raise RuntimeError(f"файла нет на сервере ({e.code})")
            last = e
        except (OSError, urllib.error.URLError) as e:
            last = e
        time.sleep(min(5, 1 + attempt))
    raise RuntimeError(f"связь всё время обрывается — попробуйте позже ({last})")
