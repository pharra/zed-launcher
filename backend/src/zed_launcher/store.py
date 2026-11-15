from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .paths import db_path, ensure_dirs

SCHEMA_VERSION = 6

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    prefix_path TEXT NOT NULL DEFAULT '',
    proton_path TEXT NOT NULL DEFAULT '',
    args TEXT NOT NULL DEFAULT '',
    launch_args TEXT NOT NULL DEFAULT '',
    env TEXT NOT NULL DEFAULT '',
    extra_programs TEXT NOT NULL DEFAULT '[]',
    mount_dirs TEXT NOT NULL DEFAULT '[]',
    working_dir TEXT NOT NULL DEFAULT '',
    pre_launch TEXT NOT NULL DEFAULT '',
    post_launch TEXT NOT NULL DEFAULT '',
    cover TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '',
    mangohud INTEGER NOT NULL DEFAULT 0,
    gamemode INTEGER NOT NULL DEFAULT 0,
    gamescope INTEGER NOT NULL DEFAULT 0,
    gamescope_args TEXT NOT NULL DEFAULT '',
    mangohud_args TEXT NOT NULL DEFAULT '',
    no_sleep INTEGER NOT NULL DEFAULT 0,
    sdl INTEGER NOT NULL DEFAULT 0,
    wayland INTEGER NOT NULL DEFAULT 0,
    wow64 INTEGER NOT NULL DEFAULT 0,
    owned_prefix INTEGER NOT NULL DEFAULT 1,
    playtime INTEGER NOT NULL DEFAULT 0,
    last_played TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS installs (
    id TEXT PRIMARY KEY,
    prefix_path TEXT NOT NULL,
    proton_path TEXT NOT NULL DEFAULT '',
    installer TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    baseline TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'starting',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration INTEGER,
    exit_code INTEGER,
    log_path TEXT NOT NULL DEFAULT '',
    pid INTEGER,
    pid_started TEXT
);
"""

BOOL_FIELDS = (
    "mangohud",
    "gamemode",
    "gamescope",
    "no_sleep",
    "sdl",
    "wayland",
    "wow64",
    "owned_prefix",
)

GAME_FIELDS = (
    "id",
    "title",
    "path",
    "prefix_path",
    "proton_path",
    "args",
    "launch_args",
    "env",
    "extra_programs",
    "mount_dirs",
    "working_dir",
    "pre_launch",
    "post_launch",
    "cover",
    "icon",
    "mangohud",
    "gamemode",
    "gamescope",
    "gamescope_args",
    "mangohud_args",
    "no_sleep",
    "sdl",
    "wayland",
    "wow64",
    "owned_prefix",
    "playtime",
    "last_played",
    "created_at",
    "updated_at",
)

EDITABLE_FIELDS = tuple(
    field
    for field in GAME_FIELDS
    if field not in ("id", "created_at", "updated_at", "playtime", "last_played")
)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(path or db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        return set()
    return {row["name"] for row in rows}


def _migrate_legacy(conn: sqlite3.Connection, fallback_root: str) -> None:
    """Move an early (kind/prefix_id) database to the per-game prefix schema."""

    legacy_prefixes: dict[str, str] = {}
    if _columns(conn, "prefixes"):
        for row in conn.execute("SELECT id, path FROM prefixes").fetchall():
            legacy_prefixes[row["id"]] = row["path"]

    rows = conn.execute("SELECT * FROM games").fetchall()
    conn.execute("ALTER TABLE games RENAME TO games_legacy")
    conn.executescript(SCHEMA)

    root = Path(fallback_root).expanduser()
    for row in rows:
        record = {key: row[key] for key in row.keys()}  # noqa: SIM118
        game_id = record.get("id") or uuid.uuid4().hex[:12]
        prefix_path = legacy_prefixes.get(record.get("prefix_id") or "", "")
        owned = 0
        if not prefix_path:
            prefix_path = str(root / game_id)
            owned = 1
        values = {
            "id": game_id,
            "title": record.get("title") or "Game",
            "path": record.get("path") or "",
            "prefix_path": prefix_path,
            "proton_path": record.get("runner") if record.get("runner") not in (None, "", "default") else "",
            "args": record.get("args") or "",
            "launch_args": record.get("launch_args") or "",
            "env": "",
            "extra_programs": "[]",
            "mount_dirs": "[]",
            "working_dir": record.get("working_dir") or "",
            "pre_launch": record.get("pre_launch") or "",
            "post_launch": record.get("post_launch") or "",
            "cover": record.get("cover") or "",
            "icon": record.get("icon") or "",
            "playtime": int(record.get("playtime") or 0),
            "last_played": record.get("last_played"),
            "created_at": record.get("created_at") or now(),
            "updated_at": record.get("updated_at") or now(),
            "owned_prefix": owned,
        }
        for field in BOOL_FIELDS:
            if field == "owned_prefix":
                continue
            values[field] = int(bool(record.get(field, False)))
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        conn.execute(f"INSERT INTO games ({columns}) VALUES ({placeholders})", tuple(values.values()))

    conn.execute("DROP TABLE games_legacy")
    if _columns(conn, "prefixes"):
        conn.execute("DROP TABLE prefixes")


GAME_COLUMN_MIGRATIONS = {
    "gamescope_args": "TEXT NOT NULL DEFAULT ''",
    "mangohud_args": "TEXT NOT NULL DEFAULT ''",
    "env": "TEXT NOT NULL DEFAULT ''",
    "extra_programs": "TEXT NOT NULL DEFAULT '[]'",
    "mount_dirs": "TEXT NOT NULL DEFAULT '[]'",
}

RUN_COLUMN_MIGRATIONS = {
    "pid": "INTEGER",
    "pid_started": "TEXT",
}

DROPPED_COLUMNS = ("discord_rpc", "hidden")


def _sync_columns(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database was created, drop ones we retired."""

    present = _columns(conn, "games")
    for column, ddl in GAME_COLUMN_MIGRATIONS.items():
        if column not in present:
            conn.execute(f"ALTER TABLE games ADD COLUMN {column} {ddl}")
    for column in DROPPED_COLUMNS:
        if column in present:
            with contextlib.suppress(sqlite3.Error):
                conn.execute(f"ALTER TABLE games DROP COLUMN {column}")

    run_columns = _columns(conn, "runs")
    for column, ddl in RUN_COLUMN_MIGRATIONS.items():
        if column not in run_columns:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {ddl}")


