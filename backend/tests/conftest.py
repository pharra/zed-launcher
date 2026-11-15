from __future__ import annotations

import os
from pathlib import Path

import pytest

from zed_launcher import store


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    (home / "Games").mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ZED_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ZED_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ZED_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ZED_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("ZED_TOKEN", "test-token")
    monkeypatch.delenv("ZED_UMU_RUN", raising=False)
    monkeypatch.delenv("ZED_PROTON_PATH", raising=False)
    monkeypatch.delenv("ZED_GITHUB_API", raising=False)
    monkeypatch.delenv("ZED_PROTON_DOWNLOAD_BASE", raising=False)
    for path in ("config", "data", "state", "cache"):
        (tmp_path / path).mkdir()
    store.init_db(str(home / "Games" / "Zed"))
    return home


@pytest.fixture()
def executable(tmp_path: Path) -> Path:
    path = tmp_path / "game.exe"
    path.write_text("MZ fake", encoding="utf-8")
    return path


@pytest.fixture()
def umu_run(tmp_path: Path) -> Path:
    path = tmp_path / "umu-run"
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture()
def proton_dir(tmp_path: Path) -> Path:
    path = tmp_path / "GE-Proton9-1"
    (path / "files/bin").mkdir(parents=True)
    (path / "proton").write_text("", encoding="utf-8")
    (path / "files/bin/wine").write_text("", encoding="utf-8")
    (path / "version").write_text("GE-Proton9-1\n", encoding="utf-8")
    return path


@pytest.fixture()
def wine_prefix(tmp_path: Path) -> Path:
    path = tmp_path / "existing-prefix"
    (path / "drive_c").mkdir(parents=True)
    (path / "system.reg").write_text("", encoding="utf-8")
    return path


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("ZED_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def no_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nix builders may export proxy variables; local test servers must stay direct."""

    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    ):
        monkeypatch.delenv(key, raising=False)
