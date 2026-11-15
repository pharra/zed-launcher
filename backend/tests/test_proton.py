from __future__ import annotations

import http.server
import io
import socketserver
import tarfile
import threading
from pathlib import Path

import pytest

from zed_launcher import store
from zed_launcher.services import proton


def _tarball(tag: str) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        payload = b"#!/bin/sh\n"
        for name in (f"{tag}/proton", f"{tag}/files/bin/wine"):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


@pytest.fixture()
def proton_server():
    payload = _tarball("GE-Proton9-9")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args) -> None:
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_candidates_include_env_and_steam(monkeypatch, proton_dir: Path, tmp_path: Path) -> None:
    steam = tmp_path / "home/.local/share/Steam/compatibilitytools.d"
    steam.mkdir(parents=True)
    other = steam / "GE-Proton10-1"
    (other / "files/bin").mkdir(parents=True)
    (other / "proton").write_text("")
    (other / "compatibilitytool.vdf").write_text(
        '"compatibilitytools"\n{\n  "compat_tools"\n  {\n    "x"\n    {\n'
        '      "display_name" "GE-Proton10-1"\n    }\n  }\n}\n'
    )

    monkeypatch.setenv("ZED_PROTON_PATH", str(proton_dir))
    builds = proton.candidates({"proton_paths": []})

    paths = {build["path"]: build for build in builds}
    assert str(proton_dir) in paths
    assert paths[str(proton_dir)]["source"] == "system"
    assert paths[str(other)]["name"] == "GE-Proton10-1"
    assert paths[str(other)]["source"] == "steam"


def test_candidates_from_manual_paths(proton_dir: Path) -> None:
    builds = proton.candidates({"proton_paths": [str(proton_dir)]})
    assert len(builds) == 1
    assert builds[0]["source"] == "manual"
    assert builds[0]["version"] == "GE-Proton9-1"


def test_find_prefers_configured_default(proton_dir: Path, tmp_path: Path) -> None:
    second = tmp_path / "GE-Proton10-2"
    (second / "files/bin").mkdir(parents=True)
    (second / "proton").write_text("")

    config = {"proton_paths": [str(proton_dir), str(second)], "proton_default": str(second)}
    assert proton.find("", config) == str(second)
    assert proton.find(str(proton_dir), config) == str(proton_dir)


def test_download_and_extract(proton_server: str, monkeypatch) -> None:
    monkeypatch.setenv("ZED_PROTON_DOWNLOAD_BASE", proton_server)
    job = proton.start_download("GE-Proton9-9", {"proton_paths": []})

    for _ in range(200):
        current = proton.get_job(job["id"])
        assert current is not None
        if current["status"] in ("done", "failed"):
            break
        threading.Event().wait(0.05)

    final = proton.get_job(job["id"])
    assert final is not None
    assert final["status"] == "done", final.get("error")
    installed = Path(final["path"])
    assert (installed / "proton").is_file()
    assert proton.candidates({"proton_paths": []})[-1]["source"] == "download"
    assert proton.remove_build(str(installed)) is True
    assert not installed.exists()


def test_download_rejects_installed(proton_server: str, monkeypatch) -> None:
    monkeypatch.setenv("ZED_PROTON_DOWNLOAD_BASE", proton_server)
    target = proton.download_root() / "GE-Proton9-9"
    target.mkdir(parents=True)
    with pytest.raises(proton.ProtonError, match="already installed"):
        proton.start_download("GE-Proton9-9", {"proton_paths": []})


def test_remove_rejects_outside_download_dir(proton_dir: Path) -> None:
    with pytest.raises(proton.ProtonError, match="downloaded"):
        proton.remove_build(str(proton_dir))


def test_invalid_tag_rejected() -> None:
    with pytest.raises(proton.ProtonError, match="Invalid"):
        proton.start_download("../escape", {"proton_paths": []})


