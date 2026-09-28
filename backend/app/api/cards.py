from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import get_services
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
