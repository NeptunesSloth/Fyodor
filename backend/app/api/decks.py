from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import PlainTextResponse

from app.api.deps import get_services
from app.decks import service
from app.decks.models import DeckImportRequest, DeckIn
from app.decks.parser import DeckTextTooLarge, format_deck_text
from app.decks.repository import DeckNotFound
from app.services import Services

router = APIRouter(tags=["decks"])
ServicesDep = Annotated[Services, Depends(get_services)]


def _full(services: Services, deck_id: str) -> dict[str, Any]:
    try:
        deck = services.decks.get(deck_id)
    except DeckNotFound:
        raise HTTPException(404, "Deck not found") from None
    data = service.deck_cards(deck, services.cards)
    return {
        **deck.model_dump(),
        "summary": service.summarize(deck, data),
        "warnings": [w.model_dump() for w in service.validate(deck, services.cards, data)],
    }


@router.get("/decks")
def list_decks(services: ServicesDep) -> list[dict[str, Any]]:
    decks = services.decks.list()
    ids = [e.printing_id for d in decks for e in d.entries if e.printing_id and e.section == "commander"]
    ids += [next((e.printing_id for e in d.entries if e.printing_id), "") for d in decks]
    data = services.cards.get_many([i for i in ids if i]) if services.cards.available else {}
    return [service.summarize(d, data) for d in decks]


@router.post("/decks/parse")
def parse_preview(body: DeckImportRequest, services: ServicesDep) -> dict[str, Any]:
    """Parse and resolve deck text without saving (import preview)."""
    try:
        parsed, entries, unresolved = service.import_text(body.text, services.cards)
    except DeckTextTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    return {
        "name": parsed.name,
        "entries": [e.model_dump() for e in entries],
        "unresolved": [u.model_dump() for u in unresolved],
        "errors": parsed.errors,
        "notes": parsed.notes,
    }


@router.post("/decks", status_code=201)
def create_deck(body: DeckImportRequest, services: ServicesDep) -> dict[str, Any]:
    """Create a deck, optionally importing its list from text."""
    entries = []
    parsed_name = None
    report: dict[str, Any] = {"unresolved": [], "errors": [], "notes": []}
    if body.text.strip():
        try:
            parsed, entries, unresolved = service.import_text(body.text, services.cards)
        except DeckTextTooLarge as exc:
            raise HTTPException(413, str(exc)) from exc
        parsed_name = parsed.name
        report = {"unresolved": [u.model_dump() for u in unresolved], "errors": parsed.errors, "notes": parsed.notes}
    commanders = [e.name for e in entries if e.section == "commander"]
    name = body.name or parsed_name or (" & ".join(commanders) if commanders else None) or (
        "Imported deck" if entries else "New deck"
    )
    deck = services.decks.create(DeckIn(name=name, format=body.format or "commander", entries=entries))
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
    return _full(services, deck_id)


@router.post("/decks/{deck_id}/import")
def import_into_deck(deck_id: str, body: DeckImportRequest, services: ServicesDep) -> dict[str, Any]:
    try:
        deck = services.decks.get(deck_id)
        parsed, entries, unresolved = service.import_text(body.text, services.cards)
    except DeckNotFound:
        raise HTTPException(404, "Deck not found") from None
    except DeckTextTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    new_entries = (deck.entries + entries) if body.mode == "append" else entries
    services.decks.update(
        deck_id,
        DeckIn(name=body.name or deck.name, format=body.format or deck.format, notes=deck.notes, entries=new_entries[:1000]),
    )
    report = {"unresolved": [u.model_dump() for u in unresolved], "errors": parsed.errors, "notes": parsed.notes}
    return {**_full(services, deck_id), "import_report": report}


@router.post("/decks/{deck_id}/duplicate", status_code=201)
def duplicate_deck(deck_id: str, services: ServicesDep) -> dict[str, Any]:
    try:
        deck = services.decks.get(deck_id)
    except DeckNotFound:
        raise HTTPException(404, "Deck not found") from None
    copy = services.decks.create(
        DeckIn(name=f"{deck.name} (copy)"[:120], format=deck.format, notes=deck.notes, entries=deck.entries)
    )
    return _full(services, copy.id)


@router.delete("/decks/{deck_id}", status_code=204)
def delete_deck(deck_id: str, services: ServicesDep) -> Response:
    try:
        services.decks.delete(deck_id)
    except DeckNotFound:
        raise HTTPException(404, "Deck not found") from None
    return Response(status_code=204)


@router.get("/decks/{deck_id}/export", response_class=PlainTextResponse)
def export_deck(deck_id: str, services: ServicesDep) -> str:
    try:
        deck = services.decks.get(deck_id)
    except DeckNotFound:
        raise HTTPException(404, "Deck not found") from None
    return format_deck_text([e.model_dump() for e in deck.entries])
