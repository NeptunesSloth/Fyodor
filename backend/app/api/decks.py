from __future__ import annotations

import functools
import json
import time
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.api.deps import get_services, require_local
from app.decks import archidekt, service, sites
from app.decks.models import Deck, DeckImportRequest, DeckIn
from app.decks.parser import DeckTextTooLarge, format_deck_text
from app.decks.repository import DeckNotFound
from app.services import Services

# The deck library belongs to the host. LAN players bring their own decks through the game
# lobby (/api/games/{id}/lobby/deck); they can never browse or read the host's decks.
router = APIRouter(tags=["decks"], dependencies=[Depends(require_local)])
ServicesDep = Annotated[Services, Depends(get_services)]
SOURCE_CACHE_SECONDS = 600


def _get(services: Services, deck_id: str) -> Deck:
    try:
        return services.decks.get(deck_id)
    except DeckNotFound:
        raise HTTPException(404, "Deck not found") from None


def _full(services: Services, deck_id: str) -> dict[str, Any]:
    deck = _get(services, deck_id)
    entries, repairs = service.reconcile_entries(deck.entries, services.cards)
    deck = deck.model_copy(update={"entries": entries})
    data = service.deck_cards(deck, services.cards)
    warnings = [w.model_dump() for w in service.validate(deck, services.cards, data)]
    warnings += [{"level": "info", "message": m, "card": None} for m in repairs]
    body = deck.model_dump(exclude={"source_snapshot"})
    return {**body, "summary": service.summarize(deck, data), "warnings": warnings}


def _import(services: Services, body: DeckImportRequest) -> service.ImportResult:
    try:
        return service.import_any(body, services.cards, fetch=services.archidekt_fetch if services.settings.allow_network else None)
    except DeckTextTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    except archidekt.ArchidektError as exc:
        raise HTTPException(502 if body.archidekt and not isinstance(exc, sites.DeckLinkRefused) else 422, str(exc)) from exc


def _preview(result: service.ImportResult) -> dict[str, Any]:
    return {
        "name": result.parsed.name,
        "format": result.format,
        "source": result.source.model_dump() if result.source else None,
        "entries": [e.model_dump() for e in result.entries],
        "categories": [c.model_dump() for c in service.deck_categories(result.parsed)],
        "report": result.report.as_dict(),
        # kept for older clients
        "unresolved": [u.model_dump() for u in result.report.unresolved],
        "errors": result.report.errors,
        "notes": result.report.notes,
    }


@router.get("/decks")
def list_decks(services: ServicesDep) -> list[dict[str, Any]]:
    decks = services.decks.list_all()
    ids = [e.printing_id for d in decks for e in d.entries if e.printing_id and e.section == "commander"]
    ids += [next((e.printing_id for e in d.entries if e.printing_id), "") for d in decks]
    data = services.cards.get_many([i for i in ids if i]) if services.cards.available else {}
    return [service.summarize(d, data) for d in decks]


# -- precons -- every Commander precon's list, bundled (tools/update_precons.py), to add to the library offline
PRECON_FOLDER = "Precons"


@functools.cache
def _precons() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[1] / "decks" / "precons.json"
    return json.loads(path.read_text("utf-8")) if path.is_file() else []


@router.get("/decks/precons")
def list_precons(services: ServicesDep) -> list[dict[str, Any]]:
    """Every Commander precon (newest first), and whether the library already has it (by name, in the Precons folder)."""
    have = {d.name for d in services.decks.list_all() if d.folder == PRECON_FOLDER}
    return [{k: p[k] for k in ("id", "name", "set", "released", "commanders")} | {"added": p["name"] in have}
            for p in reversed(_precons())]


class PreconsIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)


