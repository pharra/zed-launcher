from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "zed-launcher"


def _home() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


def _xdg(env: str, fallback: str) -> Path:
    value = os.environ.get(env)
    return Path(value).expanduser() if value else _home() / fallback


def config_dir() -> Path:
    value = os.environ.get("ZED_CONFIG_DIR")
    return Path(value).expanduser() if value else _xdg("XDG_CONFIG_HOME", ".config") / APP_NAME


def data_dir() -> Path:
    value = os.environ.get("ZED_DATA_DIR")
    return Path(value).expanduser() if value else _xdg("XDG_DATA_HOME", ".local/share") / APP_NAME


def state_dir() -> Path:
    value = os.environ.get("ZED_STATE_DIR")
    return Path(value).expanduser() if value else _xdg("XDG_STATE_HOME", ".local/state") / APP_NAME


def cache_dir() -> Path:
    value = os.environ.get("ZED_CACHE_DIR")
    return Path(value).expanduser() if value else _xdg("XDG_CACHE_HOME", ".cache") / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


def db_path() -> Path:
    return data_dir() / "library.db"


def log_dir() -> Path:
    return state_dir() / "logs"


def prune_proton_logs(keep: int = 20) -> list[Path]:
    """Remove old ``steam-*.log`` files Proton writes into the log directory."""

    directory = log_dir()
    if not directory.is_dir():
        return []
    logs = sorted(
        (path for path in directory.glob("steam-*.log") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed: list[Path] = []
    for path in logs[keep:]:
        try:
            path.unlink()
        except OSError:
            continue
        removed.append(path)
    return removed


def script_dir() -> Path:
    """Batch files that start a whole run inside one umu-run invocation."""

    return state_dir() / "scripts"


def prune_scripts(keep: int = 200) -> list[Path]:
    """Drop launch scripts of old runs; they are only useful while debugging."""

    directory = script_dir()
    if not directory.is_dir():
        return []
    scripts = sorted(
        (
            path
            for pattern in ("*.bat", "*.sh")
            for path in directory.glob(pattern)
            if path.is_file()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed: list[Path] = []
    for path in scripts[keep:]:
        try:
            path.unlink()
        except OSError:
            continue
        removed.append(path)
    return removed


def artwork_dir() -> Path:
    return data_dir() / "artwork"


def web_root() -> Path | None:
    """Locate the built frontend."""

    value = os.environ.get("ZED_WEB_ROOT")
    if value:
        candidate = Path(value).expanduser()
        return candidate if candidate.is_dir() else None

    package_web = Path(__file__).resolve().parent / "web"
    if package_web.is_dir():
        return package_web

    repo_web = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return repo_web if repo_web.is_dir() else None


def ensure_dirs() -> None:
    for path in (config_dir(), data_dir(), state_dir(), cache_dir(), log_dir(), artwork_dir()):
        path.mkdir(parents=True, exist_ok=True)
