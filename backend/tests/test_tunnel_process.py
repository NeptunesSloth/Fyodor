"""Running the tunnel (app/tunnel/process.py, manager.py). No real cloudflared: a stand-in Python script serves /quicktunnel."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.config import Settings
from app.tunnel import binary, process
from app.tunnel.binary import TunnelUnavailable
from app.tunnel.manager import TunnelManager

STAND_IN = r'''
import json, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
port, mode, hostname = int(sys.argv[1]), sys.argv[2], sys.argv[3]
if mode == "die":
    sys.exit(1)
if mode == "silent":
    time.sleep(120)
    sys.exit(0)
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"hostname": hostname}).encode()
        self.send_response(200 if self.path == "/quicktunnel" else 404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass
HTTPServer(("127.0.0.1", port), H).serve_forever()
'''

HOST = "lucky-cat-1.trycloudflare.com"


@pytest.fixture()
def stand_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Replace cloudflared by the stand-in; returns a dict to set its mode/hostname and the list of commands started."""
    script = tmp_path / "standin.py"
    script.write_text(STAND_IN)
    fake_exe = tmp_path / "cloudflared.exe"
    fake_exe.write_bytes(b"x")
    conf = {"mode": "serve", "hostname": HOST}
    started: list[list[str]] = []
    verified: list[Path] = []

    def command(exe: Path, port: int, metrics_port: int, config: Path) -> list[str]:
        cmd = [sys.executable, str(script), str(metrics_port), conf["mode"], conf["hostname"]]
        started.append(cmd)
        return cmd

    monkeypatch.setattr(process, "command", command)
    monkeypatch.setattr(binary, "ensure_binary", lambda folder, client, **kw: fake_exe)
    monkeypatch.setattr(binary, "asset_for", lambda system, machine: object())

    def verify(path: Path, asset: object) -> bool:
        verified.append(path)
        return True

    monkeypatch.setattr(binary, "verify", verify)
    conf_out = {"conf": conf, "started": started, "verified": verified}
    return conf_out


@pytest.fixture()
def manager(settings: Settings):
    m = TunnelManager(settings)
    m.port = 18555
    yield m
    m.stop()  # every test's stand-in ends with it


def test_start_reports_the_hostname(manager: TunnelManager, stand_in) -> None:
    assert asyncio.run(manager.start()) == HOST
    assert (manager.state, manager.hostname, manager.reason) == ("running", HOST, None)
    assert stand_in["verified"], "verify() runs before the process is started"
    assert asyncio.run(manager.start()) == HOST  # while running: the same hostname, no second process
    assert len(stand_in["started"]) == 1


def test_two_starts_at_once_spawn_one_process(manager: TunnelManager, stand_in) -> None:
    async def both() -> list[str]:
        return list(await asyncio.gather(manager.start(), manager.start()))

    assert asyncio.run(both()) == [HOST, HOST]
    assert len(stand_in["started"]) == 1


@pytest.mark.parametrize("bad", ["evil.example.com", "a.trycloudflare.com.evil.com", "", "A.trycloudflare.com"])
def test_a_hostname_that_is_not_trycloudflare_fails_closed(manager: TunnelManager, stand_in, monkeypatch, bad: str) -> None:
    monkeypatch.setattr(process, "HOSTNAME_TIMEOUT", 1.5)
    stand_in["conf"]["hostname"] = bad
    with pytest.raises(TunnelUnavailable, match="didn't come up"):
        asyncio.run(manager.start())
    assert manager.state == "failed" and manager.hostname is None
    assert manager.reason == "The internet link didn't come up. Check this computer's connection and try again."
    assert manager._proc is None


def test_start_times_out_when_no_hostname(manager: TunnelManager, stand_in, monkeypatch) -> None:
    monkeypatch.setattr(process, "HOSTNAME_TIMEOUT", 1.0)
    stand_in["conf"]["mode"] = "silent"
    t0 = time.monotonic()
    with pytest.raises(TunnelUnavailable):
        asyncio.run(manager.start())
    assert time.monotonic() - t0 < 8
    assert manager.state == "failed" and manager._proc is None


def test_a_process_that_dies_while_starting_fails_fast_and_closes_its_job_once(manager: TunnelManager, stand_in,
                                                                                monkeypatch) -> None:
    closed: list[int] = []
    real_close = process.close_job

    def close_job(job: int | None) -> None:
        if job is not None:
            closed.append(job)
        real_close(job)

    monkeypatch.setattr(process, "close_job", close_job)
    stand_in["conf"]["mode"] = "die"
    t0 = time.monotonic()
    with pytest.raises(TunnelUnavailable, match="didn't come up"):
        asyncio.run(manager.start())
    assert time.monotonic() - t0 < 10  # not the 30 s timeout: the process is seen to be gone
    assert manager.state == "failed" and manager._proc is None
    assert len(closed) == len(set(closed))
    if os.name == "nt":
        assert len(closed) == 1


def test_a_stop_right_after_start_wins(manager: TunnelManager, stand_in) -> None:
    async def run() -> None:
        task = asyncio.ensure_future(manager.start())
        await asyncio.sleep(0)  # start() has made its task; the task hasn't run yet
        manager.stop()
        with pytest.raises(TunnelUnavailable, match="turned off"):
            await task

    asyncio.run(run())
    assert (manager.state, manager.hostname) == ("stopped", None)
    assert manager._proc is None and stand_in["started"] == []


