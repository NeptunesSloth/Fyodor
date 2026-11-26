"""The tunnel's state: the loopback port cloudflared forwards to, the public hostname it was given, and the cloudflared process."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import platform
import socket
import subprocess
import sys
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

import httpx

from app.config import Settings
from app.tunnel import binary, process
from app.tunnel.binary import TunnelUnavailable

log = logging.getLogger(__name__)

TunnelState = Literal["stopped", "starting", "running", "failed"]
WENT_DOWN = "The internet link went down."
CANT_PREPARE = "The tunnel program couldn't be prepared in Fyodor's data folder. Check the folder can be written to and try again."
CANT_START = "The internet link couldn't be started on this computer."


class TunnelManager:
    """``port``: the tunnel port the launcher bound (127.0.0.1, chosen by the OS); None for a server the launcher didn't start
    (``uvicorn --factory``), which then has no tunnel port and cannot share. ``hostname``: the ``*.trycloudflare.com`` name while
    running (only ever set once it fullmatches process.QUICK_HOST). Requests that arrive on ``port`` are tunnel requests
    (app/api/deps.py is_tunnel_request). ``on_down``: called on the event loop when cloudflared exits while running (not on stop)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.port: int | None = None
        self.hostname: str | None = None
        self.state: TunnelState = "stopped"
        self.reason: str | None = None
        self.on_down: Callable[[], Awaitable[None]] | None = None
        self.folder = settings.data_dir / "tunnel"
        self.http_client: Callable[..., httpx.Client] = self._client
        self._lock = threading.Lock()  # _proc, _job, _gen, and state changes made off the loop
        self._binary_lock = threading.Lock()  # ensure_binary uses fixed .part names: one at a time
        self._proc: subprocess.Popen[bytes] | None = None
        self._job: int | None = None
        self._gen = 0  # bumped by stop(): a start still under way when it is stopped doesn't come back to life
        self._pending: asyncio.Task[str] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _client(self, **kwargs: Any) -> httpx.Client:
        return httpx.Client(headers={"User-Agent": self.settings.user_agent},
                            timeout=httpx.Timeout(60.0, connect=15.0), **kwargs)

    async def start(self) -> str:
        """The public hostname, starting cloudflared first unless it is running. A second call while starting awaits the first."""
        if self.state == "running" and self.hostname:
            return self.hostname
        if self._pending is None or self._pending.done():
            self.state, self.reason, self.hostname = "starting", None, None
            self._loop = asyncio.get_running_loop()
            self._pending = asyncio.ensure_future(self._start())
        return await asyncio.shield(self._pending)

    async def _start(self) -> str:
        assert self._loop is not None
        gen = self._gen
        try:
            return await self._loop.run_in_executor(None, self._launch, gen)
        except Exception as exc:
            with self._lock:
                if gen == self._gen:
                    self.state, self.hostname = "failed", None
                    self.reason = str(exc) if isinstance(exc, TunnelUnavailable) else CANT_START
            if not isinstance(exc, TunnelUnavailable):
                log.exception("The tunnel could not be started")
            raise

    def _executable(self) -> tuple[Path, Path]:
        """The verified cloudflared and the empty config file, in data_dir/tunnel. Never while a cloudflared runs (stopped first):
        on Windows os.replace can't overwrite a running program."""
        try:
            exe = binary.ensure_binary(self.folder, self.http_client, allow_network=self.settings.allow_network)
            asset = binary.asset_for(platform.system(), platform.machine())
            if asset is None or not binary.verify(exe, asset):  # checked again just before it is run
                raise TunnelUnavailable("The tunnel program didn't match the expected checksum, so it wasn't used.")
            config = self.folder / "empty.yml"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_bytes(b"")
        except OSError as exc:
            raise TunnelUnavailable(CANT_PREPARE) from exc
        return exe, config

    def _launch(self, gen: int) -> str:
        if self.port is None:
            raise TunnelUnavailable("Sharing over the internet needs Fyodor started from its launcher.")
        self._end(*self._take())  # a cloudflared that went down: gone before the program file is touched
        with self._binary_lock:
            exe, config = self._executable()
            metrics_port = _free_port()
            try:
                proc = subprocess.Popen(  # noqa: S603 - the pinned, verified program; fixed arguments
                    process.command(exe, self.port, metrics_port, config),
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            except OSError as exc:
                raise TunnelUnavailable(CANT_START) from exc
        job: int | None = None
        try:
            job = process.kill_with_parent(proc)
            with self._lock:
                if gen != self._gen:
                    raise TunnelUnavailable("The internet link was turned off.")
                self._proc, self._job = proc, job
            threading.Thread(target=self._watch, args=(proc,), name="tunnel-watch", daemon=True).start()
            hostname = process.read_hostname(metrics_port, process.HOSTNAME_TIMEOUT, alive=lambda: proc.poll() is None)
            with self._lock:
                if self._proc is not proc:
                    raise TunnelUnavailable("The internet link was turned off.")
                self.state, self.hostname, self.reason = "running", hostname, None
            return hostname
        except BaseException:
            with self._lock:
                if self._proc is proc:
                    self._proc, self._job = None, None
            self._end(proc, job)
            raise

    def _watch(self, proc: subprocess.Popen[bytes]) -> None:
        proc.wait()
        with self._lock:
            if self._proc is not proc:
                return  # stopped, or failed while starting (that path tidies up itself)
            job, self._proc, self._job = self._job, None, None
            down = self.state == "running"
            if down:
                self.state, self.reason, self.hostname = "failed", WENT_DOWN, None
        process.close_job(job)
        loop, on_down = self._loop, self.on_down
        if down and on_down is not None and loop is not None and not loop.is_closed():
            def call() -> None:
                asyncio.ensure_future(on_down())
            with contextlib.suppress(RuntimeError):  # the loop closed in between
                loop.call_soon_threadsafe(call)

    def _take(self) -> tuple[subprocess.Popen[bytes] | None, int | None]:
        with self._lock:
            proc, job, self._proc, self._job = self._proc, self._job, None, None
        return proc, job

    @staticmethod
    def _end(proc: subprocess.Popen[bytes] | None, job: int | None) -> None:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        process.close_job(job)

    def stop(self) -> None:
        """End cloudflared (terminate, 5 s, kill). The link is gone; on_down isn't called (the host turned it off)."""
        with self._lock:
            self._gen += 1
            proc, job, self._proc, self._job = self._proc, self._job, None, None
            self.state, self.hostname, self.reason = "stopped", None, None
        self._end(proc, job)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
