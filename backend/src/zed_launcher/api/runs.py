from __future__ import annotations

import secrets
from contextlib import suppress
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from .. import store
from ..services import processes

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])

LOG_TAIL = 400


def _log_tail(log_path: str) -> list[str]:
    if not log_path:
        return []
    target = Path(log_path)
    if not target.is_file():
        return []
    try:
        with target.open("r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return []
    return [line.rstrip("\n") for line in lines[-LOG_TAIL:]]


def _pid_alive(record: dict) -> bool:
    """Whether the recorded process is still ours.

    The start time rules out a recycled pid; runs recorded before that column existed
    fall back to the run marker.
    """

    pid = record.get("pid")
    started = str(record.get("pid_started") or "")
    if started:
        return processes.same_process(pid, started)
    return processes.belongs_to_run(pid, str(record["id"]))


def detached_snapshot(record: dict) -> dict:
    game = store.get_game(str(record["game_id"])) or {}
    return {
        "run_id": record["id"],
        "game_id": record["game_id"],
        "title": game.get("title") or "Game",
        "status": record["status"],
        "argv": [],
        "pid": None,
        "started_at": record.get("started_at"),
        "log_path": record.get("log_path") or "",
        "lines": _log_tail(record.get("log_path") or ""),
        "detached": True,
    }


@router.get("")
def active_runs(request: Request) -> list[dict]:
    live = request.app.state.runs.active()
    known = {entry["run_id"] for entry in live}
    extra = []
    for record in store.running_runs():
        if record["id"] in known:
            continue
        if not _pid_alive(record):
            # The process is gone and no watcher survived: close it now.
            store.resolve_run(
                record["id"], "closed", None, store._seconds_since(record.get("started_at"))
            )
            continue
        extra.append(detached_snapshot(record))
    return [*live, *extra]


@router.get("/recent")
def recent_runs(limit: int = 20) -> list[dict]:
    return store.recent_runs(limit)


@router.get("/{run_id}")
def get_run(run_id: str, request: Request) -> dict:
    run = request.app.state.runs.get(run_id)
    if run is not None:
        return run.snapshot()
    record = store.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if record["status"] in store.OPEN_RUN_STATUSES:
        return detached_snapshot(record)
    return record


@router.post("/{run_id}/stop")
async def stop_run(run_id: str, request: Request) -> dict:
    if await request.app.state.runs.stop(run_id):
        return {"ok": True}

    record = store.get_run(run_id)
    if record is None or record["status"] not in store.OPEN_RUN_STATUSES:
        raise HTTPException(status_code=409, detail="Run is not active")

    killed = processes.terminate_run(run_id)
    if killed == 0:
        raise HTTPException(status_code=409, detail="No process left to stop")
    store.resolve_run(run_id, "stopped", None, store._seconds_since(record.get("started_at")))
    return {"ok": True, "detached": True}


@router.websocket("/{run_id}/events")
async def run_events(websocket: WebSocket, run_id: str) -> None:
    token = websocket.query_params.get("token", "")
    expected = getattr(websocket.app.state, "token", "")
    if not expected or not secrets.compare_digest(token, expected):
        await websocket.close(code=4401)
        return

    run = websocket.app.state.runs.get(run_id)
    if run is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    manager = websocket.app.state.runs
    queue, backlog, status = manager.subscribe(run)
    try:
        await websocket.send_json({"type": "snapshot", "status": status, "lines": backlog})
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            if event.get("type") == "exit":
                break
    except WebSocketDisconnect:
        pass
    finally:
        manager.unsubscribe(run, queue)
        with suppress(Exception):
            await websocket.close()