def test_a_failed_job_assignment_leaves_no_process(manager: TunnelManager, stand_in, monkeypatch) -> None:
    procs: list[subprocess.Popen[bytes]] = []

    def broken(proc: subprocess.Popen[bytes]) -> int | None:
        procs.append(proc)
        raise TunnelUnavailable("The internet link couldn't be started on this computer.")

    monkeypatch.setattr(process, "kill_with_parent", broken)
    with pytest.raises(TunnelUnavailable):
        asyncio.run(manager.start())
    assert len(procs) == 1 and procs[0].poll() is not None
    assert manager.state == "failed" and manager._proc is None


def test_a_hostname_from_a_process_that_is_gone_is_refused(stand_in, tmp_path: Path) -> None:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    cmd = process.command(tmp_path / "x", 1, port, tmp_path / "c")
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert process.read_hostname(port, 10) == HOST
        with pytest.raises(TunnelUnavailable):
            process.read_hostname(port, 10, alive=lambda: False)
    finally:
        proc.kill()
        proc.wait()


def test_an_on_down_that_fails_is_logged(manager: TunnelManager, stand_in, caplog) -> None:
    async def run() -> None:
        async def on_down() -> None:
            raise RuntimeError("boom")

        manager.on_down = on_down
        await manager.start()
        assert manager._proc is not None
        manager._proc.kill()
        for _ in range(100):
            await asyncio.sleep(0.1)
            if "going down failed" in caplog.text:
                break

    asyncio.run(run())
    assert "Handling the internet link going down failed" in caplog.text
    assert not manager._down_tasks


def test_a_dying_process_calls_on_down_and_clears_the_hostname(manager: TunnelManager, stand_in) -> None:
    async def run() -> int:
        down = asyncio.Event()
        calls = 0

        async def on_down() -> None:
            nonlocal calls
            calls += 1
            down.set()

        manager.on_down = on_down
        await manager.start()
        assert manager._proc is not None
        manager._proc.kill()  # cloudflared crashes
        await asyncio.wait_for(down.wait(), 10)
        return calls

    assert asyncio.run(run()) == 1
    assert manager.state == "failed"
    assert manager.reason == "The internet link went down."
    assert manager.hostname is None


def test_stop_ends_the_process_and_not_on_down(manager: TunnelManager, stand_in) -> None:
    calls: list[int] = []

    async def on_down() -> None:
        calls.append(1)

    async def run() -> subprocess.Popen[bytes]:
        manager.on_down = on_down
        await manager.start()
        proc = manager._proc
        assert proc is not None
        manager.stop()
        await asyncio.sleep(0.5)  # a scheduled on_down would have run by now
        return proc

    proc = asyncio.run(run())
    assert proc.poll() is not None
    assert (manager.state, manager.hostname) == ("stopped", None)
    assert calls == []


def test_services_close_stops_the_tunnel(settings: Settings, stand_in) -> None:
    from app.services import Services

    services = Services(settings)
    services.tunnel.port = 18556
    asyncio.run(services.tunnel.start())
    proc = services.tunnel._proc
    assert proc is not None
    services.close()
    assert proc.poll() is not None
    assert services.tunnel.state == "stopped"


def test_command_disables_autoupdate_and_pins_metrics_to_loopback(tmp_path: Path) -> None:
    exe, conf = tmp_path / "cloudflared.exe", tmp_path / "empty.yml"
    assert process.command(exe, 18599, 18600, conf) == [
        str(exe), "tunnel", "--no-autoupdate", "--config", str(conf),
        "--metrics", "127.0.0.1:18600", "--url", "http://127.0.0.1:18599",
    ]


def test_the_config_file_is_empty(manager: TunnelManager, stand_in, settings: Settings) -> None:
    asyncio.run(manager.start())
    config = settings.data_dir / "tunnel" / "empty.yml"
    assert config.is_file() and config.read_bytes() == b""


def test_an_os_error_while_getting_the_program_is_a_tunnel_failure(manager: TunnelManager, stand_in, monkeypatch) -> None:
    def broken(folder: Path, client: object, **kw: object) -> Path:
        raise PermissionError("denied")

    monkeypatch.setattr(binary, "ensure_binary", broken)
    with pytest.raises(TunnelUnavailable):
        asyncio.run(manager.start())
    assert manager.state == "failed" and manager.reason and "denied" not in manager.reason
    assert stand_in["started"] == []


def test_a_program_that_fails_verification_is_not_started(manager: TunnelManager, stand_in, monkeypatch) -> None:
    monkeypatch.setattr(binary, "verify", lambda path, asset: False)
    with pytest.raises(TunnelUnavailable):
        asyncio.run(manager.start())
    assert stand_in["started"] == [] and manager.state == "failed"


@pytest.mark.skipif(os.name != "nt", reason="Windows Job objects")
def test_the_child_dies_with_the_job() -> None:
    import ctypes

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        job = process.kill_with_parent(proc)
        assert job is not None
        assert proc.poll() is None
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(job))  # what happens when Fyodor dies
        assert proc.wait(5) is not None
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.skipif(os.name != "nt", reason="Windows Job objects")
def test_a_suspended_child_runs_once_it_is_in_the_job() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "pass"], creationflags=process.CREATE_SUSPENDED,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    job = None
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            proc.wait(1)  # suspended: it doesn't run on its own
        job = process.kill_with_parent(proc)
        assert proc.wait(10) == 0
    finally:
        proc.kill()
        proc.wait()
        process.close_job(job)
