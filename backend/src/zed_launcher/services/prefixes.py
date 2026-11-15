from __future__ import annotations

import re
import shutil
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class PrefixError(RuntimeError):
    pass


def slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return slug[:60] or "prefix"


def ensure_root(root: str | Path) -> Path:
    path = Path(root).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_prefix(root: str | Path, hint: str) -> Path:
    """Create a fresh, empty prefix directory under ``root``."""

    base = ensure_root(root)
    slug = slugify(hint)
    candidate = base / slug
    suffix = 2
    while candidate.exists():
        candidate = base / f"{slug}-{suffix}"
        suffix += 1
    try:
        candidate.mkdir(parents=True)
    except OSError as error:
        raise PrefixError(f"Could not create prefix: {error}") from error
    return candidate


def validate_prefix(path: str | Path) -> Path:
    target = Path(path).expanduser()
    if not target.exists():
        raise PrefixError(f"Prefix does not exist: {target}")
    if not target.is_dir():
        raise PrefixError(f"Prefix is not a directory: {target}")
    if not (target / "drive_c").is_dir() and not (target / "system.reg").is_file():
        raise PrefixError(
            f"{target} does not look like a Wine prefix (no drive_c or system.reg)"
        )
    return target


def require_dir(path: str | Path) -> Path:
    """Confirm the prefix folder still exists without forcing a fresh init.

    A brand new prefix is an empty directory: Wine fills it in on the first
    launch. A prefix that is gone entirely is a different story - recreating it
    silently would install the game into a blank environment.
    """

    target = Path(path).expanduser()
    if not target.is_dir():
        raise PrefixError(f"Prefix folder is missing: {target}")
    return target


def remove_prefix(path: str | Path) -> bool:
    target = Path(path).expanduser()
    if not target.is_dir():
        return False
    shutil.rmtree(target)
    return True


WINETRICKS_PRESETS = (
    {
        "id": "runtimes",
        "verbs": "vcrun2022 corefonts",
        "label": "Visual C++ 2022 and core fonts",
        "chinese": "Visual C++ 2022 与核心字体",
    },
    {
        "id": "legacy-runtimes",
        "verbs": "vcrun2019 d3dx9 d3dcompiler_47",
        "label": "Legacy DirectX and Visual C++ 2019",
        "chinese": "旧版 DirectX 与 Visual C++ 2019",
    },
    {
        "id": "dotnet48",
        "verbs": "dotnet48",
        "label": ".NET Framework 4.8",
        "chinese": ".NET Framework 4.8",
    },
    {
        "id": "physx",
        "verbs": "physx",
        "label": "NVIDIA PhysX",
        "chinese": "NVIDIA PhysX",
    },
    {
        "id": "media",
        "verbs": "mf wmp11",
        "label": "Media Foundation and Windows Media Player",
        "chinese": "Media Foundation 与 Windows Media Player",
    },
    {
        "id": "audio",
        "verbs": "xact xaudio2_7",
        "label": "DirectX audio (XACT, XAudio2)",
        "chinese": "DirectX 音频（XACT、XAudio2）",
    },
)

CLEANUP_PATTERNS = (
    "drive_c/users/*/Temp/**",
    "drive_c/windows/temp/**",
    "drive_c/windows/Logs/**",
    "*.log",
    "drive_c/users/*/AppData/Local/Temp/**",
)


def temp_size(path: str | Path) -> int:
    root = Path(path).expanduser()
    total = 0
    for pattern in CLEANUP_PATTERNS:
        for entry in root.glob(pattern):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat().st_size
            except OSError:
                continue
    return total


def cleanup_temp(path: str | Path) -> int:
    """Remove Wine temporary files from a prefix and return the bytes freed."""

    root = Path(path).expanduser()
    freed = 0
    for pattern in CLEANUP_PATTERNS:
        for entry in list(root.glob(pattern)):
            try:
                if entry.is_file(follow_symlinks=False):
                    size = entry.stat().st_size
                    entry.unlink()
                    freed += size
                elif entry.is_dir():
                    size = prefix_size(entry)
                    shutil.rmtree(entry, ignore_errors=True)
                    freed += size
            except OSError:
                continue
    return freed


def prefix_size(path: str | Path) -> int:
    total = 0
    for entry in Path(path).expanduser().rglob("*"):
        try:
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
        except OSError:
            continue
    return total
