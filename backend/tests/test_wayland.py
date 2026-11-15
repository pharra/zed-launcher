from __future__ import annotations

import socket
import struct
import threading
import time
from pathlib import Path

from zed_launcher.services import wayland


def _encode_string(text: str) -> bytes:
    raw = text.encode("utf-8") + b"\0"
    return struct.pack("<I", len(raw)) + raw + b"\0" * (-len(raw) % 4)


def _fake_compositor(path: Path, interfaces: list[str]) -> threading.Thread:
    """Speak just enough Wayland to answer get_registry + sync."""

    def serve() -> None:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        server.listen(1)
        try:
            client, _ = server.accept()
        finally:
            pass
        with client:
            client.settimeout(5)
            # get_registry and sync: two 12-byte requests, ignored beyond their new ids.
            # recv() may return a short read, and closing early would break the client's write.
            received = b""
            while len(received) < 24:
                chunk = client.recv(24 - len(received))
                if not chunk:
                    return
                received += chunk
            events = b""
            for index, name in enumerate(interfaces):
                payload = struct.pack("<I", index + 10) + _encode_string(name) + struct.pack("<I", 1)
                events += struct.pack("<II", 2, ((8 + len(payload)) << 16) | 0) + payload
            done = struct.pack("<I", 1)
            events += struct.pack("<II", 3, ((8 + len(done)) << 16) | 0) + done
            client.sendall(events)
        server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    for _ in range(200):
        if path.exists():
            break
        time.sleep(0.01)
    return thread


def test_globals_reads_the_registry(tmp_path: Path) -> None:
    socket_file = tmp_path / "wayland-test"
    thread = _fake_compositor(socket_file, ["wl_compositor", "wl_shm"])
    found = wayland.globals(str(socket_file))
    thread.join(timeout=5)

    assert [entry["interface"] for entry in found] == ["wl_compositor", "wl_shm"]
    assert found[1]["name"] == 11


def test_probe_reports_a_missing_protocol(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-plain")
    wayland.reset_cache()
    thread = _fake_compositor(tmp_path / "wayland-plain", ["wl_compositor", "wl_shm"])

    result = wayland.probe(refresh=True)
    thread.join(timeout=5)

    assert result["wayland"] is True
    assert result["supported"] is False
    assert "wl_shm" in result["protocols"]


def test_probe_accepts_the_protocol(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-ok")
    wayland.reset_cache()
    thread = _fake_compositor(
        tmp_path / "wayland-ok", ["wl_compositor", wayland.PROTOCOL]
    )

    result = wayland.probe(refresh=True)
    thread.join(timeout=5)

    assert result["supported"] is True
    assert result["error"] == ""


def test_probe_stays_permissive_without_a_wayland_session(monkeypatch) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    wayland.reset_cache()

    # An X11 session nests KWin through --x11-display, so nothing has to be checked.
    assert wayland.probe() == {"wayland": False, "supported": True, "protocols": [], "error": ""}


def test_probe_does_not_block_on_an_unreadable_socket(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-gone")
    wayland.reset_cache()

    # Guessing "unsupported" here would block launches that actually work.
    result = wayland.probe()

    assert result["supported"] is True
    assert result["error"]
