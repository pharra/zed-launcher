"""Find and terminate the processes that belong to one run or one Wine prefix.

Every launch exports ``ZED_RUN_ID`` so the whole tree - umu-run, the pressure-vessel
container, the Proton wrapper, wineserver and every wine process - can be found again
even after they call ``setsid`` and leave the launcher's process group.

Matching is always exact: an environment entry that equals ``KEY=value``. Pids are
recorded together with their ``/proc/<pid>/stat`` start time so a recycled pid is never
signalled.
"""

from __future__ import annotations

import contextlib
import os
import signal
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

RUN_MARKER = "ZED_RUN_ID"

WINE_NAMES = frozenset(
    {
        "wine",
        "wine64",
        "wine-preloader",
        "wine64-preloader",
        "wineserver",
        "winedevice.exe",
        "winemenubuilder.exe",
        "services.exe",
        "explorer.exe",
        "plugplay.exe",
        "rpcss.exe",
        "svchost.exe",
        "conhost.exe",
    }
)


@dataclass(frozen=True)
class ProcessRef:
    """A pid plus the start time that identifies it across pid reuse."""

    pid: int
    starttime: str

    @property
    def alive(self) -> bool:
        return starttime_of(self.pid) == self.starttime


def _read(path: str) -> bytes:
    with contextlib.suppress(OSError), open(path, "rb") as handle:
        return handle.read()
    return b""


def starttime_of(pid: int) -> str:
    """Field 22 of ``/proc/<pid>/stat``, empty when the process is gone."""

    raw = _read(f"/proc/{pid}/stat").decode("utf-8", "replace")
    if not raw:
        return ""
    # The command name may contain spaces and parentheses, so split after the last ')'.
    _head, _separator, rest = raw.rpartition(")")
    fields = rest.split()
    # rest starts at field 3 (state), so field 22 (starttime) is index 19.
    return fields[19] if len(fields) > 19 else ""


def _cwd(pid: int) -> str:
    with contextlib.suppress(OSError):
        return os.readlink(f"/proc/{pid}/cwd")
    return ""


def _argv(pid: int) -> list[str]:
    raw = _read(f"/proc/{pid}/cmdline")
    return [part for part in raw.decode("utf-8", "replace").split("\0") if part]


def _environ(pid: int) -> list[bytes]:
    return [entry for entry in _read(f"/proc/{pid}/environ").split(b"\0") if entry]


def _env_value(pid: int, key: str) -> str:
    prefix = f"{key}=".encode()
    for entry in _environ(pid):
        if entry.startswith(prefix):
            return entry[len(prefix) :].decode("utf-8", "replace")
    return ""


def _has_marker(pid: int, run_id: str) -> bool:
    return f"{RUN_MARKER}={run_id}".encode() in _environ(pid)


def _basenames(argv: Iterable[str], limit: int = 4) -> set[str]:
    names: set[str] = set()
    for argument in list(argv)[:limit]:
        name = argument.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if name:
            names.add(name)
    return names


def _is_wine(argv: list[str]) -> bool:
    return bool(_basenames(argv) & WINE_NAMES)


def _pids() -> list[int]:
    with contextlib.suppress(OSError):
        return sorted(int(entry.name) for entry in Path("/proc").iterdir() if entry.name.isdigit())
    return []


def run_processes(run_id: str) -> list[ProcessRef]:
    """Every live process carrying ``ZED_RUN_ID=<run_id>``."""

    if not run_id:
        return []
    own = os.getpid()
    found: list[ProcessRef] = []
    for pid in _pids():
        if pid == own:
            continue
        if not _has_marker(pid, run_id):
            continue
        started = starttime_of(pid)
        if started:
            found.append(ProcessRef(pid=pid, starttime=started))
    return found


def leftovers(prefix_path: str | Path) -> list[ProcessRef]:
    """Wine processes that belong to ``prefix_path``.

    A process matches when its ``WINEPREFIX`` environment entry is exactly the prefix,
    or - for wine helpers that dropped the variable - when it is a known wine binary
    whose working directory is inside the prefix.
    """

    target = str(Path(prefix_path).expanduser())
    if not target:
        return []

    own = os.getpid()
    found: list[ProcessRef] = []
    for pid in _pids():
        if pid == own:
            continue
        argv = _argv(pid)
        if not argv:
            continue
        if _env_value(pid, "WINEPREFIX") == target:
            pass
        else:
            cwd = _cwd(pid)
            inside = bool(cwd) and (cwd == target or cwd.startswith(target + os.sep))
            if not inside or not _is_wine(argv):
                continue
        started = starttime_of(pid)
        if started:
            found.append(ProcessRef(pid=pid, starttime=started))
    return found


def terminate_refs(refs: list[ProcessRef], *, grace: float = 2.0) -> int:
    """SIGTERM the given processes, SIGKILL whatever survives the grace period."""

    live = [entry for entry in refs if entry.alive]
    if not live:
        return 0

    for entry in live:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(entry.pid, signal.SIGTERM)

    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not any(entry.alive for entry in live):
            return len(live)
        time.sleep(0.05)

    for entry in live:
        if entry.alive:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(entry.pid, signal.SIGKILL)
    return len(live)


def terminate_run(run_id: str, *, grace: float = 2.0) -> int:
    """Stop everything a single run started, including wineserver in its own session."""

    return terminate_refs(run_processes(run_id), grace=grace)


def terminate_prefix(prefix_path: str | Path, *, grace: float = 2.0) -> int:
    """Stop the wine processes of a prefix (prefix tools, not a tracked run)."""

    return terminate_refs(leftovers(prefix_path), grace=grace)


def same_process(pid: int | None, started: str) -> bool:
    """True when ``pid`` is still the process that had this start time."""

    if not pid:
        return False
    if not started:
        return False
    return starttime_of(int(pid)) == started


def belongs_to_run(pid: int | None, run_id: str) -> bool:
    """Whether ``pid`` is alive *and* still carries this run's marker.

    A recycled pid - or a pid that now belongs to something else - returns False, so a
    finished run is never reported as running because an unrelated process reused the
    number.
    """

    if not pid or not run_id:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return _has_marker(int(pid), run_id)
