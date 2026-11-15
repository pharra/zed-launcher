from __future__ import annotations

import os
import re
import shlex
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class LaunchPlan:
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    pre_launch: str = ""
    post_launch: str = ""
    description: str = ""
    notes: list[str] = field(default_factory=list)
    drop_env_prefixes: tuple[str, ...] = ()
    # Batch file that starts every program inside one umu-run/pressure-vessel.
    script: str = ""
    # Shell wrapper that becomes the single program of a nested compositor session.
    session_script: str = ""
    # Human-readable launch order, used in the log.
    order: list[str] = field(default_factory=list)


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


def split_args(value: str) -> list[str]:
    """Split a typed argument line without eating Windows backslashes.

    ``shlex.split`` in POSIX mode treats ``\\`` as an escape, so ``-path C:\\Games``
    would reach wine as ``C:Games``. Quote-aware splitting keeps the argument intact.
    """

    lexer = shlex.shlex(value or "", posix=False)
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = list(lexer)
    return [
        token[1:-1] if len(token) > 1 and token[0] == token[-1] and token[0] in "\"'" else token
        for token in tokens
    ]


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


SCRIPT_TOKEN = "__ZED_REPLACE_ME__"
SESSION_TOKEN = "__ZED_SESSION_SCRIPT__"

# pressure-vessel shows the container only the paths a game needs: the executable's own
# directory, the prefix and Proton. A program living elsewhere (a deck tracker on another
# disk) is therefore invisible and wine's `start` fails without a word. This variable
# asks pressure-vessel to bind those directories into the container.
MOUNT_ENV = "PRESSURE_VESSEL_FILESYSTEMS_RW"


# Every row is launched with a plain `start ""`, which returns at once: Proton keeps the
# session (and therefore the container) alive until the wine processes end, so no /wait
# is needed and the rows after the game start as soon as the game is up.
def _win(path: str) -> str:
    """DOS path with forward slashes: wine accepts them and `start` handles them best."""

    return 'z:/' + str(path).lstrip("/")


def _quote(argument: str) -> str:
    return f'"{argument}"' if " " in argument else argument


def _start(program: str, args: list[str]) -> str:
    """One `start` line, in the same shape Faugus generates.

    Wine's `start` is happiest with forward slashes and an always-quoted path;
    `start "" /d <unquoted dir>` silently did nothing for the first row, which is
    how Hearthstone Deck Tracker ended up never launching.
    """

    return " ".join(['start ""', f'"{_win(program)}"', *map(_quote, args)])


