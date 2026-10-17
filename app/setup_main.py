"""VoiceImitatorSetup.exe: без аргументов — мастер установки, с --uninstall — удаление
(так его запускает «Приложения» Windows)."""

import sys
from pathlib import Path

from app import installer


def main():
    args = sys.argv[1:]
    if "--uninstall" in args:
        # из папки программы себя не удалить — продолжаем из копии во %TEMP%
        if "--dir" not in args and installer.relaunch_from_temp(args):
            return
        d = installer.arg_after(args, "--dir")
        mode, remove_dir = "uninstall", Path(d) if d else installer.existing_dir()
    else:
        mode, remove_dir = "install", None

    from app.setup_ui import SetupApp
    SetupApp(mode, remove_dir).mainloop()


if __name__ == "__main__":
    main()
