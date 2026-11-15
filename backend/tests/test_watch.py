from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from zed_launcher import store, watch
from zed_launcher.services import processes


def _dead_pid() -> int:
    process = subprocess.Popen(["true"])
    process.wait()
    return process.pid


def test_resolve_dead_run_records_exit(executable: Path, tmp_path: Path) -> None:
    game = store.create_game(
        {"title": "Watched", "path": str(executable), "prefix_path": str(tmp_path / "p")}
    )
    run = store.create_run(game["id"], str(tmp_path / "log"))

    assert watch.resolve_dead_run(run["id"], game["id"], _dead_pid()) is True

    finished = store.get_run(run["id"])
    assert finished is not None
    assert finished["status"] == "closed"
    refreshed = store.get_game(game["id"])
    assert refreshed is not None
    assert refreshed["last_played"] is not None


def test_resolve_skips_alive_process(executable: Path, tmp_path: Path) -> None:
    game = store.create_game(
        {"title": "Alive", "path": str(executable), "prefix_path": str(tmp_path / "p")}
    )
    run = store.create_run(game["id"], str(tmp_path / "log"))

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        env={**os.environ, "ZED_RUN_ID": run["id"]},
    )
    try:
        store.set_run_pid(run["id"], child.pid, processes.starttime_of(child.pid))
        assert watch.resolve_dead_run(run["id"], game["id"], child.pid) is False
        current = store.get_run(run["id"])
        assert current is not None
        assert current["status"] in ("starting", "running")
    finally:
        child.kill()
        child.wait(timeout=10)


def test_resolve_ignores_recycled_pid(executable: Path, tmp_path: Path) -> None:
    """A live pid that is not ours must not keep the run open."""

    game = store.create_game(
        {"title": "Recycled", "path": str(executable), "prefix_path": str(tmp_path / "p")}
    )
    run = store.create_run(game["id"], str(tmp_path / "log"))

    assert watch.resolve_dead_run(run["id"], game["id"], os.getpid()) is True
    current = store.get_run(run["id"])
    assert current is not None
    assert current["status"] == "closed"


def test_resolve_skips_finished_run(executable: Path, tmp_path: Path) -> None:
    game = store.create_game(
        {"title": "Done", "path": str(executable), "prefix_path": str(tmp_path / "p")}
    )
    run = store.create_run(game["id"], str(tmp_path / "log"))
    store.finish_run(run["id"], "exited", 0, 5)

    assert watch.resolve_dead_run(run["id"], game["id"], _dead_pid()) is False
    current = store.get_run(run["id"])
    assert current is not None
    assert current["duration"] == 5


def test_main_requires_arguments() -> None:
    assert watch.main([]) == 2
    assert watch.main(["a"]) == 2
    assert watch.main(["a", "b", "not-a-pid"]) == 2
