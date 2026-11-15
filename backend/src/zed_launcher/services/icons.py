"""Extract Windows executable icons to the artwork folder."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

from ..paths import artwork_dir

ICON_DIR = "icons"


class IconError(RuntimeError):
    pass


def _to_png(data: bytes) -> bytes | None:
    """Convert ICO bytes to PNG (WebKit renders PNG far more reliably)."""

    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        with Image.open(io.BytesIO(data)) as image:
            sizes = getattr(image, "ico", None)
            if sizes is not None:
                with contextlib.suppress(ValueError, AttributeError):
                    image.size = max(sizes.sizes())
            frame = image.convert("RGBA")
        out = io.BytesIO()
        frame.save(out, format="PNG")
        return out.getvalue()
    except (OSError, ValueError):
        return None


def available() -> bool:
    try:
        import icoextract  # noqa: F401
    except ImportError:
        return False
    return True


def extract_icon(exe_path: str | Path, game_id: str) -> str | None:
    """Return the relative artwork path of the extracted icon, or ``None``."""

    executable = Path(exe_path).expanduser()
    if not executable.is_file() or executable.suffix.lower() != ".exe":
        return None

    try:
        from icoextract import IconExtractor, IconExtractorError
    except ImportError:
        return None

    try:
        data = IconExtractor(str(executable)).get_icon().getvalue()
    except (IconExtractorError, OSError, ValueError, IndexError):
        return None
    except Exception:  # icoextract may raise pefile errors
        return None

    if not data:
        return None

    target_dir = artwork_dir() / ICON_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    for stale in target_dir.glob(f"{game_id}.*"):
        stale.unlink(missing_ok=True)

    png = _to_png(data)
    target = target_dir / f"{game_id}{'.png' if png is not None else '.ico'}"
    try:
        target.write_bytes(png if png is not None else data)
    except OSError as error:
        raise IconError(f"Could not write the icon: {error}") from error
    return f"{ICON_DIR}/{target.name}"


def remove_icon(game_id: str) -> None:
    target_dir = artwork_dir() / ICON_DIR
    if not target_dir.is_dir():
        return
    for stale in target_dir.glob(f"{game_id}.*"):
        stale.unlink(missing_ok=True)
