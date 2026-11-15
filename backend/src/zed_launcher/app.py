from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, store
from .api import artwork, backups, games, installer, prefixes, runs
from .api import system as system_api
from .api.security import TokenMiddleware
from .config import load_config
from .paths import artwork_dir, ensure_dirs, prune_proton_logs, web_root
from .services.runner import RunManager


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def _backup_scheduler(interval: float = 3600.0) -> None:
    from .services import backup

    while True:
        with suppress(Exception):
            await asyncio.to_thread(backup.run_scheduled)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ensure_dirs()
    store.init_db(load_config().get("prefix_root"))
    for stale in store.prune_runs():
        with suppress(OSError):
            Path(stale).unlink(missing_ok=True)
    prune_proton_logs()
    store.reconcile_open_runs(_pid_alive)

    scheduler = asyncio.create_task(_backup_scheduler())
    yield
    scheduler.cancel()
    with suppress(asyncio.CancelledError):
        await scheduler


def create_app(token: str | None = None) -> FastAPI:
    ensure_dirs()
    app = FastAPI(title="Zed Launcher", version=__version__, lifespan=lifespan)
    app.state.token = token or os.environ.get("ZED_TOKEN") or "zed-dev-token"
    app.state.runs = RunManager()
    app.add_middleware(TokenMiddleware)

    app.include_router(system_api.router)
    app.include_router(games.router)
    app.include_router(installer.router)
    app.include_router(prefixes.router)
    app.include_router(backups.router)
    app.include_router(artwork.router)
    app.include_router(runs.router)

    app.mount("/artwork", StaticFiles(directory=str(artwork_dir())), name="artwork")

    root = web_root()
    if root is not None:
        app.mount("/", StaticFiles(directory=str(root), html=True), name="web")
    else:

        @app.get("/")
        def missing_frontend() -> JSONResponse:
            return JSONResponse(
                {
                    "detail": "The frontend is not built yet.",
                    "hint": "Run `npm run build` in frontend/ or use `nix build`.",
                }
            )

    return app
