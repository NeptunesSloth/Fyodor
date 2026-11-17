"""-- Teach Fyodor -- teaching the engine new mechanics and card lines from snap-together pieces (docs/TEACH_FYODOR.md).

Anyone at the table may read the library, the vocabulary and check a script; only the host computer changes the library (taught
entries apply to every game the host starts) or opens a "Try it" table. Entries are data checked against the vocabulary
(``app.rules.taught``), and only saved when the engine's own parser reads every ability they make.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import get_services, require_local
from app.rules import coverage, taught
from app.rules.oracle import strip_reminders
from app.rules.taught_vocab import vocabulary
from app.services import Services
from app.storage.taught import MAX_FILE_BYTES, TaughtNotFound

router = APIRouter(tags=["teach"])
ServicesDep = Annotated[Services, Depends(get_services)]


class EntryIn(BaseModel):
    entry: dict[str, Any]
    enabled: bool | None = None


class CheckIn(BaseModel):
    entry: dict[str, Any]
    type_line: str | None = Field(default=None, max_length=200)


class EnabledIn(BaseModel):
    enabled: bool


class TryIn(BaseModel):
    entry: dict[str, Any]
    card_id: str | None = Field(default=None, max_length=64)


@router.get("/teach/vocabulary")
def get_vocabulary() -> dict[str, Any]:
    return vocabulary()


@router.get("/teach")
def list_taught(services: ServicesDep) -> list[dict[str, Any]]:
    return services.taught.list_all()


@router.post("/teach/check")
def check_entry(body: CheckIn) -> dict[str, Any]:
    """What the pieces say, what's missing, and whether the engine reads it (nothing saved)."""
    result = taught.check(body.entry, type_line=body.type_line)
    result.pop("entry", None)
    return result


