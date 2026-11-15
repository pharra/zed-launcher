from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from zed_launcher.services import processes


def _spawn(prefix: Path, name: str) -> subprocess.Popen:
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", name],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_leftovers_only_match_the_prefix(tmp_path: Path) -> None:
    mine = tmp_path / "mine"
    theirs = tmp_path / "theirs"
    mine.mkdir()
    theirs.mkdir()

    ours = _spawn(mine, "wineserver")
    other = _spawn(theirs, "wineserver")
    try:
        time.sleep(0.3)
        found = processes.leftovers(mine)
        pids = {entry.pid for entry in found}
        assert ours.pid in pids
        assert other.pid not in pids
    finally:
        ours.terminate()
        other.terminate()


def test_terminate_kills_leftovers(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    child = _spawn(prefix, "wineserver")
    try:
        time.sleep(0.3)
        assert processes.terminate_prefix(prefix) >= 1
        child.wait(timeout=10)
        assert processes.leftovers(prefix) == []
    finally:
        if child.poll() is None:
            child.kill()


def _spawn_family(prefix: Path, run_id: str, root: Path) -> subprocess.Popen:
    """A fake umu-run: a child that leaves our process group the way wineserver does."""

    script = root / "fake-umu"
    script.write_text(
        "import os, subprocess, sys, time\n"
        "subprocess.Popen(\n"
        "    [sys.executable, '-c', 'import time; time.sleep(60)'],\n"
        "    start_new_session=True,\n"
        "    stdout=subprocess.DEVNULL,\n"
        "    stderr=subprocess.DEVNULL,\n"
        ")\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    env["ZED_RUN_ID"] = run_id
    return subprocess.Popen(
        [sys.executable, str(script)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_run_marker_finds_children_that_left_the_group(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    parent = _spawn_family(prefix, "run-abc", tmp_path)
    try:
        assert _wait_for(lambda: len(processes.run_processes("run-abc")) >= 2)
        found = processes.run_processes("run-abc")
        assert any(entry.pid == parent.pid for entry in found)
        # The nested child is in its own session, so a killpg would have missed it.
        assert len({entry.pid for entry in found}) >= 2
    finally:
        processes.terminate_run("run-abc")
        parent.wait(timeout=10)
    assert processes.run_processes("run-abc") == []


def test_terminate_run_leaves_other_runs_alone(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    mine = _spawn_family(prefix, "run-mine", tmp_path)
    other = _spawn_family(prefix, "run-other", tmp_path)
    try:
        assert _wait_for(lambda: len(processes.run_processes("run-mine")) >= 2)
        assert _wait_for(lambda: len(processes.run_processes("run-other")) >= 2)
        processes.terminate_run("run-mine")
        mine.wait(timeout=10)
        assert processes.run_processes("run-mine") == []
        assert other.poll() is None
        assert processes.run_processes("run-other")
    finally:
        processes.terminate_run("run-mine")
        processes.terminate_run("run-other")
        for handle in (mine, other):
            if handle.poll() is None:
                handle.kill()
            handle.wait(timeout=10)


def test_leftovers_ignore_non_wine_process_inside_the_prefix(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    (prefix / "drive_c").mkdir(parents=True)
    env = os.environ.copy()
    env.pop("WINEPREFIX", None)
    idle = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", "helper"],
        cwd=prefix,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.3)
        assert all(entry.pid != idle.pid for entry in processes.leftovers(prefix))
    finally:
        idle.kill()
        idle.wait(timeout=10)


def test_same_process_rejects_a_recycled_pid() -> None:
    me = os.getpid()
    started = processes.starttime_of(me)
    assert processes.same_process(me, started) is True
    assert processes.same_process(me, "1") is False
    assert processes.same_process(me, "") is False
    assert processes.same_process(None, started) is False
