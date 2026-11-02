"""Pod statistics: readable by everyone at the table; corrections only on the host computer."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

from app.api.deps import get_services, require_local
from app.services import Services
from app.stats.repository import ResultError, ResultNotFound
from app.textutil import clean_text

router = APIRouter(tags=["pod"])
ServicesDep = Annotated[Services, Depends(get_services)]


class ResultEdit(BaseModel):
    result_type: Literal["single", "multiple", "draw", "no_result"] | None = None
    winners: list[str] | None = Field(default=None, max_length=6)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("notes")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return None if v is None else clean_text(v, 500, multiline=True)


@router.get("/pod/players")
def pod_players(services: ServicesDep) -> list[dict[str, Any]]:
    return services.stats.players()


@router.get("/pod/players/{player_id}")
def pod_player(player_id: str, services: ServicesDep) -> dict[str, Any]:
    try:
        return services.stats.player(player_id)
    except ResultNotFound:
        raise HTTPException(404, "No such player") from None


@router.get("/pod/results")
def pod_results(services: ServicesDep, limit: Annotated[int, Query(ge=1, le=1000)] = 100) -> list[dict[str, Any]]:
    return services.stats.history(limit=limit)


@router.get("/pod/results/{result_id}")
def pod_result(result_id: str, services: ServicesDep) -> dict[str, Any]:
    """One recorded game (-- pod history -- the session recap opens its final board from here)."""
    try:
        return services.stats.get(result_id)
    except ResultNotFound:
        raise HTTPException(404, "No such result") from None


@router.put("/pod/results/{result_id}")
async def edit_result(result_id: str, body: ResultEdit, request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    try:
        result = services.stats.edit(result_id, result_type=body.result_type, winners=body.winners, notes=body.notes)
    except ResultNotFound:
        raise HTTPException(404, "No such result") from None
    except ResultError as exc:
        raise HTTPException(422, str(exc)) from exc
    return result


@router.delete("/pod/results/{result_id}", status_code=204)
async def delete_result(result_id: str, request: Request, services: ServicesDep) -> Response:
    require_local(request)
    try:
        game_id = services.stats.get(result_id)["game_id"]
        services.stats.delete(result_id)
    except ResultNotFound:
        raise HTTPException(404, "No such result") from None
    room = services.hub.get(game_id.split("#", 1)[0])  # later games of a night are "<table>#<n>"
    if room is not None and room.night.result_key(room.id) == game_id:
        room.result_id = None  # the game can be recorded again
        night = room.night
        if night.result is not None:  # -- final board -- an erroneous result is taken back: the table opens again
            night.history = [h for h in night.history if h.get("number") != night.number]
            night.result, night.votes, night.last_winner_key = None, {}, None
        services.hub.persist(room)
        await services.hub.broadcast(room)
    return Response(status_code=204)


@router.get("/pod/export")
def export_stats(request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    return services.stats.export()
