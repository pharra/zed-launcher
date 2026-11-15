from __future__ import annotations

from pathlib import Path

from zed_launcher.services import autostart


def test_autostart_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert autostart.enabled() is False

    assert autostart.set_enabled(True) is True
    entry = autostart.entry_path()
    assert entry.is_file()
    text = entry.read_text(encoding="utf-8")
    assert "Type=Application" in text
    assert "Exec=" in text
    assert entry.parent == tmp_path / "autostart"

    assert autostart.set_enabled(False) is False
    assert entry.is_file() is False
