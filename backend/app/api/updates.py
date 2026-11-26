"""INSTALL UPDATE (host computer only): Settings → Install update… (app/storage/update.py does the work).

GET /api/update            whether this copy can install updates (the Fyodor app, started by its launcher), its version, the update waiting
                           to be installed, what the last one did
POST /api/update/upload    the zip, as the request body: checked, and what installing it would do (nothing changes yet)
POST /api/update/apply     install it: games saved, players told, files unpacked beside Fyodor.exe, the updater started, Fyodor exits
DELETE /api/update         forget the uploaded zip
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_services, require_local
from app.config import FROZEN, install_dir
from app.services import Services
from app.storage import update as up

log = logging.getLogger(__name__)
router = APIRouter(tags=["update"])
ServicesDep = Annotated[Services, Depends(get_services)]

NOT_FROZEN = ("This Fyodor runs from its source code (python -m app.launcher), not the Fyodor app: update it with git and a rebuild "
              "(scripts/build-app.sh). Install update… works in the Fyodor app (Fyodor.exe).")
NOT_WINDOWS = "Installing an update from Settings works on Windows. On this computer, unzip the update over the Fyodor folder while Fyodor is closed."
NO_LAUNCHER = "Fyodor wasn't started by its own launcher here, so it can't restart itself: close Fyodor and unzip the update over its folder."


def target(request: Request) -> Path | None:
    """The install folder updates go to: the folder of Fyodor.exe in the Fyodor app (tests set ``app.state.update_install_dir``)."""
    forced = getattr(request.app.state, "update_install_dir", None)
    if forced is not None:
        return Path(forced)
    return install_dir() if FROZEN and os.name == "nt" else None


def unavailable(request: Request) -> str | None:
    if target(request) is not None:
        return None
    return NOT_FROZEN if not FROZEN else NOT_WINDOWS


@router.get("/update")
def status(request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    data = services.settings.data_dir
    where = target(request)
    pending = up.load_pending(data)
    return {"available": where is not None, "reason": unavailable(request), "install_dir": str(where) if where else None,
            "installed": up.installed(where), "pending": pending.summary() if pending else None, "last": up.last_result(data),
            "log": str(data / up.LOG), "can_restart": getattr(request.app.state, "request_exit", None) is not None}


@router.post("/update/upload")
async def upload(request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    where = target(request)
    if where is None:
        raise HTTPException(409, unavailable(request))
    data = services.settings.data_dir
    up.discard(where, data)  # (one update at a time: a new pick replaces the last)
    part = data / (up.UPLOAD + ".part")
    size = 0
    try:
        with open(part, "wb") as out:  # to a file, never memory: an update is hundreds of megabytes
            async for chunk in request.stream():
                size += len(chunk)
                if size > up.MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "That file is too large to be a Fyodor update")
                out.write(chunk)
        if size == 0:
            raise HTTPException(422, "The file is empty")
        part.replace(data / up.UPLOAD)
        plan = await run_in_threadpool(up.inspect_zip, data / up.UPLOAD, where)
        plan.zip_name = unquote(request.headers.get("x-file-name") or "")[:200] or plan.zip_name  # (the page sends it URI-encoded)
        up.save_pending(data, plan)
    except up.UpdateError as exc:
        up.discard(None, data)
        up.log(data, f"Update refused: {exc}")
        raise HTTPException(422, str(exc)) from exc
    except BaseException:
        up.discard(None, data)
        raise
    up.log(data, f"Update checked: {len(plan.files)} files, {plan.total_bytes:,} bytes, version {plan.version or '?'}"
                 f"{' (manifest verified)' if plan.verified else ' (no manifest)'}")
    return plan.summary()


@router.delete("/update", status_code=204)
def forget(request: Request, services: ServicesDep) -> None:
    require_local(request)
    up.discard(target(request), services.settings.data_dir)


@router.post("/update/apply", status_code=202)
async def apply(request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    where = target(request)
    if where is None:
        raise HTTPException(409, unavailable(request))
    leave = getattr(request.app.state, "request_exit", None)
    if leave is None:
        raise HTTPException(409, NO_LAUNCHER)
    data = services.settings.data_dir
    plan = up.load_pending(data)
    if plan is None:
        raise HTTPException(409, "Pick the update again: the one checked earlier is gone")
    try:
        await run_in_threadpool(up.stage, data / up.UPLOAD, plan, where)
    except up.UpdateError as exc:
        up.log(data, f"Update not staged: {exc}")
        raise HTTPException(422, str(exc)) from exc
    close_window = up.touches_browser(plan)
    script = up.write_updater(where)
    exe = Path(sys.executable)
    cmd = up.updater_command(script, pid=os.getpid(), install_dir=where, data_dir=data, exe=exe,
                             exe_args=up.restart_args(sys.argv[1:], window_stays=not close_window), close_window=close_window)
    # everyone at a table hears it before the server goes (their tables come back after the restart: crash recovery)
    await tell_everyone(services, "Updating — Fyodor will restart. Your game is saved and comes back in a minute.")
    await run_in_threadpool(save_everything, services)
    try:
        launch(cmd)
    except OSError as exc:
        up.discard(where, data)
        up.log(data, f"Update not started: the updater wouldn't run ({exc})")
        raise HTTPException(500, f"The updater wouldn't start: {exc}") from exc
    up.log(data, f"Update {plan.version or ''} staged ({len(plan.files)} files); Fyodor closes and the updater takes over"
                 f"{' (closing Fyodor’s window: the update replaces it)' if close_window else ''}")
    (data / up.UPLOAD).unlink(missing_ok=True)
    (data / up.PLAN).unlink(missing_ok=True)
    threading.Timer(1.0, leave).start()  # (after this answer has gone out)
    return {"restarting": True, "closes_window": close_window, "files": len(plan.files), "version": plan.version}


async def tell_everyone(services: Services, message: str) -> None:
    payload = {"type": "signal", "kind": "update", "from": None, "from_name": "Fyodor", "message": message}
    for room in list(services.hub.rooms.values()):
        for conn in list(room.connections.values()):
            with contextlib.suppress(Exception):  # best effort, like every push
                await asyncio.wait_for(conn.send(payload), 2)


def save_everything(services: Services) -> None:
    """A last save of every table now (the shutdown saves them again: Services.close)."""
    for room in list(services.hub.rooms.values()):
        try:
            services.autosave(room)
            services.hub.persist(room)
        except Exception:  # noqa: BLE001 - one table's save must not stop the update; the shutdown tries again
            log.exception("Save before the update failed for %s", room.id)


def launch(cmd: list[str]) -> None:
    """Start the updater on its own: no window, its own process group, out of any job Fyodor runs in (it must outlive Fyodor)."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    try:
        subprocess.Popen(cmd, creationflags=flags | breakaway, close_fds=True,  # noqa: S603 - our own script, our own arguments
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        if not breakaway:
            raise
        subprocess.Popen(cmd, creationflags=flags, close_fds=True,  # noqa: S603 - (a job that forbids breaking away)
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
