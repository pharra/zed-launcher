from __future__ import annotations

from pathlib import Path

from zed_launcher.services.command import SCRIPT_TOKEN, SESSION_TOKEN, LaunchPlan
from zed_launcher.services.runner import RunManager


def test_session_script_gets_the_batch_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZED_STATE_DIR", str(tmp_path / "state"))
    manager = RunManager()
    plan = LaunchPlan(
        argv=["kwin_wayland", "--exit-with-session", SESSION_TOKEN],
        script="@echo off\r\n",
        session_script=f"#!/bin/sh\nexec umu-run {SCRIPT_TOKEN}\n",
    )

    argv = manager._prepare_script(plan, "abc123", lambda _line: None)

    session = tmp_path / "state" / "scripts" / "abc123.sh"
    assert argv == ["kwin_wayland", "--exit-with-session", str(session)]
    # The wrapper has to point at the batch file that was just written, not at the token.
    assert f"exec umu-run {tmp_path / 'state' / 'scripts' / 'abc123.bat'}" in session.read_text()
    assert session.stat().st_mode & 0o111


def test_plan_without_scripts_is_untouched(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZED_STATE_DIR", str(tmp_path / "state"))
    manager = RunManager()
    plan = LaunchPlan(argv=["umu-run", "/game/game.exe"])

    assert manager._prepare_script(plan, "def456", lambda _line: None) == plan.argv
