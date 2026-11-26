"""DESKTOP SHORTCUT (host computer only): the first start offers one (frontend/src/pages/ShortcutOffer.tsx).

GET  /api/shortcut   whether this copy can make one (the Fyodor app on Windows) and whether the desktop already has it
POST /api/shortcut   make "Fyodor.lnk" on the desktop, pointing at this Fyodor.exe
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import require_local
from app.config import FROZEN, install_dir

router = APIRouter(tags=["shortcut"])


def _desktops() -> list[Path]:
    """Where Windows may keep the desktop (OneDrive moves it)."""
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    onedrive = os.environ.get("ONEDRIVE")  # (Windows environment names ignore case)
    return [home / "Desktop", *([Path(onedrive) / "Desktop"] if onedrive else [])]


def _supported() -> bool:
    return FROZEN and os.name == "nt"


@router.get("/shortcut")
def shortcut_state(request: Request) -> dict[str, Any]:
    require_local(request)
    return {"supported": _supported(), "exists": any((d / "Fyodor.lnk").exists() for d in _desktops())}


@router.post("/shortcut")
def make_shortcut(request: Request) -> dict[str, Any]:
    require_local(request)
    if not _supported():
        raise HTTPException(400, "A desktop shortcut can be made by the Fyodor app on Windows")
    exe = install_dir() / "Fyodor.exe"
    # the shell's own desktop folder (OneDrive-aware); the path goes in as data, never as code
    script = ("$d=[Environment]::GetFolderPath('Desktop');$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Fyodor.lnk'));"
              "$s.TargetPath=$env:FY_EXE;$s.WorkingDirectory=(Split-Path $env:FY_EXE);$s.IconLocation=$env:FY_EXE;$s.Save()")
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env={**os.environ, "FY_EXE": str(exe)},  # noqa: S603, S607
                          capture_output=True, text=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if done.returncode != 0:
        raise HTTPException(500, f"Windows didn't make the shortcut: {done.stderr.strip()[:200]}")
    return {"supported": True, "exists": True}
