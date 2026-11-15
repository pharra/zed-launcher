from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from .. import store
from ..config import load_config
from ..paths import log_dir
from ..services import prefixes, proton, system, wine
from ..services.command import PlanError, build_installer_plan
from .models import InstallerRunRequest

router = APIRouter(prefix="/api/v1/installers", tags=["installers"])


def _require_install(install_id: str) -> dict:
    install = store.get_install(install_id)
    if install is None:
        raise HTTPException(status_code=404, detail="Install session not found")
    return install


@router.post("/run", status_code=201)
async def start_install(payload: InstallerRunRequest, request: Request) -> dict:
    installer = Path(payload.installer).expanduser()
    if not installer.is_file():
        raise HTTPException(status_code=400, detail=f"Installer not found: {installer}")

    config = load_config()
    if payload.prefix_path:
        try:
            prefix_path = prefixes.validate_prefix(payload.prefix_path)
        except prefixes.PrefixError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        owned = False
    else:
        try:
            prefix_path = prefixes.create_prefix(
                config.get("prefix_root", ""), payload.prefix_name or payload.title or installer.stem
            )
        except prefixes.PrefixError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        owned = True

    proton_path = proton.find(payload.proton_path, config)
    if proton_path is None and payload.proton_path:
        proton_path = proton.find("", config)
    available = system.tools(config)
    try:
        plan = build_installer_plan(
            installer=str(installer),
            title=payload.title,
            prefix_path=str(prefix_path),
            proton_path=proton_path,
            umu_run=available.get("umu_run"),
            args=payload.args,
            log_dir=str(log_dir()),
        )
    except PlanError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    baseline = sorted(wine.list_shortcuts(prefix_path))
    install = store.create_install(
        str(prefix_path), proton_path or "", str(installer), payload.title, baseline
    )

    synthetic = {
        "id": f"install-{install['id']}",
        "title": payload.title or installer.stem,
        "path": str(installer),
        "args": "",
        "launch_args": "",
        "env": "",
        "working_dir": str(installer.parent),
        "pre_launch": "",
        "post_launch": "",
        "mangohud": False,
        "gamemode": False,
        "gamescope": False,
        "kwin": False,
        "no_sleep": False,
        "sdl": False,
        "wayland": False,
        "wow64": False,
    }
    try:
        run = await request.app.state.runs.start(synthetic, plan, logs=True)
    except RuntimeError as error:
        store.delete_install(install["id"])
        raise HTTPException(status_code=500, detail=str(error)) from error

    return {
        "install_id": install["id"],
        "run_id": run.run_id,
        "prefix_path": str(prefix_path),
        "owned_prefix": owned,
        "proton_path": proton_path or "",
        "snapshot": run.snapshot(),
    }


@router.get("/{install_id}")
def get_install(install_id: str) -> dict:
    install = _require_install(install_id)
    return {
        "install_id": install["id"],
        "prefix_path": install["prefix_path"],
        "proton_path": install["proton_path"],
        "installer": install["installer"],
        "title": install["title"],
    }


@router.get("/{install_id}/detect")
def detect(install_id: str) -> dict:
    install = _require_install(install_id)
    baseline = store.install_baseline(install)
    result = wine.detect_after_install(install["prefix_path"], baseline)
    result["prefix_path"] = install["prefix_path"]
    return result


@router.delete("/{install_id}", status_code=204)
def delete_install(install_id: str, remove_prefix: bool = False) -> None:
    install = _require_install(install_id)
    if remove_prefix:
        try:
            prefixes.remove_prefix(install["prefix_path"])
        except OSError as error:
            raise HTTPException(status_code=400, detail=f"Could not remove prefix: {error}") from error
    store.delete_install(install_id)
