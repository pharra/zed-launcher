from __future__ import annotations

import json
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import store
from ..config import expand, load_config
from ..paths import artwork_dir, data_dir, db_path

BACKUP_PREFIX = "zed-launcher-backup-"
METADATA_NAME = "backup.json"
LIBRARY_NAME = "library.db"
ARTWORK_DIR = "artwork"
RESTORE_SUFFIX = ".before-restore"
SAVES_DIR = "saves"
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class BackupError(RuntimeError):
    pass


def default_dir(config: dict[str, Any] | None = None) -> Path:
    config = config or load_config()
    configured = expand(str(config.get("backup_dir") or ""))
    path = Path(configured) if configured else data_dir() / "backups"
    return path


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _artwork_files() -> list[Path]:
    root = artwork_dir()
    if not root.is_dir():
        return []
    return [entry for entry in root.rglob("*") if entry.is_file()]


def create_backup(
    destination: str | None = None,
    include_artwork: bool = True,
    include_saves: bool = False,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a zip with the library database, artwork and optionally savegames."""

    target = Path(expand(destination)) if destination else default_dir(config)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise BackupError(f"Could not create the backup folder: {error}") from error

    library = db_path()
    if not library.is_file():
        raise BackupError("The library database does not exist yet")

    archive = target / f"{BACKUP_PREFIX}{_timestamp()}.zip"
    games = store.list_games()
    artwork = _artwork_files() if include_artwork else []
    prefixes = sorted({game["prefix_path"] for game in games if game["prefix_path"]})
    saves = [(prefix, savegame_dirs(prefix)) for prefix in prefixes] if include_saves else []

    metadata = {
        "app": "zed-launcher",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "games": len(games),
        "artwork_files": len(artwork),
        "prefixes": prefixes,
        "includes_saves": bool(include_saves),
        "save_dirs": sum(len(dirs) for _, dirs in saves),
    }

    try:
        with tempfile.TemporaryDirectory(dir=target) as tmp:
            snapshot = Path(tmp) / LIBRARY_NAME
            _snapshot_database(library, snapshot)
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.write(snapshot, LIBRARY_NAME)
                for entry in artwork:
                    bundle.write(entry, f"{ARTWORK_DIR}/{entry.relative_to(artwork_dir()).as_posix()}")
                for prefix, directories in saves:
                    key = _SAFE.sub("-", Path(prefix).name) or "prefix"
                    root = Path(prefix).expanduser()
                    for directory in directories:
                        try:
                            base = directory.resolve().relative_to(root.resolve())
                        except ValueError:
                            continue
                        for entry in directory.rglob("*"):
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            relative = entry.relative_to(directory).as_posix()
                            bundle.write(entry, f"{SAVES_DIR}/{key}/{base.as_posix()}/{relative}")
                bundle.writestr(METADATA_NAME, json.dumps(metadata, indent=2))
    except (OSError, zipfile.BadZipFile, sqlite3.Error) as error:
        archive.unlink(missing_ok=True)
        raise BackupError(f"Could not write the backup: {error}") from error

    return {
        "path": str(archive),
        "name": archive.name,
        "size": archive.stat().st_size,
        **metadata,
    }


SAVE_DIRS = (
    "drive_c/users/*/Documents/My Games",
    "drive_c/users/*/Documents/Saved Games",
    "drive_c/users/*/Saved Games",
    "drive_c/users/*/AppData/Roaming",
    "drive_c/users/*/AppData/LocalLow",
)


def savegame_dirs(prefix_path: str | Path) -> list[Path]:
    root = Path(prefix_path).expanduser()
    found: list[Path] = []
    seen: set[Path] = set()
    for pattern in SAVE_DIRS:
        for entry in root.glob(pattern):
            if not entry.is_dir():
                continue
            resolved = entry.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(entry)
    return found


def savegame_size(prefixes: list[str], limit: int = 5) -> dict[str, object]:
    """Estimate how large a savegame backup would be."""

    total = 0
    counted: list[str] = []
    for prefix in prefixes[:limit]:
        for directory in savegame_dirs(prefix):
            for entry in directory.rglob("*"):
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat().st_size
                except OSError:
                    continue
            counted.append(str(directory))
    return {"bytes": total, "directories": counted[:20], "count": len(counted)}


def _snapshot_database(source: Path, target: Path) -> None:
    """Copy the library through SQLite so the backup is never half-written."""

    with sqlite3.connect(source) as source_conn, sqlite3.connect(target) as target_conn:
        source_conn.backup(target_conn)


def _looks_like_library(path: Path) -> bool:
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
    except sqlite3.Error:
        return False
    return "games" in tables


def describe(archive: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": str(archive),
        "name": archive.name,
        "size": archive.stat().st_size if archive.is_file() else 0,
        "created_at": None,
        "games": None,
        "restorable": False,
    }
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = set(bundle.namelist())
            info["restorable"] = LIBRARY_NAME in names
            if METADATA_NAME in names:
                metadata = json.loads(bundle.read(METADATA_NAME))
                info["created_at"] = metadata.get("created_at")
                info["games"] = metadata.get("games")
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError):
        info["restorable"] = False
    return info


def list_backups(destination: str | None = None, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    target = Path(expand(destination)) if destination else default_dir(config)
    if not target.is_dir():
        return []
    archives = sorted(
        (entry for entry in target.glob(f"{BACKUP_PREFIX}*.zip") if entry.is_file()),
        key=lambda entry: entry.stat().st_mtime,
        reverse=True,
    )
    return [describe(archive) for archive in archives[:50]]


def restore_backup(archive: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Replace the library (and artwork) with the contents of a backup."""

    source = Path(expand(archive))
    if not source.is_file():
        raise BackupError(f"Backup not found: {source}")

    try:
        with zipfile.ZipFile(source) as bundle:
            names = set(bundle.namelist())
            if LIBRARY_NAME not in names:
                raise BackupError("This zip does not contain a Zed Launcher library")

            library = db_path()
            library.parent.mkdir(parents=True, exist_ok=True)
            if library.is_file():
                shutil.copy2(library, library.with_suffix(library.suffix + RESTORE_SUFFIX))

            temporary = library.with_suffix(library.suffix + ".restoring")
            with bundle.open(LIBRARY_NAME) as handle, temporary.open("wb") as target:
                shutil.copyfileobj(handle, target)
            if not _looks_like_library(temporary):
                temporary.unlink(missing_ok=True)
                raise BackupError("The library inside this backup is not a Zed Launcher database")
            temporary.replace(library)

            restored_artwork = 0
            artwork_root = artwork_dir()
            for name in names:
                if not name.startswith(f"{ARTWORK_DIR}/"):
                    continue
                relative = name.removeprefix(f"{ARTWORK_DIR}/")
                if not relative or ".." in Path(relative).parts:
                    continue
                destination = artwork_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(name) as handle, destination.open("wb") as target:
                    shutil.copyfileobj(handle, target)
                restored_artwork += 1
    except zipfile.BadZipFile as error:
        raise BackupError(f"The backup is not a valid zip file: {error}") from error
    except OSError as error:
        raise BackupError(f"Could not restore the backup: {error}") from error

    restored_saves = 0
    with suppress(Exception):
        restored_saves = _restore_saves(source)

    store.init_db(load_config().get("prefix_root"))
    return {
        "restored": source.name,
        "games": len(store.list_games()),
        "artwork_files": restored_artwork,
        "save_files": restored_saves,
    }


def _restore_saves(archive: Path) -> int:
    """Put archived savegames back into the matching prefix, by folder name."""

    prefixes = {
        _SAFE.sub("-", Path(game["prefix_path"]).name): game["prefix_path"]
        for game in store.list_games()
        if game.get("prefix_path")
    }
    restored = 0
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if not name.startswith(f"{SAVES_DIR}/"):
                continue
            parts = name.split("/")
            if len(parts) < 4:
                continue
            prefix_key = parts[1]
            prefix = prefixes.get(prefix_key)
            if not prefix:
                continue
            target_dir = Path(prefix).expanduser()
            if not target_dir.is_dir():
                continue
            destination = target_dir
            for chunk in parts[2:]:
                if chunk in ("", ".", ".."):
                    destination = None
                    break
                destination = destination / chunk
            if destination is None:
                continue
            if not str(destination.resolve()).startswith(str(target_dir.resolve())):
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(name) as handle, destination.open("wb") as out:
                shutil.copyfileobj(handle, out)
            restored += 1
    return restored


SCHEDULES = {"off": 0, "daily": 24 * 3600, "weekly": 7 * 24 * 3600}


def schedule_due(config: dict[str, Any] | None = None, *, now: float | None = None) -> bool:
    config = config or load_config()
    interval = SCHEDULES.get(str(config.get("backup_schedule") or "off"))
    if not interval:
        return False
    newest = 0.0
    for entry in list_backups(None, config):
        path = Path(entry["path"])
        with suppress(OSError):
            newest = max(newest, path.stat().st_mtime)
    stamp = now if now is not None else time.time()
    return (stamp - newest) >= interval


def run_scheduled(config: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Create a scheduled backup when one is due; returns the new backup."""

    config = config or load_config()
    if not schedule_due(config):
        return None
    try:
        return create_backup(include_artwork=True, config=config)
    except BackupError:
        return None


def delete_backup(archive: str) -> bool:
    target = Path(expand(archive))
    if target.is_file() and target.suffix == ".zip":
        target.unlink()
        return True
    return False
