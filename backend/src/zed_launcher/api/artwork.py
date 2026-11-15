from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import store
from ..config import load_config
from ..services import icons, sgdb
from .models import SgdbCoverRequest

router = APIRouter(prefix="/api/v1", tags=["artwork"])


@router.get("/sgdb/search")
def sgdb_search(term: str) -> list[dict]:
    try:
        return sgdb.search(term, load_config())
    except sgdb.SgdbError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/sgdb/grids/{sgdb_id}")
def sgdb_grids(sgdb_id: str) -> list[dict]:
    try:
        return sgdb.grids(sgdb_id, load_config())
    except sgdb.SgdbError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/games/{game_id}/artwork/sgdb")
def set_sgdb_cover(game_id: str, payload: SgdbCoverRequest) -> dict:
    if store.get_game(game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    try:
        cover = sgdb.download_cover(game_id, payload.url)
    except sgdb.SgdbError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    updated = store.update_game(game_id, {"cover": cover})
    assert updated is not None
    return updated


@router.post("/games/{game_id}/icon")
def extract_icon(game_id: str) -> dict:
    game = store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if not icons.available():
        raise HTTPException(status_code=400, detail="Icon extraction is not available")
    try:
        icon = icons.extract_icon(game["path"], game_id)
    except icons.IconError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    if icon is None:
        raise HTTPException(status_code=400, detail="No icon found in this executable")
    updated = store.update_game(game_id, {"icon": icon})
    assert updated is not None
    return updated


@router.delete("/games/{game_id}/icon", status_code=204)
def delete_icon(game_id: str) -> None:
    if store.get_game(game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    icons.remove_icon(game_id)
    store.update_game(game_id, {"icon": ""})
