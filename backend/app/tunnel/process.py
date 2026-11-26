"""cloudflared as a child of Fyodor: its command line, the public hostname read from its metrics endpoint, and (on Windows) a Job
object that ends it when Fyodor ends, however Fyodor ends. cloudflared's own output is never read."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from app.tunnel.binary import TunnelUnavailable

QUICK_HOST = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com")
HOSTNAME_TIMEOUT = 30.0  # seconds read_hostname waits when the manager starts the tunnel (the tests shorten it)
POLL_EVERY = 0.5
MAX_BODY = 4096  # /quicktunnel answers ~60 bytes
CREATE_SUSPENDED = 0x00000004  # Windows: cloudflared is started suspended and resumed once it is in its job
NOT_UP = "The internet link didn't come up. Check this computer's connection and try again."


def command(exe: Path, port: int, metrics_port: int, config: Path) -> list[str]:
    """``--config``: an empty file Fyodor owns, so a named tunnel's config.yaml in ~/.cloudflared can't take over the quick tunnel's
    routing (docs/superpowers/specs/2026-11-25-stage2-audit.md 3.7). Metrics on loopback only."""
    return [str(exe), "tunnel", "--no-autoupdate", "--config", str(config),
            "--metrics", f"127.0.0.1:{metrics_port}", "--url", f"http://127.0.0.1:{port}"]


def read_hostname(metrics_port: int, timeout: float = 30.0, *, alive: Callable[[], bool] | None = None) -> str:
    """The quick tunnel's ``*.trycloudflare.com`` hostname from ``/quicktunnel``, polled every 0.5 s; anything else (a name that isn't
    a trycloudflare one, no answer, the process gone: ``alive`` false) is TunnelUnavailable once ``timeout`` passes."""
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{metrics_port}/quicktunnel"
    with httpx.Client(trust_env=False, timeout=2.0) as client:  # trust_env: never through a proxy
        while True:
            try:
                body = b""
                with client.stream("GET", url) as response:
                    for chunk in response.iter_bytes():
                        body += chunk
                        if len(body) > MAX_BODY:
                            break
                hostname = json.loads(body[:MAX_BODY]).get("hostname")  # a longer answer is cut, fails to parse: keep polling
                # alive: the answer came from our cloudflared, not something else on that port after it died
                if isinstance(hostname, str) and QUICK_HOST.fullmatch(hostname) and (alive is None or alive()):
                    return hostname
            except (httpx.HTTPError, ValueError, RecursionError, AttributeError):
                pass
            if (alive is not None and not alive()) or time.monotonic() >= deadline:
                raise TunnelUnavailable(NOT_UP)
            time.sleep(POLL_EVERY)


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _ntdll = ctypes.WinDLL("ntdll")
    _ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    _ntdll.NtResumeProcess.restype = ctypes.c_long  # NTSTATUS, 0 = success

    def kill_with_parent(proc: subprocess.Popen[bytes]) -> int | None:
        """Put ``proc`` (started with CREATE_SUSPENDED, so it has run nothing yet) in a new Job object that kills it when the job's
        last handle closes, which Windows does when Fyodor exits (even killed), then resume it. Returns the job handle; the caller
        keeps it open for the process's life and closes it after. A job that can't be made, or a process that can't be resumed,
        is TunnelUnavailable and the caller ends the process (still suspended if the job failed): a cloudflared outliving Fyodor
        is not acceptable. (Resuming a process that wasn't suspended does nothing.)"""
        handle = int(proc._handle)  # type: ignore[attr-defined]  # Popen's own handle to the child (full access)
        job = _kernel32.CreateJobObjectW(None, None)
        if not job:
            raise TunnelUnavailable("The internet link couldn't be started on this computer.")
        try:
            info = _ExtendedLimits()
            info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not _kernel32.SetInformationJobObject(job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                                     ctypes.byref(info), ctypes.sizeof(info)):
                raise TunnelUnavailable("The internet link couldn't be started on this computer.")
            if not _kernel32.AssignProcessToJobObject(job, handle):
                raise TunnelUnavailable("The internet link couldn't be started on this computer.")
            if _ntdll.NtResumeProcess(handle) != 0:
                raise TunnelUnavailable("The internet link couldn't be started on this computer.")
        except BaseException:
            _kernel32.CloseHandle(job)
            raise
        return int(job)

    def close_job(job: int | None) -> None:
        if job is not None:
            _kernel32.CloseHandle(job)

else:

    def kill_with_parent(proc: subprocess.Popen[bytes]) -> int | None:
        """A no-op off Windows: a hard kill of Fyodor on macOS/Linux leaves cloudflared forwarding to a closed port (the audit's
        remaining risks)."""
        return None

    def close_job(job: int | None) -> None:
        return None
