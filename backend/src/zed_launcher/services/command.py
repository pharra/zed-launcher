from __future__ import annotations

import re
import shlex
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProgramRun:
    """An extra program started around the game, in the same prefix."""

    argv: list[str]
    path: str
    delay: int = 0


@dataclass(frozen=True)
class LaunchPlan:
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    pre_launch: str = ""
    post_launch: str = ""
    description: str = ""
    notes: list[str] = field(default_factory=list)
    programs_before: list[ProgramRun] = field(default_factory=list)
    programs_after: list[ProgramRun] = field(default_factory=list)
    drop_env_prefixes: tuple[str, ...] = ()


GAME_ENTRY = {"kind": "game"}


def normalize_programs(entries: Any, game_path: str) -> list[dict[str, Any]]:
    """Validate the ordered launch sequence and make sure the game appears once.

    The game row is authoritative: its path always comes from the game record, so
    the UI shows it read-only and the stored value cannot drift.
    """

    sequence: list[dict[str, Any]] = []
    seen_game = False
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "program")
        if kind == "game":
            if seen_game:
                continue
            seen_game = True
            sequence.append(dict(GAME_ENTRY, path=game_path, args="", delay=0))
            continue
        path = str(entry.get("path") or "").strip()
        if not path:
            continue
        delay = entry.get("delay", 0)
        try:
            delay = max(0, min(int(delay), 600))
        except (TypeError, ValueError):
            delay = 0
        sequence.append(
            {
                "kind": "program",
                "path": path,
                "args": str(entry.get("args") or "").strip(),
                "delay": delay,
            }
        )

    if not seen_game:
        sequence.append(dict(GAME_ENTRY, path=game_path, args="", delay=0))
    return sequence


