"""Macro library over HTTP. Readable by everyone at the table; editable from the host computer
or by a seated player (trusted pod). Definitions are validated declarative data."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, ValidationError

from app.api.deps import get_services, is_local_request
from app.game.macros import MacroDef
from app.services import Services
from app.storage.macros import MacroNotFound

router = APIRouter(tags=["macros"])
ServicesDep = Annotated[Services, Depends(get_services)]


class MacroIn(BaseModel):
    scope: Literal["card", "library"] = "library"
    oracle_id: str | None = Field(default=None, max_length=64)
    definition: MacroDef


def _may_edit(request: Request, services: Services, token: str | None) -> None:
    if is_local_request(request):
        return
    if token and any(r.seat_for_token(token) not in (None, "__spectator__") for r in services.hub.rooms.values()):
        return
    raise HTTPException(403, "Join a table first")


@router.get("/macros")
def list_macros(services: ServicesDep, oracle_id: Annotated[str | None, Query(max_length=64)] = None) -> list[dict[str, Any]]:
    return services.macros.list_all(oracle_id)


@router.post("/macros", status_code=201)
def create_macro(body: MacroIn, request: Request, services: ServicesDep,
                 x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _may_edit(request, services, x_seat_token)
    try:
        return services.macros.save(body.definition, scope=body.scope, oracle_id=body.oracle_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/macros/{macro_id}")
def update_macro(macro_id: str, body: MacroIn, request: Request, services: ServicesDep,
                 x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _may_edit(request, services, x_seat_token)
    try:
        return services.macros.save(body.definition, scope=body.scope, oracle_id=body.oracle_id, macro_id=macro_id)
    except MacroNotFound:
        raise HTTPException(404, "No such macro") from None
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/macros/{macro_id}", status_code=204)
def delete_macro(macro_id: str, request: Request, services: ServicesDep,
                 x_seat_token: Annotated[str | None, Header()] = None) -> Response:
    _may_edit(request, services, x_seat_token)
    try:
        services.macros.delete(macro_id)
    except MacroNotFound:
        raise HTTPException(404, "No such macro") from None
    return Response(status_code=204)
