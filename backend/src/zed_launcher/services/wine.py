"""Wine prefix helpers: shortcuts, installer detection and prefix tools."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

UTILITY_KEYWORDS = ("uninstall", "setup", "config", "readme", "repair", "install")
_SKIP_DIRS = (
    "windows",
    "$recycle.bin",
    "temp",
    "system32",
    "syswow64",
    "windows.old",
    "locales",
    "redist",
    "redistributables",
    "_commonredist",
    "support",
    "docs",
    "directx",
    "vcredist",
    "installers",
)
_SKIP_EXE_HINTS = ("crash", "unins", "uninst", "setup", "install", "helper", "launcher_helper")


class WineError(RuntimeError):
    pass


# --- .lnk parsing -----------------------------------------------------------


def parse_lnk_target(lnk_path: str | Path) -> str | None:
    """Read the local base path from a Windows shortcut."""

    try:
        data = Path(lnk_path).read_bytes()
    except OSError:
        return None

    if len(data) < 76 or data[:4] != b"\x4c\x00\x00\x00":
        return None

    link_flags = int.from_bytes(data[20:24], "little")
    has_link_target_id_list = 0x01
    has_link_info = 0x02

    offset = 76
    if link_flags & has_link_target_id_list:
        if offset + 2 > len(data):
            return None
        id_list_size = int.from_bytes(data[offset : offset + 2], "little")
        offset += 2 + id_list_size

    if not (link_flags & has_link_info) or offset + 8 > len(data):
        return None

    link_info_start = offset
    header_size = int.from_bytes(data[link_info_start + 4 : link_info_start + 8], "little")
    info_flags = int.from_bytes(data[link_info_start + 8 : link_info_start + 12], "little")

    if not (info_flags & 0x01):
        return None

    local_offset = int.from_bytes(data[link_info_start + 16 : link_info_start + 20], "little")
    unicode_offset = 0
    if header_size >= 0x24 and link_info_start + 32 <= len(data):
        unicode_offset = int.from_bytes(data[link_info_start + 28 : link_info_start + 32], "little")

    if unicode_offset:
        start = link_info_start + unicode_offset
        if start >= len(data):
            return None
        end = data.find(b"\x00\x00", start)
        if end == -1:
            return None
        if (end - start) % 2:
            end += 1
        try:
            return data[start:end].decode("utf-16-le")
        except UnicodeDecodeError:
            return None

    if local_offset:
        start = link_info_start + local_offset
        if start >= len(data):
            return None
        end = data.find(b"\x00", start)
        if end == -1:
            return None
        return data[start:end].decode("cp1252", errors="replace")

    return None


def windows_path_to_prefix(win_path: str | None, prefix: str | Path) -> Path | None:
    if not win_path:
        return None
    cleaned = win_path.strip().strip('"')
    if len(cleaned) < 2 or cleaned[1] != ":":
        return None
    drive = cleaned[0].lower()
    rest = re.sub(r"\\+", "/", cleaned[2:]).lstrip("/")
    root = Path(prefix)
    if drive == "c":
        return root / "drive_c" / rest
    dosdevice = root / "dosdevices" / f"{drive}:"
    if dosdevice.is_symlink():
        return Path(os.path.realpath(dosdevice)) / rest
    return None


def resolve_ci(path: Path | None) -> Path | None:
    """Resolve a path case-insensitively, because Wine paths are case-insensitive."""

    if path is None:
        return None
    if path.is_file():
        return path
    if not path.parent.is_dir():
        return None
    wanted = path.name.lower()
    try:
        for entry in path.parent.iterdir():
            if entry.name.lower() == wanted and entry.is_file():
                return entry
    except OSError:
        return None
    return None


def list_shortcuts(prefix: str | Path) -> set[str]:
    root = Path(prefix)
    found: set[str] = set()
    for base in (root / "drive_c" / "users", root / "drive_c" / "ProgramData"):
        if not base.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in filenames:
                if name.lower().endswith(".lnk"):
                    found.add(os.path.join(dirpath, name))
    return found


def is_utility(name: str) -> bool:
    lowered = name.lower()
    return any(keyword in lowered for keyword in UTILITY_KEYWORDS)


def shortcut_candidates(prefix: str | Path, shortcuts: set[str] | None = None) -> list[dict[str, Any]]:
    """Turn .lnk files into launch candidates inside the prefix."""

    prefix_path = Path(prefix)
    entries = shortcuts if shortcuts is not None else list_shortcuts(prefix_path)
    by_name: dict[str, list[str]] = {}
    for shortcut in entries:
        by_name.setdefault(Path(shortcut).name.lower(), []).append(shortcut)

    results: list[dict[str, Any]] = []
    for paths in by_name.values():
        label = Path(paths[0]).stem.strip()
        if not label or is_utility(label):
            continue
        target: Path | None = None
        for shortcut in paths:
            resolved = resolve_ci(windows_path_to_prefix(parse_lnk_target(shortcut), prefix_path))
            if resolved is not None and resolved.suffix.lower() == ".exe":
                target = resolved
                break
        if target is None:
            continue
        results.append(
            {
                "name": label,
                "path": str(target),
                "shortcut": paths[0],
                "on_desktop": any("/Desktop" in p.replace(os.sep, "/") for p in paths),
                "in_menu": any("/Start Menu" in p.replace(os.sep, "/") for p in paths),
            }
        )
    return results


def detect_new_executable(prefix: str | Path, baseline: set[str]) -> str | None:
    """Best new shortcut target installed since ``baseline`` was taken."""

    candidates = shortcut_candidates(prefix, list_shortcuts(prefix) - baseline)
    if not candidates:
        return None
    preferred = [entry for entry in candidates if entry["in_menu"] or entry["on_desktop"]]
    pool = preferred or candidates
    best = min(pool, key=lambda entry: entry["name"].lower())
    return str(best["path"])


def scan_executables(prefix: str | Path, limit: int = 60) -> list[dict[str, Any]]:
    """Fallback search for executables inside a prefix."""

    root = Path(prefix) / "drive_c"
    if not root.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for base in (root / "Program Files", root / "Program Files (x86)", root / "Games", root / "ProgramData"):
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [name for name in dirnames if name.lower() not in _SKIP_DIRS]
            depth = len(Path(dirpath).relative_to(base).parts)
            if depth > 4:
                dirnames[:] = []
                continue
            for name in filenames:
                lowered = name.lower()
                if not lowered.endswith(".exe") or is_utility(name):
                    continue
                if any(hint in lowered for hint in _SKIP_EXE_HINTS):
                    continue
                path = Path(dirpath) / name
                results.append({"name": path.stem, "path": str(path)})
                if len(results) >= limit:
                    return results
    return results


def detect_after_install(prefix: str | Path, baseline: set[str]) -> dict[str, Any]:
    """Everything the wizard needs once the installer exits."""

    prefix_path = Path(prefix)
    new_shortcuts = list_shortcuts(prefix_path) - baseline
    candidates = shortcut_candidates(prefix_path, new_shortcuts)
    best = detect_new_executable(prefix_path, baseline)
    return {
        "best": best,
        "candidates": candidates,
        "fallback": [] if candidates else scan_executables(prefix_path),
    }