_ENV_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _migrate_env_split(conn: sqlite3.Connection) -> None:
    """Move ``KEY=VALUE`` tokens out of launch_args into the new env column."""

    rows = conn.execute(
        "SELECT id, launch_args FROM games WHERE env = '' AND launch_args LIKE '%=%'"
    ).fetchall()
    for row in rows:
        tokens = str(row["launch_args"] or "").split()
        env_lines: list[str] = []
        argv: list[str] = []
        for token in tokens:
            key, separator, rest = token.partition("=")
            if separator and _ENV_TOKEN.match(key):
                env_lines.append(f"{key}={rest}")
            else:
                argv.append(token)
        if not env_lines:
            continue
        conn.execute(
            "UPDATE games SET env = ?, launch_args = ? WHERE id = ?",
            ("\n".join(env_lines), " ".join(argv), row["id"]),
        )


def init_db(fallback_prefix_root: str | None = None, path: Path | None = None) -> None:
    with connect(path) as conn:
        existing = _columns(conn, "games")
        if existing and "prefix_path" not in existing:
            _migrate_legacy(conn, fallback_prefix_root or str(Path.home() / "Games" / "Zed"))
        conn.executescript(SCHEMA)
        _sync_columns(conn)
        _migrate_env_split(conn)

        row = conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
        elif row["version"] != SCHEMA_VERSION:
            conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
        conn.commit()


JSON_FIELDS = ("extra_programs", "mount_dirs")


def _dump_list(value: Any) -> str:
    if isinstance(value, str):
        return value or "[]"
    return json.dumps(list(value or []), ensure_ascii=False)