@router.post("/decks/precons")
def add_precons(body: PreconsIn, services: ServicesDep) -> dict[str, Any]:
    """Add precons to the library, in the Precons folder; ones already there are skipped."""
    have = {d.name for d in services.decks.list_all() if d.folder == PRECON_FOLDER}
    wanted = set(body.ids)
    added = []
    for p in _precons():
        if p["id"] not in wanted or p["name"] in have:
            continue
        deck = create_deck(DeckImportRequest(text=p["text"], name=p["name"][:120]), services)
        services.decks.set_folder(deck["id"], PRECON_FOLDER)
        have.add(p["name"])
        added.append(deck["id"])
    return {"added": len(added), "ids": added}


@router.get("/decks/import-options")
def import_options(services: ServicesDep) -> dict[str, Any]:
    """Which import workflows work right now, so the UI never shows a dead button."""
    return {
        "archidekt_url": services.settings.allow_network,
        "archidekt_url_note": (
            "Uses Archidekt's public deck data (Internet needed only while importing). Public decks only."
            if services.settings.allow_network
            else "Network access is disabled (FYODOR_ALLOW_NETWORK=false). Paste or upload the Archidekt export instead."
        ),
        "text": True,
        "file": True,
        "card_database": services.cards.available,
    }


# -- keep deck art -- each saved deck's art is downloaded for offline play while online (app/cards/art_keeper.py)


class ArtKeeperIn(BaseModel):
    enabled: bool


@router.get("/decks/art-keeper")
def art_keeper_status(services: ServicesDep) -> dict[str, Any]:
    """Keep deck art for offline play: on or off, how many decks wait for the network, what is downloading now."""
    return {**services.art_keeper.status(), "network": services.settings.allow_network}


@router.put("/decks/art-keeper")
def set_art_keeper(body: ArtKeeperIn, services: ServicesDep) -> dict[str, Any]:
    services.art_keeper.set_enabled(body.enabled)
    return {**services.art_keeper.status(), "network": services.settings.allow_network}


@router.post("/decks/preview")
def preview_import(body: DeckImportRequest, services: ServicesDep) -> dict[str, Any]:
    """Parse and resolve an import (Archidekt URL/JSON or deck text) without saving."""
    return _preview(_import(services, body))


@router.post("/decks/parse")
def parse_preview(body: DeckImportRequest, services: ServicesDep) -> dict[str, Any]:
    """Backwards-compatible alias of ``/decks/preview``."""
    return _preview(_import(services, body))


@router.post("/decks", status_code=201)
def create_deck(body: DeckImportRequest, services: ServicesDep) -> dict[str, Any]:
    """Create a deck, optionally importing its list (Archidekt URL/JSON or text)."""
    result = _import(services, body) if body.archidekt or body.json_data or body.text.strip() else None
    entries = result.entries if result else []
    commanders = [e.name for e in entries if e.section == "commander"]
    name = body.name or (result.parsed.name if result else None) or (" & ".join(commanders) if commanders else None) or (
        "Imported deck" if entries else "New deck"
    )
    fmt = body.format or (result.format if result else None) or "commander"
    deck = services.decks.create(
        DeckIn(name=name, format=fmt, entries=entries,  # type: ignore[arg-type]
               categories=service.deck_categories(result.parsed) if result else []),
        source=result.source if result else None,
        snapshot=entries if result and result.source and result.source.kind == "archidekt" and result.source.id else None,
    )
    report = _preview(result)["report"] if result else service.ImportReport().as_dict()
    services.art_keeper.want(deck.id)  # -- keep deck art --
    return {**_full(services, deck.id), "import_report": report}


@router.get("/decks/{deck_id}")
def get_deck(deck_id: str, services: ServicesDep) -> dict[str, Any]:
    return _full(services, deck_id)


@router.put("/decks/{deck_id}")
def update_deck(deck_id: str, body: DeckIn, services: ServicesDep) -> dict[str, Any]:
    body = body.model_copy(update={"entries": service.resolve_entries(body.entries, services.cards)})
    try:
        services.decks.update(deck_id, body)
    except DeckNotFound:
        raise HTTPException(404, "Deck not found") from None
    services.art_keeper.want(deck_id)  # -- keep deck art --
    return _full(services, deck_id)