def test_download_url_uses_base(monkeypatch) -> None:
    monkeypatch.setenv("ZED_PROTON_DOWNLOAD_BASE", "http://example.test")
    assert proton.download_url("GE-Proton9-9") == (
        "http://example.test/GloriousEggroll/proton-ge-custom/releases/download/"
        "GE-Proton9-9/GE-Proton9-9-x86_64.tar.gz"
    )


def test_store_roundtrip_after_download(proton_server: str, monkeypatch, executable: Path) -> None:
    monkeypatch.setenv("ZED_PROTON_DOWNLOAD_BASE", proton_server)
    job = proton.start_download("GE-Proton9-9", {"proton_paths": []})
    for _ in range(200):
        current = proton.get_job(job["id"])
        if current and current["status"] in ("done", "failed"):
            break
        threading.Event().wait(0.05)
    final = proton.get_job(job["id"])
    assert final is not None

    game = store.create_game(
        {
            "title": "Proton game",
            "path": str(executable),
            "prefix_path": "/tmp/prefix",
            "proton_path": final["path"],
        }
    )
    assert game["proton_path"] == final["path"]


def test_remove_refuses_build_in_use(executable: Path, tmp_path: Path) -> None:
    from zed_launcher import store
    from zed_launcher.services import proton

    installed = proton.download_root() / "GE-Proton-in-use"
    (installed / "files/bin").mkdir(parents=True, exist_ok=True)
    (installed / "proton").write_text("", encoding="utf-8")

    store.create_game(
        {
            "title": "User",
            "path": str(executable),
            "prefix_path": str(tmp_path / "p"),
            "proton_path": str(installed),
        }
    )
    with pytest.raises(proton.ProtonError, match="still used by"):
        proton.remove_build(str(installed))
    assert installed.is_dir()


def test_job_reports_rate_and_eta(proton_server: str, monkeypatch) -> None:
    monkeypatch.setenv("ZED_PROTON_DOWNLOAD_BASE", proton_server)
    job = proton.start_download("GE-Proton9-11", {"proton_paths": []})
    for _ in range(200):
        current = proton.get_job(job["id"])
        assert current is not None
        if current["status"] in ("done", "failed"):
            break
        threading.Event().wait(0.05)
    final = proton.get_job(job["id"])
    assert final is not None
    assert final["status"] == "done", final.get("error")
    assert final["rate"] == 0.0
    assert final["eta"] is None


def test_cancel_finished_job_is_rejected(proton_server: str, monkeypatch) -> None:
    monkeypatch.setenv("ZED_PROTON_DOWNLOAD_BASE", proton_server)
    job = proton.start_download("GE-Proton9-12", {"proton_paths": []})
    for _ in range(200):
        current = proton.get_job(job["id"])
        assert current is not None
        if current["status"] in ("done", "failed"):
            break
        threading.Event().wait(0.05)
    assert proton.cancel_job(job["id"]) is False


def test_download_rejects_non_proton_archive(proton_server: str, monkeypatch, tmp_path: Path) -> None:
    import tarfile

    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "readme.txt").write_text("not proton", encoding="utf-8")
    archive = tmp_path / "broken.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload / "readme.txt", arcname="broken/readme.txt")

    monkeypatch.setenv("ZED_PROTON_DOWNLOAD_BASE", proton_server)
    monkeypatch.setattr(proton.httpx, "stream", lambda *a, **k: _ArchiveStream(archive))
    job = proton.start_download("GE-Proton-broken", {"proton_paths": []})
    for _ in range(200):
        current = proton.get_job(job["id"])
        assert current is not None
        if current["status"] in ("done", "failed"):
            break
        threading.Event().wait(0.05)
    final = proton.get_job(job["id"])
    assert final is not None
    assert final["status"] == "failed"
    assert "does not look like a Proton build" in final["error"]
    assert not (proton.download_root() / "GE-Proton-broken").exists()


class _ArchiveStream:
    def __init__(self, archive: Path) -> None:
        self.archive = archive
        self.headers = {"content-length": str(archive.stat().st_size)}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self, size: int = 65536):
        yield self.archive.read_bytes()
