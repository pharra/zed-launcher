from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zed_launcher.app import create_app
from zed_launcher.services import proton, system


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, umu_run: Path, proton_dir: Path):
    def fake_tools(config=None):
        configured = (config or {}).get("umu_run") or None
        return {
            "umu_run": configured,
            "mangohud": None,
            "gamemoderun": None,
            "gamescope": None,
            "systemd_inhibit": None,
        }

    monkeypatch.setattr(system, "tools", fake_tools)
    app = create_app("test-token")
    with TestClient(app, headers={"X-Zed-Token": "test-token"}) as test_client:
        test_client.put(
            "/api/v1/settings",
            json={"umu_run": str(umu_run), "proton_paths": [str(proton_dir)]},
        )
        yield test_client


def _create(client: TestClient, executable: Path, mode: str = "create", **extra) -> dict:
    response = client.post(
        "/api/v1/games",
        json={"title": "Test", "path": str(executable), "mode": mode, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_api_requires_token(client: TestClient) -> None:
    assert client.get("/api/v1/games", headers={"X-Zed-Token": "wrong"}).status_code == 401


def test_create_mode_builds_prefix_under_root(client: TestClient, executable: Path, tmp_path: Path) -> None:
    root = tmp_path / "prefixes"
    client.put("/api/v1/settings", json={"prefix_root": str(root)})

    game = _create(client, executable, title="My Game")
    prefix = Path(game["prefix_path"])
    assert prefix.parent == root
    assert prefix.name == "my-game"
    assert prefix.is_dir()
    assert game["owned_prefix"] is True

    second = _create(client, executable, title="My Game")
    assert Path(second["prefix_path"]).name == "my-game-2"


def test_add_mode_requires_existing_prefix(
    client: TestClient, executable: Path, wine_prefix: Path
) -> None:
    response = client.post(
        "/api/v1/games",
        json={"title": "No prefix", "path": str(executable), "mode": "add"},
    )
    assert response.status_code == 400

    game = _create(client, executable, mode="add", prefix_path=str(wine_prefix))
    assert game["prefix_path"] == str(wine_prefix)
    assert game["owned_prefix"] is False


def test_add_mode_rejects_invalid_prefix(client: TestClient, executable: Path, tmp_path: Path) -> None:
    empty = tmp_path / "not-a-prefix"
    empty.mkdir()
    response = client.post(
        "/api/v1/games",
        json={"title": "Bad", "path": str(executable), "mode": "add", "prefix_path": str(empty)},
    )
    assert response.status_code == 400
    assert "Wine prefix" in response.json()["detail"]


def test_executable_must_exist(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/api/v1/games", json={"title": "Missing", "path": str(tmp_path / "nope.exe")}
    )
    assert response.status_code == 400


def test_game_crud_and_launch(client: TestClient, executable: Path) -> None:
    game = _create(client, executable)

    listed = client.get("/api/v1/games")
    assert listed.status_code == 200
    assert any(item["id"] == game["id"] for item in listed.json())

    patched = client.patch(f"/api/v1/games/{game['id']}", json={"mangohud": True})
    assert patched.status_code == 200
    assert patched.json()["mangohud"] is True

    launch = client.post(f"/api/v1/games/{game['id']}/launch")
    assert launch.status_code == 200, launch.text
    assert launch.json()["argv"][-1] == str(executable)

    assert client.delete(f"/api/v1/games/{game['id']}").status_code == 204


def test_launch_reports_missing_runtime(client: TestClient, executable: Path) -> None:
    game = _create(client, executable)
    client.put("/api/v1/settings", json={"umu_run": "", "proton_paths": []})

    launch = client.post(f"/api/v1/games/{game['id']}/launch")
    assert launch.status_code == 400
    assert "umu-run" in launch.json()["detail"]


def test_create_requires_dependencies(client: TestClient, executable: Path) -> None:
    client.put("/api/v1/settings", json={"proton_paths": []})
    missing_proton = client.post(
        "/api/v1/games",
        json={"mode": "create", "path": str(executable), "title": "No Proton"},
    )
    assert missing_proton.status_code == 400
    assert "Proton" in missing_proton.json()["detail"]

    client.put("/api/v1/settings", json={"umu_run": ""})
    missing_umu = client.post(
        "/api/v1/games",
        json={"mode": "create", "path": str(executable), "title": "No umu"},
    )
    assert missing_umu.status_code == 400
    assert "umu-run" in missing_umu.json()["detail"]


def test_info_exposes_dependencies(client: TestClient) -> None:
    info = client.get("/api/v1/info").json()
    deps = info["dependencies"]
    assert deps["ready"] is True
    assert deps["missing_required"] == []
    assert deps["required"]["proton"]["available"] is True
    assert deps["required"]["proton"]["path"]
    assert info["proton_effective"] == deps["required"]["proton"]["path"]
    assert "mangohud" in deps["optional"]


def test_delete_with_prefix_removal(client: TestClient, executable: Path) -> None:
    game = _create(client, executable, title="Removable")
    prefix = Path(game["prefix_path"])
    assert prefix.is_dir()

    assert client.delete(f"/api/v1/games/{game['id']}?remove_prefix=true").status_code == 204
    assert not prefix.exists()


def test_settings_roundtrip(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "games-root"
    response = client.put("/api/v1/settings", json={"prefix_root": str(root)})
    assert response.status_code == 200
    assert root.is_dir()
    assert response.json()["prefix_root"] == str(root)

    fetched = client.get("/api/v1/settings")
    assert fetched.json()["prefix_root"] == str(root)


def test_settings_proton_paths_filtered(client: TestClient, proton_dir: Path, tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    response = client.put(
        "/api/v1/settings",
        json={"proton_paths": [str(proton_dir), str(missing)]},
    )
    assert response.status_code == 200
    assert response.json()["proton_paths"] == [str(proton_dir)]


def test_info_and_diagnostics(client: TestClient, proton_dir: Path) -> None:
    info = client.get("/api/v1/info")
    assert info.status_code == 200
    assert "protons" in info.json()
    assert "prefix_root" in info.json()["config"]

    diagnostics = client.get("/api/v1/diagnostics")
    assert diagnostics.status_code == 200
    assert "umu_run" in diagnostics.json()
    assert "proton_sources" in diagnostics.json()


def test_browse(client: TestClient, tmp_path: Path, wine_prefix: Path) -> None:
    (tmp_path / "folder").mkdir()
    (tmp_path / "game.exe").write_text("")

    response = client.get("/api/v1/browse", params={"path": str(tmp_path)})
    assert response.status_code == 200
    payload = response.json()
    names = {entry["name"] for entry in payload["entries"]}
    assert {"folder", "game.exe"} <= names

    prefixes = client.get("/api/v1/browse", params={"path": str(wine_prefix.parent)}).json()
    flagged = [entry for entry in prefixes["entries"] if entry["wine_prefix"]]
    assert any(entry["path"] == str(wine_prefix) for entry in flagged)

    assert client.get("/api/v1/browse", params={"path": str(tmp_path / "missing")}).status_code == 404


def test_protons_endpoints(client: TestClient, proton_dir: Path) -> None:
    added = client.post("/api/v1/protons/paths", json={"path": str(proton_dir)})
    assert added.status_code == 200
    assert any(build["path"] == str(proton_dir) for build in added.json()["builds"])

    listing = client.get("/api/v1/protons")
    assert listing.status_code == 200
    assert listing.json()["has_token"] is False

    removed = client.delete("/api/v1/protons/paths", params={"path": str(proton_dir)})
    assert removed.status_code == 200
    assert all(build["path"] != str(proton_dir) for build in removed.json()["builds"])


def test_proton_path_validation(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/api/v1/protons/paths", json={"path": str(tmp_path)})
    assert response.status_code == 400


def test_proton_releases_rate_limit(client: TestClient, monkeypatch) -> None:
    def raise_error(config=None, limit=30):
        raise proton.ProtonError("GitHub rate limit reached.")

    monkeypatch.setattr(proton, "fetch_releases", raise_error)
    response = client.get("/api/v1/protons/releases")
    assert response.status_code == 502
    assert "rate limit" in response.json()["detail"]


def test_game_history(client: TestClient, executable: Path) -> None:
    game = _create(client, executable)
    response = client.get(f"/api/v1/games/{game['id']}/runs")
    assert response.status_code == 200
    assert response.json() == []


def test_artwork_upload_and_remove(client: TestClient, executable: Path, tmp_path: Path) -> None:
    game = _create(client, executable, title="Art")
    image = tmp_path / "cover.png"
    image.write_bytes(PNG_PIXEL)

    response = client.post(f"/api/v1/games/{game['id']}/artwork", json={"path": str(image)})
    assert response.status_code == 200
    cover = response.json()["cover"]
    assert cover.startswith("covers/")

    served = client.get(f"/artwork/{cover}")
    assert served.status_code == 200
    assert served.content == PNG_PIXEL

    bad = tmp_path / "cover.txt"
    bad.write_text("not an image")
    assert client.post(f"/api/v1/games/{game['id']}/artwork", json={"path": str(bad)}).status_code == 400

    assert client.delete(f"/api/v1/games/{game['id']}/artwork").status_code == 204
    assert client.get(f"/api/v1/games/{game['id']}").json()["cover"] == ""


PNG_PIXEL = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000000020001e221bc33000000"
    "0049454e44ae426082"
)


def test_prefix_scan_and_tools(client: TestClient, wine_prefix: Path, umu_run: Path, proton_dir: Path) -> None:
    exe = wine_prefix / "drive_c/Program Files/Studio/Game.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")

    scan = client.post("/api/v1/prefixes/scan", json={"path": str(wine_prefix)})
    assert scan.status_code == 200
    assert any(item["path"] == str(exe) for item in scan.json()["fallback"])

    bad = client.post("/api/v1/prefixes/scan", json={"path": "/nope/nope"})
    assert bad.status_code == 400

    client.put(
        "/api/v1/settings",
        json={"umu_run": str(umu_run), "proton_paths": [str(proton_dir)]},
    )

    for kind, extra in (
        ("winecfg", {}),
        ("regedit", {"target": str(exe)}),
        ("exe", {"target": str(exe)}),
    ):
        response = client.post(
            "/api/v1/prefixes/run",
            json={"prefix_path": str(wine_prefix), "kind": kind, **extra},
        )
        assert response.status_code == 200, response.text
        assert response.json()["snapshot"]["argv"]

    verbs = client.post(
        "/api/v1/prefixes/run",
        json={"prefix_path": str(wine_prefix), "kind": "winetricks", "args": "vcrun2022"},
    )
    assert verbs.status_code == 200
    assert "winetricks" in verbs.json()["snapshot"]["argv"]

    missing = client.post(
        "/api/v1/prefixes/run",
        json={"prefix_path": str(wine_prefix), "kind": "winetricks"},
    )
    assert missing.status_code == 400


def test_installer_flow(client: TestClient, tmp_path: Path, umu_run: Path, proton_dir: Path) -> None:
    client.put(
        "/api/v1/settings",
        json={
            "prefix_root": str(tmp_path / "root"),
            "umu_run": str(umu_run),
            "proton_paths": [str(proton_dir)],
        },
    )

    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"MZ")

    response = client.post(
        "/api/v1/installers/run",
        json={"installer": str(installer), "title": "Cool Game", "prefix_name": "cool-game"},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["install_id"]
    assert payload["prefix_path"] == str(tmp_path / "root/cool-game")
    assert Path(payload["prefix_path"]).is_dir()

    detected = client.get(f"/api/v1/installers/{payload['install_id']}/detect")
    assert detected.status_code == 200
    assert detected.json()["best"] is None

    assert client.get(f"/api/v1/installers/{payload['install_id']}").status_code == 200
    assert client.delete(f"/api/v1/installers/{payload['install_id']}").status_code == 204
    assert client.get(f"/api/v1/installers/{payload['install_id']}").status_code == 404


def test_installer_requires_umu(client: TestClient, tmp_path: Path) -> None:
    client.put("/api/v1/settings", json={"umu_run": ""})
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"MZ")
    response = client.post(
        "/api/v1/installers/run",
        json={"installer": str(installer)},
    )
    assert response.status_code == 400
    assert "umu-run" in response.json()["detail"]


def test_create_game_reuses_install_prefix(
    client: TestClient, tmp_path: Path, umu_run: Path, proton_dir: Path
) -> None:
    client.put(
        "/api/v1/settings",
        json={
            "prefix_root": str(tmp_path / "root"),
            "umu_run": str(umu_run),
            "proton_paths": [str(proton_dir)],
        },
    )
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"MZ")
    session = client.post(
        "/api/v1/installers/run",
        json={"installer": str(installer), "title": "Session Game", "prefix_name": "session-game"},
    ).json()

    game_exe = Path(session["prefix_path"]) / "drive_c/Program Files/Game/Game.exe"
    game_exe.parent.mkdir(parents=True)
    game_exe.write_bytes(b"MZ")

    response = client.post(
        "/api/v1/games",
        json={
            "mode": "create",
            "title": "Session Game",
            "path": str(game_exe),
            "install_id": session["install_id"],
        },
    )
    assert response.status_code == 201, response.text
    game = response.json()
    assert game["prefix_path"] == session["prefix_path"]
    assert game["owned_prefix"] is True
    assert game["proton_path"] == session["proton_path"]

    # The install session is consumed.
    assert client.get(f"/api/v1/installers/{session['install_id']}").status_code == 404


def test_launch_marks_run_running(client: TestClient, executable: Path) -> None:
    game = _create(client, executable, title="Running state")
    launch = client.post(f"/api/v1/games/{game['id']}/launch")
    assert launch.status_code == 200

    history = client.get(f"/api/v1/games/{game['id']}/runs").json()
    assert history[0]["status"] in ("running", "exited", "failed")


def test_proton_default_must_exist(client: TestClient, tmp_path: Path) -> None:
    response = client.put(
        "/api/v1/settings", json={"proton_default": str(tmp_path / "missing-proton")}
    )
    assert response.status_code == 400
    assert "Proton build not found" in response.json()["detail"]


def test_dependency_status_reflects_optional_tools(client: TestClient) -> None:
    deps = client.get("/api/v1/info").json()["dependencies"]
    assert deps["optional"]["mangohud"]["available"] is False
    assert deps["optional"]["mangohud"]["label"] == "MangoHud"


def test_backup_endpoints(client: TestClient, executable: Path, tmp_path: Path) -> None:
    _create(client, executable, title="Backup API")
    destination = tmp_path / "backups"

    created = client.post("/api/v1/backups", json={"destination": str(destination)})
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["games"] == 1
    assert Path(payload["path"]).is_file()

    listed = client.get("/api/v1/backups", params={"destination": str(destination)})
    assert listed.status_code == 200
    assert listed.json()["destination"] == str(destination)
    assert len(listed.json()["backups"]) == 1

    restored = client.post("/api/v1/backups/restore", json={"path": payload["path"]})
    assert restored.status_code == 200, restored.text
    assert restored.json()["games"] == 1

    assert client.delete("/api/v1/backups", params={"path": payload["path"]}).status_code == 200
    assert client.delete("/api/v1/backups", params={"path": payload["path"]}).status_code == 404


def test_backup_settings_roundtrip(client: TestClient, tmp_path: Path) -> None:
    destination = tmp_path / "my-backups"
    response = client.put(
        "/api/v1/settings",
        json={"backup_dir": str(destination), "language": "zh-CN"},
    )
    assert response.status_code == 200
    assert response.json()["backup_dir"] == str(destination)
    assert response.json()["language"] == "zh-CN"


def test_launch_rejects_missing_prefix(client: TestClient, executable: Path, tmp_path: Path) -> None:
    game = _create(client, executable, title="Gone")
    import shutil

    shutil.rmtree(game["prefix_path"])

    response = client.post(f"/api/v1/games/{game['id']}/launch")
    assert response.status_code == 400
    assert "Prefix folder is missing" in response.json()["detail"]


def test_launch_twice_reports_conflict(
    client: TestClient, executable: Path, tmp_path: Path
) -> None:
    slow = tmp_path / "slow-umu-run"
    slow.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    slow.chmod(0o755)
    client.put("/api/v1/settings", json={"umu_run": str(slow)})

    game = _create(client, executable, title="Twice")
    first = client.post(f"/api/v1/games/{game['id']}/launch")
    assert first.status_code == 200
    run_id = first.json()["run_id"]
    assert client.get("/api/v1/runs").json()

    second = client.post(f"/api/v1/games/{game['id']}/launch")
    assert second.status_code == 409
    assert "already running" in second.json()["detail"]

    assert client.post(f"/api/v1/runs/{run_id}/stop").status_code == 200


def test_hidden_flag_is_gone(client: TestClient, executable: Path) -> None:
    game = _create(client, executable, title="No hidden")
    assert "hidden" not in game
    assert "discord_rpc" not in game


def test_tool_arguments_round_trip(client: TestClient, executable: Path) -> None:
    game = _create(client, executable, title="Args", gamescope_args="-f -r 60")
    assert game["gamescope_args"] == "-f -r 60"

    updated = client.patch(f"/api/v1/games/{game['id']}", json={"mangohud_args": "--dlsym"})
    assert updated.status_code == 200
    assert updated.json()["mangohud_args"] == "--dlsym"
    assert updated.json()["gamescope_args"] == "-f -r 60"


def test_active_runs_include_detached_entries(
    client: TestClient, executable: Path, tmp_path: Path
) -> None:
    import subprocess
    import sys

    from zed_launcher import store
    from zed_launcher.services import processes

    game = _create(client, executable, title="Detached")
    log = tmp_path / "detached.log"
    log.write_text("wine: some output\n", encoding="utf-8")
    run = store.create_run(game["id"], str(log))
    # A real detached run carries the marker in its environment; that is how the
    # launcher recognises a process it still owns. /proc/<pid>/environ only shows the
    # exec-time block, so the marker has to be handed to a real child.
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        env={**os.environ, "ZED_RUN_ID": run["id"]},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        store.set_run_pid(
            run["id"], child.pid, processes.starttime_of(child.pid)
        )
        store.set_run_status(run["id"], "running")

        active = client.get("/api/v1/runs").json()
        entry = next(item for item in active if item["run_id"] == run["id"])
        assert entry["detached"] is True
        assert entry["lines"] == ["wine: some output"]

        snapshot = client.get(f"/api/v1/runs/{run['id']}").json()
        assert snapshot["detached"] is True
        assert snapshot["game_id"] == game["id"]
    finally:
        child.kill()
        child.wait(timeout=10)


def test_prefix_presets_and_cleanup(client: TestClient, wine_prefix: Path) -> None:
    presets = client.get("/api/v1/prefixes/presets").json()
    assert any(entry["id"] == "runtimes" for entry in presets)
    assert all(entry["verbs"] for entry in presets)

    scratch = wine_prefix / "drive_c/users/steamuser/Temp"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "junk.tmp").write_bytes(b"x" * 128)

    result = client.post("/api/v1/prefixes/cleanup-temp", json={"path": str(wine_prefix)})
    assert result.status_code == 200
    assert result.json()["freed"] >= 128


