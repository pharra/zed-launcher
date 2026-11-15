from __future__ import annotations

import contextlib
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import expand, load_config, update_config
from ..paths import config_dir, data_dir, log_dir, state_dir, web_root
from ..services import autostart, proton, system
from .models import (
    ProtonDownloadRequest,
    ProtonPathRequest,
    ProtonRemoveRequest,
    SettingsPatch,
)

router = APIRouter(prefix="/api/v1", tags=["system"])


class OpenPathRequest(BaseModel):
    path: str


@router.get("/health")
def health() -> dict:
    return {"ok": True, "app": "zed-launcher"}


@router.get("/info")
def info() -> dict:
    config = load_config()
    builds = proton.candidates(config)
    effective = proton.find(str(config.get("proton_default") or ""), config)
    return {
        "config": config,
        "tools": system.tools(config),
        "dependencies": system.dependency_status(config),
        "autostart": autostart.enabled(),
        "tray_host": system.tray_host_available(),
        "proton_effective": effective,
        "protons": builds,
        "proton_sources": proton.sources(config),
        "gpus": system.gpu_list(),
        "paths": {
            "config": str(config_dir()),
            "data": str(data_dir()),
            "state": str(state_dir()),
            "logs": str(log_dir()),
            "protons": str(proton.download_root()),
            "web": str(web_root() or ""),
        },
    }


@router.get("/diagnostics")
def diagnostics() -> dict:
    return system.diagnostics()


@router.get("/browse")
def browse(path: str | None = None, show_hidden: bool = False) -> dict:
    root = Path(path).expanduser() if path else Path.home()
    if not root.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be absolute")
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Path does not exist: {root}")
    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {root}")

    entries: list[dict] = []
    try:
        children = sorted(root.iterdir(), key=lambda entry: (not entry.is_dir(), entry.name.lower()))
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=f"Permission denied: {root}") from error

    for child in children:
        if not show_hidden and child.name.startswith("."):
            continue
        try:
            is_dir = child.is_dir()
            size = child.stat().st_size if child.is_file() else 0
            executable = is_dir or child.suffix.lower() in (".exe", ".msi", ".bat", ".sh") or (
                child.is_file() and child.stat().st_mode & 0o111 != 0
            )
            is_prefix = is_dir and (child / "drive_c").is_dir()
        except OSError:
            is_dir = False
            size = 0
            executable = False
            is_prefix = False
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "is_dir": is_dir,
                "size": size,
                "executable": executable,
                "wine_prefix": is_prefix,
            }
        )

    return {
        "path": str(root),
        "parent": str(root.parent) if root.parent != root else None,
        "entries": entries[:1000],
    }


@router.post("/open")
def open_path(payload: OpenPathRequest) -> dict:
    try:
        system.open_path(payload.path)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"Path does not exist: {payload.path}") from error
    return {"ok": True}


@router.get("/settings")
def get_settings() -> dict:
    return load_config()


@router.put("/settings")
def put_settings(payload: SettingsPatch) -> dict:
    patch = payload.model_dump(exclude_unset=True)

    if "prefix_root" in patch:
        root = Path(expand(patch["prefix_root"]))
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise HTTPException(status_code=400, detail=f"Could not create folder: {error}") from error
        patch["prefix_root"] = str(root)

    if patch.get("proton_default"):
        resolved = proton.find(str(patch["proton_default"]))
        if resolved is None:
            raise HTTPException(
                status_code=400,
                detail=f"Proton build not found: {patch['proton_default']}",
            )
        patch["proton_default"] = resolved

    if "umu_run" in patch and patch["umu_run"]:
        binary = Path(expand(str(patch["umu_run"])))
        if not binary.is_file():
            raise HTTPException(status_code=400, detail=f"umu-run not found: {binary}")
        patch["umu_run"] = str(binary)

    if "tool_paths" in patch:
        cleaned_tools: dict[str, str] = {}
        for key, value in (patch.get("tool_paths") or {}).items():
            if key not in system.TOOL_BINARIES:
                continue
            raw = str(value or "").strip()
            if not raw:
                continue
            candidate = Path(expand(raw))
            if not candidate.is_file():
                raise HTTPException(
                    status_code=400,
                    detail=f"{system.OPTIONAL_TOOLS.get(key, key)} not found: {candidate}",
                )
            cleaned_tools[key] = str(candidate)
        patch["tool_paths"] = cleaned_tools

    if "proton_paths" in patch:
        cleaned: list[str] = []
        for entry in patch["proton_paths"] or []:
            path = Path(expand(str(entry)))
            if path.is_dir() and str(path) not in cleaned:
                cleaned.append(str(path))
        patch["proton_paths"] = cleaned

    return update_config(patch)


