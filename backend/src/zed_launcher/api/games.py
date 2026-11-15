from __future__ import annotations

import contextlib
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from .. import store
from ..config import load_config
from ..paths import log_dir
from ..services import artwork, icons, prefixes, proton, system
from ..services.command import PlanError, build_plan, normalize_programs
from ..services.shortcuts import create_desktop_entry, remove_desktop_entry, shortcut_exists
from .models import ArtworkRequest, GameCreate, GamePatch

router = APIRouter(prefix="/api/v1/games", tags=["games"])


def _with_shortcut(game: dict) -> dict:
    """Tell the UI whether a desktop entry already exists for this game."""

    return {**game, "shortcut": shortcut_exists(str(game["id"]))}


@router.get("")
def list_games(search: str | None = None, sort: str = "title") -> list[dict]:
    return [_with_shortcut(game) for game in store.list_games(search, sort)]


@router.get("/{game_id}")
def get_game(game_id: str) -> dict:
    game = store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return _with_shortcut(game)


@router.get("/{game_id}/runs")
def get_game_runs(game_id: str, limit: int = 20) -> list[dict]:
    if store.get_game(game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return store.game_runs(game_id, limit)


@router.post("", status_code=201)
def create_game(payload: GameCreate) -> dict:
    data = payload.model_dump()
    mode = data.pop("mode")
    prefix_name = data.pop("prefix_name")
    requested_prefix = data.pop("prefix_path")

    path = Path(data["path"]).expanduser()
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Executable does not exist: {path}")

    config = load_config()
    status = system.dependency_status(config)
    if not status["required"]["umu_run"]["available"]:
        raise HTTPException(
            status_code=400,
            detail="umu-run was not found. Install umu-launcher or set its path in Settings.",
        )
    if not status["required"]["proton"]["available"]:
        raise HTTPException(
            status_code=400,
            detail="No Proton build found. Download one from the Proton manager.",
        )

    install_id = data.pop("install_id", "")
    if install_id:
        from .. import store as _store

        install = _store.get_install(install_id)
        if install is None:
            raise HTTPException(status_code=404, detail="Install session not found")
        data["prefix_path"] = install["prefix_path"]
        data["owned_prefix"] = True
        if not data.get("proton_path"):
            data["proton_path"] = install.get("proton_path") or ""
        if not data.get("title"):
            data["title"] = install.get("title") or "Game"
    elif mode == "create":
        try:
            prefix = prefixes.create_prefix(
                config.get("prefix_root", ""), prefix_name or data.get("title") or path.stem
            )
        except prefixes.PrefixError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        data["prefix_path"] = str(prefix)
        data["owned_prefix"] = True
    else:
        if not requested_prefix:
            raise HTTPException(status_code=400, detail="Choose an existing Wine prefix")
        try:
            prefix = prefixes.validate_prefix(requested_prefix)
        except prefixes.PrefixError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        data["prefix_path"] = str(prefix)
        data["owned_prefix"] = False

    data["path"] = str(path)
    if not data.get("title"):
        data["title"] = path.stem or "Game"
    if data.get("proton_path"):
        resolved = proton.find(str(data["proton_path"]), config)
        if resolved is None:
            raise HTTPException(status_code=400, detail=f"Proton build not found: {data['proton_path']}")
        data["proton_path"] = resolved
    if not data.get("id"):
        data["id"] = uuid.uuid4().hex[:12]
    if not data.get("icon") and icons.available():
        with contextlib.suppress(Exception):
            extracted = icons.extract_icon(data["path"], data["id"])
            if extracted:
                data["icon"] = extracted

    data["extra_programs"] = normalize_programs(data.get("extra_programs"), data["path"])
    game = store.create_game(data)
    if install_id:
        store.delete_install(install_id)
    return game


@router.patch("/{game_id}")
def update_game(game_id: str, payload: GamePatch) -> dict:
    patch = payload.model_dump(exclude_unset=True)

    if "path" in patch:
        path = Path(patch["path"]).expanduser()
        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"Executable does not exist: {path}")
        patch["path"] = str(path)

    if "prefix_path" in patch:
        try:
            patch["prefix_path"] = str(prefixes.validate_prefix(patch["prefix_path"]))
        except prefixes.PrefixError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    if "proton_path" in patch and patch["proton_path"]:
        resolved = proton.find(str(patch["proton_path"]))
        if resolved is None:
            raise HTTPException(status_code=400, detail=f"Proton build not found: {patch['proton_path']}")
        patch["proton_path"] = resolved

    if "extra_programs" in patch or "path" in patch:
        current = store.get_game(game_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Game not found")
        game_path = patch.get("path", current["path"])
        raw = patch.get("extra_programs", current.get("extra_programs"))
        patch["extra_programs"] = normalize_programs(raw, game_path)

    game = store.update_game(game_id, patch)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.delete("/{game_id}", status_code=204)
def delete_game(game_id: str, request: Request, remove_prefix: bool = False) -> None:
    game = store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if request.app.state.runs.active_for(game_id) is not None:
        raise HTTPException(status_code=409, detail="Stop the game before removing it")
    if remove_prefix and game.get("owned_prefix") and game.get("prefix_path"):
        try:
            prefixes.remove_prefix(game["prefix_path"])
        except OSError as error:
            raise HTTPException(status_code=400, detail=f"Could not remove prefix: {error}") from error
    store.delete_game(game_id)


@router.post("/{game_id}/launch")
async def launch_game(game_id: str, request: Request, logs: bool = True) -> dict:
    game = store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    existing = request.app.state.runs.active_for(game_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"{game['title']} is already running")

    config = load_config()
    prefix_path = game.get("prefix_path") or ""
    try:
        prefixes.require_dir(prefix_path)
    except prefixes.PrefixError as error:
        raise HTTPException(
            status_code=400,
            detail=f"{error}. Create the game again or point it at a prefix in Edit.",
        ) from error

    proton_path = proton.find(game.get("proton_path") or "", config)
    notes: list[str] = []
    requested_proton = str(game.get("proton_path") or "")
    if proton_path is None and requested_proton:
        proton_path = proton.find("", config)
        if proton_path:
            notes.append(
                f"The configured Proton build is gone ({requested_proton}); "
                f"falling back to {proton_path}."
            )
    available = system.tools(config)
    try:
        plan = build_plan(
            game,
            prefix_path=prefix_path,
            proton_path=proton_path,
            available=available,
            config=config,
            log_dir=str(log_dir()),
            logs=logs,
            notes=notes,
        )
    except PlanError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        run = await request.app.state.runs.start(game, plan, logs=logs)
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return run.snapshot()


@router.post("/{game_id}/shortcut")
def create_shortcut(game_id: str, target: str = "applications") -> dict:
    game = store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if target not in ("applications", "desktop"):
        raise HTTPException(status_code=400, detail="target must be 'applications' or 'desktop'")
    path = create_desktop_entry(game, target)
    return {"path": str(path)}


@router.delete("/{game_id}/shortcut", status_code=204)
def delete_shortcut(game_id: str, target: str = "applications") -> None:
    remove_desktop_entry(game_id, target)


@router.post("/{game_id}/artwork")
def set_artwork(game_id: str, payload: ArtworkRequest) -> dict:
    game = store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    try:
        cover = artwork.save_cover(game_id, payload.path)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"Image not found: {payload.path}") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    updated = store.update_game(game_id, {"cover": cover})
    assert updated is not None
    return updated


@router.delete("/{game_id}/artwork", status_code=204)
def delete_artwork(game_id: str) -> None:
    if store.get_game(game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    artwork.remove_cover(game_id)
    store.update_game(game_id, {"cover": ""})