def test_prefix_clone(client: TestClient, wine_prefix: Path, tmp_path: Path) -> None:
    root = tmp_path / "clones"
    client.put("/api/v1/settings", json={"prefix_root": str(root)})
    response = client.post(
        "/api/v1/prefixes/clone", json={"path": str(wine_prefix), "name": "copied"}
    )
    assert response.status_code == 201
    cloned = Path(response.json()["path"])
    assert cloned.is_dir()
    assert (cloned / "drive_c").is_dir()
    assert cloned.name.startswith("copied")


def test_dead_detached_run_is_closed(client: TestClient, executable: Path, tmp_path: Path) -> None:
    from zed_launcher import store

    game = _create(client, executable, title="Ghost")
    log = tmp_path / "ghost.log"
    log.write_text("gone\n", encoding="utf-8")
    run = store.create_run(game["id"], str(log), status="running", pid=999_999)

    active = client.get("/api/v1/runs").json()
    assert all(entry["run_id"] != run["id"] for entry in active)

    closed = store.get_run(run["id"])
    assert closed is not None
    assert closed["status"] == "closed"


def test_tool_paths_must_exist(client: TestClient, tmp_path: Path) -> None:
    response = client.put(
        "/api/v1/settings", json={"tool_paths": {"mangohud": str(tmp_path / "missing")}}
    )
    assert response.status_code == 400
    assert "MangoHud not found" in response.json()["detail"]

    fake = tmp_path / "mangohud"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    ok = client.put("/api/v1/settings", json={"tool_paths": {"mangohud": str(fake)}})
    assert ok.status_code == 200
    assert ok.json()["tool_paths"]["mangohud"] == str(fake)

    cleared = client.put("/api/v1/settings", json={"tool_paths": {}})
    assert cleared.json()["tool_paths"] == {}