def _as_game(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    game = {key: row[key] for key in row.keys()}  # noqa: SIM118
    for field in BOOL_FIELDS:
        game[field] = bool(game.get(field))
    for field in JSON_FIELDS:
        try:
            game[field] = json.loads(game.get(field) or "[]")
        except (TypeError, ValueError):
            game[field] = []
    return game


def list_games(search: str | None = None, sort: str = "title") -> list[dict[str, Any]]:
    order = {
        "title": "title COLLATE NOCASE ASC",
        "playtime": "playtime DESC, title COLLATE NOCASE ASC",
        "last_played": "last_played DESC NULLS LAST, title COLLATE NOCASE ASC",
        "created_at": "created_at DESC",
    }.get(sort, "title COLLATE NOCASE ASC")

    query = f"SELECT * FROM games {'' if not search else 'WHERE title LIKE ?'} ORDER BY {order}"
    params: tuple[Any, ...] = () if not search else (f"%{search}%",)
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [game for row in rows if (game := _as_game(row)) is not None]


def get_game(game_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    return _as_game(row)


def create_game(data: dict[str, Any]) -> dict[str, Any]:
    game_id = data.get("id") or uuid.uuid4().hex[:12]
    timestamp = now()
    values: dict[str, Any] = {
        "id": game_id,
        "title": data.get("title") or Path(data.get("path", "Game")).stem or "Game",
        "path": data.get("path", ""),
        "prefix_path": data.get("prefix_path", ""),
        "proton_path": data.get("proton_path", ""),
        "args": data.get("args", ""),
        "launch_args": data.get("launch_args", ""),
        "env": data.get("env", ""),
        "extra_programs": _dump_list(data.get("extra_programs")),
        "working_dir": data.get("working_dir", ""),
        "pre_launch": data.get("pre_launch", ""),
        "post_launch": data.get("post_launch", ""),
        "cover": data.get("cover", ""),
        "icon": data.get("icon", ""),
        "gamescope_args": data.get("gamescope_args", ""),
        "mangohud_args": data.get("mangohud_args", ""),
        "playtime": int(data.get("playtime", 0) or 0),
        "last_played": data.get("last_played"),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    for field in BOOL_FIELDS:
        default = field == "owned_prefix"
        values[field] = int(bool(data.get(field, default)))

    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    with connect() as conn:
        conn.execute(f"INSERT INTO games ({columns}) VALUES ({placeholders})", tuple(values.values()))
        conn.commit()
    result = get_game(game_id)
    assert result is not None
    return result


def update_game(game_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    current = get_game(game_id)
    if current is None:
        return None

    values: dict[str, Any] = {}
    for key, value in patch.items():
        if key in EDITABLE_FIELDS:
            if key in BOOL_FIELDS:
                values[key] = int(bool(value))
            elif key in JSON_FIELDS:
                values[key] = _dump_list(value)
            else:
                values[key] = value
    if not values:
        return current
    values["updated_at"] = now()

    assignments = ", ".join(f"{key} = ?" for key in values)
    with connect() as conn:
        conn.execute(f"UPDATE games SET {assignments} WHERE id = ?", (*values.values(), game_id))
        conn.commit()
    return get_game(game_id)


def delete_game(game_id: str) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
        conn.commit()
        return cursor.rowcount > 0


def add_playtime(game_id: str, seconds: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE games SET playtime = playtime + ?, last_played = ?, updated_at = ? WHERE id = ?",
            (max(0, seconds), now(), now(), game_id),
        )
        conn.commit()


OPEN_RUN_STATUSES = ("starting", "running", "stopping")


def resolve_run(run_id: str, status: str, exit_code: int | None, duration: int) -> bool:
    """Close an open run exactly once and credit its playtime.

    Both the GUI and the detached watcher race to report the same exit; the
    conditional update makes sure only the first one wins, so playtime is never
    counted twice and a finished run is not rewritten.
    """

    timestamp = now()
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE runs SET status = ?, exit_code = ?, duration = ?, ended_at = ? "
            "WHERE id = ? AND status IN (?, ?, ?)",
            (status, exit_code, max(0, duration), timestamp, run_id, *OPEN_RUN_STATUSES),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            return False
        conn.execute(
            "UPDATE games SET playtime = playtime + ?, last_played = ?, updated_at = ? "
            "WHERE id = (SELECT game_id FROM runs WHERE id = ?)",
            (max(0, duration), timestamp, timestamp, run_id),
        )
        conn.commit()
    return True


def create_run(
    game_id: str,
    log_path: str,
    status: str = "starting",
    pid: int | None = None,
    pid_started: str = "",
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    started = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO runs (id, game_id, status, started_at, log_path, pid, pid_started) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, game_id, status, started, log_path, pid, pid_started),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row)


def set_run_status(run_id: str, status: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE runs SET status = ? WHERE id = ?", (status, run_id))
        conn.commit()


def set_run_pid(run_id: str, pid: int | None, pid_started: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET pid = ?, pid_started = ? WHERE id = ?", (pid, pid_started, run_id)
        )
        conn.commit()


def finish_run(run_id: str, status: str, exit_code: int | None, duration: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET status = ?, exit_code = ?, duration = ?, ended_at = ? WHERE id = ?",
            (status, exit_code, duration, now(), run_id),
        )
        conn.commit()


def get_run(run_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def prune_runs(keep_per_game: int = 50) -> list[str]:
    """Drop old finished runs and return the log files that are now orphaned."""

    removed_logs: list[str] = []
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, game_id, log_path FROM runs "
            "WHERE status NOT IN (?, ?, ?) "
            "ORDER BY started_at DESC",
            OPEN_RUN_STATUSES,
        ).fetchall()

        seen: dict[str, int] = {}
        doomed: list[sqlite3.Row] = []
        for row in rows:
            game_id = str(row["game_id"])
            seen[game_id] = seen.get(game_id, 0) + 1
            if seen[game_id] > keep_per_game:
                doomed.append(row)

        for row in doomed:
            conn.execute("DELETE FROM runs WHERE id = ?", (row["id"],))
            if row["log_path"]:
                removed_logs.append(str(row["log_path"]))
        conn.commit()
    return removed_logs


def recent_runs(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def game_runs(game_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runs WHERE game_id = ? ORDER BY started_at DESC LIMIT ?",
            (game_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def reconcile_open_runs(alive: Callable[[int, str], bool]) -> list[str]:
    """Close runs whose recorded process is gone (crash, reboot, killed watcher)."""

    closed: list[str] = []
    for record in running_runs():
        pid = record.get("pid")
        if pid and alive(int(pid), str(record.get("pid_started") or "")):
            continue
        duration = _seconds_since(record.get("started_at"))
        if resolve_run(record["id"], "closed", None, duration):
            closed.append(record["id"])
    return closed


def _seconds_since(started_at: str | None) -> int:
    if not started_at:
        return 0
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return 0
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - started).total_seconds()))


def running_runs() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runs WHERE status IN ('starting', 'running') ORDER BY started_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def mark_run_stale(run_id: str, status: str = "unknown") -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET status = ?, ended_at = ? WHERE id = ? AND status IN ('starting', 'running')",
            (status, now(), run_id),
        )
        conn.commit()


def create_install(
    prefix_path: str, proton_path: str, installer: str, title: str, baseline: list[str]
) -> dict[str, Any]:
    install_id = uuid.uuid4().hex[:12]
    with connect() as conn:
        conn.execute(
            "INSERT INTO installs (id, prefix_path, proton_path, installer, title, baseline, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (install_id, prefix_path, proton_path, installer, title, json.dumps(baseline), now()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM installs WHERE id = ?", (install_id,)).fetchone()
    return dict(row)


def get_install(install_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM installs WHERE id = ?", (install_id,)).fetchone()
    return dict(row) if row else None


def install_baseline(install: dict[str, Any]) -> set[str]:
    try:
        return set(json.loads(install.get("baseline") or "[]"))
    except (TypeError, ValueError):
        return set()


def delete_install(install_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM installs WHERE id = ?", (install_id,))
        conn.commit()


def iter_game_ids() -> Iterable[str]:
    with connect() as conn:
        rows = conn.execute("SELECT id FROM games").fetchall()
    return (row["id"] for row in rows)
