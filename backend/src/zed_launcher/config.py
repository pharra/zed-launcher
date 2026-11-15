from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .paths import config_path, ensure_dirs


def default_prefix_root() -> str:
    """Resolved per call so HOME (and tests) are honoured."""

    return str(Path.home() / "Games" / "Zed")


DEFAULTS: dict[str, Any] = {
    "prefix_root": "",
    "proton_paths": [],
    "proton_default": "",
    "github_token": "",
    "steamgriddb_api_key": "",
    "notifications": True,
    "tray": False,
    "backup_dir": "",
    "backup_schedule": "off",
    "language": "auto",
    "umu_run": "",
    "tool_paths": {},
    "confirm_kill": True,
    "proton_log": False,
}

LEGACY_KEYS = ("default_prefix", "default_runner", "proton_path", "steam_cmd")


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _normalise(stored: dict[str, Any]) -> dict[str, Any]:
    config = dict(DEFAULTS)
    config["prefix_root"] = default_prefix_root()
    config.update(stored)

    legacy_prefix = stored.get("default_prefix")
    if legacy_prefix and not stored.get("prefix_root"):
        config["prefix_root"] = legacy_prefix

    legacy_proton = stored.get("proton_path")
    paths = config.get("proton_paths")
    if not isinstance(paths, list):
        paths = []
    paths = [str(entry) for entry in paths if entry]
    if legacy_proton and legacy_proton not in paths:
        paths.append(str(legacy_proton))
    config["proton_paths"] = paths

    for key in LEGACY_KEYS:
        config.pop(key, None)
    for key in [key for key in config if key not in DEFAULTS]:
        config.pop(key, None)
    return config


def load_config() -> dict[str, Any]:
    ensure_dirs()
    path = config_path()
    stored: dict[str, Any] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            stored = data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return _normalise(stored)


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = _normalise(config)
    _atomic_write(config_path(), merged)
    return merged


def update_config(patch: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    for key, value in patch.items():
        if key in DEFAULTS:
            config[key] = value
    return save_config(config)


def expand(value: str | None) -> str:
    if not value:
        return ""
    return os.path.expandvars(os.path.expanduser(value))