@router.get("/autostart")
def get_autostart() -> dict:
    return {"enabled": autostart.enabled(), "path": str(autostart.entry_path())}


@router.post("/autostart")
def set_autostart(enabled: bool = True) -> dict:
    autostart.set_enabled(enabled)
    return {"enabled": autostart.enabled(), "path": str(autostart.entry_path())}


@router.get("/protons")
def list_protons() -> dict:
    config = load_config()
    builds = proton.candidates(config)
    for build in builds:
        path = Path(build["path"])
        build["size"] = proton.directory_size(path) if path.is_dir() else 0
    return {
        "builds": builds,
        "sources": proton.sources(config),
        "default": str(config.get("proton_default") or ""),
        "effective": proton.find(str(config.get("proton_default") or ""), config),
        "download_dir": str(proton.download_root()),
        "has_token": bool(str(config.get("github_token") or "").strip()),
    }


@router.get("/protons/releases")
def list_releases(limit: int = 30) -> list[dict]:
    try:
        return proton.fetch_releases(load_config(), limit)
    except proton.ProtonError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.delete("/protons/downloads/{job_id}")
def cancel_download(job_id: str) -> dict:
    if not proton.cancel_job(job_id):
        raise HTTPException(status_code=409, detail="This download already finished")
    return {"ok": True}


@router.post("/protons/downloads", status_code=202)
def start_download(payload: ProtonDownloadRequest) -> dict:
    try:
        return proton.start_download(payload.tag, load_config(), payload.url or None)
    except proton.ProtonError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/protons/downloads/{job_id}")
def download_status(job_id: str) -> dict:
    job = proton.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Download not found")
    return job


@router.post("/protons/paths")
def add_proton_path(payload: ProtonPathRequest) -> dict:
    path = Path(expand(payload.path))
    if not path.is_dir() or not proton.is_proton_dir(path):
        raise HTTPException(status_code=400, detail=f"{path} is not a Proton build")
    config = load_config()
    paths = list(config.get("proton_paths") or [])
    if str(path) not in paths:
        paths.append(str(path))
        config = update_config({"proton_paths": paths})
    return {"paths": config.get("proton_paths") or [], "builds": proton.candidates(config)}


@router.delete("/protons/paths")
def remove_proton_path(path: str) -> dict:
    config = load_config()
    paths = [entry for entry in (config.get("proton_paths") or []) if entry != expand(path)]
    config = update_config({"proton_paths": paths})
    return {"paths": config.get("proton_paths") or [], "builds": proton.candidates(config)}


@router.post("/protons/remove")
def remove_build(payload: ProtonRemoveRequest) -> dict:
    try:
        removed = proton.remove_build(payload.path)
    except proton.ProtonError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not removed:
        raise HTTPException(status_code=404, detail="Proton build not found")
    return {"ok": True}


@router.get("/prefixes/default")
def default_prefix_root() -> dict:
    config = load_config()
    root = Path(expand(str(config.get("prefix_root") or "")))
    with contextlib.suppress(OSError):
        root.mkdir(parents=True, exist_ok=True)
    return {"prefix_root": str(root), "exists": root.is_dir()}
