from __future__ import annotations

from pathlib import Path

import pytest

from zed_launcher.services.command import PlanError, build_plan, umu_game_id


def make_game(path: Path, **overrides):
    game = {
        "id": "abc123",
        "title": "Test",
        "path": str(path),
        "prefix_path": "/tmp/prefix",
        "proton_path": "",
        "args": "",
        "launch_args": "",
        "working_dir": "",
        "pre_launch": "",
        "post_launch": "",
        "mangohud": False,
        "gamemode": False,
        "gamescope": False,
        "no_sleep": False,
        "sdl": False,
        "wayland": False,
        "wow64": False,
    }
    game.update(overrides)
    return game


def test_umu_game_id_is_stable() -> None:
    assert umu_game_id("abc123") == umu_game_id("abc123")
    assert umu_game_id("abc123").startswith("umu-zed")
    assert umu_game_id("abc123") != umu_game_id("abc124")


def test_plan_builds_umu_environment(
    executable: Path, umu_run: Path, proton_dir: Path, tmp_path: Path
) -> None:
    plan = build_plan(
        make_game(executable, args="--windowed"),
        prefix_path=str(tmp_path / "prefix"),
        proton_path=str(proton_dir),
        available={"umu_run": str(umu_run)},
        config={"gamescope_args": "-f"},
        log_dir=str(tmp_path / "logs"),
    )

    assert plan.argv == [str(umu_run), str(executable), "--windowed"]
    assert plan.env["WINEPREFIX"] == str(tmp_path / "prefix")
    assert plan.env["PROTONPATH"] == str(proton_dir)
    assert plan.env["GAMEID"] == umu_game_id("abc123")
    assert plan.env["UMU_LOG"] == "1"
    assert plan.env["PROTON_LOG_DIR"] == str(tmp_path / "logs")
    assert plan.cwd == str(executable.parent)


def test_wrappers_are_applied_in_order(
    executable: Path, umu_run: Path, proton_dir: Path, tmp_path: Path
) -> None:
    plan = build_plan(
        make_game(
            executable,
            no_sleep=True,
            gamemode=True,
            gamescope=True,
            mangohud=True,
        ),
        prefix_path=str(tmp_path / "prefix"),
        proton_path=str(proton_dir),
        available={
            "umu_run": str(umu_run),
            "systemd_inhibit": "/usr/bin/systemd-inhibit",
            "gamemoderun": "/usr/bin/gamemoderun",
            "gamescope": "/usr/bin/gamescope",
            "mangohud": "/usr/bin/mangohud",
        },
        config={"gamescope_args": "-f -W 1920 -H 1080"},
        log_dir=str(tmp_path / "logs"),
    )

    assert plan.argv[:8] == [
        "/usr/bin/systemd-inhibit",
        "--what=sleep:idle",
        "--why=Zed Launcher is running a game",
        "--",
        "/usr/bin/gamemoderun",
        "/usr/bin/gamescope",
        "-f",
        "-W",
    ]
    assert plan.argv[-2:] == [str(umu_run), str(executable)]
    assert "/usr/bin/mangohud" in plan.argv


def test_launch_arguments_split_env(
    executable: Path, umu_run: Path, proton_dir: Path, tmp_path: Path
) -> None:
    plan = build_plan(
        make_game(executable, launch_args="DXVK_HUD=fps PROTON_NO_ESYNC=1 --foo"),
        prefix_path=str(tmp_path / "prefix"),
        proton_path=str(proton_dir),
        available={"umu_run": str(umu_run)},
        config={},
        log_dir=str(tmp_path / "logs"),
    )

    assert plan.env["DXVK_HUD"] == "fps"
    assert plan.env["PROTON_NO_ESYNC"] == "1"
    # umu-run only accepts the executable as its first argument, so leftovers go
    # after the executable and the move is reported in the run log.
    assert plan.argv == [str(umu_run), str(executable), "--foo"]
    assert any("passed to the game" in note for note in plan.notes)


def test_missing_umu_raises(executable: Path, tmp_path: Path) -> None:
    with pytest.raises(PlanError, match="umu-run"):
        build_plan(
            make_game(executable),
            prefix_path=str(tmp_path / "prefix"),
            proton_path=str(tmp_path / "proton"),
            available={},
            config={},
            log_dir="/tmp",
        )


def test_missing_proton_raises(executable: Path, umu_run: Path, tmp_path: Path) -> None:
    with pytest.raises(PlanError, match="Proton"):
        build_plan(
            make_game(executable),
            prefix_path=str(tmp_path / "prefix"),
            proton_path=None,
            available={"umu_run": str(umu_run)},
            config={},
            log_dir="/tmp",
        )