def test_extra_program_sequence_is_stored_with_game_sentinel(
    client: TestClient, executable: Path, tmp_path: Path
) -> None:
    extra = tmp_path / "extra.exe"
    extra.write_bytes(b"")
    game = _create(
        client,
        executable,
        extra_programs=[
            {"kind": "program", "path": str(extra), "args": "", "delay": 3},
            {"kind": "game"},
        ],
    )
    found = client.get(f"/api/v1/games/{game['id']}").json()
    assert [entry["kind"] for entry in found["extra_programs"]] == ["program", "game"]
    assert found["extra_programs"][0]["delay"] == 3
    assert found["extra_programs"][1]["path"] == str(executable)


def test_patch_keeps_sequence_when_only_path_changes(
    client: TestClient, executable: Path, tmp_path: Path
) -> None:
    extra = tmp_path / "extra.exe"
    extra.write_bytes(b"")
    game = _create(
        client,
        executable,
        extra_programs=[{"kind": "program", "path": str(extra)}],
    )
    assert [entry["kind"] for entry in game["extra_programs"]] == ["program", "game"]

    moved = tmp_path / "renamed.exe"
    moved.write_bytes(b"")
    patched = client.patch(f"/api/v1/games/{game['id']}", json={"path": str(moved)}).json()
    assert patched["extra_programs"][-1]["path"] == str(moved)
    assert patched["extra_programs"][0]["path"] == str(extra)


