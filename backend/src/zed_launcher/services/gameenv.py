from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Exact names a game or Proton needs from the session.
KEEP_EXACT = frozenset(
    {
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XAUTHORITY",
        "DBUS_SESSION_BUS_ADDRESS",
        "XDG_RUNTIME_DIR",
        "XDG_SESSION_TYPE",
        "XDG_SESSION_DESKTOP",
        "XDG_CURRENT_DESKTOP",
        "XDG_SEAT",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "TMPDIR",
        "TZ",
        "LANG",
        "LANGUAGE",
        "DRI_PRIME",
        "__GLX_VENDOR_LIBRARY_NAME",
        "__NV_PRIME_RENDER_OFFLOAD",
        "__VK_LAYER_NV_optimus",
        "NVD_BACKEND",
        "SDL_VIDEODRIVER",
        "SDL_AUDIODRIVER",
    }
)

# Prefixes worth carrying over: locale, audio, GPU drivers and the tuning knobs
# users set globally (Wine, DXVK, VKD3D, MangoHud, Gamescope).
KEEP_PREFIXES = (
    "LC_",
    "PULSE_",
    "PIPEWIRE_",
    "MESA_",
    "VK_",
    "LIBVA_",
    "WINE",
    "DXVK_",
    "VKD3D_",
    "MANGOHUD",
    "GAMESCOPE_",
    "SDL_",
)

# Everything the launcher itself brings along is dropped: Nix build inputs, the
# GTK/GObject typelib paths, the editor's variables and any LD_* injection.
# Forwarding LD_LIBRARY_PATH in particular makes pressure-vessel capture those
# host libraries into the Proton container.
DROP_PREFIXES = (
    "LD_",
    "PYTHON",
    "GI_",
    "GTK_",
    "GDK_",
    "QT_",
    "GSETTINGS_",
    "VSCODE_",
    "ZED_",
    "NIX_",
    "STEAM_",
    "UMU_",
    "PROTON_",
    "COPILOT_",
    "DENIA",
)


def _wanted(name: str) -> bool:
    if name in KEEP_EXACT:
        return True
    if any(name.startswith(prefix) for prefix in DROP_PREFIXES):
        return False
    return any(name.startswith(prefix) for prefix in KEEP_PREFIXES)


def game_path(parent: Mapping[str, str]) -> str:
    """Host directories first, then whatever the session already provides."""

    home = parent.get("HOME") or str(Path.home())
    host = [
        f"{home}/.nix-profile/bin",
        "/run/current-system/sw/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]
    entries = [path for path in host if Path(path).is_dir()]
    entries.extend(part for part in parent.get("PATH", "").split(":") if part)
    return ":".join(dict.fromkeys(entries))


def game_env(
    overrides: Mapping[str, str] | None = None,
    parent: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the environment for umu-run, the game and any extra program."""

    source = os.environ if parent is None else parent
    env = {key: value for key, value in source.items() if _wanted(key)}
    env["PATH"] = game_path(source)
    env.update({str(key): str(value) for key, value in (overrides or {}).items()})
    return env


def describe(env: Mapping[str, Any]) -> str:
    """Short human-readable summary used in log notes."""

    return f"PATH={env.get('PATH', '')}"
