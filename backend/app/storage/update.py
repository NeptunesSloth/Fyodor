"""INSTALL UPDATE (host computer only): an update zip carried to an offline computer, checked, staged and handed to a small updater.

An update zip holds only the files that changed, as ``Fyodor/<path in the install folder>`` (``Fyodor/Fyodor.exe``,
``Fyodor/_internal/...``, maybe ``Fyodor/browser/...``), and, when ``scripts/make-update-zip.py`` built it, ``Fyodor/update-manifest.json``:
its version and commit, and every file with its size and sha256 (checked here), and the files the new version no longer uses (shown;
left in place). Windows can't overwrite the running ``Fyodor.exe`` and ``_internal`` DLLs, so the files are unpacked into ``_update/``
inside the install folder and a PowerShell script (``_update/apply-update.ps1``) waits for Fyodor to exit, backs up each file it replaces
into ``_update_backup/``, copies the new ones over, and starts Fyodor again. If a copy fails it puts the backed-up files back and starts the
old version. It writes what happened to ``<data dir>/update.log`` and ``<data dir>/update-result.json``. Cards, decks and saves live in the
data folder and are never touched; ``seed/`` and anything else in the install folder change only when the zip carries them.

Everything here takes its folders as arguments (no ``FROZEN``), so the tests run it on a folder of their own.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import time
import zipfile
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = "Fyodor"  # every entry of an update zip sits under this folder
MANIFEST = "update-manifest.json"
STAGE = "_update"  # the install folder's staging area (its files/, plan.json and the updater script)
BACKUP = "_update_backup"  # the files the last update replaced, as they were
UPLOAD = "update-upload.zip"  # in the data folder: the zip being looked at, until it is installed or discarded
PLAN = "update-plan.json"  # in the data folder: what UPLOAD was found to hold
RESULT = "update-result.json"  # in the data folder: what the updater did last
LOG = "update.log"  # in the data folder

MAX_UPLOAD_BYTES = 3 * 1024**3  # an update with Fyodor's own browser is ~250 MB zipped; a whole portable copy ~600 MB
MAX_TOTAL_BYTES = 6 * 1024**3  # unpacked
MAX_FILE_BYTES = 2 * 1024**3
MAX_ENTRIES = 100_000
MAX_MANIFEST_BYTES = 32 * 1024**2
_CHUNK = 1024 * 1024
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class UpdateError(Exception):
    """An update zip Fyodor won't install, with the reason in words."""


@dataclass
class PlanFile:
    path: str  # relative to the install folder, with "/"
    size: int
    sha256: str
    replaces: bool  # a file of that name is there now


@dataclass
class Plan:
    files: list[PlanFile]
    total_bytes: int
    version: str | None = None
    commit: str | None = None
    built_at: str | None = None
    verified: bool = False  # every file matched the manifest's size and sha256
    removed: list[str] = field(default_factory=list)  # the manifest's files the new version no longer uses (left in place)
    warnings: list[str] = field(default_factory=list)
    zip_name: str | None = None

    def summary(self) -> dict[str, Any]:
        """What the Settings page shows: counts, sizes, the folders it touches (not the whole file list)."""
        groups: dict[str, dict[str, int]] = {}
        for f in self.files:
            top = f.path.split("/", 1)[0]
            g = groups.setdefault(top, {"files": 0, "bytes": 0, "folder": "/" in f.path})
            g["files"] += 1
            g["bytes"] += f.size
        return {
            "files": len(self.files), "total_bytes": self.total_bytes, "replaced": sum(f.replaces for f in self.files),
            "added": sum(not f.replaces for f in self.files), "version": self.version, "commit": self.commit, "built_at": self.built_at,
            "verified": self.verified, "removed": len(self.removed), "removed_sample": self.removed[:20], "warnings": self.warnings,
            "groups": [{"name": k, **v} for k, v in sorted(groups.items(), key=lambda kv: (-kv[1]["bytes"], kv[0]))],
            "closes_window": touches_browser(self), "zip_name": self.zip_name,
        }

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(data: dict[str, Any]) -> Plan:
        files = [PlanFile(**f) for f in data.get("files", [])]
        return Plan(files=files, **{k: v for k, v in data.items() if k != "files"})


