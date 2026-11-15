from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from platformdirs import user_desktop_dir

from ..paths import artwork_dir


def applications_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".local/share"
    return root / "applications"


def _escape(value: str) -> str:
    return " ".join(str(value).split())


def _icon_value(game: dict[str, Any]) -> str:
    """Absolute artwork path, or the theme icon name when the game has none."""

    for key in ("cover", "icon"):
        value = str(game.get(key) or "").strip()
        if not value:
            continue
        candidate = Path(value).expanduser()
        if candidate.is_absolute() and candidate.is_file():
            return str(candidate)
    root = artwork_dir()
    for key in ("cover", "icon"):
        value = str(game.get(key) or "").strip()
        if value:
            candidate = root / value
            if candidate.is_file():
                return str(candidate)
    return "zed-launcher"


def create_desktop_entry(game: dict[str, Any], target: str = "applications") -> Path:
    launcher = shutil.which("zed-launcher") or "zed-launcher"
    directory = applications_dir() if target == "applications" else Path(user_desktop_dir())
    directory.mkdir(parents=True, exist_ok=True)

    path = directory / f"zed-launcher-{game['id']}.desktop"
    icon = _icon_value(game)
    content = "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            f"Name={_escape(game.get('title') or 'Game')}",
            "Comment=Launch with Zed Launcher",
            f"Exec={launcher} --run {game['id']}",
            f"Icon={icon}",
            "Terminal=false",
            "Categories=Game;",
            "StartupWMClass=zed-launcher",
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


def remove_desktop_entry(game_id: str, target: str = "applications") -> bool:
    directory = applications_dir() if target == "applications" else Path(user_desktop_dir())
    path = directory / f"zed-launcher-{game_id}.desktop"
    if path.exists():
        path.unlink()
        return True
    return False