def test_missing_prefix_raises(executable: Path, umu_run: Path, proton_dir: Path) -> None:
    with pytest.raises(PlanError, match="prefix"):
        build_plan(
            make_game(executable),
            prefix_path="",
            proton_path=str(proton_dir),
            available={"umu_run": str(umu_run)},
            config={},
            log_dir="/tmp",
        )


def test_missing_executable_raises(tmp_path: Path) -> None:
    with pytest.raises(PlanError, match="not found"):
        build_plan(
            make_game(tmp_path / "missing.exe"),
            prefix_path=str(tmp_path / "prefix"),
            proton_path=None,
            available={},
            config={},
            log_dir="/tmp",
        )


def _tool_plan(executable, umu_run, proton_dir, tmp_path, **overrides):
    available = {
        "umu_run": str(umu_run),
        "gamescope": "/usr/bin/gamescope",
        "mangohud": "/usr/bin/mangohud",
        "gamemoderun": "/usr/bin/gamemoderun",
    }
    return build_plan(
        make_game(executable, **overrides),
        prefix_path=str(tmp_path / "prefix"),
        proton_path=str(proton_dir),
        available=available,
        config={},
        log_dir=str(tmp_path / "logs"),
    )


def test_gamescope_uses_per_game_arguments(executable, umu_run, proton_dir, tmp_path) -> None:
    plan = _tool_plan(
        executable, umu_run, proton_dir, tmp_path, gamescope=True, gamescope_args="-W 1280 -H 720 -f"
    )
    gamescope = plan.argv.index("/usr/bin/gamescope")
    assert plan.argv[gamescope + 1 : gamescope + 4] == ["-W", "1280", "-H"]


def test_gamescope_falls_back_to_fullscreen(executable, umu_run, proton_dir, tmp_path) -> None:
    plan = _tool_plan(executable, umu_run, proton_dir, tmp_path, gamescope=True, gamescope_args="")
    gamescope = plan.argv.index("/usr/bin/gamescope")
    assert plan.argv[gamescope + 1] == "-f"
    assert plan.argv[gamescope + 2] == "--"


def test_mangohud_arguments_follow_the_binary(executable, umu_run, proton_dir, tmp_path) -> None:
    plan = _tool_plan(
        executable, umu_run, proton_dir, tmp_path, mangohud=True, mangohud_args="--dlsym"
    )
    mangohud = plan.argv.index("/usr/bin/mangohud")
    assert plan.argv[mangohud + 1] == "--dlsym"
    assert plan.argv[mangohud + 2].endswith("umu-run")


def test_gamescope_chain_order(executable, umu_run, proton_dir, tmp_path) -> None:
    plan = _tool_plan(
        executable,
        umu_run,
        proton_dir,
        tmp_path,
        gamescope=True,
        mangohud=True,
        gamemode=True,
    )
    names = [Path(part).name for part in plan.argv]
    assert names.index("gamemoderun") < names.index("gamescope") < names.index("mangohud")
    assert names.index("mangohud") < names.index("umu-run")


def test_env_lines_become_environment(executable, umu_run, proton_dir, tmp_path) -> None:
    plan = build_plan(
        make_game(executable, env="DXVK_HUD=fps\nexport MANGOHUD_CONFIG=cpu_temp\n# comment\n"),
        prefix_path=str(tmp_path / "prefix"),
        proton_path=str(proton_dir),
        available={"umu_run": str(umu_run)},
        config={},
        log_dir=str(tmp_path / "logs"),
    )
    assert plan.env["DXVK_HUD"] == "fps"
    assert plan.env["MANGOHUD_CONFIG"] == "cpu_temp"
    assert plan.argv == [str(umu_run), str(executable)]


def test_launcher_args_never_precede_the_executable(
    executable, umu_run, proton_dir, tmp_path
) -> None:
    plan = build_plan(
        make_game(executable, launch_args="--some-flag --other=value"),
        prefix_path=str(tmp_path / "prefix"),
        proton_path=str(proton_dir),
        available={"umu_run": str(umu_run)},
        config={},
        log_dir=str(tmp_path / "logs"),
    )
    assert plan.argv == [str(umu_run), str(executable), "--some-flag", "--other=value"]
    assert plan.argv[1] == str(executable)
    assert "some-flag" not in plan.env


def test_legacy_mixed_launch_args_are_split(executable, umu_run, proton_dir, tmp_path) -> None:
    plan = build_plan(
        make_game(executable, launch_args="DXVK_HUD=fps --some-flag"),
        prefix_path=str(tmp_path / "prefix"),
        proton_path=str(proton_dir),
        available={"umu_run": str(umu_run)},
        config={},
        log_dir=str(tmp_path / "logs"),
    )
    assert plan.env["DXVK_HUD"] == "fps"
    assert plan.argv == [str(umu_run), str(executable), "--some-flag"]


