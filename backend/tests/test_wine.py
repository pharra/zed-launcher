from __future__ import annotations

import struct
from pathlib import Path

from zed_launcher.services import wine


def make_lnk(target: str) -> bytes:
    """Build a minimal Shell Link with a unicode local base path."""

    header = bytearray(76)
    header[0:4] = b"\x4c\x00\x00\x00"
    # LinkFlags: HasLinkInfo only (0x02)
    header[20:24] = struct.pack("<I", 0x02)

    encoded = target.encode("utf-16-le") + b"\x00\x00"
    header_size = 0x24
    # LinkInfo layout relative to its start.
    unicode_offset = header_size
    local_offset = 0
    link_info = bytearray(header_size)
    struct.pack_into("<I", link_info, 0, header_size)  # size (unused by parser)
    struct.pack_into("<I", link_info, 4, header_size)
    struct.pack_into("<I", link_info, 8, 0x01)  # VolumeIDAndLocalBasePath
    struct.pack_into("<I", link_info, 16, local_offset)
    struct.pack_into("<I", link_info, 28, unicode_offset)
    return bytes(header) + bytes(link_info) + encoded


def write_lnk(path: Path, target: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(make_lnk(target))
    return path


def make_prefix(root: Path) -> Path:
    prefix = root / "prefix"
    (prefix / "drive_c" / "users/steamuser/Desktop").mkdir(parents=True)
    (prefix / "drive_c" / "users/steamuser/AppData/Roaming/Microsoft/Windows/Start Menu/Programs").mkdir(
        parents=True
    )
    (prefix / "system.reg").write_text("")
    return prefix


def test_parse_lnk_target(tmp_path: Path) -> None:
    lnk = write_lnk(tmp_path / "game.lnk", r"C:\Games\My Game\game.exe")
    assert wine.parse_lnk_target(lnk) == r"C:\Games\My Game\game.exe"


def test_parse_lnk_rejects_junk(tmp_path: Path) -> None:
    junk = tmp_path / "junk.lnk"
    junk.write_bytes(b"nope")
    assert wine.parse_lnk_target(junk) is None


def test_windows_path_to_prefix(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    resolved = wine.windows_path_to_prefix(r"C:\Games\game.exe", prefix)
    assert resolved == prefix / "drive_c/Games/game.exe"

    drive_d = prefix / "dosdevices" / "d:"
    (prefix / "dosdevices").mkdir(exist_ok=True)
    target = tmp_path / "mnt"
    target.mkdir()
    drive_d.symlink_to(target)
    assert wine.windows_path_to_prefix(r"D:\stuff\a.exe", prefix) == target / "stuff/a.exe"
    assert wine.windows_path_to_prefix("relative", prefix) is None


def test_case_insensitive_resolution(tmp_path: Path) -> None:
    actual = tmp_path / "Game.Exe"
    actual.write_bytes(b"")
    assert wine.resolve_ci(tmp_path / "game.exe") == actual
    assert wine.resolve_ci(tmp_path / "missing.exe") is None


def test_shortcut_candidates_and_utility_filter(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    exe = prefix / "drive_c/Games/My Game/game.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")

    write_lnk(
        prefix / "drive_c/users/steamuser/Desktop/My Game.lnk",
        r"C:\Games\My Game\game.exe",
    )
    write_lnk(
        prefix / "drive_c/users/steamuser/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Uninstall My Game.lnk",
        r"C:\Games\My Game\uninstall.exe",
    )

    candidates = wine.shortcut_candidates(prefix)
    names = [entry["name"] for entry in candidates]
    assert names == ["My Game"]
    assert candidates[0]["path"] == str(exe)
    assert candidates[0]["on_desktop"] is True


def test_detect_new_executable_ignores_baseline(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    exe = prefix / "drive_c/Program Files/New Game/Game.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")

    before = wine.list_shortcuts(prefix)
    write_lnk(
        prefix / "drive_c/users/steamuser/Desktop/New Game.lnk",
        r"C:\Program Files\New Game\Game.exe",
    )

    assert wine.detect_new_executable(prefix, before) == str(exe)
    # Once recorded, the same shortcut is not "new" anymore.
    assert wine.detect_new_executable(prefix, wine.list_shortcuts(prefix)) is None


def test_scan_executables_fallback(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    game = prefix / "drive_c/Program Files/Studio/Game.exe"
    game.parent.mkdir(parents=True)
    game.write_bytes(b"")
    uninstall = prefix / "drive_c/Program Files/Studio/uninstall.exe"
    uninstall.write_bytes(b"")

    languages = prefix / "drive_c/Program Files/Studio/locales"
    languages.mkdir()
    (languages / "helper.exe").write_bytes(b"")

    found = wine.scan_executables(prefix)
    names = [entry["name"] for entry in found]
    assert "Game" in names
    assert "uninstall" not in names
    assert "helper" not in names


def test_detect_after_install_shape(tmp_path: Path) -> None:
    prefix = make_prefix(tmp_path)
    exe = prefix / "drive_c/Program Files/New/Game.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    write_lnk(
        prefix / "drive_c/users/steamuser/Desktop/New.lnk",
        r"C:\Program Files\New\Game.exe",
    )

    result = wine.detect_after_install(prefix, set())
    assert result["best"] == str(exe)
    assert result["candidates"][0]["path"] == str(exe)
    assert result["fallback"] == []

    empty_prefix = tmp_path / "empty-prefix"
    (empty_prefix / "drive_c").mkdir(parents=True)
    nothing = wine.detect_after_install(empty_prefix, set())
    assert nothing["best"] is None
    assert nothing["fallback"] == []
