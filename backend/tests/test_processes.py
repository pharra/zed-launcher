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
        pids = {entry["pid"] for entry in found}
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
        assert processes.terminate(prefix) >= 1
        child.wait(timeout=10)
        assert processes.leftovers(prefix) == []
    finally:
        if child.poll() is None:
            child.kill()