def test_extra_program_delay_is_bounded(client: TestClient, executable: Path, tmp_path: Path) -> None:
    response = client.post(
        "/api/v1/games",
        json={
            "title": "Test",
            "path": str(executable),
            "mode": "add",
            "prefix_path": str(tmp_path / "prefix"),
            "extra_programs": [{"kind": "program", "path": "/x.exe", "delay": 9999}],
        },
    )
    if response.status_code == 201:
        assert response.json()["extra_programs"][0]["delay"] == 600
    else:
        assert response.status_code == 422


def test_stop_kills_children_that_left_the_process_group(
    client: TestClient, executable: Path, tmp_path: Path
) -> None:
    """A game stop must reach wineserver, which runs in its own session."""

    import sys
    import time

    fake = tmp_path / "fake-umu-run"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import subprocess, sys, time\n"
        "subprocess.Popen(\n"
        "    [sys.executable, '-c', 'import time; time.sleep(60)'],\n"
        "    start_new_session=True,\n"
        "    stdout=subprocess.DEVNULL,\n"
        "    stderr=subprocess.DEVNULL,\n"
        ")\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    client.put("/api/v1/settings", json={"umu_run": str(fake)})

    game = _create(client, executable, title="Group")
    run = client.post(f"/api/v1/games/{game['id']}/launch")
    assert run.status_code == 200, run.text
    run_id = run.json()["run_id"]

    from zed_launcher.services import processes

    def family() -> int:
        return len(processes.run_processes(run_id))

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and family() < 2:
        time.sleep(0.05)
    assert family() >= 2

    assert client.post(f"/api/v1/runs/{run_id}/stop").status_code == 200

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and family():
        time.sleep(0.05)
    assert family() == 0

    record = client.get(f"/api/v1/runs/{run_id}").json()
    assert record["status"] in ("stopped", "exited")


def test_run_finishes_when_a_grandchild_keeps_the_pipe_open(
    client: TestClient, executable: Path, tmp_path: Path
) -> None:
    """wineserver inherits the game's stdout; that must not keep the run "running"."""

    import sys
    import time

    fake = tmp_path / "pipe-umu-run"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print('game finished', flush=True)\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    client.put("/api/v1/settings", json={"umu_run": str(fake)})

    game = _create(client, executable, title="Pipe")
    run = client.post(f"/api/v1/games/{game['id']}/launch")
    assert run.status_code == 200, run.text
    run_id = run.json()["run_id"]

    deadline = time.monotonic() + 15
    status = "running"
    while time.monotonic() < deadline:
        status = client.get(f"/api/v1/runs/{run_id}").json()["status"]
        if status not in ("starting", "running"):
            break
        time.sleep(0.1)

    assert status == "exited"
    assert not client.get("/api/v1/runs").json()