def test_env_field_overrides_legacy_value(executable, umu_run, proton_dir, tmp_path) -> None:
    plan = build_plan(
        make_game(executable, env="DXVK_HUD=compiler", launch_args="DXVK_HUD=fps"),
        prefix_path=str(tmp_path / "prefix"),
        proton_path=str(proton_dir),
        available={"umu_run": str(umu_run)},
        config={},
        log_dir=str(tmp_path / "logs"),
    )
    assert plan.env["DXVK_HUD"] == "compiler"


def test_invalid_env_line_is_rejected(executable, umu_run, proton_dir, tmp_path) -> None:
    with pytest.raises(PlanError, match="Invalid environment variable line"):
        build_plan(
            make_game(executable, env="NOT AN ASSIGNMENT"),
            prefix_path=str(tmp_path / "prefix"),
            proton_path=str(proton_dir),
            available={"umu_run": str(umu_run)},
            config={},
            log_dir=str(tmp_path / "logs"),
        )


def test_game_arguments_follow_the_executable(executable, umu_run, proton_dir, tmp_path) -> None:
    plan = build_plan(
        make_game(executable, args="-windowed -novid"),
        prefix_path=str(tmp_path / "prefix"),
        proton_path=str(proton_dir),
        available={"umu_run": str(umu_run)},
        config={},
        log_dir=str(tmp_path / "logs"),
    )
    assert plan.argv == [str(umu_run), str(executable), "-windowed", "-novid"]


def test_wrappers_stay_before_umu_run(executable, umu_run, proton_dir, tmp_path) -> None:
    plan = _tool_plan(executable, umu_run, proton_dir, tmp_path, gamescope=True, mangohud=True)
    assert Path(plan.argv[0]).name == "gamescope"
    assert Path(plan.argv[-2]).name == "umu-run"
    assert plan.argv[-1] == str(executable)


def test_every_program_runs_inside_one_umu_invocation(
    executable, umu_run, proton_dir, tmp_path
) -> None:
    first = tmp_path / "trainer.exe"
    last = tmp_path / "overlay.exe"
    first.write_bytes(b"")
    last.write_bytes(b"")
    plan = _tool_plan(
        executable,
        umu_run,
        proton_dir,
        tmp_path,
        extra_programs=[
            {"kind": "program", "path": str(first), "args": "-a 1", "delay": 0},
            {"kind": "game", "path": "ignored.exe"},
            {"kind": "program", "path": str(last), "args": "", "delay": 5},
        ],
    )
    # One umu-run call for the whole run, so every program shares the container.
    assert plan.argv.count(str(umu_run)) == 1
    assert plan.argv[1].endswith("cmd.exe") or plan.argv[1] == "cmd"
    assert plan.argv[2] == "/c"
    assert plan.argv[3] == "__ZED_REPLACE_ME__"
    assert plan.order == [str(first), str(executable), str(last)]

    script = plan.script
    assert script.startswith("@echo off\r\n")
    # extras first, then the game with /wait so cmd keeps the session alive
    assert script.index("trainer.exe") < script.index(executable.name)
    assert 'start "" /wait' in script
    assert "ping -n 6 127.0.0.1" in script  # the 5s delay of the program below the game
    assert script.rstrip().endswith("exit /b %ZED_GAME_EXIT%")


def test_game_entry_is_appended_when_missing(executable, umu_run, proton_dir, tmp_path) -> None:
    extra = tmp_path / "tools.exe"
    extra.write_bytes(b"")
    plan = _tool_plan(
        executable,
        umu_run,
        proton_dir,
        tmp_path,
        extra_programs=[{"kind": "program", "path": str(extra)}],
    )
    assert plan.order == [str(extra), str(executable)]


def test_no_script_without_extra_programs(executable, umu_run, proton_dir, tmp_path) -> None:
    plan = _tool_plan(executable, umu_run, proton_dir, tmp_path)
    assert plan.script == ""
    assert plan.argv[1] == str(executable)


def test_missing_extra_program_is_skipped_with_note(executable, umu_run, proton_dir, tmp_path) -> None:
    plan = _tool_plan(
        executable,
        umu_run,
        proton_dir,
        tmp_path,
        extra_programs=[{"kind": "program", "path": str(tmp_path / "gone.exe")}],
    )
    assert plan.script == ""
    assert any("gone.exe" in note for note in plan.notes)
    assert plan.argv[-1].endswith(".exe")


def test_duplicate_game_entries_are_collapsed(tmp_path: Path) -> None:
    from zed_launcher.services.command import normalize_programs

    sequence = normalize_programs(
        [
            {"kind": "game", "path": "old.exe"},
            {"kind": "program", "path": "/x/a.exe"},
            {"kind": "game", "path": "old.exe"},
            {"kind": "program", "path": "  "},
        ],
        "/games/real.exe",
    )
    assert [entry["kind"] for entry in sequence] == ["game", "program"]
    assert sequence[0]["path"] == "/games/real.exe"
    assert sequence[1]["delay"] == 0


