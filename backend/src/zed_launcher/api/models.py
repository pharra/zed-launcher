from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtraProgram(BaseModel):
    """One entry of the launch sequence; ``kind == "game"`` marks the game itself."""

    kind: Literal["game", "program"] = "program"
    path: str = ""
    args: str = ""
    delay: int = Field(default=0, ge=0, le=600)


class GameToggles(BaseModel):
    mangohud: bool = False
    gamemode: bool = False
    gamescope: bool = False
    kwin: bool = False
    no_sleep: bool = False
    sdl: bool = False
    wayland: bool = False
    wow64: bool = False


class GameCreate(GameToggles):
    mode: Literal["create", "add"] = "create"
    install_id: str = ""
    title: str | None = None
    path: str = Field(min_length=1)
    prefix_name: str = ""
    prefix_path: str = ""
    proton_path: str = ""
    args: str = ""
    launch_args: str = ""
    env: str = ""
    extra_programs: list[ExtraProgram] = []
    mount_dirs: list[str] = []
    working_dir: str = ""
    pre_launch: str = ""
    post_launch: str = ""
    cover: str = ""
    icon: str = ""
    gamescope_args: str = ""
    kwin_args: str = ""
    mangohud_args: str = ""


class GamePatch(BaseModel):
    title: str | None = None
    path: str | None = None
    prefix_path: str | None = None
    proton_path: str | None = None
    args: str | None = None
    launch_args: str | None = None
    env: str | None = None
    extra_programs: list[ExtraProgram] | None = None
    mount_dirs: list[str] | None = None
    working_dir: str | None = None
    pre_launch: str | None = None
    post_launch: str | None = None
    cover: str | None = None
    icon: str | None = None
    mangohud: bool | None = None
    gamemode: bool | None = None
    gamescope: bool | None = None
    kwin: bool | None = None
    gamescope_args: str | None = None
    kwin_args: str | None = None
    mangohud_args: str | None = None
    no_sleep: bool | None = None
    sdl: bool | None = None
    wayland: bool | None = None
    wow64: bool | None = None


class SettingsPatch(BaseModel):
    prefix_root: str | None = None
    backup_dir: str | None = None
    backup_schedule: str | None = None
    language: str | None = None
    proton_paths: list[str] | None = None
    proton_default: str | None = None
    github_token: str | None = None
    steamgriddb_api_key: str | None = None
    notifications: bool | None = None
    tray: bool | None = None
    umu_run: str | None = None
    tool_paths: dict[str, str] | None = None
    confirm_kill: bool | None = None
    proton_log: bool | None = None


class ArtworkRequest(BaseModel):
    path: str = Field(min_length=1)


class ProtonPathRequest(BaseModel):
    path: str = Field(min_length=1)


class ProtonDownloadRequest(BaseModel):
    tag: str = Field(min_length=1)
    url: str = ""


class ProtonRemoveRequest(BaseModel):
    path: str = Field(min_length=1)


class BackupRequest(BaseModel):
    destination: str = ""
    include_artwork: bool = True
    include_saves: bool = False


class RestoreRequest(BaseModel):
    path: str = Field(min_length=1)


class SgdbCoverRequest(BaseModel):
    url: str = Field(min_length=1)


class InstallerRunRequest(BaseModel):
    installer: str = Field(min_length=1)
    title: str = ""
    prefix_name: str = ""
    prefix_path: str = ""
    proton_path: str = ""
    args: str = ""


class PrefixCleanupRequest(BaseModel):
    path: str = Field(min_length=1)


class PrefixCloneRequest(BaseModel):
    path: str = Field(min_length=1)
    name: str = ""


class PrefixScanRequest(BaseModel):
    path: str = Field(min_length=1)


class PrefixToolRequest(BaseModel):
    prefix_path: str = Field(min_length=1)
    kind: Literal["winecfg", "regedit", "winetricks", "exe"]
    proton_path: str = ""
    target: str = ""
    args: str = ""
    env: str = ""
