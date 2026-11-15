from __future__ import annotations

import shutil
from pathlib import Path

from ..paths import artwork_dir

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".avif"}


def save_cover(game_id: str, source: str) -> str:
    path = Path(source).expanduser()
    if not path.is_file():
        raise FileNotFoundError(source)
    extension = path.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported image type: {extension or 'unknown'}")

    covers = artwork_dir() / "covers"
    covers.mkdir(parents=True, exist_ok=True)

    destination = covers / f"{game_id}{extension}"
    staging = covers / f".{game_id}{extension}.tmp"
    try:
        shutil.copyfile(path, staging)
        staging.replace(destination)
    finally:
        staging.unlink(missing_ok=True)

    for stale in covers.glob(f"{game_id}.*"):
        if stale != destination:
            stale.unlink(missing_ok=True)
    return f"covers/{destination.name}"


def remove_cover(game_id: str) -> None:
    covers = artwork_dir() / "covers"
    if not covers.is_dir():
        return
    for stale in covers.glob(f"{game_id}.*"):
        stale.unlink(missing_ok=True)
