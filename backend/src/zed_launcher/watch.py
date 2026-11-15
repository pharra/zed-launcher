"""Detached run watcher.

The GUI keeps a live view of a running game, but the game outlives the window.
Each launch also starts this tiny process: when the game process disappears it
records the exit and playtime, unless the GUI already did it.
"""

from __future__ import annotations

import contextlib
import sys
import time
from datetime import UTC, datetime

from . import store
from .config import load_config
from .services import processes
from .services.notify import notify_game_exit

POLL_INTERVAL = 2.0
SETTLE_DELAY = 3.0


def _alive(pid: int, run_id: str) -> bool:
    """Alive *and* still the process this run started (never a recycled pid)."""

    run = store.get_run(run_id) or {}
    started = str(run.get("pid_started") or "")
    if started:
        return processes.same_process(pid, started)
    return processes.belongs_to_run(pid, run_id)


def _duration(started_at: str | None, now: datetime) -> int:
    if not started_at:
        return 0
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return 0
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return max(0, int((now - started).total_seconds()))


def resolve_dead_run(run_id: str, game_id: str, pid: int) -> bool:
    """Close a run whose process is gone. Returns True when it was closed here."""

    run = store.get_run(run_id)
    if run is None:
        return False
    if pid > 0 and _alive(pid, run_id):
        return False

    duration = _duration(run.get("started_at"), datetime.now(UTC))
    # The game is gone, but wineserver may still be alive in its own session.
    with contextlib.suppress(Exception):
        processes.terminate_run(run_id, grace=1.0)
    if not store.resolve_run(run_id, "closed", None, duration):
        return False
    config = load_config()
    if config.get("notifications", True):
        game = store.get_game(run["game_id"]) or {}
        notify_game_exit(
            str(game.get("title") or "Game"),
            "closed",
            duration,
            None,
            language=config.get("language"),
        )
    return True


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 3:
        print("usage: python -m zed_launcher.watch RUN_ID GAME_ID PID", file=sys.stderr)
        return 2

    run_id, game_id, raw_pid = args
    try:
        pid = int(raw_pid)
    except ValueError:
        return 2

    while _alive(pid, run_id):
        time.sleep(POLL_INTERVAL)

    time.sleep(SETTLE_DELAY)
    with contextlib.suppress(Exception):
        resolve_dead_run(run_id, game_id, pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
