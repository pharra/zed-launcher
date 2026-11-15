"""Desktop notifications through notify-send (freedesktop)."""

from __future__ import annotations

import contextlib
import os
import subprocess
from typing import Any

APP_NAME = "Zed Launcher"


def binary_path(config: dict[str, Any] | None = None) -> str | None:
    from . import system

    return system.resolve_tool("notify_send", config)


def available(config: dict[str, Any] | None = None) -> bool:
    return binary_path(config) is not None


def send(title: str, body: str = "", *, urgency: str = "normal", binary: str | None = None) -> bool:
    binary = binary or binary_path()
    if binary is None or not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return False
    argv = [
        binary,
        "--app-name",
        APP_NAME,
        "--urgency",
        urgency,
        "--icon",
        "zed-launcher",
        title,
    ]
    if body:
        argv.append(body)
    try:
        subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False
    return True


def resolve_language(setting: str | None) -> str:
    if setting in ("en", "zh"):
        return setting
    locale = (
        os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES")
        or os.environ.get("LANG")
        or ""
    )
    return "zh" if locale.lower().startswith("zh") else "en"


def notify_game_exit(
    title: str,
    status: str,
    duration: int,
    exit_code: int | None,
    language: str | None = None,
) -> None:
    minutes = duration // 60
    seconds = duration % 60
    played = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
    chinese = f"{minutes} 分 {seconds} 秒" if minutes else f"{seconds} 秒"
    zh = resolve_language(language) == "zh"
    if status == "exited":
        message = f"已退出，用时 {chinese}" if zh else f"Exited after {played}"
    elif status == "stopped":
        message = f"已停止，用时 {chinese}" if zh else f"Stopped after {played}"
    elif status == "closed":
        message = f"已关闭，用时 {chinese}" if zh else f"Closed after {played}"
    else:
        message = (
            f"启动失败，用时 {chinese}（退出码 {exit_code}）"
            if zh
            else f"Failed after {played} (exit {exit_code})"
        )
    with contextlib.suppress(Exception):
        send(title, message, urgency="normal", binary=binary_path())
