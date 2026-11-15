from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..config import expand, load_config
from ..paths import config_dir, data_dir, log_dir, state_dir
from . import icons, proton, wayland


def which(name: str) -> str | None:
    return shutil.which(name)


def find_umu_run(config: dict[str, Any] | None = None) -> str | None:
    config = config or load_config()
    configured = expand(str(config.get("umu_run") or ""))
    candidates = [
        configured,
        os.environ.get("ZED_UMU_RUN", ""),
        which("umu-run") or "",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


OPTIONAL_TOOLS = {
    "mangohud": "MangoHud",
    "gamemoderun": "GameMode",
    "gamescope": "Gamescope",
    "kwin": "KWin (nested session)",
    "systemd_inhibit": "systemd-inhibit",
    "notify_send": "Desktop notifications",
    "icoextract": "Icon extraction",
}


TOOL_BINARIES = {
    "mangohud": "mangohud",
    "gamemoderun": "gamemoderun",
    "gamescope": "gamescope",
    "kwin": "kwin_wayland",
    "systemd_inhibit": "systemd-inhibit",
    "notify_send": "notify-send",
}


def configured_tools(config: dict[str, Any]) -> dict[str, str]:
    raw = config.get("tool_paths")
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value).strip() for key, value in raw.items() if str(value).strip()}


def resolve_tool(name: str, config: dict[str, Any] | None = None) -> str | None:
    """A configured path wins over PATH lookup, but only when it is a real file."""

    config = config if config is not None else load_config()
    override = configured_tools(config).get(name, "")
    if override:
        candidate = Path(expand(override))
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    binary = TOOL_BINARIES.get(name, name)
    return which(binary)


def tools(config: dict[str, Any] | None = None) -> dict[str, str | None]:
    config = config or load_config()
    return {
        "umu_run": find_umu_run(config),
        "mangohud": resolve_tool("mangohud", config),
        "gamemoderun": resolve_tool("gamemoderun", config),
        "gamescope": resolve_tool("gamescope", config),
        "kwin": resolve_tool("kwin", config),
        # The binary is not enough: a nested KWin also needs a protocol from the host
        # compositor, so every caller of build_plan gets the session verdict too.
        "kwin_session": wayland.probe(),
        "systemd_inhibit": resolve_tool("systemd_inhibit", config),
        "notify_send": resolve_tool("notify_send", config),
        "icoextract": "available" if icons.available() else None,
    }


def tray_host_available() -> bool:
    """Does this desktop provide a StatusNotifierWatcher for the tray icon?"""

    try:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
    except (ImportError, ValueError):
        return False

    try:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = connection.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "NameHasOwner",
            GLib.Variant("(s)", ("org.kde.StatusNotifierWatcher",)),
            GLib.VariantType("(b)"),
            Gio.DBusCallFlags.NONE,
            500,
            None,
        )
    except Exception:
        return False
    return bool(reply.get_child_value(0).get_boolean())


def dependency_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Which runtime dependencies are available, split into required and optional."""

    config = config or load_config()
    available = tools(config)
    builds = proton.candidates(config)
    proton_path = proton.find(str(config.get("proton_default") or ""), config)

    umu_path = available["umu_run"]
    required = {
        "umu_run": {
            "available": umu_path is not None,
            "path": umu_path,
            "hint": "Install umu-launcher or set its path in Settings.",
            "warning": (
                "This is the unwrapped build. pressure-vessel cannot create its container from it "
                "(bwrap: execvp true / ld.so.cache). Use pkgs.umu-launcher instead."
                if umu_path and "umu-launcher-unwrapped" in umu_path
                else ""
            ),
        },
        "proton": {
            "available": bool(builds),
            "path": proton_path,
            "count": len(builds),
            "hint": "Download a Proton build from the Proton manager.",
        },
    }
    overrides = configured_tools(config)
    optional = {
        key: {
            "available": available.get(key) is not None,
            "path": available.get(key),
            "label": label,
            "configured": overrides.get(key, ""),
            "hint": f"{label} is not installed, so this option is unavailable.",
        }
        for key, label in OPTIONAL_TOOLS.items()
    }
    # A nested KWin needs wp_single_pixel_buffer_manager_v1 from the host compositor.
    optional["kwin"]["session"] = available.get("kwin_session") or {}
    missing = [key for key, entry in required.items() if not entry["available"]]
    return {
        "required": required,
        "optional": optional,
        "missing_required": missing,
        "ready": not missing,
    }


def gpu_list() -> list[dict[str, str]]:
    gpus: list[dict[str, str]] = []
    drm = Path("/sys/class/drm")
    if not drm.is_dir():
        return gpus
    for card in sorted(drm.glob("card[0-9]*")):
        device = card / "device"
        vendor_path = device / "vendor"
        device_path = device / "device"
        if not vendor_path.is_file():
            continue
        try:
            vendor = vendor_path.read_text().strip()
            device_id = device_path.read_text().strip() if device_path.is_file() else ""
        except OSError:
            continue
        gpus.append({"card": card.name, "vendor": vendor, "device": device_id})
    return gpus


def diagnostics() -> dict[str, Any]:
    config = load_config()
    return {
        "umu_run": find_umu_run(config),
        "protons": proton.candidates(config),
        "proton_sources": proton.sources(config),
        "tools": tools(config),
        "dependencies": dependency_status(config),
        "gpus": gpu_list(),
        "paths": {
            "config": str(config_dir()),
            "data": str(data_dir()),
            "state": str(state_dir()),
            "logs": str(log_dir()),
            "protons": str(proton.download_root()),
        },
        "environment": {
            "session_type": os.environ.get("XDG_SESSION_TYPE", ""),
            "desktop": os.environ.get("XDG_CURRENT_DESKTOP", ""),
            "nixos": Path("/etc/NIXOS").exists(),
        },
    }


def open_path(path: str) -> None:
    target = Path(path).expanduser()
    if not target.exists():
        raise FileNotFoundError(path)
    subprocess.Popen(["xdg-open", str(target)], start_new_session=True)
