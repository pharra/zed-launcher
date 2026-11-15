"""SteamGridDB artwork search."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from ..config import load_config
from ..paths import artwork_dir

DEFAULT_API = "https://www.steamgriddb.com/api/v2"
_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


class SgdbError(RuntimeError):
    pass


def _base() -> str:
    return os.environ.get("ZED_SGDB_API", DEFAULT_API).rstrip("/")


def _key(config: dict[str, Any]) -> str:
    key = str(config.get("steamgriddb_api_key") or "").strip()
    if not key:
        raise SgdbError("Add a SteamGridDB API key in Settings first.")
    return key


def _get(path: str, config: dict[str, Any], params: dict[str, Any] | None = None) -> Any:
    url = f"{_base()}{path}"
    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {_key(config)}", "User-Agent": "zed-launcher"},
            params=params or {},
            timeout=20.0,
        )
    except httpx.HTTPError as error:
        raise SgdbError(f"Could not reach SteamGridDB: {error}") from error

    if response.status_code == 401:
        raise SgdbError("SteamGridDB rejected the API key.")
    if response.status_code == 404:
        return []
    if response.status_code != 200:
        raise SgdbError(f"SteamGridDB returned {response.status_code}")
    payload = response.json()
    if not payload.get("success", True):
        raise SgdbError(str(payload.get("errors") or "SteamGridDB request failed"))
    return payload.get("data") or []


def search(term: str, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = config or load_config()
    term = term.strip()
    if not term:
        return []
    data = _get(f"/search/autocomplete/{quote(term)}", config)
    return [{"id": str(entry.get("id")), "name": entry.get("name", "")} for entry in data]


def grids(sgdb_id: str, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = config or load_config()
    data = _get(f"/grids/game/{sgdb_id}", config, {"dimensions": "600x900", "types": "static"})
    if not data:
        data = _get(f"/grids/game/{sgdb_id}", config)
    return [
        {
            "id": str(entry.get("id")),
            "url": entry.get("url", ""),
            "thumb": entry.get("thumb", entry.get("url", "")),
            "width": entry.get("width"),
            "height": entry.get("height"),
        }
        for entry in data
        if entry.get("url")
    ]


def download_cover(game_id: str, url: str) -> str:
    """Download a cover into the artwork folder and return its relative path."""

    if not url.startswith("https://"):
        raise SgdbError("Only https image URLs are allowed")
    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
    except httpx.HTTPError as error:
        raise SgdbError(f"Could not download the cover: {error}") from error
    if response.status_code != 200:
        raise SgdbError(f"Cover download failed with {response.status_code}")

    suffix = Path(httpx.URL(url).path).suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        suffix = ".png"

    covers = artwork_dir() / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    safe_id = _SAFE.sub("-", game_id)
    for stale in covers.glob(f"{safe_id}.*"):
        stale.unlink(missing_ok=True)
    target = covers / f"{safe_id}{suffix}"
    target.write_bytes(response.content)
    return f"covers/{target.name}"
