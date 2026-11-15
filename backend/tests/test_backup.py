from __future__ import annotations

import time
import zipfile
from pathlib import Path

import pytest

from zed_launcher import store
from zed_launcher.services import backup


def _seed(executable: Path, artwork: Path) -> dict:
    game = store.create_game(
        {"title": "Backup Game", "path": str(executable), "prefix_path": "/tmp/prefix"}
    )
    store.update_game(game["id"], {"cover": "covers/backup.png"})
    covers = artwork / "covers"
    covers.mkdir(parents=True)
    (covers / "backup.png").write_bytes(b"png-bytes")
    return game


def test_create_and_restore_roundtrip(tmp_path: Path, executable: Path) -> None:
    from zed_launcher.paths import artwork_dir

    game = _seed(executable, artwork_dir())
    result = backup.create_backup(str(tmp_path / "backups"))

    archive = Path(result["path"])
    assert archive.is_file()
    assert result["games"] == 1
    assert result["artwork_files"] == 1

    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
    assert "library.db" in names
    assert "backup.json" in names
    assert "artwork/covers/backup.png" in names

    # Lose the library and the artwork, then restore.
    store.delete_game(game["id"])
    assert store.list_games() == []
    (artwork_dir() / "covers" / "backup.png").unlink()

    restored = backup.restore_backup(str(archive))
    assert restored["games"] == 1
    assert restored["artwork_files"] == 1
    assert (artwork_dir() / "covers" / "backup.png").read_bytes() == b"png-bytes"

    recovered = store.get_game(game["id"])
    assert recovered is not None
    assert recovered["title"] == "Backup Game"


def test_restore_keeps_previous_database(tmp_path: Path, executable: Path) -> None:
    from zed_launcher.paths import db_path

    _seed(executable, tmp_path)
    archive = backup.create_backup(str(tmp_path / "backups"))["path"]
    backup.restore_backup(archive)

    assert db_path().with_suffix(db_path().suffix + ".before-restore").is_file()


def test_list_and_describe(tmp_path: Path, executable: Path) -> None:
    _seed(executable, tmp_path)
    backup.create_backup(str(tmp_path / "backups"))
    entries = backup.list_backups(str(tmp_path / "backups"))

    assert len(entries) == 1
    assert entries[0]["restorable"] is True
    assert entries[0]["games"] == 1
    assert entries[0]["size"] > 0


def test_list_missing_directory(tmp_path: Path) -> None:
    assert backup.list_backups(str(tmp_path / "nope")) == []


def test_restore_rejects_invalid_zip(tmp_path: Path) -> None:
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"not a zip")
    with pytest.raises(backup.BackupError, match="valid zip"):
        backup.restore_backup(str(junk))


def test_restore_rejects_zip_without_library(tmp_path: Path) -> None:
    other = tmp_path / "other.zip"
    with zipfile.ZipFile(other, "w") as bundle:
        bundle.writestr("readme.txt", "hello")
    with pytest.raises(backup.BackupError, match="does not contain"):
        backup.restore_backup(str(other))


def test_restore_missing_file(tmp_path: Path) -> None:
    with pytest.raises(backup.BackupError, match="not found"):
        backup.restore_backup(str(tmp_path / "missing.zip"))


def test_delete_backup(tmp_path: Path, executable: Path) -> None:
    _seed(executable, tmp_path)
    archive = backup.create_backup(str(tmp_path / "backups"))["path"]
    assert backup.delete_backup(archive) is True
    assert backup.delete_backup(archive) is False


def test_backup_without_artwork(tmp_path: Path, executable: Path) -> None:
    _seed(executable, tmp_path)
    result = backup.create_backup(str(tmp_path / "backups"), include_artwork=False)
    with zipfile.ZipFile(result["path"]) as bundle:
        assert not any(name.startswith("artwork/") for name in bundle.namelist())


def test_restore_rejects_foreign_database(tmp_path: Path) -> None:
    import zipfile

    from zed_launcher.services import backup

    bogus = tmp_path / "zed-launcher-backup-bad.zip"
    with zipfile.ZipFile(bogus, "w") as bundle:
        bundle.writestr("library.db", b"this is not a database")

    with pytest.raises(backup.BackupError, match="not a Zed Launcher database"):
        backup.restore_backup(str(bogus))

    # The real library must survive a rejected restore.
    assert store.list_games() is not None


def test_savegames_are_backed_up_and_restored(executable: Path, tmp_path: Path) -> None:
    from zed_launcher.services import backup

    prefix = tmp_path / "prefix"
    saves = prefix / "drive_c/users/steamuser/Documents/My Games/Celeste"
    saves.mkdir(parents=True)
    (saves / "save.dat").write_bytes(b"progress")

    game = store.create_game(
        {"title": "Celeste", "path": str(executable), "prefix_path": str(prefix)}
    )

    result = backup.create_backup(str(tmp_path / "out"), include_saves=True)
    assert result["save_dirs"] >= 1

    estimate = backup.savegame_size([str(prefix)])
    assert estimate["bytes"] >= len(b"progress")

    (saves / "save.dat").unlink()
    restored = backup.restore_backup(result["path"])
    assert restored["save_files"] >= 1
    assert (saves / "save.dat").read_bytes() == b"progress"
    assert store.get_game(game["id"]) is not None


def test_schedule_due_only_when_configured(tmp_path: Path) -> None:
    from zed_launcher.services import backup

    config = {"backup_schedule": "off", "backup_dir": str(tmp_path / "b")}
    assert backup.schedule_due(config) is False
    assert backup.run_scheduled(config) is None

    config["backup_schedule"] = "daily"
    assert backup.schedule_due(config, now=time.time()) is True

    backup.create_backup(str(tmp_path / "b"), config=config)
    assert backup.schedule_due(config) is False
    assert backup.schedule_due(config, now=time.time() + 25 * 3600) is True