@router.post("/teach", status_code=201)
def create_taught(body: EntryIn, request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    try:
        return services.taught.save(body.entry, enabled=body.enabled)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/teach/{entry_id}")
def update_taught(entry_id: str, body: EntryIn, request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    try:
        return services.taught.save(body.entry, entry_id=entry_id, enabled=body.enabled)
    except TaughtNotFound:
        raise HTTPException(404, "Nothing taught with that id") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.patch("/teach/{entry_id}")
def enable_taught(entry_id: str, body: EnabledIn, request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    try:
        return services.taught.set_enabled(entry_id, body.enabled)
    except TaughtNotFound:
        raise HTTPException(404, "Nothing taught with that id") from None


@router.delete("/teach/{entry_id}", status_code=204)
def delete_taught(entry_id: str, request: Request, services: ServicesDep) -> Response:
    require_local(request)
    try:
        services.taught.delete(entry_id)
    except TaughtNotFound:
        raise HTTPException(404, "Nothing taught with that id") from None
    return Response(status_code=204)


@router.get("/teach/export")
def export_taught(services: ServicesDep, ids: Annotated[list[str] | None, Query(max_length=500)] = None) -> Response:
    """The library (or some of it) as a small JSON file to share with the pod."""
    data = services.taught.export(ids)
    name = "fyodor-taught.json" if not ids or len(data["entries"]) != 1 else re.sub(r"[^A-Za-z0-9-]+", "-", data["entries"][0]["name"]).strip("-").lower() + ".fyodor-teach.json"
    return Response(json.dumps(data, indent=1), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name or "fyodor-taught.json"}"'})


@router.post("/teach/import")
async def import_taught(request: Request, services: ServicesDep) -> dict[str, Any]:
    """A shared file: every entry checked against the vocabulary and the engine; anything unexpected refuses the whole file."""
    require_local(request)
    raw = await request.body()
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(413, "That file is too big to be a Teach Fyodor file")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(422, "Not a Teach Fyodor file") from None
    try:
        return services.taught.import_file(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _card(services: Services, card_id: str) -> dict[str, Any]:
    if not services.cards.available:
        raise HTTPException(409, "Import the card database first")
    data = services.cards.get(card_id)
    if data is None:
        raise HTTPException(404, "No such card")
    return data


_KEYWORDISH = re.compile(r"([A-Z][a-z'\-]+(?: [a-z'\-]+)?)(?: (\d{1,2}|X))?")


@router.get("/teach/card/{card_id}")
def card_lines(card_id: str, services: ServicesDep) -> dict[str, Any]:
    """One card's Oracle lines: which ones the engine plays by itself, which are manual, which are taught (and its coverage now)."""
    data = _card(services, card_id)
    before = coverage.of_card_data(data)
    library = [r["entry"] for r in services.taught.list_all() if r["enabled"]]
    after = coverage.of_card_data(taught.apply(data, library) or data)
    manual = set(before.manual_parts)
    faces = data.get("faces") if (data.get("faces") and len(data["faces"]) > 1) else [data]
    taught_lines = {r["entry"]["line"]: r["id"] for r in services.taught.list_all()
                    if r["kind"] == "card" and r["oracle_id"] == data.get("oracle_id")}
    keywords = {r["name"].lower(): r["id"] for r in services.taught.list_all() if r["kind"] == "keyword"}
    out = []
    for face in faces:
        for raw in str(face.get("oracle_text") or "").split("\n"):
            line = strip_reminders(raw).strip()
            if not line:
                continue
            kw = _KEYWORDISH.fullmatch(line.rstrip("."))
            out.append({"text": line, "face": face.get("name") or data.get("name"), "type_line": face.get("type_line") or data.get("type_line"),
                        "manual": line in manual or any(line in m for m in manual),
                        "taught_id": taught_lines.get(line) or (keywords.get(kw[1].lower()) if kw else None),
                        "keyword": ({"name": kw[1], "param": kw[2] is not None} if kw and line in manual else None)})
    return {"card": {"id": data["id"], "name": data.get("name"), "oracle_id": data.get("oracle_id"), "type_line": data.get("type_line"),
                     "has_script": _has_script(data)},
            "level": before.level, "level_taught": after.level, "lines": out}


def _has_script(data: dict[str, Any]) -> bool:
    from app.rules import cards as scripts

    return scripts.get(data.get("oracle_id")) is not None


# -------------------------------------------------------------------------------------------------------------- Try it
_FILLER = ("Grizzly Bears", "Llanowar Elves", "Runeclaw Bear", "Elvish Mystic", "Savannah Lions", "Memnite")
_STAND_IN = ("Grizzly Bears", "Runeclaw Bear", "Savannah Lions", "Llanowar Elves", "Memnite")
_BASICS = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}


def _resolve_first(services: Services, names: tuple[str, ...]) -> dict[str, Any] | None:
    for name in names:
        card = services.cards.resolve(name)
        if card is not None:
            return card
    return None


def _keyword_card(services: Services, entry: dict[str, Any]) -> dict[str, Any] | None:
    """A card in the database with the taught keyword on it, if there is one."""
    try:
        found = services.cards.search(f'o:"{entry["name"]}"', limit=40)
    except Exception:  # (an odd name in the full-text query: no hit, a stand-in plays it)
        return None
    for hit in found:
        data = services.cards.get(hit["id"])
        if data is not None and taught.apply(data, [entry]) is not data:
            return data
    return None


@router.post("/teach/try", status_code=201)
def try_it(body: TryIn, request: Request, services: ServicesDep) -> dict[str, Any]:
    """A test table: your card (or a stand-in creature with the keyword) in hand, lands to cast it, a library to mill and a
    target dummy, rules automation on — the taught ability works as it will in a game."""
    require_local(request)
    from app.api.games import _create_room
    from app.game.factory import DeckCard, PlayerSetup, new_game
    from app.game.mulligan import resolve_policy
    from app.game.session import GameSession
    from app.game.state import GameSettings

    if not services.cards.available:
        raise HTTPException(409, "Import the card database first")
    try:
        entry = services.taught.checked(body.entry)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    stand_in = None
    if body.card_id:
        card = _card(services, body.card_id)
    elif entry["kind"] == "card":
        pid = services.cards.default_printing_id(entry["oracle_id"])
        card = _card(services, pid) if pid else None
    else:
        card = _keyword_card(services, entry)
        if card is None:
            card = _resolve_first(services, _STAND_IN)
            if card is not None:
                text = f"{entry['name']} 2" if entry.get("param") else entry["name"]
                stand_in = {"kind": "stand_in", "card_id": card["id"], "oracle_text": text}
    if card is None:
        raise HTTPException(404, "No card to try it on")
    others = [r["entry"] for r in services.taught.list_all() if r["enabled"] and taught.match_key_of(r["entry"]) != taught.match_key_of(entry)]
    filler = next((f for f in (services.cards.resolve(n) for n in _FILLER) if f is not None and f["id"] != card["id"]), None)  # (not the card itself)
    colors = [c for c in (card.get("color_identity") or card.get("colors") or []) if c in _BASICS] or ["G"]
    lands = [services.cards.resolve(_BASICS[c]) for c in colors]
    cards = [DeckCard("main", 1, card["name"], card["id"])]
    if filler is not None:
        cards.append(DeckCard("main", 12, filler["name"], filler["id"]))
    per = max(2, 8 // len(lands))
    cards += [DeckCard("main", per, land["name"], land["id"]) for land in lands if land is not None]
    settings = GameSettings(starting_life=40, deck_privacy="private", allow_test_objects=True, mulligan=resolve_policy("none"))
    state = new_game([PlayerSetup(name="You", deck_name=f"Try {entry['name']}", cards=cards)], name=f"Try it — {entry['name']}",
                     format="sandbox", settings=settings, shuffle=False, related_tokens=services.related_tokens)
    state.taught = [*others, entry, *([stand_in] if stand_in else [])]  # (this table only: the entry being built, saved or not)
    session = GameSession(state, cards=services.cards, history_limit=services.settings.history_limit, rules=services.rules)
    session.perform("p1", {"type": "add_dummy"}, trusted=True, host=True)
    ids = [c.id for c in state.cards.values() if c.owner == "p1"]
    test = next(c for c in state.cards.values() if c.owner == "p1" and c.card_id == card["id"])
    session.perform("p1", {"type": "move", "card_ids": [test.id], "to": {"zone": "hand"}}, trusted=True, host=True)
    land_ids = [c for c in ids if session.state.cards[c].card_id in {land["id"] for land in lands if land}]
    session.perform("p1", {"type": "move", "card_ids": land_ids, "to": {"player": "p1", "zone": "battlefield"}}, trusted=True, host=True)
    session.perform("p1", {"type": "configure", "automation": "full"}, trusted=True, host=True)
    for _ in range(3):  # into the first main phase, so the card can be cast at once
        if session.state.turn.phase.startswith("main") or session.state.rules is None:
            break
        try:
            session.perform("p1", {"type": "pass_priority"}, trusted=True, host=True)
        except Exception:  # noqa: BLE001 (a prompt in the way: the player takes it from here)
            break
    note = f" {card['name']} plays as a card with {stand_in['oracle_text']} here." if stand_in else ""
    session.notice(f"Try it: {entry['name']}.{note} Cast it and watch Fyodor play the taught ability.")
    return _create_room(services, session, "lan", None, "p1")
