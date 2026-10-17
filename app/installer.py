"""Установщик VoiceImitator, как в ZapretLauncher: всегда ставит последнюю версию с GitHub.

Отличие от лаунчера: программа весит ~180 МБ (внутри PyTorch), поэтому установщик —
отдельный маленький VoiceImitatorSetup.exe. Он находит последний релиз по адресу
/releases/latest (не через API — у того лимит запросов в час), скачивает
VoiceImitator.exe с докачкой (связь до GitHub бывает рваной), кладёт его в папку
пользователя (права администратора не нужны), создаёт ярлыки и запись в «Приложениях».

Для проверок без следов в системе: переменная VOICEIMITATOR_SETUP_TEST=1 — другие
имена ярлыков и записи реестра, программа после установки не запускается.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import winreg
from dataclasses import dataclass
from pathlib import Path

from app import __version__

TEST = os.environ.get("VOICEIMITATOR_SETUP_TEST") == "1"
APP_NAME = "VoiceImitator"
TITLE = APP_NAME + (" Test" if TEST else "")
EXE = "VoiceImitator.exe"
SETUP_EXE = "VoiceImitatorSetup.exe"
REPO = "pikacu1337/VoiceImitator"
RELEASES = f"https://github.com/{REPO}/releases"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\VoiceImitator" + ("Test" if TEST else "")
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "VoiceImitator"   # настройки, модель
NO_WINDOW = 0x08000000   # CREATE_NO_WINDOW


@dataclass
class Release:
    tag: str
    url: str

    @property
    def version(self) -> str:
        return self.tag.lstrip("vV")


def default_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Programs" / (APP_NAME + ("Test" if TEST else ""))


def existing_dir() -> Path | None:
    """Куда программа уже установлена — чтобы переустановка предложила ту же папку."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
            value, _ = winreg.QueryValueEx(k, "InstallLocation")
            return Path(value) if value else None
    except OSError:
        return None


def installed_version() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
            return winreg.QueryValueEx(k, "DisplayVersion")[0]
    except OSError:
        return None


# ------------------------------------------------------------- GitHub

def _opener():
    return urllib.request.build_opener()


