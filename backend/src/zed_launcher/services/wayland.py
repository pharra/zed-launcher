"""Ask the running Wayland compositor which globals it advertises.

A nested KWin needs ``wp_single_pixel_buffer_manager_v1`` from the host compositor; without
it ``kwin_wayland`` gives up right after creating its socket, which looks like a crash. The
check is a minimal Wayland client: connect, send ``get_registry`` and ``sync``, read the
globals, disconnect. No bindings are involved, so nothing has to be installed for it.
"""

from __future__ import annotations

import os
import socket
import struct
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PROTOCOL = "wp_single_pixel_buffer_manager_v1"

# The registry only changes when the compositor restarts, so a short cache keeps /info cheap.
CACHE_SECONDS = 30.0
TIMEOUT_SECONDS = 2.0

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def socket_path(environ: Mapping[str, str]) -> str | None:
    display = str(environ.get("WAYLAND_DISPLAY") or "")
    if not display:
        return None
    if display.startswith("/"):
        return display
    runtime = str(environ.get("XDG_RUNTIME_DIR") or "")
    if not runtime:
        return None
    return str(Path(runtime) / display)


def _message(object_id: int, opcode: int, payload: bytes = b"") -> bytes:
    return struct.pack("<II", object_id, ((8 + len(payload)) << 16) | opcode) + payload


def _read_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise OSError("the compositor closed the connection")
        data += chunk
    return data


def _string(payload: bytes, offset: int) -> tuple[str, int]:
    """A Wayland string and the offset just past its padding."""

    length = struct.unpack_from("<I", payload, offset)[0]
    start = offset + 4
    text = payload[start : start + max(0, length - 1)].decode("utf-8", "replace")
    return text, start + ((length + 3) // 4) * 4


def globals(path: str, timeout: float = TIMEOUT_SECONDS) -> list[dict[str, Any]]:
    """Every ``wl_registry`` global the compositor offers, as name/interface/version."""

    display_id, registry_id, callback_id = 1, 2, 3
    found: list[dict[str, Any]] = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(path)
        sock.sendall(_message(display_id, 1, struct.pack("<I", registry_id)))  # get_registry
        sock.sendall(_message(display_id, 0, struct.pack("<I", callback_id)))  # sync
        while True:
            object_id, size_opcode = struct.unpack("<II", _read_exact(sock, 8))
            size, opcode = size_opcode >> 16, size_opcode & 0xFFFF
            payload = _read_exact(sock, size - 8) if size > 8 else b""
            if object_id == display_id and opcode == 0:  # wl_display.error
                _code = struct.unpack_from("<I", payload, 4)[0]
                message, _ = _string(payload, 8)
                raise OSError(f"the compositor reported an error: {message}")
            if object_id == callback_id and opcode == 0:  # wl_callback.done
                return found
            if object_id == registry_id and opcode == 0:  # wl_registry.global
                name = struct.unpack_from("<I", payload, 0)[0]
                interface, offset = _string(payload, 4)
                version = struct.unpack_from("<I", payload, offset)[0]
                found.append({"name": name, "interface": interface, "version": version})


def probe(environ: Mapping[str, str] | None = None, *, refresh: bool = False) -> dict[str, Any]:
    """Whether this session can host a nested KWin.

    ``supported`` stays true when the session cannot be inspected (X11, a socket we may not
    open), because guessing "unsupported" would block launches that actually work.
    """

    environ = os.environ if environ is None else environ
    path = socket_path(environ)
    if path is None:
        # X11 session: kwin nests through --x11-display, no Wayland protocol involved.
        return {"wayland": False, "supported": True, "protocols": [], "error": ""}

    now = time.monotonic()
    cached = _cache.get(path)
    if cached and not refresh and now - cached[0] < CACHE_SECONDS:
        return cached[1]

    try:
        names = [entry["interface"] for entry in globals(path)]
    except OSError as error:
        result = {"wayland": True, "supported": True, "protocols": [], "error": str(error)}
    else:
        result = {
            "wayland": True,
            "supported": PROTOCOL in names,
            "protocols": names,
            "error": "",
        }
    _cache[path] = (now, result)
    return result


def reset_cache() -> None:
    _cache.clear()
