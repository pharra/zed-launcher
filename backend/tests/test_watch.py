from __future__ import annotations

import os
import subprocess
from pathlib import Path

from zed_launcher import store, watch


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

    assert watch.resolve_dead_run(run["id"], game["id"], os.getpid()) is False
    current = store.get_run(run["id"])
    assert current is not None
    assert current["status"] in ("starting", "running")


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
