"""Rules-engine information over HTTP: what is automated, per card and for the pod's decks."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.api.deps import get_services, require_local
from app.rules import coverage, inventory
from app.services import Services

router = APIRouter(tags=["rules"])
ServicesDep = Annotated[Services, Depends(get_services)]
MAX_IDS = 250


@router.get("/rules/support")
def support() -> dict[str, Any]:
    """Engine features and keywords that are automated today (everything else is manual)."""
    return {"features": sorted(coverage.SUPPORTED), "keywords": sorted(coverage.SUPPORTED_KEYWORDS)}


def _ids(raw: str | None) -> list[str]:
    ids = [x.strip() for x in (raw or "").split(",") if x.strip()]
    if len(ids) > MAX_IDS:
        raise HTTPException(422, f"At most {MAX_IDS} cards per request")
    return ids


@router.get("/rules/coverage")
def card_coverage(services: ServicesDep,
                  card_ids: Annotated[str | None, Query(max_length=20000)] = None,
                  oracle_ids: Annotated[str | None, Query(max_length=20000)] = None) -> dict[str, Any]:
    """FULL / PARTIAL / MANUAL (and the manual parts) for printings or Oracle cards. Card data is
    public, so any player may ask."""
    out: dict[str, Any] = {}
    for cid in _ids(card_ids):
        data = services.cards.get(cid)
        if data is not None:
            out[cid] = coverage.of_card_data(data).as_dict()
    for oid in _ids(oracle_ids):
        pid = services.cards.default_printing_id(oid)
        data = services.cards.get(pid) if pid else None
        if data is not None:
            out[oid] = coverage.of_card_data(data).as_dict()
    return out


def _latest_games(services: Services) -> list[tuple[str, Any]]:
    games: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for save in services.saves.list_all():  # newest first
        if save["game_id"] in seen:
            continue
        seen.add(save["game_id"])
        try:
            state, _ = services.saves.load(save["id"], history_limit=1)
        except Exception:  # noqa: BLE001 - an unreadable save shouldn't stop the report
            continue
        games.append((save["game_id"], state))
    return games


def build_report(services: Services) -> dict[str, Any]:
    inv = inventory.build(services.decks.list_all(), _latest_games(services), services.cards)
    return inv.report()


@router.get("/rules/inventory", dependencies=[Depends(require_local)])
def pod_inventory(services: ServicesDep) -> dict[str, Any]:
    """The pod card inventory from the host's deck library and saved games (host computer only)."""
    return build_report(services)


@router.get("/rules/inventory.md", dependencies=[Depends(require_local)], response_class=PlainTextResponse)
def pod_inventory_markdown(services: ServicesDep) -> PlainTextResponse:
    return PlainTextResponse(inventory.markdown(build_report(services)), media_type="text/markdown; charset=utf-8")
