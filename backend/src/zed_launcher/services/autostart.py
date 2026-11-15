"""Manage the XDG autostart entry."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ENTRY_NAME = "zed-launcher.desktop"

CONTENT = """[Desktop Entry]
Type=Application
Name=Zed Launcher
Comment=Start the game launcher with your session
Exec={exec}
Icon=zed-launcher
Terminal=false
Categories=Game;
X-GNOME-Autostart-enabled=true
"""


def autostart_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "autostart"


def entry_path() -> Path:
    return autostart_dir() / ENTRY_NAME


def enabled() -> bool:
    return entry_path().is_file()


def set_enabled(value: bool) -> bool:
    path = entry_path()
    if not value:
        path.unlink(missing_ok=True)
        return False

    launcher = shutil.which("zed-launcher") or "zed-launcher"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CONTENT.format(exec=launcher), encoding="utf-8")
    path.chmod(0o644)
    return True
