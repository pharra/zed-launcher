"""Turn raw Wine/Proton output into a short, actionable hint."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Hint:
    key: str
    message: str
    chinese: str


RULES: tuple[tuple[re.Pattern[str], Hint], ...] = (
    (
        re.compile(r"err:vulkan|vulkan.*not found|failed to (?:create|init)\w* vulkan", re.I),
        Hint(
            "vulkan",
            "The Vulkan driver could not be initialised. Check that your GPU driver is installed "
            "and that the Proton build supports it.",
            "Vulkan 驱动初始化失败。请检查显卡驱动是否安装，以及 Proton 版本是否支持。",
        ),
    ),
    (
        re.compile(r"wine: (?:created|.*)prefix|wine: cannot find|is not a valid win32 application", re.I),
        Hint(
            "prefix",
            "The Wine prefix looks broken or incomplete. Recreate it, or point the game at a valid prefix.",
            "Wine prefix 可能损坏或不完整。请重建 prefix，或在编辑中指到有效的 prefix。",
        ),
    ),
    (
        re.compile(r"missing .* (?:d3dcompiler|d3dx9|d3dx11|vcruntime|msvcp|msvcr)", re.I),
        Hint(
            "runtimes",
            "A Windows runtime is missing. Install it with winetricks (vcrun2022, d3dx9) from the prefix tools.",
            "缺少 Windows 运行库。可在 prefix 工具中用 winetricks 安装（vcrun2022、d3dx9）。",
        ),
    ),
    (
        re.compile(r"(?:dll|module) not found|cannot import dll|unimplemented function", re.I),
        Hint(
            "dll",
            "A required DLL is missing. Install the usual redistributables with winetricks, then try again.",
            "缺少必要的 DLL。请用 winetricks 安装常用运行库后重试。",
        ),
    ),
    (
        re.compile(r"easy anti-?cheat|battleye|denuvo|failed to initialize anti", re.I),
        Hint(
            "anticheat",
            "This game uses anti-cheat that usually refuses to run under Proton.",
            "该游戏使用反作弊组件，在 Proton 下通常无法运行。",
        ),
    ),
    (
        re.compile(r"no space left on device", re.I),
        Hint(
            "disk",
            "The disk is full. Free some space before launching the game again.",
            "磁盘已满，请先腾出空间后再启动游戏。",
        ),
    ),
    (
        re.compile(r"permission denied", re.I),
        Hint(
            "permission",
            "A file could not be accessed. Check the permissions of the game folder and the prefix.",
            "文件访问被拒绝。请检查游戏目录与 prefix 的权限。",
        ),
    ),
    (
        re.compile(r"single_pixel_buffer_manager_v1 isn't supported", re.I),
        Hint(
            "kwin-protocols",
            "KWin cannot open its window in this desktop session: the running compositor lacks "
            "wp_single_pixel_buffer_manager_v1, which nested KWin requires. Run the desktop session "
            "under KWin itself, or turn KWin off for this game (Gamescope still works).",
            "KWin 无法在当前桌面会话里开窗口：正在运行的合成器缺少 "
            "wp_single_pixel_buffer_manager_v1（嵌套 KWin 必需）。请把桌面会话换成 KWin，"
            "或为此游戏关闭 KWin（Gamescope 仍可用）。",
        ),
    ),
    (
        re.compile(r"umu(?:-launcher)?: .*(?:runtime|steamrt)|steam runtime (?:missing|not found)", re.I),
        Hint(
            "runtime",
            "The Steam Linux Runtime container could not start. Run umu-launcher once from a terminal "
            "so it can download the runtime.",
            "Steam Linux Runtime 容器启动失败。请在终端中直接运行一次 umu-launcher 让它下载运行时。",
        ),
    ),
)


def analyse(lines: list[str], *, limit: int = 400) -> list[dict[str, str]]:
    """Return the distinct hints that match the tail of ``lines``."""

    text = "\n".join(lines[-limit:])
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for pattern, hint in RULES:
        if hint.key in seen or not pattern.search(text):
            continue
        seen.add(hint.key)
        found.append({"key": hint.key, "message": hint.message, "chinese": hint.chinese})
    return found