def _prefix_tool_plan(proton_dir: Path, umu_run: Path, **kwargs):
    from zed_launcher.services.command import build_tool_plan

    return build_tool_plan(
        prefix_path="/tmp/prefix",
        proton_path=str(proton_dir),
        umu_run=str(umu_run),
        log_dir="/tmp/logs",
        **kwargs,
    )


def test_regedit_imports_through_the_proton_builtin(
    proton_dir: Path, umu_run: Path, tmp_path: Path
) -> None:
    wine_dir = proton_dir / "files/lib/wine/x86_64-windows"
    wine_dir.mkdir(parents=True)
    regedit = wine_dir / "regedit.exe"
    regedit.write_text("", encoding="utf-8")
    reg = tmp_path / "hidpi.reg"
    reg.write_text("Windows Registry Editor Version 5.00\n", encoding="utf-8")

    plan = _prefix_tool_plan(proton_dir, umu_run, kind="regedit", target=str(reg))
    assert plan.argv[1] == str(regedit)
    # Silent import, and a DOS path: wine programs cannot open /home/... arguments.
    assert plan.argv[2] == "/S"
    assert plan.argv[3] == f"Z:{reg}".replace("/", "\\")


def test_regedit_falls_back_to_the_bare_name(proton_dir: Path, umu_run: Path, tmp_path: Path) -> None:
    reg = tmp_path / "x.reg"
    reg.write_text("", encoding="utf-8")
    plan = _prefix_tool_plan(proton_dir, umu_run, kind="regedit", target=str(reg))
    assert plan.argv[1] == "regedit"


def test_missing_registry_file_is_rejected(proton_dir: Path, umu_run: Path, tmp_path: Path) -> None:
    with pytest.raises(PlanError, match="Registry file not found"):
        _prefix_tool_plan(proton_dir, umu_run, kind="regedit", target=str(tmp_path / "gone.reg"))


def test_a_reg_file_run_as_exe_is_imported(
    proton_dir: Path, umu_run: Path, tmp_path: Path
) -> None:
    reg = tmp_path / "layer.reg"
    reg.write_text("", encoding="utf-8")
    plan = _prefix_tool_plan(proton_dir, umu_run, kind="exe", target=str(reg))
    assert plan.argv[1].endswith("regedit.exe") or plan.argv[1] == "regedit"
    assert plan.argv[2] == "/S"


def test_tool_plan_defaults_to_c_locale(proton_dir: Path, umu_run: Path) -> None:
    plan = _prefix_tool_plan(proton_dir, umu_run, kind="winecfg")
    # Otherwise Proton generates locales inside the container on every run.
    assert plan.env["LANG"] == "C"
    assert plan.env["LC_ALL"] == "C"
    assert plan.env["WINEPREFIX"] == "/tmp/prefix"


def test_tool_plan_env_overrides_the_defaults(proton_dir: Path, umu_run: Path) -> None:
    plan = _prefix_tool_plan(
        proton_dir,
        umu_run,
        kind="winecfg",
        env="LANG=zh_CN.UTF-8\nSTEAM_COMPAT_APP_ID=42\n# comment ignored",
    )
    assert plan.env["LANG"] == "zh_CN.UTF-8"
    assert plan.env["STEAM_COMPAT_APP_ID"] == "42"
    assert plan.env["LC_ALL"] == "C"


def test_tool_plan_rejects_a_broken_env_line(proton_dir: Path, umu_run: Path) -> None:
    with pytest.raises(PlanError, match="Invalid environment variable"):
        _prefix_tool_plan(proton_dir, umu_run, kind="winecfg", env="LANG")


def test_windows_backslashes_survive_argument_splitting() -> None:
    from zed_launcher.services.command import split_args

    # shlex in POSIX mode would turn C:\Games into C:Games and break the game.
    assert split_args(r"-path C:\Games\Foo") == ["-path", r"C:\Games\Foo"]
    assert split_args(r'-name "Two Words"') == ["-name", "Two Words"]
    assert split_args("/S Z:\\home\\wf\\a.reg") == ["/S", "Z:\\home\\wf\\a.reg"]
    assert split_args("") == []


def test_script_keeps_extra_program_arguments(
    executable, umu_run, proton_dir, tmp_path
) -> None:
    extra = tmp_path / "trainer.exe"
    extra.write_bytes(b"")
    plan = _tool_plan(
        executable,
        umu_run,
        proton_dir,
        tmp_path,
        extra_programs=[
            {"kind": "program", "path": str(extra), "args": r"--cfg C:\x\y.ini"},
            {"kind": "game"},
        ],
    )
    assert r"--cfg C:\x\y.ini" in plan.script
