from __future__ import annotations

from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import get_services, require_local
from app.cards import updater
from app.cards.downloader import DownloadError
from app.cards.images import IMAGE_SIZES, InvalidImageRequest
from app.services import Services

router = APIRouter(tags=["cards"])
ServicesDep = Annotated[Services, Depends(get_services)]


@router.get("/cards/stats")
def card_stats(services: ServicesDep) -> dict[str, Any]:
    return services.cards.stats()


@router.get("/cards/search")
def search_cards(
    services: ServicesDep,
    q: Annotated[str, Query(max_length=300)] = "",
    tokens: Literal["false", "true", "any"] = "false",
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> dict[str, Any]:
    want = {"false": False, "true": True, "any": None}[tokens]
    results = services.cards.search(q, tokens=want, limit=limit + 1, offset=offset)
    return {"results": results[:limit], "has_more": len(results) > limit}


@router.get("/cards/autocomplete")
def autocomplete(services: ServicesDep, q: Annotated[str, Query(max_length=100)] = "") -> list[str]:
    return services.cards.autocomplete(q)


class BatchRequest(BaseModel):
    ids: list[str] = Field(max_length=2000)


@router.post("/cards/batch")
def cards_batch(body: BatchRequest, services: ServicesDep) -> dict[str, Any]:
    return services.cards.get_many(body.ids)


@router.get("/cards/{card_id}")
def get_card(card_id: str, services: ServicesDep) -> dict[str, Any]:
    card = services.cards.get(card_id)
    if card is None:
        raise HTTPException(404, "Card not found")
    return card


@router.get("/cards/{card_id}/printings")
def get_printings(card_id: str, services: ServicesDep) -> list[dict[str, Any]]:
    card = services.cards.get(card_id)
    if card is None:
        raise HTTPException(404, "Card not found")
    return services.cards.printings(card["oracle_id"])


@router.get("/images/card-back", response_class=FileResponse)
def get_card_back(services: ServicesDep) -> FileResponse:
    """The Magic card back, once it's cached with the art (404 until then: tables draw their own back)."""
    path = services.images.card_back()
    if path is None:
        raise HTTPException(404, "Card back not cached")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})


@router.get("/images/{card_id}", response_class=FileResponse)
def get_image(
    card_id: str,
    services: ServicesDep,
    face: Annotated[int, Query(ge=0, le=3)] = 0,
    size: Annotated[str, Query(pattern="^(" + "|".join(IMAGE_SIZES) + ")$")] = "normal",
) -> FileResponse:
    try:
        path = services.images.find(card_id, face=face, size=size)
    except InvalidImageRequest as exc:
        raise HTTPException(400, str(exc)) from exc
    if path is None:
        raise HTTPException(404, "Image not cached")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})


# ---------------------------------------------------------------------------- UPDATE CARD DATABASE (host only)


def _needs_network(services: Services) -> None:
    if not services.settings.allow_network:
        raise HTTPException(409, "Network access is turned off on this computer (FYODOR_ALLOW_NETWORK=0)")


class ArtRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=50)


@router.post("/cards/cache-art", status_code=202)
def cache_card_art(body: ArtRequest, request: Request, services: ServicesDep) -> dict[str, Any]:
    """Download the missing art for these printings, as for a deck's (the Bag of Extras' common tokens): host only, online."""
    require_local(request)
    _needs_network(services)
    ids = list(dict.fromkeys(body.ids))
    job = services.jobs.start("cache-art", "Artwork for the Bag of Extras", lambda progress: services.cache_artwork(ids, progress))
    return job.as_dict()


@router.get("/card-data")
def card_data(request: Request, services: ServicesDep) -> dict[str, Any]:
    """The local card database and the latest update job, for Settings → Card database."""
    require_local(request)
    job = services.jobs.latest("card-update")
    return {"current": services.cards.stats(), "job": job.as_dict() if job else None,
            "network": services.settings.allow_network}


@router.post("/card-data/check")
def card_data_check(request: Request, services: ServicesDep) -> dict[str, Any]:
    """Ask Scryfall whether newer card data exists (one small request)."""
    require_local(request)
    _needs_network(services)
    try:
        return updater.check(services.settings, services.cards, client_factory=services.http_client)
    except (httpx.HTTPError, DownloadError) as exc:
        raise HTTPException(502, f"Couldn't reach Scryfall: {exc}") from exc


class CardUpdateIn(BaseModel):
    force: bool = False


@router.post("/card-data/update", status_code=202)
def card_data_update(request: Request, services: ServicesDep, body: CardUpdateIn | None = None) -> dict[str, Any]:
    """Download and switch to the newest card data in the background; poll GET /card-data for progress."""
    require_local(request)
    _needs_network(services)
    running = services.jobs.latest("card-update")
    if running is not None and running.state == "running":
        return running.as_dict()
    force = bool(body and body.force)
    job = services.jobs.start("card-update", "Card database", lambda progress: updater.update(
        services.settings, services.cards, progress, force=force, client_factory=services.http_client))
    return job.as_dict()