def split_programs(sequence: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Programs to start before the game and after it, in launch order."""

    for index, entry in enumerate(sequence):
        if entry.get("kind") == "game":
            return sequence[:index], sequence[index + 1 :]
    return sequence, []


def umu_game_id(game_id: str) -> str:
    checksum = zlib.crc32(game_id.encode()) & 0xFFFFFFFF
    return f"umu-zed{checksum:08x}"


ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_env(value: str) -> dict[str, str]:
    """Read ``KEY=VALUE`` lines (one per line, ``export`` allowed, # comments skipped)."""

    env: dict[str, str] = {}
    for raw in str(value or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, separator, rest = line.partition("=")
        key = key.strip()
        if not separator or not ENV_KEY.match(key):
            raise PlanError(f"Invalid environment variable line: {raw.strip()}")
        env[key] = rest.strip().strip('"').strip("'")
    return env


def legacy_launch_args(value: str) -> tuple[str, str]:
    """Split old-style mixed ``launch_args`` into (env lines, argv)."""

    env_lines: list[str] = []
    argv: list[str] = []
    for token in shlex.split(value or ""):
        key, separator, rest = token.partition("=")
        if separator and ENV_KEY.match(key):
            env_lines.append(f"{key}={rest}")
        else:
            argv.append(token)
    return "\n".join(env_lines), " ".join(argv)


def build_plan(
    game: dict[str, Any],
    *,
    prefix_path: str,
    proton_path: str | None,
    available: dict[str, str | None],
    config: dict[str, Any],
    log_dir: str,
    logs: bool = True,
    notes: list[str] | None = None,
) -> LaunchPlan:
    path = str(game.get("path") or "")
    if not Path(path).is_file():
        raise PlanError(f"Game executable not found: {path}")

    umu_run = available.get("umu_run")
    if not umu_run:
        raise PlanError("umu-run was not found. Install umu-launcher or set its path in settings.")
    if not proton_path:
        raise PlanError("No Proton build found. Add one in the Proton manager or install proton-ge-bin.")
    if not prefix_path:
        raise PlanError("This game has no Wine prefix.")

    game_args = shlex.split(str(game.get("args") or ""))
    env_override = parse_env(str(game.get("env") or ""))
    legacy_env, legacy_argv = legacy_launch_args(str(game.get("launch_args") or ""))

    # umu-run takes the executable as its first argument: anything in front of it
    # would be mistaken for the exe ("Executable not found: --some-flag"), so the
    # old launcher-argument tokens are replayed after the executable instead.
    leftover = shlex.split(legacy_argv)
    notes_extra: list[str] = []
    if leftover:
        game_args = [*leftover, *game_args]
        notes_extra.append(
            "umu-run does not accept arguments before the executable, so the old "
            f"launcher arguments ({legacy_argv}) are now passed to the game."
        )

    env: dict[str, str] = {}
    if legacy_env:
        env.update(parse_env(legacy_env))
    env.update(env_override)
    env.update(
        {
            "WINEPREFIX": prefix_path,
            "PROTONPATH": proton_path,
            "GAMEID": umu_game_id(game.get("id", "")),
        }
    )
    if logs:
        env["UMU_LOG"] = "1"
        env["PROTON_LOG_DIR"] = log_dir
        if config.get("proton_log"):
            env["PROTON_LOG"] = "1"
    if game.get("sdl"):
        env["PROTON_PREFER_SDL"] = "1"
    if game.get("wayland"):
        env["PROTON_ENABLE_WAYLAND"] = "1"
    if game.get("wow64"):
        env["PROTON_USE_WOW64"] = "1"

    wrappers: list[str] = []
    if game.get("no_sleep") and available.get("systemd_inhibit"):
        wrappers.extend(
            [
                str(available["systemd_inhibit"]),
                "--what=sleep:idle",
                "--why=Zed Launcher is running a game",
                "--",
            ]
        )
    if game.get("gamemode") and available.get("gamemoderun"):
        wrappers.append(str(available["gamemoderun"]))
    if game.get("gamescope") and available.get("gamescope"):
        raw = str(game.get("gamescope_args") or "").strip()
        if not raw:
            raw = str(config.get("gamescope_args") or "-f")
        wrappers.extend([str(available["gamescope"]), *shlex.split(raw), "--"])
    if game.get("mangohud") and available.get("mangohud"):
        wrappers.append(str(available["mangohud"]))
        wrappers.extend(shlex.split(str(game.get("mangohud_args") or "")))

    sequence = normalize_programs(game.get("extra_programs"), path)
    before, after = split_programs(sequence)

    def program_run(entry: dict[str, Any]) -> ProgramRun:
        extra_args = shlex.split(str(entry.get("args") or ""))
        return ProgramRun(
            argv=[umu_run, str(entry["path"]), *extra_args],
            path=str(entry["path"]),
            delay=int(entry.get("delay") or 0),
        )

    programs_before = [program_run(entry) for entry in before]
    programs_after = [program_run(entry) for entry in after]
    missing = [entry["path"] for entry in [*before, *after] if not Path(entry["path"]).is_file()]
    if missing:
        notes_extra.append(
            "These extra programs do not exist and were skipped: " + ", ".join(missing)
        )
    programs_before = [run for run in programs_before if Path(run.path).is_file()]
    programs_after = [run for run in programs_after if Path(run.path).is_file()]

    argv = [*wrappers, umu_run, path, *game_args]

    cwd = str(game.get("working_dir") or "") or str(Path(path).parent)

    return LaunchPlan(
        argv=argv,
        env=env,
        cwd=cwd,
        pre_launch=str(game.get("pre_launch") or ""),
        post_launch=str(game.get("post_launch") or ""),
        description=" ".join(shlex.quote(part) for part in argv),
        notes=[*notes_extra, *(notes or [])],
        programs_before=programs_before,
        programs_after=programs_after,
    )


# Layout of the builtin Windows tools inside a Proton build. GE-Proton and the
# Steam builds use files/, older ones dist/.
PROTON_WINE_DIRS = (
    "files/lib/wine/x86_64-windows",
    "files/lib/wine/i386-windows",
    "dist/lib/wine/x86_64-windows",
    "dist/lib/wine/i386-windows",
)


def wine_program(proton_path: str, name: str) -> str | None:
    """Absolute path of a builtin tool (reg, regedit, winecfg) shipped with Proton.

    Passing the real executable keeps umu on its "execute this file" path; a bare
    name like ``regedit`` makes Proton warn "Executable not found" and fall back to
    whatever the prefix happens to contain. Console tools such as ``reg.exe`` are
    avoided for imports: wineconsole keeps its window open after the program ends.
    """

    for directory in PROTON_WINE_DIRS:
        candidate = Path(proton_path) / directory / f"{name}.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def to_windows_path(path: str) -> str:
    """Wine programs need a DOS path; Z: is the host root inside the prefix."""

    return "Z:" + str(Path(path).expanduser()).replace("/", "\\")


# C keeps Proton from generating locales inside the container on every run.
TOOL_DEFAULT_ENV = {"LANG": "C", "LC_ALL": "C"}


def build_tool_plan(
    *,
    kind: str,
    prefix_path: str,
    proton_path: str | None,
    umu_run: str | None,
    target: str = "",
    args: str = "",
    log_dir: str = "",
    env: str = "",
) -> LaunchPlan:
    """Run a maintenance tool inside a prefix (winecfg, regedit, winetricks, exe)."""

    if not umu_run:
        raise PlanError("umu-run was not found. Install umu-launcher or set its path in settings.")
    if not proton_path:
        raise PlanError("No Proton build found. Add one in the Proton manager.")
    if not prefix_path:
        raise PlanError("This prefix is missing.")

    extra = shlex.split(args or "")
    tool_env: dict[str, str] = dict(TOOL_DEFAULT_ENV)
    tool_env.update(parse_env(env))
    tool_env.update(
        {
            "WINEPREFIX": prefix_path,
            "PROTONPATH": proton_path,
            "GAMEID": "zed-prefix-tools",
            "STORE": "none",
            "PROTON_LOG": "1",
        }
    )
    if log_dir:
        tool_env["PROTON_LOG_DIR"] = log_dir

    def builtin(name: str) -> str:
        return wine_program(proton_path, name) or name

    if kind == "winecfg":
        argv = [umu_run, builtin("winecfg"), *extra]
    elif kind == "regedit":
        if not target:
            raise PlanError("Choose a .reg file to import.")
        if not Path(target).is_file():
            raise PlanError(f"Registry file not found: {target}")
        argv = [umu_run, builtin("regedit"), "/S", to_windows_path(target), *extra]
    elif kind == "winetricks":
        if not extra:
            raise PlanError("Add at least one winetricks verb, for example `vcrun2022`.")
        argv = [umu_run, "winetricks", *extra]
    elif kind == "exe":
        if not Path(target).is_file():
            raise PlanError(f"File not found: {target}")
        if Path(target).suffix.lower() == ".reg":
            # Picking a .reg in the file picker means "import it", not "execute it".
            argv = [umu_run, builtin("regedit"), "/S", to_windows_path(target), *extra]
        else:
            argv = [umu_run, target, *extra]
    else:
        raise PlanError(f"Unknown prefix tool: {kind}")

    cwd = str(Path(target).parent) if target and Path(target).parent.is_dir() else None
    return LaunchPlan(
        argv=argv,
        env=tool_env,
        # The session locale would make pressure-vessel regenerate en_US/zh_CN inside
        # the container on every tool run; LANG/LC_ALL from the editor still apply.
        drop_env_prefixes=("LC_",),
        cwd=cwd,
        description=" ".join(shlex.quote(part) for part in argv),
    )


def build_installer_plan(
    *,
    installer: str,
    title: str,
    prefix_path: str,
    proton_path: str | None,
    umu_run: str | None,
    args: str = "",
    log_dir: str = "",
) -> LaunchPlan:
    """Run an installer inside a fresh prefix."""

    if not Path(installer).is_file():
        raise PlanError(f"Installer not found: {installer}")
    if not umu_run:
        raise PlanError("umu-run was not found. Install umu-launcher or set its path in settings.")
    if not proton_path:
        raise PlanError("No Proton build found. Add one in the Proton manager.")

    env = {
        "WINEPREFIX": prefix_path,
        "PROTONPATH": proton_path,
        "GAMEID": umu_game_id(f"installer-{title or Path(installer).stem}"),
        "PROTON_LOG": "1",
    }
    if log_dir:
        env["PROTON_LOG_DIR"] = log_dir

    extra = shlex.split(args or "")
    argv = [umu_run, installer, *extra]
    return LaunchPlan(
        argv=argv,
        env=env,
        cwd=str(Path(installer).parent),
        description=" ".join(shlex.quote(part) for part in argv),
    )
