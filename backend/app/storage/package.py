"""Portable game packages: one ``.fyodor.zip`` holding a save, the custom images it uses and
the macros for its cards, so a table can move to another pod machine without Internet.

Import never trusts the archive: only the expected member names are read (nothing is
extracted by name to disk), sizes are bounded before decompressing, every image is
content-sniffed and hash-checked, macros are re-validated as declarative data and the save goes
through the normal versioned migrations.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
import zipfile
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from app.assets.store import EXT, KINDS, AssetStore
from app.game.macros import MacroDef
from app.storage.macros import MacroRepository
from app.storage.save_format import SaveFormatError, decode
from app.storage.saves import SaveRepository, load_payload

PACKAGE_FORMAT = "fyodor-package"
PACKAGE_VERSION = 1
MAX_PACKAGE_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 300
_ASSET_NAME = re.compile(r"^assets/([0-9a-f]{8,32})\.(png|jpg|webp)$")
_ID = re.compile(r"^[0-9a-f]{8,32}$")


class PackageError(ValueError):
    pass


def _asset_ids(state: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for p in (state.get("players") or {}).values():
        if p.get("sleeve"):
            ids.add(p["sleeve"])
        if p.get("playmat"):
            ids.add(p["playmat"]["asset_id"])
    mat = (state.get("table") or {}).get("playmat")
    if mat:
        ids.add(mat["asset_id"])
    return ids


def export_package(saves: SaveRepository, assets: AssetStore, macros: MacroRepository, save_id: str,
                   *, oracle_ids_of: Callable[[list[str]], set[str]]) -> tuple[bytes, str]:
    """(zip bytes, suggested file name)."""
    blob = saves.export_blob(save_id)
    summary = saves.get_summary(save_id)
    payload = decode(blob)
    state = payload["state"]
    ids = _asset_ids(state)
    for snap in (payload.get("extras") or {}).get("table_snapshots") or []:
        if isinstance(snap, dict) and isinstance(snap.get("state"), dict):
            ids |= _asset_ids(snap["state"])
    oracle_ids = oracle_ids_of(sorted({c["card_id"] for c in (state.get("cards") or {}).values() if c.get("card_id")}))
    wanted_macros = [m for m in macros.list_all() if m["scope"] == "library" or m["oracle_id"] in oracle_ids]

    buf = io.BytesIO()
    manifest: dict[str, Any] = {
        "format": PACKAGE_FORMAT, "version": PACKAGE_VERSION, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "save": {"name": summary["name"], "game_name": summary["game_name"], "turn": summary["turn"]},
        "assets": [], "macros": len(wanted_macros),
    }
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("save.fyodor", blob)
        for aid in sorted(ids):
            try:
                data, info = assets.read(aid)
            except LookupError:
                continue  # already deleted locally: the game still loads, the image is just missing
            member = f"assets/{aid}.{EXT[info['mime'].split('/')[1]]}"
            zf.writestr(member, data)
            manifest["assets"].append({"id": aid, "kind": info["kind"], "name": info["name"], "file": member,
                                       "sha256": hashlib.sha256(data).hexdigest()})
        zf.writestr("macros.json", json.dumps([{"scope": m["scope"], "oracle_id": m["oracle_id"], "definition": m["definition"]}
                                               for m in wanted_macros]))
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "", summary["name"]).strip() or "game"
    return buf.getvalue(), f"{safe[:60]}.fyodor.zip"


def _read(zf: zipfile.ZipFile, name: str, limit: int = MAX_MEMBER_BYTES) -> bytes:
    try:
        info = zf.getinfo(name)
    except KeyError:
        raise PackageError(f"Package is missing {name}") from None
    if info.file_size > limit:
        raise PackageError(f"{name} is too large")
    with zf.open(info) as fh:
        data = fh.read(limit + 1)  # never trust the header's size alone
    if len(data) > limit:
        raise PackageError(f"{name} is too large")
    return data


def _replace_ids(node: Any, mapping: dict[str, str]) -> Any:
    if isinstance(node, dict):
        return {k: _replace_ids(v, mapping) for k, v in node.items()}
    if isinstance(node, list):
        return [_replace_ids(v, mapping) for v in node]
    if isinstance(node, str):
        return mapping.get(node, node)
    return node


def import_package(data: bytes, saves: SaveRepository, assets: AssetStore, macros: MacroRepository,
                   *, history_limit: int = 500) -> dict[str, Any]:
    if len(data) > MAX_PACKAGE_BYTES:
        raise PackageError("Package is too large")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise PackageError("Not a Fyodor package (not a zip file)") from exc
    with zf:
        names = zf.namelist()
        if len(names) > MAX_MEMBERS:
            raise PackageError("Package has too many files")
        if sum(i.file_size for i in zf.infolist()) > MAX_PACKAGE_BYTES:
            raise PackageError("Package is too large when unpacked")
        try:
            manifest = json.loads(_read(zf, "manifest.json", 1024 * 1024))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PackageError("Package manifest is unreadable") from exc
        if not isinstance(manifest, dict) or manifest.get("format") != PACKAGE_FORMAT:
            raise PackageError("Not a Fyodor package")
        if not isinstance(manifest.get("version"), int) or manifest["version"] > PACKAGE_VERSION:
            raise PackageError("This package was made by a newer Fyodor")

        # The save first: if it's broken nothing else gets imported.
        try:
            payload = decode(_read(zf, "save.fyodor"))
            load_payload(payload, history_limit=history_limit)
        except SaveFormatError as exc:
            raise PackageError(str(exc)) from exc

        mapping: dict[str, str] = {}
        added_assets = 0
        entries = manifest.get("assets")
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                raise PackageError("Bad asset entry in manifest")
            member, old_id, kind = entry.get("file"), entry.get("id"), entry.get("kind")
            m = _ASSET_NAME.match(member) if isinstance(member, str) else None
            if (not isinstance(member, str) or not m or m.group(1) != old_id or not isinstance(old_id, str)
                    or not _ID.match(old_id) or kind not in KINDS):
                raise PackageError("Bad asset entry in manifest")
            blob = _read(zf, member, 20 * 1024 * 1024)
            if hashlib.sha256(blob).hexdigest() != entry.get("sha256"):
                raise PackageError(f"{member} does not match its checksum")
            name = str(entry.get("name") or "Imported image")[:80]
            try:
                info, created = assets.import_image(blob, kind=kind, name=name)
            except ValueError as exc:
                raise PackageError(f"{member}: {exc}") from exc
            added_assets += created
            if info["id"] != old_id:
                mapping[old_id] = info["id"]

        added_macros = 0
        if "macros.json" in names:
            try:
                items = json.loads(_read(zf, "macros.json", 4 * 1024 * 1024))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise PackageError("macros.json is unreadable") from exc
            existing = {(m["scope"], m["oracle_id"], m["name"]) for m in macros.list_all()}
            for item in items if isinstance(items, list) else []:
                try:
                    definition = MacroDef.model_validate(item["definition"])
                    scope, oracle = item["scope"], item.get("oracle_id")
                except (KeyError, TypeError, ValidationError) as exc:
                    raise PackageError(f"A macro in the package is invalid: {exc}") from exc
                if (scope, oracle if scope == "card" else None, definition.name) in existing:
                    continue
                try:
                    macros.save(definition, scope=scope, oracle_id=oracle)
                except ValueError as exc:
                    raise PackageError(str(exc)) from exc
                added_macros += 1

    if mapping:
        payload = _replace_ids(payload, mapping)
    state, history = load_payload(payload, history_limit=history_limit)
    name = str((manifest.get("save") or {}).get("name") or state.name)[:70]
    save = saves.save(state, history, name=f"{name} (imported)", extras=payload.get("extras") or {})
    return {"save": save, "assets_added": added_assets, "macros_added": added_macros}
