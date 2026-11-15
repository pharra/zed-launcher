"""Find and terminate Wine processes that belong to a single prefix."""

from __future__ import annotations

import contextlib
import os
import signal
import time
from pathlib import Path

WINE_HINTS = (
    "wineserver",
    "winedevice.exe",
    "wine-preloader",
    "wine64-preloader",
    "services.exe",
    "explorer.exe",
    "winemenubuilder",
)


def _read(path: str) -> bytes:
    with contextlib.suppress(OSError), open(path, "rb") as handle:
        return handle.read()
    return b""


def _cwd(pid: int) -> str:
    with contextlib.suppress(OSError):
        return os.readlink(f"/proc/{pid}/cwd")
    return ""


def _argv(pid: int) -> list[str]:
    raw = _read(f"/proc/{pid}/cmdline")
    return [part for part in raw.decode("utf-8", "replace").split("\0") if part]


def _prefix_of(pid: int) -> str:
    for entry in _read(f"/proc/{pid}/environ").split(b"\0"):
        if entry.startswith(b"WINEPREFIX="):
            return entry.split(b"=", 1)[1].decode("utf-8", "replace")
    return ""


def _is_wine(argv: list[str], cwd: str, prefix: str) -> bool:
    haystack = " ".join([*argv, cwd, prefix]).lower()
    return any(hint in haystack for hint in WINE_HINTS)


def leftovers(prefix_path: str | Path) -> list[dict[str, object]]:
    """Wine processes whose environment or working directory points at ``prefix_path``."""

    target = str(Path(prefix_path).expanduser())
    if not target:
        return []

    found: list[dict[str, object]] = []
    own = os.getpid()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == own:
            continue
        argv = _argv(pid)
        if not argv:
            continue
        env_prefix = _prefix_of(pid)
        cwd = _cwd(pid)
        if env_prefix != target and not cwd.startswith(target + os.sep) and cwd != target:
            continue
        if not _is_wine(argv, cwd, env_prefix):
            continue
        found.append({"pid": pid, "command": " ".join(argv)[:200]})
    return found


def terminate(prefix_path: str | Path, *, grace: float = 2.0) -> int:
    """SIGTERM the leftovers for ``prefix_path``; SIGKILL whatever survives."""

    targets = leftovers(prefix_path)
    if not targets:
        return 0

    for entry in targets:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(int(entry["pid"]), signal.SIGTERM)

    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not leftovers(prefix_path):
            return len(targets)
        time.sleep(0.1)

    for entry in leftovers(prefix_path):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(int(entry["pid"]), signal.SIGKILL)
    return len(targets)
