from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
import signal
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import store
from ..config import load_config
from ..paths import ensure_dirs, log_dir, script_dir
from . import diagnose, notify, processes
from .command import SCRIPT_TOKEN, LaunchPlan
from .gameenv import game_env

# How long to keep reading the game's pipe after the process itself exited.
PIPE_DRAIN_TIMEOUT = 2.0


@dataclass
class RunningGame:
    run_id: str
    game_id: str
    title: str
    status: str
    argv: list[str]
    process: asyncio.subprocess.Process
    started_monotonic: float
    log_path: str
    lines: deque[str] = field(default_factory=lambda: deque(maxlen=2000))
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    log_handle: Any = None
    pump_task: asyncio.Task[None] | None = None
    wait_task: asyncio.Task[None] | None = None
    stopped: bool = False

    def snapshot(self) -> dict[str, Any]:
        record = store.get_run(self.run_id)
        return {
            "run_id": self.run_id,
            "game_id": self.game_id,
            "title": self.title,
            "status": self.status,
            "argv": self.argv,
            "pid": self.process.pid if self.process.returncode is None else None,
            "started_at": record["started_at"] if record else None,
            "log_path": self.log_path,
            "lines": list(self.lines),
        }


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, RunningGame] = {}
        # asyncio only keeps a weak reference to a task, so an unreferenced task can be
        # garbage collected before it ever runs.
        self._tasks: set[asyncio.Task[Any]] = set()

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def get(self, run_id: str) -> RunningGame | None:
        return self._runs.get(run_id)

    def active(self) -> list[dict[str, Any]]:
        return [run.snapshot() for run in self._runs.values() if run.status in ("starting", "running")]

    def active_for(self, game_id: str) -> RunningGame | None:
        for run in self._runs.values():
            if run.game_id == game_id and run.status in ("starting", "running"):
                return run
        return None

    def subscribe(self, run: RunningGame) -> tuple[asyncio.Queue[dict[str, Any]], list[str], str]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=2000)
        run.subscribers.add(queue)
        return queue, list(run.lines), run.status

    def unsubscribe(self, run: RunningGame, queue: asyncio.Queue[dict[str, Any]]) -> None:
        run.subscribers.discard(queue)

    def _broadcast(self, run: RunningGame, event: dict[str, Any]) -> None:
        for queue in list(run.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                run.subscribers.discard(queue)

    def _append(self, run: RunningGame, line: str) -> None:
        run.lines.append(line)
        if run.log_handle is not None:
            with contextlib.suppress(OSError):
                run.log_handle.write(line + "\n")
                run.log_handle.flush()
        self._broadcast(run, {"type": "log", "line": line})

    async def start(self, game: dict[str, Any], plan: LaunchPlan, *, logs: bool = True) -> RunningGame:
        ensure_dirs()
        log_path = str(log_dir() / f"{game['id']}-{int(time.time())}.log")
        record = store.create_run(game["id"], log_path, status="starting")
        run_id = record["id"]

        env = game_env(plan.env, drop_prefixes=plan.drop_env_prefixes)
        env[processes.RUN_MARKER] = run_id

        early: list[str] = []

        def note(line: str) -> None:
            early.append(line)
            with contextlib.suppress(OSError), open(log_path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")

        argv = self._prepare_script(plan, run_id, note)

        if plan.pre_launch:
            pre = await asyncio.create_subprocess_shell(
                plan.pre_launch,
                env=env,
                cwd=plan.cwd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
            await pre.wait()

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=plan.cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as error:
            store.finish_run(run_id, "failed", None, 0)
            raise RuntimeError(f"Could not start game: {error}") from error

        run = RunningGame(
            run_id=run_id,
            game_id=game["id"],
            title=game.get("title", ""),
            status="running",
            argv=argv,
            process=process,
            started_monotonic=time.monotonic(),
            log_path=log_path,
        )
        run.lines.extend(early)
        if logs:
            run.log_handle = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        self._runs[run_id] = run
        store.set_run_status(run_id, "running")
        store.set_run_pid(run_id, process.pid, processes.starttime_of(process.pid))
        await self._spawn_watcher(run_id, game["id"], process.pid)
        self._broadcast(run, {"type": "status", "status": "running", "pid": process.pid})
        self._append(run, "$ " + " ".join(shlex.quote(part) for part in argv))
        for note in plan.notes:
            self._append(run, f"# {note}")

        run.pump_task = asyncio.create_task(self._pump(run))
        run.wait_task = asyncio.create_task(self._wait(run, plan))
        return run

    def _prepare_script(self, plan: LaunchPlan, run_id: str, note: Any) -> list[str]:
        """Write the launch script and point the command line at it.

        All programs of a run share one umu-run invocation (and therefore one
        pressure-vessel container): a batch file starts the extras around the game.
        """

        if not plan.script:
            return list(plan.argv)

        directory = script_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{run_id}.bat"
        try:
            path.write_text(plan.script, encoding="utf-8", newline="")
        except OSError as error:
            note(f"# could not write the launch script: {error}")
            return list(plan.argv)

        note(f"# launch script: {path}")
        if plan.order:
            note("# order: " + " -> ".join(Path(part).name for part in plan.order))
        return [part.replace(SCRIPT_TOKEN, str(path)) for part in plan.argv]

    async def _spawn_watcher(self, run_id: str, game_id: str, pid: int) -> None:
        """Keep recording the run even if the launcher window is closed."""

        with contextlib.suppress(OSError):
            await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "zed_launcher.watch",
                run_id,
                game_id,
                str(pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )

    async def _pump(self, run: RunningGame) -> None:
        assert run.process.stdout is not None
        while True:
            raw = await run.process.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip()
            if len(line) > 4000:
                line = line[:4000] + "…"
            self._append(run, line)

    async def _wait(self, run: RunningGame, plan: LaunchPlan) -> None:
        exit_code = await run.process.wait()
        if run.pump_task is not None:
            # A grandchild can inherit the pipe (wineserver, a game-launched daemon) and
            # keep it open long after the game is gone. Never wait for EOF forever.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(run.pump_task), timeout=PIPE_DRAIN_TIMEOUT)
            if not run.pump_task.done():
                run.pump_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await run.pump_task
        duration = int(time.monotonic() - run.started_monotonic)
        status = "stopped" if run.stopped else ("exited" if exit_code == 0 else "failed")
        run.status = status
        claimed = store.resolve_run(run.run_id, status, exit_code, duration)
        if run.log_handle is not None:
            with contextlib.suppress(OSError):
                run.log_handle.close()
            run.log_handle = None
        hints = diagnose.analyse(list(run.lines)) if status != "exited" else []
        self._broadcast(
            run,
            {
                "type": "exit",
                "status": status,
                "exit_code": exit_code,
                "duration": duration,
                "hints": hints,
            },
        )
        # wineserver keeps running for a while after the game and would otherwise be
        # inherited by the next launch; reap this run's leftovers in the background so
        # the exit is reported immediately.
        self._spawn(asyncio.to_thread(processes.terminate_run, run.run_id))
        config = load_config()
        if claimed and config.get("notifications", True):
            notify.notify_game_exit(
                run.title or "Game",
                status,
                duration,
                exit_code,
                language=config.get("language"),
            )
        if plan.post_launch:
            env = game_env(plan.env, drop_prefixes=plan.drop_env_prefixes)
            env.update(plan.env)
            with contextlib.suppress(Exception):
                post = await asyncio.create_subprocess_shell(
                    plan.post_launch,
                    env=env,
                    cwd=plan.cwd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=True,
                )
                await post.wait()

    async def stop(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if run is None or run.process.returncode is not None:
            return False
        run.stopped = True
        run.status = "stopping"
        self._broadcast(run, {"type": "status", "status": "stopping"})
        with contextlib.suppress(ProcessLookupError):
            os.killpg(run.process.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(run.process.wait(), timeout=5)
        except TimeoutError:
            # The pid may already be reaped and reused, so only signal the group while
            # the process still exists.
            if run.process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(run.process.pid, signal.SIGKILL)
            await run.process.wait()
        # wineserver, services.exe and the game itself call setsid(), so they are not in
        # the group that was just signalled: stop them by their run marker.
        await asyncio.to_thread(processes.terminate_run, run.run_id)
        return True