@router.post("/decks/{deck_id}/import")
def import_into_deck(deck_id: str, body: DeckImportRequest, services: ServicesDep) -> dict[str, Any]:
    deck = _get(services, deck_id)
    result = _import(services, body)
    new_entries = (deck.entries + result.entries) if body.mode == "append" else result.entries
    categories = list(deck.categories) if body.mode == "append" else []
    known = {c.name.lower() for c in categories}
    categories += [c for c in service.deck_categories(result.parsed) if c.name.lower() not in known]
    services.decks.update(
        deck_id,
        DeckIn(name=body.name or deck.name, format=body.format or deck.format, notes=deck.notes,
               entries=new_entries[:1000], categories=categories[:100]),
    )
    services.art_keeper.want(deck_id)  # -- keep deck art --
    return {**_full(services, deck_id), "import_report": result.report.as_dict()}


@router.post("/decks/{deck_id}/duplicate", status_code=201)
def duplicate_deck(deck_id: str, services: ServicesDep) -> dict[str, Any]:
    deck = _get(services, deck_id)
    copy = services.decks.create(
        DeckIn(name=f"{deck.name} (copy)"[:120], format=deck.format, notes=deck.notes, entries=deck.entries,
               categories=deck.categories)
    )
    if deck.folder:
        services.decks.set_folder(copy.id, deck.folder)
    return _full(services, copy.id)


class FolderIn(BaseModel):
    folder: str = Field(default="", max_length=60)


def _folder_name(raw: str) -> str:
    return " ".join(raw.split())  # trimmed, single spaces: "  Pod  decks " and "Pod decks" are one folder


@router.put("/decks/{deck_id}/folder")
def move_deck_to_folder(deck_id: str, body: FolderIn, services: ServicesDep) -> dict[str, Any]:
    """-- deck folders -- put a deck in a shelf folder ('' takes it out of every folder)."""
    try:
        services.decks.set_folder(deck_id, _folder_name(body.folder))
    except DeckNotFound:
        raise HTTPException(404, "Deck not found") from None
    return {"id": deck_id, "folder": _folder_name(body.folder)}


class FolderRename(BaseModel):
    old: str = Field(min_length=1, max_length=60)
    new: str = Field(default="", max_length=60)


@router.post("/deck-folders/rename")
def rename_folder(body: FolderRename, services: ServicesDep) -> dict[str, Any]:
    """Rename a folder; renaming to '' removes the folder (its decks stay, back on the shelf)."""
    return {"moved": services.decks.rename_folder(_folder_name(body.old), _folder_name(body.new))}


@router.delete("/decks/{deck_id}", status_code=204)
def delete_deck(deck_id: str, services: ServicesDep) -> Response:
    try:
        services.decks.delete(deck_id)
    except DeckNotFound:
        raise HTTPException(404, "Deck not found") from None
    return Response(status_code=204)


@router.get("/decks/{deck_id}/export", response_class=PlainTextResponse)
def export_deck(deck_id: str, services: ServicesDep,
                format: Annotated[Literal["archidekt", "plain"], Query()] = "archidekt") -> str:
    deck = _get(services, deck_id)
    rows = [e.model_dump() for e in deck.entries]
    return archidekt.format_archidekt_text(rows) if format == "archidekt" else format_deck_text(rows)


# ---------------------------------------------------------------------------- Archidekt source link


def _remote(services: Services, deck: Deck, *, refresh: bool) -> service.ImportResult:
    if deck.source is None or deck.source.kind != "archidekt" or not deck.source.id:
        raise HTTPException(409, "This deck was not imported from an Archidekt URL")
    if not services.settings.allow_network:
        raise HTTPException(409, "Network access is disabled")
    cached = services.source_cache.get(deck.id)
    if cached and not refresh and time.monotonic() - cached[0] < SOURCE_CACHE_SECONDS:
        return cached[1]
    result = _import(services, DeckImportRequest(archidekt=deck.source.id))
    services.source_cache[deck.id] = (time.monotonic(), result)
    return result