def latest_release(timeout: float = 15) -> Release:
    """Последний релиз: идём по адресу /releases/latest до тега, на который он ведёт."""
    req = urllib.request.Request(RELEASES + "/latest", method="HEAD",
                                 headers={"User-Agent": f"VoiceImitatorSetup/{__version__}"})
    last_error = None
    for _ in range(4):
        try:
            with _opener().open(req, timeout=timeout) as resp:
                final = resp.geturl()
            m = re.match(r"^(https://github\.com/[^/]+/[^/]+/releases)/tag/([^/?#]+)$", final)
            if not m:
                raise RuntimeError("на GitHub пока нет ни одного релиза")
            return Release(tag=urllib.request.unquote(m.group(2)),
                           url=f"{m.group(1)}/download/{m.group(2)}/{EXE}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_error = e
            time.sleep(1.5)
    raise RuntimeError(f"GitHub не отвечает ({last_error})")


def download(url: str, dest: Path, progress=lambda done, total: None, attempts: int = 30) -> Path:
    """Скачивает с докачкой: обрыв посреди файла — продолжаем с того же места."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    total = None
    for attempt in range(attempts):
        have = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": f"VoiceImitatorSetup/{__version__}"}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with _opener().open(urllib.request.Request(url, headers=headers), timeout=30) as resp:
                if have and resp.status != 206:      # сервер не умеет докачку — начинаем заново
                    have = 0
                    part.unlink(missing_ok=True)
                length = int(resp.headers.get("Content-Length") or 0)
                total = have + length if length else total
                with open(part, "ab" if have else "wb") as f:
                    while True:
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        have += len(chunk)
                        progress(have, total)
            if total and have >= total:
                break
        except urllib.error.HTTPError as e:
            if e.code == 416 and total and have >= total:   # уже скачано целиком
                break
            if e.code in (403, 404):
                raise RuntimeError(f"файла нет на GitHub ({e.code})")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            pass
        time.sleep(min(5, 1 + attempt * 0.5))
    else:
        raise RuntimeError("связь с GitHub всё время обрывается — попробуйте ещё раз позже")

    with open(part, "rb") as f:
        head = f.read(2)
    if part.stat().st_size < 10 * 1024 * 1024 or head != b"MZ":
        part.unlink(missing_ok=True)
        raise RuntimeError("скачанный файл не похож на программу")
    part.replace(dest)
    return dest


# ------------------------------------------------------------- установка

def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def shortcut(link: Path, target: Path) -> None:
    """Ярлык .lnk — через COM-объект WScript.Shell (из PowerShell, без лишних библиотек)."""
    link.parent.mkdir(parents=True, exist_ok=True)
    script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(link)});"
              f"$s.TargetPath={_ps_quote(target)};$s.WorkingDirectory={_ps_quote(target.parent)};"
              f"$s.IconLocation={_ps_quote(str(target) + ',0')};$s.Description={_ps_quote(APP_NAME)};$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   check=True, creationflags=NO_WINDOW, capture_output=True, timeout=30)


def start_menu_link() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{TITLE}.lnk"


def desktop_link() -> Path:
    return Path(os.environ["USERPROFILE"]) / "Desktop" / f"{TITLE}.lnk"


def stop_running() -> None:
    """Закрыть запущенную программу, чтобы её файл можно было заменить."""
    subprocess.run(["taskkill", "/F", "/IM", EXE], creationflags=NO_WINDOW, capture_output=True)
    time.sleep(0.5)


def self_path() -> Path | None:
    return Path(sys.executable) if getattr(sys, "frozen", False) else None


def install(dir_: Path, new_exe: Path, version: str, desktop: bool) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    stop_running()
    exe = dir_ / EXE
    if new_exe != exe:
        exe.unlink(missing_ok=True)
        shutil.move(str(new_exe), str(exe))

    me = self_path()   # копия установщика рядом — для удаления из «Приложений»
    setup = dir_ / SETUP_EXE
    if me and me.resolve() != setup.resolve():
        shutil.copy2(me, setup)

    shortcut(start_menu_link(), exe)
    if desktop:
        shortcut(desktop_link(), exe)
    else:
        desktop_link().unlink(missing_ok=True)

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, TITLE)
        winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, version)
        winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, str(exe))
        winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, "pikacu1337")
        winreg.SetValueEx(k, "URLInfoAbout", 0, winreg.REG_SZ, f"https://github.com/{REPO}")
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, str(dir_))
        winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ, f'"{setup}" --uninstall')
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, exe.stat().st_size // 1024)
    return exe


def uninstall(dir_: Path | None, keep_settings: bool) -> None:
    stop_running()
    start_menu_link().unlink(missing_ok=True)
    desktop_link().unlink(missing_ok=True)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass
    if not keep_settings and not TEST and DATA_DIR.exists():
        shutil.rmtree(DATA_DIR, ignore_errors=True)
    if dir_:
        # только свои файлы: папку выбирал пользователь, в ней может лежать что-то ещё
        for name in (EXE, SETUP_EXE):
            try:
                (dir_ / name).unlink(missing_ok=True)
            except OSError:
                pass
        try:
            if dir_.exists() and not any(dir_.iterdir()):
                dir_.rmdir()
        except OSError:
            pass


# ------------------------------------------------------------- удаление из «Приложений»

def relaunch_from_temp(args: list[str]) -> bool:
    """Удаление запущено из папки программы: копируем себя во %TEMP% и продолжаем оттуда,
    чтобы файл в папке можно было удалить. True — копия запущена, этот процесс выходит."""
    me = self_path()
    if not me:
        return False
    tmp = Path(tempfile.gettempdir())
    if str(me).lower().startswith(str(tmp).lower()):
        return False
    copy = tmp / f"VoiceImitatorUninstall-{os.getpid()}.exe"
    shutil.copy2(me, copy)
    subprocess.Popen([str(copy), *args, "--dir", str(me.parent)], close_fds=True)
    return True


def schedule_self_delete() -> None:
    """Копия во %TEMP% удаляет себя после выхода."""
    me = self_path()
    if not me or not str(me).lower().startswith(tempfile.gettempdir().lower()):
        return
    subprocess.Popen(f'cmd.exe /c ping 127.0.0.1 -n 3 >nul & del /q "{me}"',
                     creationflags=NO_WINDOW, close_fds=True)


def arg_after(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None