def touches_browser(plan: Plan) -> bool:
    """Does the update replace Fyodor's own window (browser/, browser-legacy/)? Then that window has to close for the copy."""
    return any(f.path.split("/", 1)[0].lower() in ("browser", "browser-legacy") for f in plan.files)


def safe_relative(name: str) -> str:
    """The install-folder path an entry name stands for ("/"-separated, under ``Fyodor/``), or UpdateError. Backslashes (zips made by
    Windows' own "Send to compressed folder" and PowerShell 5) count as separators."""
    raw = name.replace("\\", "/")
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or ":" in raw:
        raise UpdateError(f"{name!r}: an absolute path or a drive in an update isn't allowed")
    parts = raw.rstrip("/").split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise UpdateError(f"{name!r}: \"..\" or an empty folder name in an update isn't allowed")
    if parts[0] != ROOT:
        raise UpdateError(f"{name!r}: everything in an update sits in a folder named {ROOT}")
    rest = parts[1:]
    for p in rest:
        if _BAD_CHARS.search(p) or p.endswith((" ", ".")) or p.split(".", 1)[0].lower() in _RESERVED:
            raise UpdateError(f"{name!r}: a file name Windows can't use")
    rel = "/".join(rest)
    if rel and rest[0].lower() in (STAGE, BACKUP):
        raise UpdateError(f"{name!r}: the update's own working folders can't be in an update")
    return rel


def _is_symlink(zi: zipfile.ZipInfo) -> bool:
    return zi.create_system == 3 and stat.S_ISLNK(zi.external_attr >> 16)


