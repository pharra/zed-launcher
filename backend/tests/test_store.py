from __future__ import annotations

import sqlite3
from pathlib import Path

from zed_launcher import store


def test_create_and_update_game(executable: Path, tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    game = store.create_game(
        {"title": "Example", "path": str(executable), "prefix_path": str(prefix)}
    )

    assert game["id"]
    assert game["title"] == "Example"
    assert game["prefix_path"] == str(prefix)
    assert game["playtime"] == 0
    assert game["mangohud"] is False
    assert game["owned_prefix"] is True

    updated = store.update_game(game["id"], {"mangohud": True, "title": "Renamed"})
    assert updated is not None
    assert updated["mangohud"] is True
    assert updated["title"] == "Renamed"

    assert store.delete_game(game["id"]) is True
    assert store.get_game(game["id"]) is None


def test_sorting_and_search(executable: Path, tmp_path: Path) -> None:
    store.create_game({"title": "Zeta", "path": str(executable), "prefix_path": str(tmp_path / "a"), "playtime": 10})
    store.create_game({"title": "Alpha", "path": str(executable), "prefix_path": str(tmp_path / "b"), "playtime": 200})

    assert [game["title"] for game in store.list_games()] == ["Alpha", "Zeta"]
    assert [game["title"] for game in store.list_games(sort="playtime")] == ["Alpha", "Zeta"]
    assert [game["title"] for game in store.list_games(search="Zet")] == ["Zeta"]


def test_default_prefix_column_and_owned_flag(executable: Path, tmp_path: Path) -> None:
    game = store.create_game(
        {
            "title": "Attached",
            "path": str(executable),
            "prefix_path": str(tmp_path / "shared"),
            "owned_prefix": False,
        }
    )
    assert game["owned_prefix"] is False


def test_runs_and_playtime(executable: Path, tmp_path: Path) -> None:
    game = store.create_game({"title": "Run", "path": str(executable), "prefix_path": str(tmp_path / "p")})
    run = store.create_run(game["id"], str(tmp_path / "run.log"))
    assert run["status"] == "starting"

    store.finish_run(run["id"], "exited", 0, 42)
    finished = store.get_run(run["id"])
    assert finished is not None
    assert finished["status"] == "exited"
    assert finished["duration"] == 42

    store.add_playtime(game["id"], 30)
    refreshed = store.get_game(game["id"])
    assert refreshed is not None
    assert refreshed["playtime"] == 30
    assert refreshed["last_played"] is not None
    assert len(store.game_runs(game["id"])) == 1


def test_migrates_legacy_database(tmp_path: Path, executable: Path) -> None:
    from zed_launcher.paths import db_path

    legacy = db_path()
    legacy.unlink(missing_ok=True)
    conn = sqlite3.connect(legacy)
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version(version) VALUES (1);
        CREATE TABLE prefixes (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
            runner TEXT NOT NULL DEFAULT 'default', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE games (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'windows',
            path TEXT NOT NULL, args TEXT NOT NULL DEFAULT '', launch_args TEXT NOT NULL DEFAULT '',
            working_dir TEXT NOT NULL DEFAULT '', pre_launch TEXT NOT NULL DEFAULT '',
            post_launch TEXT NOT NULL DEFAULT '', prefix_id TEXT, runner TEXT NOT NULL DEFAULT 'default',
            steam_appid INTEGER, cover TEXT NOT NULL DEFAULT '', icon TEXT NOT NULL DEFAULT '',
            mangohud INTEGER NOT NULL DEFAULT 0, gamemode INTEGER NOT NULL DEFAULT 0,
            gamescope INTEGER NOT NULL DEFAULT 0, no_sleep INTEGER NOT NULL DEFAULT 0,
            discord_rpc INTEGER NOT NULL DEFAULT 0, sdl INTEGER NOT NULL DEFAULT 0,
            wayland INTEGER NOT NULL DEFAULT 0, wow64 INTEGER NOT NULL DEFAULT 0,
            hidden INTEGER NOT NULL DEFAULT 0, playtime INTEGER NOT NULL DEFAULT 0,
            last_played TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO prefixes VALUES ('default', 'Default', ?, 'default', 'now', 'now')",
        (str(tmp_path / "shared-prefix"),),
    )
    conn.execute(
        "INSERT INTO games (id, title, path, prefix_id, created_at, updated_at) "
        "VALUES ('legacy1', 'Old Game', ?, 'default', 'now', 'now')",
        (str(executable),),
    )
    conn.commit()
    conn.close()

    store.init_db(tmp_path / "prefix-root")

    migrated = store.get_game("legacy1")
    assert migrated is not None
    assert migrated["prefix_path"] == str(tmp_path / "shared-prefix")
    assert migrated["owned_prefix"] is False
    assert "prefixes" not in _table_names(legacy)


def _table_names(path: Path) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    finally:
        conn.close()
    return [row[0] for row in rows]


def test_resolve_run_is_idempotent(executable: Path, tmp_path: Path) -> None:
    game = store.create_game({"title": "Once", "path": str(executable), "prefix_path": str(tmp_path / "p")})
    run = store.create_run(game["id"], str(tmp_path / "run.log"))

    assert store.resolve_run(run["id"], "exited", 0, 60) is True
    assert store.resolve_run(run["id"], "closed", None, 60) is False

    finished = store.get_run(run["id"])
    assert finished is not None
    assert finished["status"] == "exited"
    refreshed = store.get_game(game["id"])
    assert refreshed is not None
    assert refreshed["playtime"] == 60


def test_schema_adds_tool_argument_columns(executable: Path, tmp_path: Path) -> None:
    game = store.create_game(
        {
            "title": "Args",
            "path": str(executable),
            "prefix_path": str(tmp_path / "p"),
            "gamescope_args": "-W 1920 -H 1080 -f",
            "mangohud_args": "--dlsym",
        }
    )
    assert game["gamescope_args"] == "-W 1920 -H 1080 -f"
    assert game["mangohud_args"] == "--dlsym"
    assert "hidden" not in game
    assert "discord_rpc" not in game


def test_prune_runs_keeps_recent_per_game(executable: Path, tmp_path: Path) -> None:
    game = store.create_game({"title": "Prune", "path": str(executable), "prefix_path": str(tmp_path / "p")})
    log = tmp_path / "run.log"
    ids = []
    for index in range(5):
        run = store.create_run(game["id"], str(log))
        store.finish_run(run["id"], "exited", 0, index)
        ids.append(run["id"])

    removed = store.prune_runs(keep_per_game=2)
    remaining = {run["id"] for run in store.game_runs(game["id"])}
    assert len(remaining) == 2
    assert len(removed) == 3
    assert str(log) in removed
    assert len(set(ids) - remaining) == 3


def test_legacy_launch_args_are_migrated_into_env(
    executable: Path, tmp_path: Path, monkeypatch
) -> None:
    import sqlite3

    from zed_launcher.paths import db_path

    game = store.create_game(
        {"title": "Legacy", "path": str(executable), "prefix_path": str(tmp_path / "p")}
    )
    with sqlite3.connect(db_path()) as conn:
        conn.execute(
            "UPDATE games SET launch_args = ?, env = '' WHERE id = ?",
            ("DXVK_HUD=fps --some-flag", game["id"]),
        )
        conn.commit()

    store.init_db(str(tmp_path))
    migrated = store.get_game(game["id"])
    assert migrated is not None
    assert migrated["env"] == "DXVK_HUD=fps"
    assert migrated["launch_args"] == "--some-flag"