@router.post("/decks/{deck_id}/source/check")
def check_source(deck_id: str, services: ServicesDep) -> dict[str, Any]:
    """Fetch the linked Archidekt deck and report what changed since import. Changes nothing."""
    deck = _get(services, deck_id)
    remote = _remote(services, deck, refresh=True)
    diff = service.diff_entries(deck.source_snapshot or [], remote.entries)
    return {"diff": diff, "remote_updated_at": remote.source.updated_at if remote.source else None,
            "local_edits": service.diff_entries(deck.source_snapshot or [], deck.entries)["changed"]}


@router.post("/decks/{deck_id}/source/apply")
def apply_source(deck_id: str, services: ServicesDep) -> dict[str, Any]:
    """Merge Archidekt changes into the local deck, keeping local edits (three-way merge)."""
    deck = _get(services, deck_id)
    remote = _remote(services, deck, refresh=False)
    merged, conflicts = service.merge_source(deck.entries, deck.source_snapshot or [], remote.entries)
    known = {c.name.lower() for c in deck.categories}
    categories = deck.categories + [c for c in service.deck_categories(remote.parsed) if c.name.lower() not in known]
    services.decks.update(deck_id, DeckIn(name=deck.name, format=deck.format, notes=deck.notes, entries=merged[:1000],
                                          categories=categories[:100]))
    source = deck.source.model_copy(update={"updated_at": remote.source.updated_at if remote.source else None}) if deck.source else None
    services.decks.set_source(deck_id, source, remote.entries)
    services.source_cache.pop(deck_id, None)
    return {**_full(services, deck_id), "conflicts": conflicts}


@router.post("/decks/{deck_id}/source/ignore")
def ignore_source(deck_id: str, services: ServicesDep) -> dict[str, Any]:
    """Keep the local deck and acknowledge the current Archidekt version."""
    deck = _get(services, deck_id)
    remote = _remote(services, deck, refresh=False)
    source = deck.source.model_copy(update={"updated_at": remote.source.updated_at if remote.source else None}) if deck.source else None
    services.decks.set_source(deck_id, source, remote.entries)
    services.source_cache.pop(deck_id, None)
    return _full(services, deck_id)


@router.delete("/decks/{deck_id}/source", status_code=204)
def unlink_source(deck_id: str, services: ServicesDep) -> Response:
    _get(services, deck_id)
    services.decks.set_source(deck_id, None, None)
    return Response(status_code=204)


# ---------------------------------------------------------------------------- artwork cache


@router.post("/decks/{deck_id}/cache-art", status_code=202)
def cache_art(deck_id: str, services: ServicesDep) -> dict[str, Any]:
    """Download missing artwork for every card in the deck (and the tokens they make)."""
    deck = _get(services, deck_id)
    if not services.settings.allow_network:
        raise HTTPException(409, "Network access is disabled")
    ids = [e.printing_id for e in deck.entries if e.printing_id]
    job = services.jobs.start("cache-art", f"Artwork for {deck.name}", lambda progress: services.cache_artwork(ids, progress))
    return job.as_dict()


@router.get("/decks/{deck_id}/art-status")
def art_status(deck_id: str, services: ServicesDep) -> dict[str, Any]:
    deck = _get(services, deck_id)
    ids = [e.printing_id for e in deck.entries if e.printing_id]
    missing = [pid for pid in dict.fromkeys(ids) if not services.images.has(pid)]
    return {"printings": len(set(ids)), "missing": len(missing)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, services: ServicesDep) -> dict[str, Any]:
    job = services.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job.as_dict()
