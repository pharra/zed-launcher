from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from . import __version__, store
from .config import load_config
from .paths import ensure_dirs, log_dir, prune_proton_logs
from .services import prefixes, processes, proton, system
from .services.command import PlanError, build_plan
from .services.gameenv import game_env

# How long to keep draining the game's pipe after the process itself exited.
PIPE_DRAIN_TIMEOUT = 2.0


def _prepare() -> None:
    ensure_dirs()
    store.init_db(load_config().get("prefix_root"))
    for stale in store.prune_runs():
        with contextlib.suppress(OSError):
            Path(stale).unlink(missing_ok=True)
    prune_proton_logs()


def _plan_for(game_id: str, logs: bool = True):
    game = store.get_game(game_id)
    if game is None:
        raise SystemExit(f"Game not found: {game_id}")
    config = load_config()
    prefix_path = game.get("prefix_path") or ""
    try:
        prefixes.require_dir(prefix_path)
    except prefixes.PrefixError as error:
        raise PlanError(f"{error}. Create the game again or point it at a prefix in Edit.") from error
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
    return game, plan


def run_headless(game_id: str, logs: bool = True) -> int:
    _prepare()
    try:
        game, plan = _plan_for(game_id, logs=logs)
    except PlanError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    log_path = log_dir() / f"{game_id}-{int(time.time())}.log"
    record = store.create_run(game_id, str(log_path), status="starting")
    env = game_env(plan.env)
    env[processes.RUN_MARKER] = record["id"]
    if plan.env.get("WINEPREFIX"):
        Path(plan.env["WINEPREFIX"]).mkdir(parents=True, exist_ok=True)

    for program in plan.programs_before:
        subprocess.Popen(  # noqa: S603 - argv list, no shell
            program.argv,
            cwd=plan.cwd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        if program.delay:
            time.sleep(program.delay)

    if plan.pre_launch:
        subprocess.run(  # noqa: S602 - user supplied hook
            plan.pre_launch, shell=True, env=env, cwd=plan.cwd, check=False, start_new_session=True
        )

    print(f"$ {plan.description}", flush=True)
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            plan.argv,
            cwd=plan.cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except OSError as error:
        store.finish_run(record["id"], "failed", None, 0)
        print(f"error: could not start game: {error}", file=sys.stderr)
        return 2

    def spawn(program) -> None:
        with contextlib.suppress(OSError):
            subprocess.Popen(  # noqa: S603 - argv list, no shell
                program.argv,
                cwd=plan.cwd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

    for program in plan.programs_after:
        if program.delay:
            threading.Timer(program.delay, spawn, (program,)).start()
        else:
            spawn(program)

    with log_path.open("w", encoding="utf-8") as log:
        assert process.stdout is not None

        def pump() -> None:
            for line in process.stdout:  # type: ignore[union-attr]
                print(line, end="")
                log.write(line)
                log.flush()

        # A grandchild may inherit the pipe and keep it open after the game is gone, so
        # read in the background and never let the pipe decide when the run ends.
        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        exit_code = process.wait()
        reader.join(timeout=PIPE_DRAIN_TIMEOUT)

    duration = int(time.monotonic() - started)
    store.resolve_run(
        record["id"], "exited" if exit_code == 0 else "failed", exit_code, duration
    )
    # wineserver and friends survive the game in their own sessions.
    with contextlib.suppress(Exception):
        processes.terminate_run(str(record["id"]))
    if plan.post_launch:
        subprocess.run(  # noqa: S602 - user supplied hook
            plan.post_launch, shell=True, env=env, cwd=plan.cwd, check=False, start_new_session=True
        )
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zed-launcher", description="Zed Launcher")
    parser.add_argument("--version", action="store_true", help="show the version and exit")
    parser.add_argument("--serve", action="store_true", help="run the API/UI server only")
    parser.add_argument("--browser", action="store_true", help="open the UI in the default browser")
    parser.add_argument("--host", default="127.0.0.1", help="bind address for --serve")
    parser.add_argument("--port", type=int, default=8765, help="port for --serve")
    parser.add_argument("--token", default=None, help="API token (defaults to a random value)")
    parser.add_argument("--run", metavar="GAME_ID", help="launch a game without a window")
    parser.add_argument("--add", metavar="PATH", help="add a game from the command line")
    parser.add_argument("--title", default=None, help="title for --add")
    parser.add_argument(
        "--existing-prefix",
        default=None,
        help="attach --add to an existing Wine prefix instead of creating one",
    )
    parser.add_argument("--list", action="store_true", help="list games")
    parser.add_argument("--diagnostics", action="store_true", help="print diagnostics as JSON")

    args = parser.parse_args(argv)

    if args.version:
        print(f"zed-launcher {__version__}")
        return 0

    if args.run:
        return run_headless(args.run)

    if args.diagnostics:
        _prepare()
        print(json.dumps(system.diagnostics(), indent=2))
        return 0

    if args.list:
        _prepare()
        for game in store.list_games():
            print(f"{game['id']}\t{game['title']}\t{game['prefix_path']}\t{game['path']}")
        return 0

    if args.add:
        _prepare()
        path = Path(args.add).expanduser().resolve()
        if not path.is_file():
            print(f"error: file does not exist: {path}", file=sys.stderr)
            return 2
        config = load_config()
        title = args.title or path.stem
        if args.existing_prefix:
            try:
                prefix = prefixes.validate_prefix(args.existing_prefix)
            except prefixes.PrefixError as error:
                print(f"error: {error}", file=sys.stderr)
                return 2
        else:
            try:
                prefix = prefixes.create_prefix(config.get("prefix_root", ""), title)
            except prefixes.PrefixError as error:
                print(f"error: {error}", file=sys.stderr)
                return 2
        game = store.create_game(
            {
                "title": title,
                "path": str(path),
                "prefix_path": str(prefix),
                "owned_prefix": args.existing_prefix is None,
            }
        )
        print(game["id"])
        return 0

    if args.serve:
        from .server import serve_blocking

        serve_blocking(args.token, args.host, args.port)
        return 0

    from .server import start_server

    handle = start_server(args.token)

    def open_in_browser() -> int:
        webbrowser.open(handle.url)
        print(f"Zed Launcher: {handle.url}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            handle.stop()
        return 0

    if args.browser or os.environ.get("ZED_BROWSER") == "1":
        return open_in_browser()

    try:
        from .shell.window import run_window
    except ImportError:
        return open_in_browser()

    try:
        return run_window(handle.url, handle.token, keep_in_tray=load_config().get("tray", False))
    except (ImportError, ValueError, RuntimeError) as error:
        print(f"Could not open the GTK window ({error}); using the browser instead.", file=sys.stderr)
        return open_in_browser()
    finally:
        handle.stop()


if __name__ == "__main__":
    sys.exit(main())
