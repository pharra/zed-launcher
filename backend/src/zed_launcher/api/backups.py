from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import store
from ..config import load_config
from ..services import backup
from .models import BackupRequest, RestoreRequest

router = APIRouter(prefix="/api/v1/backups", tags=["backups"])


@router.get("")
def list_backups(destination: str | None = None) -> dict:
    config = load_config()
    target = destination or str(backup.default_dir(config))
    return {
        "destination": target,
        "backups": backup.list_backups(destination, config),
    }


@router.post("", status_code=201)
def create_backup(payload: BackupRequest) -> dict:
    try:
        return backup.create_backup(
            payload.destination or None,
            include_artwork=payload.include_artwork,
            include_saves=payload.include_saves,
            config=load_config(),
        )
    except backup.BackupError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/saves")
def savegame_estimate() -> dict:
    prefixes = sorted({game["prefix_path"] for game in store.list_games() if game.get("prefix_path")})
    return backup.savegame_size(prefixes)


@router.post("/restore")
def restore(payload: RestoreRequest) -> dict:
    try:
        return backup.restore_backup(payload.path, load_config())
    except backup.BackupError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("")
def delete_backup(path: str) -> dict:
    if not backup.delete_backup(path):
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"ok": True}
