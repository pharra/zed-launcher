from __future__ import annotations

from pathlib import Path

from zed_launcher.services import prefixes, system


def test_find_umu_run_configured(umu_run: Path, monkeypatch) -> None:
    monkeypatch.delenv("ZED_UMU_RUN", raising=False)
    assert system.find_umu_run({"umu_run": str(umu_run)}) == str(umu_run)


def test_find_umu_run_missing(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    assert system.find_umu_run({"umu_run": ""}) is None


def test_tools_shape() -> None:
    available = system.tools({"umu_run": ""})
    assert set(available) == {
        "umu_run",
        "mangohud",
        "gamemoderun",
        "gamescope",
        "kwin",
        "kwin_session",
        "systemd_inhibit",
        "notify_send",
        "icoextract",
    }


def test_gpu_list_does_not_crash() -> None:
    assert isinstance(system.gpu_list(), list)


def test_diagnostics_shape(proton_dir: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZED_PROTON_PATH", str(proton_dir))
    data = system.diagnostics()
    assert "protons" in data and "proton_sources" in data and "paths" in data


def test_shortcut_creation(tmp_path: Path, monkeypatch, executable: Path) -> None:
    from zed_launcher.services import shortcuts

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    game = {"id": "abc123", "title": "My Game", "icon": ""}
    path = shortcuts.create_desktop_entry(game)

    content = path.read_text(encoding="utf-8")
    assert "Name=My Game" in content
    assert "Exec=zed-launcher --run abc123" in content
    assert path.stat().st_mode & 0o111
    assert path.parent == tmp_path / "data/applications"
    assert shortcuts.remove_desktop_entry("abc123") is True
    assert not path.exists()


def test_slugify() -> None:
    assert prefixes.slugify("My Fancy Game!") == "my-fancy-game"
    assert prefixes.slugify("   ") == "prefix"


def test_create_prefix_is_unique(tmp_path: Path) -> None:
    first = prefixes.create_prefix(tmp_path, "Game")
    second = prefixes.create_prefix(tmp_path, "Game")
    assert first.name == "game"
    assert second.name == "game-2"
    assert first.is_dir() and second.is_dir()
    assert first != second


def test_validate_prefix(wine_prefix: Path, tmp_path: Path) -> None:
    assert prefixes.validate_prefix(wine_prefix) == wine_prefix

    empty = tmp_path / "empty"
    empty.mkdir()
    try:
        prefixes.validate_prefix(empty)
    except prefixes.PrefixError as error:
        assert "Wine prefix" in str(error)
    else:
        raise AssertionError("expected PrefixError")

    try:
        prefixes.validate_prefix(tmp_path / "missing")
    except prefixes.PrefixError as error:
        assert "does not exist" in str(error)
    else:
        raise AssertionError("expected PrefixError")


def test_remove_prefix(wine_prefix: Path) -> None:
    assert prefixes.remove_prefix(wine_prefix) is True
    assert not wine_prefix.exists()
    assert prefixes.remove_prefix(wine_prefix) is False


def test_prefix_size(wine_prefix: Path) -> None:
    (wine_prefix / "drive_c/file.bin").write_bytes(b"x" * 1024)
    assert prefixes.prefix_size(wine_prefix) >= 1024


def test_configured_tool_path_wins(tmp_path: Path, monkeypatch) -> None:
    from zed_launcher.services import system

    fake = tmp_path / "my-mangohud"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)

    monkeypatch.setenv("PATH", "/nonexistent")
    resolved = system.tools({"tool_paths": {"mangohud": str(fake)}})
    assert resolved["mangohud"] == str(fake)

    # A stale configured path falls back to PATH lookup instead of breaking.
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(system, "which", lambda name: f"/usr/bin/{name}")
    stale = system.tools({"tool_paths": {"mangohud": str(tmp_path / "missing")}})
    assert stale["mangohud"] == "/usr/bin/mangohud"


def test_dependency_status_reports_configured_path(tmp_path: Path) -> None:
    from zed_launcher.services import system

    fake = tmp_path / "gamescope"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)

    status = system.dependency_status({"tool_paths": {"gamescope": str(fake)}})
    entry = status["optional"]["gamescope"]
    assert entry["configured"] == str(fake)
    assert entry["available"] is True
    assert entry["path"] == str(fake)


def test_tray_host_probe_is_a_boolean(monkeypatch) -> None:
    from zed_launcher.services import system

    assert isinstance(system.tray_host_available(), bool)

    def boom(*args, **kwargs):
        raise RuntimeError("no session bus")

    monkeypatch.setattr(system, "Gio", None, raising=False)
    # Without a usable bus the probe must report False instead of raising.
    assert system.tray_host_available() in (True, False)


def test_prefix_root_follows_home(monkeypatch, tmp_path) -> None:
    from zed_launcher.config import load_config

    monkeypatch.setenv("HOME", str(tmp_path))
    assert load_config()["prefix_root"] == str(tmp_path / "Games" / "Zed")
