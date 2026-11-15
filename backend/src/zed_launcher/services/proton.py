from __future__ import annotations

import contextlib
import os
import shutil
import tarfile
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from ..config import expand, load_config
from ..paths import data_dir

GE_REPO = "GloriousEggroll/proton-ge-custom"
DEFAULT_API = "https://api.github.com"
DEFAULT_DOWNLOAD_BASE = "https://github.com"
JOB_RETENTION = 60 * 60


class ProtonError(RuntimeError):
    pass


class _Cancelled(RuntimeError):
    pass


def _cancelled(job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        return bool(job and job.get("cancel"))


def cancel_job(job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        if job is None or job["status"] in ("done", "failed"):
            return False
        job["cancel"] = True
        job["updated"] = time.time()
        return True


def download_root() -> Path:
    path = data_dir() / "protons"
    path.mkdir(parents=True, exist_ok=True)
    return path


def steam_roots() -> list[Path]:
    candidates = [
        Path.home() / ".local/share/Steam",
        Path.home() / ".steam/steam",
        Path.home() / ".steam/root",
        Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    ]
    seen: set[Path] = set()
    result: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if candidate.is_dir() and resolved not in seen:
            seen.add(resolved)
            result.append(candidate)
    return result


def compatibility_dirs() -> list[tuple[Path, str]]:
    dirs: list[tuple[Path, str]] = []

    for root in steam_roots():
        flatpak = "com.valvesoftware.Steam" in str(root)
        dirs.append((root / "compatibilitytools.d", "flatpak" if flatpak else "steam"))

    dirs.append((Path("/run/current-system/sw/share/steam/compatibilitytools.d"), "system"))
    dirs.append((download_root(), "download"))
    return dirs


def is_proton_dir(directory: Path) -> bool:
    return (
        (directory / "proton").is_file()
        or (directory / "files/bin/wine").is_file()
        or (directory / "files/bin/wine64").is_file()
    )


def _read_display_name(directory: Path) -> str:
    for candidate in ("compatibilitytool.vdf", "toolmanifest.vdf"):
        path = directory / candidate
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if '"display_name"' in line:
                    parts = line.split('"')
                    if len(parts) >= 4:
                        return parts[-2]
    return ""


def read_version(directory: Path) -> str:
    for candidate in ("version", "proton_version"):
        path = directory / candidate
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            if text:
                first, _, rest = text.partition(" ")
                if rest and first.isdigit():
                    return rest
                return text.splitlines()[0]
    return _read_display_name(directory)


def _entry(directory: Path, source: str) -> dict[str, Any]:
    return {
        "name": _read_display_name(directory) or read_version(directory) or directory.name,
        "path": str(directory),
        "version": read_version(directory) or directory.name,
        "source": source,
        "removable": source == "download",
    }


def candidates(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every Proton build the launcher can use, in priority order."""

    config = config or load_config()
    roots: list[tuple[Path, str]] = []

    for entry in config.get("proton_paths") or []:
        roots.append((Path(expand(str(entry))), "manual"))

    env_paths = os.environ.get("ZED_PROTON_PATH", "")
    for chunk in env_paths.split(os.pathsep):
        if chunk:
            roots.append((Path(chunk).expanduser(), "system"))

    for directory, source in compatibility_dirs():
        if not directory.is_dir():
            continue
        try:
            children = sorted(entry for entry in directory.iterdir() if entry.is_dir())
        except OSError:
            continue
        roots.extend((child, source) for child in children)

    seen: set[Path] = set()
    result: list[dict[str, Any]] = []
    for path, source in roots:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not path.is_dir() or not is_proton_dir(path):
            continue
        seen.add(resolved)
        result.append(_entry(path, source))
    return result


def sources(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = config or load_config()
    result = [
        {
            "path": str(path),
            "source": source,
            "exists": path.is_dir(),
        }
        for path, source in compatibility_dirs()
    ]
    result.extend(
        {"path": str(Path(expand(str(entry)))), "source": "manual", "exists": Path(expand(str(entry))).is_dir()}
        for entry in config.get("proton_paths") or []
    )
    return result


def find(tag: str, config: dict[str, Any] | None = None) -> str | None:
    config = config or load_config()
    available = candidates(config)
    if not tag:
        preferred = str(config.get("proton_default") or "")
        if preferred:
            for entry in available:
                if entry["path"] == preferred or entry["name"] == preferred:
                    return entry["path"]
        return available[0]["path"] if available else None

    expanded = expand(tag)
    if expanded and Path(expanded).is_dir():
        return expanded
    for entry in available:
        if entry["path"] == tag or entry["name"] == tag or entry["version"] == tag:
            return entry["path"]
    return None


def _api_base() -> str:
    return os.environ.get("ZED_GITHUB_API", DEFAULT_API).rstrip("/")


def _download_base() -> str:
    return os.environ.get("ZED_PROTON_DOWNLOAD_BASE", DEFAULT_DOWNLOAD_BASE).rstrip("/")


def _headers(config: dict[str, Any]) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "zed-launcher"}
    token = str(config.get("github_token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_releases(config: dict[str, Any] | None = None, limit: int = 30) -> list[dict[str, Any]]:
    config = config or load_config()
    url = f"{_api_base()}/repos/{GE_REPO}/releases"
    try:
        response = httpx.get(
            url,
            params={"per_page": max(1, min(limit, 100))},
            headers=_headers(config),
            timeout=20.0,
            follow_redirects=True,
        )
    except httpx.HTTPError as error:
        raise ProtonError(f"Could not reach GitHub: {error}") from error

    if response.status_code == 403:
        raise ProtonError(
            "GitHub rate limit reached. Add a GitHub API token in settings to raise the limit."
        )
    if response.status_code != 200:
        raise ProtonError(f"GitHub returned {response.status_code} for the release list")

    releases: list[dict[str, Any]] = []
    for item in response.json():
        if not isinstance(item, dict) or item.get("draft"):
            continue
        tag = str(item.get("tag_name") or "")
        if not tag:
            continue
        asset = next(
            (
                entry
                for entry in item.get("assets") or []
                if str(entry.get("name", "")).endswith("x86_64.tar.gz")
            ),
            None,
        )
        releases.append(
            {
                "tag": tag,
                "name": item.get("name") or tag,
                "published_at": item.get("published_at"),
                "prerelease": bool(item.get("prerelease")),
                "size": int(asset.get("size") or 0) if asset else 0,
                "url": asset.get("browser_download_url") if asset else download_url(tag),
            }
        )
    return releases


def download_url(tag: str) -> str:
    return f"{_download_base()}/{GE_REPO}/releases/download/{tag}/{tag}-x86_64.tar.gz"


_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _cleanup_jobs() -> None:
    cutoff = time.time() - JOB_RETENTION
    with _lock:
        stale = [
            job_id
            for job_id, job in _jobs.items()
            if job["status"] in ("done", "failed") and job["updated"] < cutoff
        ]
        for job_id in stale:
            _jobs.pop(job_id, None)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def list_jobs() -> list[dict[str, Any]]:
    with _lock:
        return [dict(job) for job in _jobs.values()]


def _update(job_id: str, **values: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.update(values)
        job["updated"] = time.time()


def _extract(archive: Path, target: Path) -> None:
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(archive) as tar:
            tar.extractall(tmp_path, filter="data")

        entries = [entry for entry in tmp_path.iterdir() if entry.name != "__MACOSX"]
        source = entries[0] if len(entries) == 1 and entries[0].is_dir() else tmp_path
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(source), str(target))


def _run_download(job_id: str, tag: str, url: str, config: dict[str, Any]) -> None:
    archive = download_root() / f".{tag}.tar.gz.part"
    target = download_root() / tag
    try:
        _update(job_id, status="downloading", url=url)
        with httpx.stream(
            "GET",
            url,
            headers={"User-Agent": "zed-launcher", **_headers(config)},
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, read=120.0),
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            _update(job_id, total=total)
            downloaded = 0
            started = time.monotonic()
            with archive.open("wb") as handle:
                for chunk in response.iter_bytes(1024 * 256):
                    if _cancelled(job_id):
                        raise _Cancelled
                    handle.write(chunk)
                    downloaded += len(chunk)
                    elapsed = max(0.001, time.monotonic() - started)
                    rate = downloaded / elapsed
                    eta = int((total - downloaded) / rate) if total and rate else None
                    _update(job_id, downloaded=downloaded, rate=rate, eta=eta)

        if _cancelled(job_id):
            raise _Cancelled

        _update(job_id, status="extracting", rate=0.0, eta=None)
        _extract(archive, target)
        archive.unlink(missing_ok=True)
        if not is_proton_dir(target):
            shutil.rmtree(target, ignore_errors=True)
            raise ProtonError(
                "The downloaded archive does not look like a Proton build (no proton script or wine binary)"
            )
        _update(job_id, status="done", path=str(target), rate=0.0, eta=None)
    except _Cancelled:
        with contextlib.suppress(OSError):
            archive.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            if target.exists():
                shutil.rmtree(target)
        _update(job_id, status="failed", error="Download cancelled", rate=0.0, eta=None)
    except (httpx.HTTPError, tarfile.TarError, OSError, ValueError, ProtonError) as error:
        with contextlib.suppress(OSError):
            archive.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            if target.exists():
                shutil.rmtree(target)
        _update(job_id, status="failed", error=f"{type(error).__name__}: {error}")


def start_download(
    tag: str, config: dict[str, Any] | None = None, url: str | None = None
) -> dict[str, Any]:
    tag = tag.strip()
    if not tag or "/" in tag or ".." in tag:
        raise ProtonError(f"Invalid release tag: {tag}")
    config = config or load_config()
    target = download_root() / tag
    if target.exists():
        raise ProtonError(f"{tag} is already installed")

    active = [
        job
        for job in list_jobs()
        if job["tag"] == tag and job["status"] not in ("done", "failed")
    ]
    if active:
        return active[0]

    _cleanup_jobs()
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "tag": tag,
            "status": "queued",
            "downloaded": 0,
            "total": 0,
            "rate": 0.0,
            "eta": None,
            "path": "",
            "error": "",
            "cancel": False,
            "updated": time.time(),
        }
    thread = threading.Thread(
        target=_run_download,
        args=(job_id, tag, url or download_url(tag), config),
        name=f"proton-{tag}",
        daemon=True,
    )
    thread.start()
    job = get_job(job_id)
    assert job is not None
    return job


def directory_size(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def installed_tags(config: dict[str, Any] | None = None) -> set[str]:
    root = download_root()
    if not root.is_dir():
        return set()
    return {entry.name for entry in root.iterdir() if entry.is_dir() and is_proton_dir(entry)}


def remove_build(path: str) -> bool:
    target = Path(expand(path))
    root = download_root().resolve()
    try:
        resolved = target.resolve()
    except OSError:
        return False
    if root not in resolved.parents:
        raise ProtonError("Only Proton builds downloaded by Zed Launcher can be removed")
    if not target.is_dir():
        return False

    from .. import store

    for game in store.list_games():
        game_proton = str(game.get("proton_path") or "")
        if game_proton and Path(expand(game_proton)).resolve() == resolved:
            raise ProtonError(f"{target.name} is still used by {game['title']}")

    shutil.rmtree(target)
    return True