def _manifest(zf: zipfile.ZipFile, zi: zipfile.ZipInfo) -> dict[str, Any]:
    if zi.file_size > MAX_MANIFEST_BYTES:
        raise UpdateError("The update's manifest is too large")
    try:
        data = json.loads(zf.read(zi).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise UpdateError(f"The update's manifest can't be read: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise UpdateError("The update's manifest has no file list")
    for f in data["files"]:
        if not (isinstance(f, dict) and isinstance(f.get("path"), str) and isinstance(f.get("size"), int)
                and isinstance(f.get("sha256"), str) and _HEX64.match(f["sha256"].lower())):
            raise UpdateError("The update's manifest lists a file without its path, size or sha256")
    return data


def _text(value: Any, limit: int = 200) -> str | None:
    return str(value)[:limit] if isinstance(value, str | int | float) and str(value) else None


def inspect_zip(path: Path, install_dir: Path) -> Plan:
    """Check an update zip and say what installing it would do. Reads every file once: its CRC (zipfile checks it as it reads) and its
    sha256, which must match the manifest when there is one. Raises UpdateError with the reason for anything unexpected."""
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise UpdateError("That isn't a zip file (or it is damaged)") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise UpdateError(f"The update has more than {MAX_ENTRIES:,} entries")
        entries: list[tuple[str, zipfile.ZipInfo]] = []
        seen: set[str] = set()
        manifest_info: zipfile.ZipInfo | None = None
        total = 0
        for zi in infos:
            rel = safe_relative(zi.filename)
            if _is_symlink(zi):
                raise UpdateError(f"{zi.filename!r}: links in an update aren't allowed")
            if zi.flag_bits & 0x1:
                raise UpdateError(f"{zi.filename!r}: encrypted files can't be installed")
            if zi.is_dir() or zi.filename.endswith("\\"):
                continue
            if not rel:
                raise UpdateError(f"{zi.filename!r}: a file has to be inside the {ROOT} folder")
            key = rel.lower()
            if key in seen:
                raise UpdateError(f"{zi.filename!r} is in the update twice")
            seen.add(key)
            if zi.file_size > MAX_FILE_BYTES:
                raise UpdateError(f"{rel} is larger than an update file may be")
            total += zi.file_size
            if total > MAX_TOTAL_BYTES:
                raise UpdateError("The update unpacks to more than Fyodor allows")
            if rel == MANIFEST:
                manifest_info = zi
            entries.append((rel, zi))
        if not entries or all(rel == MANIFEST for rel, _ in entries):
            raise UpdateError("The update has no files in it")
        manifest = _manifest(zf, manifest_info) if manifest_info is not None else None
        listed: dict[str, dict[str, Any]] = {}
        if manifest is not None:
            for f in manifest["files"]:
                listed[safe_relative(f"{ROOT}/{f['path']}")] = f
            payload = {rel for rel, _ in entries if rel != MANIFEST}
            if missing := sorted(set(listed) - payload):
                raise UpdateError(f"The update is missing {len(missing)} file(s) its manifest lists, e.g. {missing[0]}")
            if extra := sorted(payload - set(listed)):
                raise UpdateError(f"The update has {len(extra)} file(s) its manifest doesn't list, e.g. {extra[0]}")
        files: list[PlanFile] = []
        for rel, zi in entries:
            digest = hashlib.sha256()
            size = 0
            try:
                with zf.open(zi) as src:
                    while chunk := src.read(_CHUNK):
                        size += len(chunk)
                        digest.update(chunk)
            except (zipfile.BadZipFile, OSError, EOFError, zlib.error) as exc:
                raise UpdateError(f"{rel} is damaged in the zip ({exc})") from exc
            sha = digest.hexdigest()
            want = listed.get(rel)
            if want is not None and (want["size"] != size or want["sha256"].lower() != sha):
                raise UpdateError(f"{rel} doesn't match the update's manifest (a damaged or altered copy)")
            files.append(PlanFile(rel, size, sha, (install_dir / rel).is_file()))
    removed: list[str] = []
    warnings: list[str] = []
    if manifest is not None:
        for r in manifest.get("removed") or []:
            if isinstance(r, str):
                try:
                    removed.append(safe_relative(f"{ROOT}/{r}"))
                except UpdateError:
                    continue
    else:
        warnings.append("This update has no manifest: its files were checked for damage, but not against a list of what they should be.")
    return Plan(files=sorted(files, key=lambda f: f.path), total_bytes=sum(f.size for f in files),
                version=_text(manifest.get("version")) if manifest else None, commit=_text(manifest.get("commit"), 64) if manifest else None,
                built_at=_text(manifest.get("built_at"), 64) if manifest else None, verified=manifest is not None, removed=removed,
                warnings=warnings, zip_name=path.name)


def stage(zip_path: Path, plan: Plan, install_dir: Path) -> Path:
    """Unpack the planned files into ``<install>/_update/files`` (each checked against its sha256 again: the zip could have changed since it
    was looked at) and write ``_update/plan.json`` for the updater. Returns the staging folder. Raises UpdateError (the staging is removed)."""
    root = install_dir / STAGE
    files_dir = root / "files"
    if root.exists():
        shutil.rmtree(root)
    need = plan.total_bytes * 2 + 200 * 1024**2  # the staged copy, the backup of what it replaces, room to spare
    free = shutil.disk_usage(install_dir).free
    if free < need:
        raise UpdateError(f"Not enough free disk space for the update: it needs about {need // 1024**2:,} MB, {free // 1024**2:,} MB is free")
    files_dir.mkdir(parents=True)
    by_path = {f.path: f for f in plan.files}
    base = files_dir.resolve()
    try:
        with zipfile.ZipFile(zip_path) as zf:
            done: set[str] = set()
            for zi in zf.infolist():
                if zi.is_dir() or zi.filename.endswith(("/", "\\")):
                    continue
                rel = safe_relative(zi.filename)
                want = by_path.get(rel)
                if want is None:
                    raise UpdateError(f"{rel} wasn't in the update when it was checked")
                target = (files_dir / PurePosixPath(rel)).resolve()
                if not target.is_relative_to(base):
                    raise UpdateError(f"{rel}: outside the update folder")
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size = 0
                with zf.open(zi) as src, open(target, "wb") as out:
                    while chunk := src.read(_CHUNK):
                        size += len(chunk)
                        if size > want.size:
                            raise UpdateError(f"{rel} changed since the update was checked")
                        digest.update(chunk)
                        out.write(chunk)
                if size != want.size or digest.hexdigest() != want.sha256:
                    raise UpdateError(f"{rel} changed since the update was checked")
                done.add(rel)
            if missing := set(by_path) - done:
                raise UpdateError(f"{sorted(missing)[0]} is no longer in the update")
        (root / "plan.json").write_text(json.dumps({"version": plan.version, "commit": plan.commit,
                                                     "files": [{"path": f.path, "size": f.size, "replaces": f.replaces} for f in plan.files]},
                                                    indent=1), encoding="utf-8")
    except (UpdateError, OSError, zipfile.BadZipFile) as exc:
        shutil.rmtree(root, ignore_errors=True)
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError(f"The update couldn't be unpacked: {exc}") from exc
    return root


def discard(install_dir: Path | None, data_dir: Path) -> None:
    """Forget an uploaded update and anything staged from it."""
    for name in (UPLOAD, PLAN, UPLOAD + ".part"):
        (data_dir / name).unlink(missing_ok=True)
    if install_dir is not None and (install_dir / STAGE).exists():
        shutil.rmtree(install_dir / STAGE, ignore_errors=True)


def save_pending(data_dir: Path, plan: Plan) -> None:
    tmp = data_dir / (PLAN + ".tmp")
    tmp.write_text(json.dumps(plan.to_json()), encoding="utf-8")
    tmp.replace(data_dir / PLAN)


def load_pending(data_dir: Path) -> Plan | None:
    """The plan of the uploaded zip waiting to be installed (None when there's none, or its zip is gone)."""
    try:
        if not (data_dir / UPLOAD).is_file():
            return None
        return Plan.from_json(json.loads((data_dir / PLAN).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def installed(install_dir: Path | None) -> dict[str, Any] | None:
    """The version of the last update installed here (its manifest, copied into the install folder with it)."""
    if install_dir is None:
        return None
    try:
        data = json.loads((install_dir / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"version": _text(data.get("version")), "commit": _text(data.get("commit"), 64), "built_at": _text(data.get("built_at"), 64)} \
        if isinstance(data, dict) else None


def last_result(data_dir: Path) -> dict[str, Any] | None:
    """What the updater did last (``update-result.json``: ok, message, version, at)."""
    try:
        data = json.loads((data_dir / RESULT).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# -- the updater ----------------------------------------------------------------------------------------------------------------------
# PowerShell 5 (every Windows 10 and 11 has it). ASCII only: Windows PowerShell reads a script without a byte order mark in the ANSI code
# page; paths with other letters come in as arguments, which are Unicode.
UPDATER_PS1 = r"""# Fyodor updater: written by Fyodor (Settings > Install update) and run once Fyodor has closed. Safe to delete.
param(
  [int]$WaitPid,
  [string]$Install,
  [string]$DataDir,
  [string]$Exe,
  [string]$ExeArgs = '',
  [switch]$CloseWindow,
  [switch]$NoStart,
  [int]$Retries = 15
)
$ErrorActionPreference = 'Stop'
$stage = Join-Path $Install '_update'
$files = Join-Path $stage 'files'
$backup = Join-Path $Install '_update_backup'
$log = Join-Path $DataDir 'update.log'
$resultFile = Join-Path $DataDir 'update-result.json'

function Write-Log([string]$m) {
  $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $m
  try { Add-Content -LiteralPath $log -Value $line -Encoding UTF8 } catch { }
}
function Write-Result([bool]$ok, [string]$message, [int]$count, [string]$version) {
  $r = [ordered]@{ ok = $ok; message = $message; files = $count; version = $version; at = (Get-Date).ToString('s') }
  try { ($r | ConvertTo-Json) | Set-Content -LiteralPath $resultFile -Encoding UTF8 } catch { Write-Log ('Could not write the result: ' + $_) }
}
function Start-Fyodor {
  if ($NoStart) { Write-Log 'Not starting Fyodor (-NoStart).'; return }
  try {
    if ($ExeArgs) { Start-Process -FilePath $Exe -ArgumentList $ExeArgs -WorkingDirectory $Install | Out-Null }
    else { Start-Process -FilePath $Exe -WorkingDirectory $Install | Out-Null }
    Write-Log ('Started ' + $Exe + ' ' + $ExeArgs)
  } catch { Write-Log ('Could not start Fyodor: ' + $_.Exception.Message) }
}

$version = ''
$copied = New-Object System.Collections.ArrayList
try {
  Write-Log ('Update: waiting for Fyodor (process ' + $WaitPid + ') to close')
  $deadline = (Get-Date).AddSeconds(90)
  while ((Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) -and ((Get-Date) -lt $deadline)) { Start-Sleep -Milliseconds 300 }
  if (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) {
    Write-Log 'Fyodor did not close within 90 seconds: stopping it (its games were saved before the update began)'
    Stop-Process -Id $WaitPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }
  if ($CloseWindow) {
    # the update replaces Fyodor's own window (browser\): close the window running from this install folder, never another browser
    foreach ($dir in @('browser', 'browser-legacy')) {
      $prefix = (Join-Path $Install $dir) + '\'
      $procs = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) })
      foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
      if ($procs.Count) { Write-Log ('Closed Fyodor''s window (' + $procs.Count + ' processes from ' + $dir + ')') }
    }
    Start-Sleep -Milliseconds 1500
  }
  $plan = Get-Content -LiteralPath (Join-Path $stage 'plan.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($plan.version) { $version = [string]$plan.version }
  if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  $n = @($plan.files).Count
  Write-Log ('Installing ' + $n + ' files' + $(if ($version) { ' (version ' + $version + ')' } else { '' }))
  foreach ($f in $plan.files) {
    $rel = ([string]$f.path) -replace '/', '\'
    $src = Join-Path $files $rel
    $dst = Join-Path $Install $rel
    $bak = Join-Path $backup $rel
    $existed = Test-Path -LiteralPath $dst -PathType Leaf
    if ($existed) {
      New-Item -ItemType Directory -Path (Split-Path -Parent $bak) -Force | Out-Null
      Copy-Item -LiteralPath $dst -Destination $bak -Force
    }
    [void]$copied.Add(@{ rel = $rel; existed = $existed })
    New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
    for ($i = 1; ; $i++) {
      try { Copy-Item -LiteralPath $src -Destination $dst -Force; break }
      catch { if ($i -ge $Retries) { throw ('Could not replace ' + $rel + ': ' + $_.Exception.Message) }; Start-Sleep -Milliseconds 800 }
    }
  }
  Write-Log ('Installed ' + $n + ' files. The replaced ones are kept in ' + $backup + ' until the next update.')
  Write-Result $true ('Installed ' + $n + ' files') $n $version
  Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
} catch {
  $why = [string]$_.Exception.Message
  Write-Log ('UPDATE FAILED: ' + $why)
  $restored = 0
  $bad = 0
  for ($k = $copied.Count - 1; $k -ge 0; $k--) {
    $c = $copied[$k]
    $dst = Join-Path $Install $c.rel
    try {
      if ($c.existed) { Copy-Item -LiteralPath (Join-Path $backup $c.rel) -Destination $dst -Force }
      elseif (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Force }
      $restored++
    } catch { $bad++; Write-Log ('Could not restore ' + $c.rel + ': ' + $_.Exception.Message) }
  }
  Write-Log ('Restored ' + $restored + ' files' + $(if ($bad) { ' (' + $bad + ' could not be restored: see above; the old copies are in ' + $backup + ')' } else { '' }))
  Write-Result $false ($why + $(if ($bad) { ' Some files could not be put back: see update.log.' } else { ' The previous version was put back.' })) 0 $version
}
Start-Fyodor
"""


def write_updater(install_dir: Path) -> Path:
    """Write the updater script into the staging folder (it deletes that folder when it's done)."""
    script = install_dir / STAGE / "apply-update.ps1"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(UPDATER_PS1, encoding="ascii", newline="\r\n")
    return script


def updater_command(script: Path, *, pid: int, install_dir: Path, data_dir: Path, exe: Path, exe_args: list[str],
                    close_window: bool, powershell: str | None = None) -> list[str]:
    """The command line that runs the updater (hidden, its own process: it outlives Fyodor)."""
    shell = powershell or str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    cmd = [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script),
           "-WaitPid", str(pid), "-Install", str(install_dir), "-DataDir", str(data_dir), "-Exe", str(exe)]
    if exe_args:
        cmd += ["-ExeArgs", " ".join(_quote(a) for a in exe_args)]
    if close_window:
        cmd.append("-CloseWindow")
    return cmd


def restart_args(argv: list[str], *, window_stays: bool) -> list[str]:
    """Fyodor's own command-line options for its start after the update: the same ones, and ``--no-browser`` when the window that asked
    for the update stays open (it reloads by itself), so a second window doesn't open beside it."""
    args = list(argv)
    if window_stays and "--no-browser" not in args:
        args.append("--no-browser")
    return args


def _quote(arg: str) -> str:
    return f'"{arg}"' if not arg or any(c in arg for c in ' \t"') else arg


def log(data_dir: Path, message: str) -> None:
    """Append a line to ``update.log`` (the updater appends to the same file)."""
    try:
        with open(data_dir / LOG, "a", encoding="utf-8") as out:
            out.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {message}\n")
    except OSError:
        pass
