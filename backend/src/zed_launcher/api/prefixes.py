from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ..config import load_config
from ..paths import log_dir
from ..services import prefixes, processes, proton, system, wine
from ..services.command import PlanError, build_tool_plan
from .models import (
    PrefixCleanupRequest,
    PrefixCloneRequest,
    PrefixScanRequest,
    PrefixToolRequest,
)

router = APIRouter(prefix="/api/v1/prefixes", tags=["prefixes"])


def _describe(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return " ".join(part for part in raw.decode("utf-8", "replace").split("\0") if part)[:200]


@router.get("/processes")
def leftover_processes(path: str) -> dict:
    try:
        prefix = prefixes.require_dir(path)
    except prefixes.PrefixError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    entries = [
        {"pid": entry.pid, "command": _describe(entry.pid)}
        for entry in processes.leftovers(prefix)
    ]
    return {"prefix_path": str(prefix), "processes": entries, "count": len(entries)}


@router.post("/cleanup")
def cleanup_processes(payload: PrefixCleanupRequest) -> dict:
    try:
        prefix = prefixes.require_dir(payload.path)
    except prefixes.PrefixError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    killed = processes.terminate_prefix(prefix)
    return {"killed": killed, "remaining": len(processes.leftovers(prefix))}


@router.get("/presets")
def presets() -> list[dict]:
    return [dict(entry) for entry in prefixes.WINETRICKS_PRESETS]


@router.post("/cleanup-temp")
def cleanup_temp(payload: PrefixCleanupRequest) -> dict:
    try:
        prefix = prefixes.require_dir(payload.path)
    except prefixes.PrefixError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    freed = prefixes.cleanup_temp(prefix)
    return {"freed": freed, "size": prefixes.prefix_size(prefix)}


@router.post("/clone", status_code=201)
def clone(payload: PrefixCloneRequest) -> dict:
    try:
        source = prefixes.validate_prefix(payload.path)
    except prefixes.PrefixError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    config = load_config()
    try:
        target = prefixes.create_prefix(config.get("prefix_root", ""), payload.name or source.name)
        prefixes.remove_prefix(target)
        shutil.copytree(source, target, symlinks=True)
    except OSError as error:
        raise HTTPException(status_code=400, detail=f"Could not clone the prefix: {error}") from error
    return {"path": str(target), "size": prefixes.prefix_size(target)}


@router.post("/scan")
def scan(payload: PrefixScanRequest) -> dict:
    try:
        prefix = prefixes.validate_prefix(payload.path)
    except prefixes.PrefixError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    candidates = wine.shortcut_candidates(prefix)
    return {
        "prefix_path": str(prefix),
        "candidates": candidates,
        "fallback": wine.scan_executables(prefix),
        "size": prefixes.prefix_size(prefix),
    }


@router.post("/run")
async def run_tool(payload: PrefixToolRequest, request: Request) -> dict:
    try:
        prefix = prefixes.validate_prefix(payload.prefix_path)
    except prefixes.PrefixError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    config = load_config()
    proton_path = proton.find(payload.proton_path, config)
    available = system.tools(config)
    try:
        plan = build_tool_plan(
            kind=payload.kind,
            prefix_path=str(prefix),
            proton_path=proton_path,
            umu_run=available.get("umu_run"),
            target=payload.target,
            args=payload.args,
            log_dir=str(log_dir()),
            env=payload.env,
        )
    except PlanError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    synthetic = {
        "id": f"tool-{payload.kind}-{prefix.name}",
        "title": f"{payload.kind} · {prefix.name}",
        "path": payload.target or str(prefix),
        "args": "",
        "launch_args": "",
        "env": "",
        "working_dir": "",
        "pre_launch": "",
        "post_launch": "",
        "mangohud": False,
        "gamemode": False,
        "gamescope": False,
        "no_sleep": False,
        "sdl": False,
        "wayland": False,
        "wow64": False,
    }
    try:
        run = await request.app.state.runs.start(synthetic, plan, logs=True)
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return {"run_id": run.run_id, "snapshot": run.snapshot(), "prefix_path": str(prefix)}
