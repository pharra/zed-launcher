from __future__ import annotations

import asyncio
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

import uvicorn

from .app import create_app


@dataclass
class ServerHandle:
    token: str
    host: str
    port: int
    server: uvicorn.Server
    thread: threading.Thread

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/?token={self.token}"

    def stop(self) -> None:
        self.server.should_exit = True


def _wait_until_ready(port: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/v1/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            time.sleep(0.05)
    raise RuntimeError("The launcher backend did not start in time")


def start_server(token: str | None = None, host: str = "127.0.0.1", port: int = 0) -> ServerHandle:
    token = token or secrets.token_urlsafe(18)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.setblocking(False)
    actual_port = sock.getsockname()[1]

    app = create_app(token)
    config = uvicorn.Config(
        app,
        host=host,
        port=actual_port,
        log_level="warning",
        ws="auto",
        lifespan="on",
    )
    server = uvicorn.Server(config)

    def target() -> None:
        asyncio.run(server.serve(sockets=[sock]))

    thread = threading.Thread(target=target, name="zed-launcher-backend", daemon=True)
    thread.start()
    _wait_until_ready(actual_port)
    return ServerHandle(token=token, host=host, port=actual_port, server=server, thread=thread)


def serve_blocking(token: str | None = None, host: str = "127.0.0.1", port: int = 8765) -> None:
    token = token or secrets.token_urlsafe(18)
    print(f"Zed Launcher API: http://{host}:{port}/?token={token}")
    uvicorn.run(create_app(token), host=host, port=port, log_level="info", ws="auto")