def build_launch_script(
    game_path: str,
    game_args: list[str],
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """A .bat that starts every program inside one wine session.

    Returns the script and the launch order, so the log can show what will run.
    """

    lines = ["@echo off"]
    order: list[str] = []

    def wait(seconds: int) -> None:
        if seconds <= 0:
            return
        # ping is the only sleep available in a bare cmd, and -n counts one send too.
        lines.append(f"ping -n {seconds + 1} 127.0.0.1 >nul")

    for entry in before:
        wait(int(entry.get("delay") or 0))
        args = split_args(str(entry.get("args") or ""))
        lines.append(_start(str(entry["path"]), args))
        order.append(str(entry["path"]))

    lines.append(_start(game_path, game_args))
    order.append(game_path)

    for entry in after:
        wait(int(entry.get("delay") or 0))
        args = split_args(str(entry.get("args") or ""))
        lines.append(_start(str(entry["path"]), args))
        order.append(str(entry["path"]))

    lines.extend(["exit", ""])
    return "\r\n".join(lines), order


# A nested KWin session: windowed, with Xwayland so wine can talk to it, and without the
# Plasma desktop pieces a game does not need. KWin keeps _NET_WM_STATE_ABOVE working, which
# is what always-on-top overlays (deck trackers, chat clients) need and gamescope ignores.
KWIN_ARGS = "--width 1600 --height 900 --xwayland --no-lockscreen --no-global-shortcuts"


def kwin_prefix(binary: str, raw: str, environ: Mapping[str, str]) -> list[str]:
    """The KWin arguments in front of the command that runs inside its session."""

    argv = [binary, *(shlex.split(raw.strip() or KWIN_ARGS))]
    # Nesting into an X11 session needs the parent display; under Wayland KWin finds it.
    if not environ.get("WAYLAND_DISPLAY") and environ.get("DISPLAY"):
        argv.extend(["--x11-display", str(environ["DISPLAY"])])
    return [*argv, "--exit-with-session"]


def normalize_mount_dirs(value: Any) -> list[str]:
    """Validate the directories a game wants inside its container.

    They are absolute host paths that pressure-vessel binds read-write, so a typo has
    to be reported when the game is saved rather than swallowed at launch.
    """

    candidates = value.splitlines() if isinstance(value, str) else list(value or [])
    result: list[str] = []
    for raw in candidates:
        text = str(raw).strip()
        if not text:
            continue
        path = Path(text).expanduser()
        if not path.is_absolute():
            raise PlanError(f"Container directories must be absolute paths: {text}")
        if not path.is_dir():
            raise PlanError(f"Container directory does not exist: {text}")
        if str(path) not in result:
            result.append(str(path))
    return result


def mount_list(existing: str, entries: Iterable[str]) -> str:
    """Colon-separated directories for the container, keeping anyone else's values."""

    merged = [part for part in existing.split(":") if part]
    for entry in entries:
        if entry and entry not in merged:
            merged.append(entry)
    return ":".join(merged)


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
    if game.get("kwin") and game.get("gamescope"):
        raise PlanError(
            "Gamescope and KWin both compose the game session, so only one can be enabled."
        )

    game_args = split_args(str(game.get("args") or ""))
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

    # Wrappers that belong inside the game session.
    inner: list[str] = []
    # Wrappers that have to stay outside of it (the sleep inhibitor must cover it all).
    outer: list[str] = []
    if game.get("no_sleep") and available.get("systemd_inhibit"):
        outer.extend(
            [
                str(available["systemd_inhibit"]),
                "--what=sleep:idle",
                "--why=Zed Launcher is running a game",
                "--",
            ]
        )
    kwin_argv: list[str] = []
    if game.get("kwin"):
        session = available.get("kwin_session") or {}
        if session and not session.get("supported", True):
            raise PlanError(
                "The current compositor does not offer wp_single_pixel_buffer_manager_v1, so a "
                "nested KWin session cannot open a window. Run the desktop session under KWin, "
                "or turn KWin off for this game."
            )
        # Qt takes the KDE/portal platform theme from the session, and that theme plugin
        # segfaults inside kwin_wayland before it can open a window (seen with
        # QT_QPA_PLATFORMTHEME=xdgdesktopportal on a KDE-flavoured session).
        env.setdefault("QT_QPA_PLATFORMTHEME", "generic")
        # kwin logs to the systemd journal, which would leave this log empty.
        env.setdefault("QT_FORCE_STDERR_LOGGING", "1")
        if available.get("kwin"):
            kwin_argv = kwin_prefix(
                str(available["kwin"]), str(game.get("kwin_args") or ""), os.environ
            )
    if game.get("gamemode") and available.get("gamemoderun"):
        inner.append(str(available["gamemoderun"]))
    if game.get("gamescope") and available.get("gamescope"):
        raw = str(game.get("gamescope_args") or "").strip()
        if not raw:
            raw = str(config.get("gamescope_args") or "-f")
        inner.extend([str(available["gamescope"]), *shlex.split(raw), "--"])
    if game.get("mangohud") and available.get("mangohud"):
        inner.append(str(available["mangohud"]))
        inner.extend(shlex.split(str(game.get("mangohud_args") or "")))

    sequence = normalize_programs(game.get("extra_programs"), path)
    before, after = split_programs(sequence)

    missing = [entry["path"] for entry in [*before, *after] if not Path(entry["path"]).is_file()]
    if missing:
        notes_extra.append(
            "These extra programs do not exist and were skipped: " + ", ".join(missing)
        )
    before = [entry for entry in before if Path(entry["path"]).is_file()]
    after = [entry for entry in after if Path(entry["path"]).is_file()]

    # Everything runs inside one umu-run call: a batch file starts the extras and then
    # the game, so they share one pressure-vessel container and one wineserver. Separate
    # umu-run calls would each get their own /tmp (and therefore their own wineserver).
    script = ""
    order: list[str] = []
    folders: list[str] = []
    if before or after:
        script, order = build_launch_script(path, game_args, before, after)
        # Hand the .bat to umu-run as the executable (Faugus does the same). Wine runs a
        # batch file through the shell without allocating a console, which is why no cmd
        # window shows up; `cmd.exe /c script` would open one.
        argv = [*inner, umu_run, SCRIPT_TOKEN]
        # The container only sees the target executable's directory, so every program the
        # script starts from somewhere else has to be mounted explicitly.
        folders.extend(str(Path(part).parent) for part in order)
    else:
        argv = [*inner, umu_run, path, *game_args]

    # Directories the user added by hand, for programs and data living outside the
    # directories above; a drive that went away is skipped with a note instead of failing.
    wanted = [str(entry) for entry in (game.get("mount_dirs") or [])]
    missing_dirs = [entry for entry in wanted if not Path(entry).is_dir()]
    if missing_dirs:
        notes_extra.append(
            "These container directories do not exist and were skipped: " + ", ".join(missing_dirs)
        )
    folders.extend(entry for entry in wanted if entry not in missing_dirs)
    if folders:
        env[MOUNT_ENV] = mount_list(env.get(MOUNT_ENV, ""), folders)
        notes_extra.append(f"{MOUNT_ENV}={env[MOUNT_ENV]}")

    cwd = str(game.get("working_dir") or "") or str(Path(path).parent)

    # kwin_wayland's --exit-with-session takes exactly one program, so the whole chain has to
    # be handed over as a single executable; a tiny sh wrapper keeps the quoting intact.
    session_script = ""
    if kwin_argv:
        session_script = "#!/bin/sh\nexec " + " ".join(shlex.quote(part) for part in argv) + "\n"
        argv = [*kwin_argv, SESSION_TOKEN]
    argv = [*outer, *argv]

    return LaunchPlan(
        argv=argv,
        script=script,
        session_script=session_script,
        order=order,
        env=env,
        cwd=cwd,
        pre_launch=str(game.get("pre_launch") or ""),
        post_launch=str(game.get("post_launch") or ""),
        description=" ".join(shlex.quote(part) for part in argv),
        notes=[*notes_extra, *(notes or [])],
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

    extra = split_args(args or "")
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
