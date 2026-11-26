"""-- install update -- Settings → Install update…: the zip checks (paths, roots, links, sizes, the manifest's hashes), the plan, the
staging, the updater script's copy / backup / restore (run for real with PowerShell on Windows, without restarting anything) and the API's
host-only guard. Never the process restart itself."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import updates as api
from app.storage import update as up


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def make_zip(path: Path, files: dict[str, bytes], *, manifest: dict | None = None, sep: str = "/") -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        if manifest is not None:
            zf.writestr(f"Fyodor{sep}{up.MANIFEST}", json.dumps(manifest))
        for name, body in files.items():
            zf.writestr(name.replace("/", sep), body)
    return path


def manifest_for(files: dict[str, bytes], **extra) -> dict:
    return {"format": 1, "version": "2026-11-18a", "commit": "abc1234",
            "files": [{"path": n.split("/", 1)[1], "size": len(b), "sha256": sha(b)} for n, b in files.items()], **extra}


FILES = {"Fyodor/Fyodor.exe": b"MZ new exe", "Fyodor/_internal/app.pyd": b"new module", "Fyodor/_internal/frontend/dist/index.html": b"<html>"}


@pytest.fixture()
def install(tmp_path: Path) -> Path:
    root = tmp_path / "Fyodor"
    (root / "_internal").mkdir(parents=True)
    (root / "Fyodor.exe").write_bytes(b"MZ old exe")
    (root / "_internal" / "app.pyd").write_bytes(b"old module")
    (root / "seed").mkdir()
    (root / "seed" / "cards.sqlite").write_bytes(b"seed db")
    return root


# -- the checks ---------------------------------------------------------------------------------------------------------------------
def test_a_plain_changes_only_zip_is_planned(tmp_path, install):
    z = make_zip(tmp_path / "u.zip", FILES, sep="\\")  # (Windows' own zips store backslashes)
    plan = up.inspect_zip(z, install)
    assert [f.path for f in plan.files] == ["Fyodor.exe", "_internal/app.pyd", "_internal/frontend/dist/index.html"]
    assert [f.replaces for f in plan.files] == [True, True, False]
    assert plan.total_bytes == sum(len(b) for b in FILES.values()) and not plan.verified and plan.version is None
    assert plan.warnings and "no manifest" in plan.warnings[0]
    s = plan.summary()
    assert (s["files"], s["replaced"], s["added"], s["closes_window"]) == (3, 2, 1, False)
    assert {g["name"]: g["files"] for g in s["groups"]} == {"_internal": 2, "Fyodor.exe": 1}


def test_a_zip_with_its_manifest_is_verified(tmp_path, install):
    z = make_zip(tmp_path / "u.zip", FILES, manifest=manifest_for(FILES, removed=["_internal/old.dll", "../escape"]))
    plan = up.inspect_zip(z, install)
    assert plan.verified and plan.version == "2026-11-18a" and plan.commit == "abc1234" and not plan.warnings
    assert "update-manifest.json" in [f.path for f in plan.files]  # (installed too: Settings reads the version from it)
    assert plan.removed == ["_internal/old.dll"]  # (a removed path that isn't safe is dropped, never acted on)


@pytest.mark.parametrize("name", [
    "Fyodor/../evil.txt", "Fyodor/_internal/../../evil.txt", "Fyodor\\..\\evil.txt", "../Fyodor/x.txt", "/Fyodor/x.txt",
    "C:/Fyodor/x.txt", "Fyodor/C:x.txt", "Fyodor//x.txt", "Fyodor/./x.txt", "Fyodor/file.txt:stream",
])
def test_path_traversal_and_absolute_paths_are_refused(tmp_path, install, name):
    with pytest.raises(up.UpdateError):
        up.inspect_zip(make_zip(tmp_path / "u.zip", {**FILES, name: b"x"}), install)


@pytest.mark.parametrize("name", ["Other/Fyodor.exe", "Fyodor.exe", "fyodor/Fyodor.exe", "dist/Fyodor/Fyodor.exe", "Fyodor"])
def test_entries_outside_the_fyodor_folder_are_refused(tmp_path, install, name):
    with pytest.raises(up.UpdateError):
        up.inspect_zip(make_zip(tmp_path / "u.zip", {name: b"x"}), install)


@pytest.mark.parametrize("name", ["Fyodor/_update/files/x", "Fyodor/_update_backup/x", "Fyodor/con.txt", "Fyodor/a<b", "Fyodor/dir./x",
                                  "Fyodor/trailing "])
def test_names_windows_cant_use_or_the_updaters_own_folders_are_refused(tmp_path, install, name):
    with pytest.raises(up.UpdateError):
        up.inspect_zip(make_zip(tmp_path / "u.zip", {name: b"x"}), install)


def test_links_are_refused(tmp_path, install):
    z = tmp_path / "u.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Fyodor/Fyodor.exe", b"MZ")
        link = zipfile.ZipInfo("Fyodor/_internal/evil")
        link.create_system = 3
        link.external_attr = (0o120777 << 16)
        zf.writestr(link, "../../../Windows/System32")
    with pytest.raises(up.UpdateError, match="links"):
        up.inspect_zip(z, install)


def test_not_a_zip_empty_and_duplicates_are_refused(tmp_path, install):
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"not a zip at all")
    with pytest.raises(up.UpdateError, match="isn't a zip"):
        up.inspect_zip(junk, install)
    with pytest.raises(up.UpdateError, match="no files"):
        up.inspect_zip(make_zip(tmp_path / "e.zip", {}), install)
    with pytest.raises(up.UpdateError, match="no files"):
        up.inspect_zip(make_zip(tmp_path / "m.zip", {}, manifest={"files": []}), install)
    z = tmp_path / "d.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Fyodor/Fyodor.exe", b"a")
        zf.writestr("Fyodor/FYODOR.EXE", b"b")
    with pytest.raises(up.UpdateError, match="twice"):
        up.inspect_zip(z, install)


def test_size_limits(tmp_path, install, monkeypatch):
    monkeypatch.setattr(up, "MAX_FILE_BYTES", 5)
    with pytest.raises(up.UpdateError, match="larger"):
        up.inspect_zip(make_zip(tmp_path / "u.zip", {"Fyodor/big.bin": b"0123456789"}), install)
    monkeypatch.setattr(up, "MAX_FILE_BYTES", 100)
    monkeypatch.setattr(up, "MAX_TOTAL_BYTES", 15)
    with pytest.raises(up.UpdateError, match="more than"):
        up.inspect_zip(make_zip(tmp_path / "u.zip", {"Fyodor/a.bin": b"0123456789", "Fyodor/b.bin": b"0123456789"}), install)


def test_a_hash_mismatch_is_refused(tmp_path, install):
    m = manifest_for(FILES)
    m["files"][0]["sha256"] = sha(b"something else")
    with pytest.raises(up.UpdateError, match="doesn't match"):
        up.inspect_zip(make_zip(tmp_path / "u.zip", FILES, manifest=m), install)
    m = manifest_for(FILES)
    m["files"][1]["size"] += 1
    with pytest.raises(up.UpdateError, match="doesn't match"):
        up.inspect_zip(make_zip(tmp_path / "u.zip", FILES, manifest=m), install)


def test_files_missing_from_or_extra_to_the_manifest_are_refused(tmp_path, install):
    with pytest.raises(up.UpdateError, match="doesn't list"):
        up.inspect_zip(make_zip(tmp_path / "u.zip", {**FILES, "Fyodor/sneaky.dll": b"x"}, manifest=manifest_for(FILES)), install)
    with pytest.raises(up.UpdateError, match="missing"):
        up.inspect_zip(make_zip(tmp_path / "u.zip", {"Fyodor/Fyodor.exe": FILES["Fyodor/Fyodor.exe"]}, manifest=manifest_for(FILES)), install)
    with pytest.raises(up.UpdateError, match="manifest"):
        up.inspect_zip(make_zip(tmp_path / "u.zip", FILES, manifest={"files": [{"path": "Fyodor.exe"}]}), install)


def test_a_damaged_member_is_refused(tmp_path, install):
    z = make_zip(tmp_path / "u.zip", {"Fyodor/Fyodor.exe": b"A" * 4000})
    raw = bytearray(z.read_bytes())
    at = raw.index(b"Fyodor/Fyodor.exe") + len("Fyodor/Fyodor.exe") + 5  # into the compressed data of the first entry
    raw[at] ^= 0xFF
    z.write_bytes(bytes(raw))
    with pytest.raises(up.UpdateError):
        up.inspect_zip(z, install)


# -- staging and the plan -------------------------------------------------------------------------------------------------------------
def test_stage_unpacks_into_the_install_folder_and_writes_the_plan(tmp_path, install):
    z = make_zip(tmp_path / "u.zip", FILES, manifest=manifest_for(FILES))
    plan = up.inspect_zip(z, install)
    root = up.stage(z, plan, install)
    assert root == install / "_update"
    assert (root / "files" / "Fyodor.exe").read_bytes() == b"MZ new exe"
    assert (root / "files" / "_internal" / "frontend" / "dist" / "index.html").read_bytes() == b"<html>"
    written = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    assert written["version"] == "2026-11-18a" and len(written["files"]) == 4
    assert (install / "Fyodor.exe").read_bytes() == b"MZ old exe"  # nothing installed yet
    assert (install / "seed" / "cards.sqlite").read_bytes() == b"seed db"


def test_stage_refuses_a_zip_changed_since_it_was_checked(tmp_path, install):
    z = make_zip(tmp_path / "u.zip", FILES)
    plan = up.inspect_zip(z, install)
    make_zip(z, {**FILES, "Fyodor/Fyodor.exe": b"MZ swapped"})
    with pytest.raises(up.UpdateError, match="changed"):
        up.stage(z, plan, install)
    assert not (install / "_update").exists()
    make_zip(z, {**FILES, "Fyodor/extra.dll": b"x"})
    with pytest.raises(up.UpdateError, match="wasn't in the update"):
        up.stage(z, plan, install)


def test_pending_plan_round_trip_and_discard(tmp_path, install):
    data = tmp_path / "data"
    data.mkdir()
    z = make_zip(data / up.UPLOAD, FILES, manifest=manifest_for(FILES))
    plan = up.inspect_zip(z, install)
    up.save_pending(data, plan)
    again = up.load_pending(data)
    assert again is not None and again.summary() == plan.summary()
    up.stage(z, plan, install)
    up.discard(install, data)
    assert up.load_pending(data) is None and not z.exists() and not (install / "_update").exists()


def test_updater_command_and_restart_args(tmp_path, install):
    script = up.write_updater(install)
    text = script.read_bytes()
    assert text.isascii() and b"param(" in text and b"\r\n" in text
    cmd = up.updater_command(script, pid=4242, install_dir=install, data_dir=tmp_path, exe=install / "Fyodor.exe",
                             exe_args=["--port", "8123", "--no-browser"], close_window=True, powershell="powershell.exe")
    assert cmd[:2] == ["powershell.exe", "-NoProfile"] and cmd[cmd.index("-WaitPid") + 1] == "4242"
    assert cmd[cmd.index("-ExeArgs") + 1] == "--port 8123 --no-browser" and cmd[-1] == "-CloseWindow"
    assert up.restart_args(["--local"], window_stays=True) == ["--local", "--no-browser"]
    assert up.restart_args(["--local"], window_stays=False) == ["--local"]
    browser = up.Plan(files=[up.PlanFile("browser/chrome.dll", 1, "0" * 64, True)], total_bytes=1)
    assert up.touches_browser(browser) and not up.touches_browser(up.Plan(files=[up.PlanFile("Fyodor.exe", 1, "0" * 64, True)], total_bytes=1))


# -- the updater script itself (Windows): copy, backup, restore on failure; -NoStart so nothing is started ------------------------------
POWERSHELL = shutil.which("powershell.exe") if os.name == "nt" else None


def run_updater(install: Path, data: Path, **extra: str) -> dict:
    script = up.write_updater(install)
    dead = subprocess.Popen(["cmd", "/c", "exit 0"])  # noqa: S603,S607 - a process that has already exited: nothing to wait for
    dead.wait()
    cmd = [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), "-WaitPid", str(dead.pid),
           "-Install", str(install), "-DataDir", str(data), "-Exe", str(install / "Fyodor.exe"), "-NoStart", "-Retries", "1"]
    for k, v in extra.items():
        cmd += [f"-{k}", v]
    subprocess.run(cmd, check=True, timeout=120, capture_output=True)  # noqa: S603
    return json.loads((data / up.RESULT).read_text(encoding="utf-8-sig"))


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell")
def test_updater_installs_and_keeps_a_backup(tmp_path, install):
    data = tmp_path / "data"
    data.mkdir()
    z = make_zip(tmp_path / "u.zip", FILES, manifest=manifest_for(FILES))
    up.stage(z, up.inspect_zip(z, install), install)
    result = run_updater(install, data)
    assert result["ok"] is True and result["files"] == 4 and result["version"] == "2026-11-18a"
    assert (install / "Fyodor.exe").read_bytes() == b"MZ new exe" and (install / "_internal" / "frontend" / "dist" / "index.html").is_file()
    assert (install / "_update_backup" / "Fyodor.exe").read_bytes() == b"MZ old exe"
    assert (install / "seed" / "cards.sqlite").read_bytes() == b"seed db"  # not in the zip: untouched
    assert not (install / "_update").exists()
    assert up.installed(install) == {"version": "2026-11-18a", "commit": "abc1234", "built_at": None}
    assert "Installed 4 files" in (data / up.LOG).read_text(encoding="utf-8-sig")


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell")
def test_updater_restores_everything_when_a_copy_fails(tmp_path, install):
    data = tmp_path / "data"
    data.mkdir()
    z = make_zip(tmp_path / "u.zip", FILES)
    up.stage(z, up.inspect_zip(z, install), install)
    plan = json.loads((install / "_update" / "plan.json").read_text(encoding="utf-8"))
    plan["files"].append({"path": "_internal/zz-missing.dll", "size": 1, "replaces": False})  # (its staged copy doesn't exist: the copy fails)
    (install / "_update" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    result = run_updater(install, data)
    assert result["ok"] is False and "put back" in result["message"]
    assert (install / "Fyodor.exe").read_bytes() == b"MZ old exe" and (install / "_internal" / "app.pyd").read_bytes() == b"old module"
    assert not (install / "_internal" / "frontend" / "dist" / "index.html").exists()  # a new file of the failed update is gone again
    assert "UPDATE FAILED" in (data / up.LOG).read_text(encoding="utf-8-sig")


# -- the API ------------------------------------------------------------------------------------------------------------------------------
def zip_bytes(files: dict[str, bytes], manifest: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if manifest is not None:
            zf.writestr(f"Fyodor/{up.MANIFEST}", json.dumps(manifest))
        for n, b in files.items():
            zf.writestr(n, b)
    return buf.getvalue()


def test_a_source_checkout_shows_why_it_cant_install(client: TestClient):
    s = client.get("/api/update").json()
    assert s["available"] is False and "source" in s["reason"]
    assert client.post("/api/update/upload", content=zip_bytes(FILES)).status_code == 409


def test_update_is_host_only(client: TestClient, install):
    client.app.state.update_install_dir = install
    lan = {"X-Forwarded-For": "192.168.1.20"}
    assert client.get("/api/update", headers=lan).status_code == 403
    assert client.post("/api/update/upload", content=zip_bytes(FILES), headers=lan).status_code == 403
    assert client.post("/api/update/apply", headers=lan).status_code == 403
    assert client.delete("/api/update", headers=lan).status_code == 403


def test_upload_check_and_apply(client: TestClient, install, settings, monkeypatch):
    client.app.state.update_install_dir = install
    bad = client.post("/api/update/upload", content=zip_bytes({"Fyodor/../evil.txt": b"x"}))
    assert bad.status_code == 422 and ".." in bad.json()["detail"]
    assert not (settings.data_dir / up.UPLOAD).exists()
    res = client.post("/api/update/upload", content=zip_bytes(FILES, manifest_for(FILES)), headers={"X-File-Name": "Fyodor-update-x.zip"})
    assert res.status_code == 200, res.text
    s = res.json()
    assert (s["files"], s["replaced"], s["verified"], s["version"], s["zip_name"]) == (4, 2, True, "2026-11-18a", "Fyodor-update-x.zip")
    assert client.get("/api/update").json()["pending"]["files"] == 4
    # not started by the launcher: it says to install by hand
    assert client.post("/api/update/apply").status_code == 409
    launched: list[list[str]] = []
    left: list[bool] = []
    monkeypatch.setattr(api, "launch", launched.append)
    monkeypatch.setattr(api.threading, "Timer", lambda _t, fn: type("T", (), {"start": lambda self: fn()})())
    client.app.state.request_exit = lambda: left.append(True)
    try:
        done = client.post("/api/update/apply")
    finally:
        del client.app.state.request_exit
    assert done.status_code == 202 and done.json()["closes_window"] is False
    assert left == [True] and len(launched) == 1
    cmd = launched[0]
    assert cmd[cmd.index("-Install") + 1] == str(install) and "-CloseWindow" not in cmd
    assert "--no-browser" in cmd[cmd.index("-ExeArgs") + 1]  # the window that asked stays and reloads
    assert (install / "_update" / "files" / "Fyodor.exe").read_bytes() == b"MZ new exe" and (install / "_update" / "apply-update.ps1").is_file()
    assert client.get("/api/update").json()["pending"] is None
    assert "staged" in (settings.data_dir / up.LOG).read_text(encoding="utf-8")


def test_discard_forgets_the_upload(client: TestClient, install, settings):
    client.app.state.update_install_dir = install
    assert client.post("/api/update/upload", content=zip_bytes(FILES)).status_code == 200
    assert client.delete("/api/update").status_code == 204
    assert client.get("/api/update").json()["pending"] is None and not (settings.data_dir / up.UPLOAD).exists()


# -- scripts/make-update-zip.py: a changes-only zip the Settings check accepts -------------------------------------------------------------
def load_script():
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts" / "make-update-zip.py"
    spec = importlib.util.spec_from_file_location("make_update_zip", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_make_update_zip_keeps_only_what_changed_and_lists_what_went(tmp_path, install):
    script = load_script()
    new = tmp_path / "dist" / "Fyodor"
    (new / "_internal" / "frontend").mkdir(parents=True)
    (new / "Fyodor.exe").write_bytes(b"MZ new exe")
    (new / "_internal" / "same.dll").write_bytes(b"unchanged")
    (new / "_internal" / "frontend" / "index.html").write_bytes(b"<html>new")
    (new / "_internal" / "added.pyd").write_bytes(b"brand new")
    (new / "_update_backup").mkdir()
    (new / "_update_backup" / "junk").write_bytes(b"never shipped")
    prev = make_zip(tmp_path / "portable.zip", {"Fyodor/Fyodor.exe": b"MZ old exe", "Fyodor/_internal/same.dll": b"unchanged",
                                                 "Fyodor/_internal/frontend/index.html": b"<html>old", "Fyodor/_internal/Gone.dll": b"x",
                                                 "Fyodor/seed/cards.sqlite": b"seed"}, sep="\\")
    later = make_zip(tmp_path / "update-1.zip", {"Fyodor/_internal/frontend/index.html": b"<html>new"})  # (already installed since)
    out = tmp_path / "Fyodor-update-test.zip"
    assert script.main(["--new", str(new), "--prev", str(prev), "--prev", str(later), "--out", str(out), "--version", "2026-11-18b",
                        "--commit", "deadbeef"]) == 0
    with zipfile.ZipFile(out) as zf:
        names = sorted(zf.namelist())
        manifest = json.loads(zf.read("Fyodor/update-manifest.json"))
    assert names == ["Fyodor/Fyodor.exe", "Fyodor/_internal/added.pyd", "Fyodor/update-manifest.json"]
    assert manifest["removed"] == ["_internal/Gone.dll"]  # (seed/ isn't in the build: kept, not "removed")
    assert manifest["version"] == "2026-11-18b" and manifest["commit"] == "deadbeef" and manifest["base"] == ["portable.zip", "update-1.zip"]
    plan = up.inspect_zip(out, install)  # the Settings check accepts it and verifies every hash
    assert plan.verified and plan.version == "2026-11-18b" and plan.removed == ["_internal/Gone.dll"]
    assert [f.path for f in plan.files] == ["Fyodor.exe", "_internal/added.pyd", "update-manifest.json"]
    # nothing changed: nothing written
    assert script.main(["--new", str(new), "--prev", str(prev), "--prev", str(later), "--prev", str(out), "--out", str(tmp_path / "none.zip")]) == 1
    assert not (tmp_path / "none.zip").exists()
