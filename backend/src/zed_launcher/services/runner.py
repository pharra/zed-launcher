from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .. import store
from ..config import load_config
from ..paths import ensure_dirs, log_dir
from . import diagnose, notify
from .command import LaunchPlan, ProgramRun
from .gameenv import game_env


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

        env = game_env(plan.env)

        early: list[str] = []

        def note(line: str) -> None:
            early.append(line)
            with contextlib.suppress(OSError), open(log_path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")

        async def start_program(program: ProgramRun) -> None:
            if program.delay:
                await asyncio.sleep(program.delay)
            try:
                await asyncio.create_subprocess_exec(
                    *program.argv,
                    cwd=plan.cwd,
                    env=env,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError as error:
                note(f"# could not start {program.path}: {error}")
                return
            note(f"# started extra program: {program.path}")

        for program in plan.programs_before:
            await start_program(program)

        if plan.pre_launch:
            pre = await asyncio.create_subprocess_shell(
                plan.pre_launch,
                env=env,
                cwd=plan.cwd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await pre.wait()

        try:
            process = await asyncio.create_subprocess_exec(
                *plan.argv,
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
            argv=plan.argv,
            process=process,
            started_monotonic=time.monotonic(),
            log_path=log_path,
        )
        run.lines.extend(early)
        if logs:
            run.log_handle = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        self._runs[run_id] = run
        store.set_run_status(run_id, "running")
        store.set_run_pid(run_id, process.pid)
        await self._spawn_watcher(run_id, game["id"], process.pid)
        self._broadcast(run, {"type": "status", "status": "running", "pid": process.pid})
        self._append(run, f"$ {plan.description}")
        for note in plan.notes:
            self._append(run, f"# {note}")

        run.pump_task = asyncio.create_task(self._pump(run))
        run.wait_task = asyncio.create_task(self._wait(run, plan))
        for program in plan.programs_after:
            asyncio.create_task(self._start_program_later(run, program, env, plan.cwd))
        return run

    async def _start_program_later(
        self, run: RunningGame, program: ProgramRun, env: dict[str, str], cwd: str | None
    ) -> None:
        if program.delay:
            await asyncio.sleep(program.delay)
        await self._start_program(run, program, env, cwd)

    async def _start_program(
        self, run: RunningGame, program: ProgramRun, env: dict[str, str], cwd: str | None
    ) -> None:
        """Extra programs run detached in the same prefix; failures never kill the game."""

        try:
            await asyncio.create_subprocess_exec(
                *program.argv,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            self._append(run, f"# could not start {program.path}: {error}")
            return
        self._append(run, f"# started extra program: {program.path}")

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
            env = game_env(plan.env)
            env.update(plan.env)
            with contextlib.suppress(Exception):
                post = await asyncio.create_subprocess_shell(
                    plan.post_launch,
                    env=env,
                    cwd=plan.cwd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await post.wait()

    async def stop(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if run is None or run.process.returncode is not None:
            return False
        run.stopped = True
        run.status = "stopping"
        self._broadcast(run, {"type": "status", "status": "stopping"})
        try:
            os.killpg(run.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return False
        try:
            await asyncio.wait_for(run.process.wait(), timeout=5)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(run.process.pid, signal.SIGKILL)
            await run.process.wait()
        return True
