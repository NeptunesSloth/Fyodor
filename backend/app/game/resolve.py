"""Turns client intents into deterministic, replayable actions.

This is the only place that uses randomness or consults the card database. Everything it
decides (shuffle orders, dice results, new ids, default placements, resolution
destinations) is recorded on the action so that ``engine.apply`` stays pure.
"""

from __future__ import annotations

import secrets
import time
from typing import Any, Protocol

from app.game import actions as A
from app.game import placement
from app.game.errors import ActionError
from app.game.handlers import response
from app.game.state import STACK, GameState, TokenDef, zone_key
from app.game.views import resolve_placeholder

_rng = secrets.SystemRandom()


class CardInfo(Protocol):
    def get(self, card_id: str) -> dict[str, Any] | None: ...


class NoCardInfo:
    def get(self, card_id: str) -> dict[str, Any] | None:
        return None


def new_id() -> str:
    return secrets.token_hex(6)


def shuffle_data(size: int, rng: Any = _rng) -> A.ShuffleData:
    perm = list(range(size))
    rng.shuffle(perm)
    return A.ShuffleData(perm=perm, new_ids=[new_id() for _ in range(size)])


def _face_type(info: dict[str, Any] | None, face: int) -> str:
    if not info:
        return ""
    faces = info.get("faces") or []
    if faces and info.get("layout") in ("adventure", "split", "flip", "modal_dfc", "transform", "prepare"):
        return str(faces[min(face, len(faces) - 1)].get("type_line") or "")
    return str(info.get("type_line") or "")


def resolve(state: GameState, action: A.Action, *, actor: str, cards: CardInfo | None = None, rng: Any = _rng,
            trusted: bool = False) -> A.Action:
    """Return a copy of ``action`` with server-owned fields filled in."""
    info = cards or NoCardInfo()
    a = action.model_copy(deep=True)
    a.actor = actor
    a.ts = time.time()
    _resolve_placeholders(state, a, actor)
    if hasattr(a, "r"):
        a.r = None  # never trust client-supplied resolution data
    if isinstance(a, A.ResponseOpen):
        raise ActionError("Response checks are opened by the server")
    if a.type in A.SERVER_ONLY_TYPES and not trusted:
        raise ActionError("Only the rules engine can do that")
    if a.type in A.INTENT_TYPES:
        from app.rules.engine import compile_intent  # rules → game; imported late to stay acyclic

        a.r = compile_intent(state, a, actor=actor, info=info, rng=rng)  # type: ignore[union-attr]
        return a
    if isinstance(a, A.Configure):
        from app.rules.reconcile import compile_reconcile, needs_reconcile  # rules → game; imported late

        if needs_reconcile(state, a):
            a.r = compile_reconcile(state, a, actor=actor, info=info, rng=rng)
    if isinstance(a, A.RestoreState) and not trusted:
        raise ActionError("Restoring is done through snapshots or history")

    if isinstance(a, A.Shuffle):
        pid = a.player or actor
        a.r = shuffle_data(len(state.zones.get(zone_key(pid, a.zone), [])), rng)
    elif isinstance(a, A.Mulligan):
        pid = a.player or actor
        size = len(state.zones.get(zone_key(pid, "library"), [])) + len(state.zones.get(zone_key(pid, "hand"), []))
        a.r = shuffle_data(size, rng)
    elif isinstance(a, A.MulliganTake):
        policy = state.settings.mulligan
        if policy is not None and policy.shuffle_between_mulligans:
            pid = a.player or actor
            returned = len(a.card_ids) if a.card_ids is not None else len(state.zones.get(zone_key(pid, "hand"), []))
            lib = len(state.zones.get(zone_key(pid, "library"), []))
            a.r = shuffle_data(lib if policy.set_aside_rejected_hands else lib + returned, rng)
    elif isinstance(a, A.MulliganKeep | A.MulliganBottom):
        policy = state.settings.mulligan
        pid = a.player or actor
        aside = len(state.zones.get(zone_key(pid, "setaside"), []))
        if policy is not None and policy.final_shuffle and aside:
            lib = len(state.zones.get(zone_key(pid, "library"), []))
            bottomed = len(a.card_ids) if isinstance(a, A.MulliganBottom) else 0
            a.r = shuffle_data(lib + aside + bottomed, rng)
    elif isinstance(a, A.SearchEnd):
        key = state.searching(actor)
        if a.shuffle and key:
            a.r = shuffle_data(len(state.zones.get(key, [])), rng)
    elif isinstance(a, A.CreateToken):
        a.stacked = a.stacked if a.stacked is not None else a.count > 3
        a.r = A.NewIds(ids=[new_id() for _ in range(1 if a.stacked else a.count)])
        a.resolved_token = _token_def(a.token, info)
        if a.x is None or a.y is None:
            pid = a.player or actor
            a.x, a.y = placement.free_spot(state, zone_key(pid, "battlefield"), placement.row_for(a.resolved_token.type_line))
    elif isinstance(a, A.CopyCard | A.CreateAbility):
        count = a.count if isinstance(a, A.CopyCard) else 1
        a.r = A.NewIds(ids=[new_id() for _ in range(count)])
    elif isinstance(a, A.SpawnCard):
        data = info.get(a.card_id)
        a.resolved_name = str(data["name"]) if data else None
        a.r = A.NewIds(ids=[new_id()])
    elif isinstance(a, A.ResetDeck):
        from app.game.handlers.solo import library_size_after_reset

        a.r = shuffle_data(library_size_after_reset(state, a.player or actor), rng)
    elif isinstance(a, A.RestartGame):
        from app.game.handlers.solo import library_size_after_reset

        a.r = {pid: shuffle_data(library_size_after_reset(state, pid), rng) for pid in state.seat_order}
    elif isinstance(a, A.RunMacro):
        a.r = _resolve_macro(state, a, actor, info, rng)
    elif isinstance(a, A.AddEffect):
        a.r = A.NewIds(ids=[new_id() for _ in a.card_ids])
    elif isinstance(a, A.CreateArrow | A.Group | A.SplitStack):
        a.r = A.NewIds(ids=[new_id()])
    elif isinstance(a, A.ExpandStack):
        card = state.cards.get(a.card_id)
        a.r = A.NewIds(ids=[new_id() for _ in range(max(0, (card.quantity if card else 1) - 1))])
    elif isinstance(a, A.Roll):
        a.r = A.DiceData(results=[_rng_int(rng, 1, a.sides) for _ in range(a.count)])
    elif isinstance(a, A.Coin):
        a.r = A.DiceData(results=[_rng_int(rng, 0, 1) for _ in range(a.count)])
    elif isinstance(a, A.SetFace):
        card = state.cards.get(a.card_id)
        data = info.get(card.card_id) if card and card.card_id else None
        faces = len(data.get("faces") or []) if data else 0
        a.faces = max(1, faces or 2)
    elif isinstance(a, A.Move):
        a.r = _resolve_move(state, a, actor, info)
    elif isinstance(a, A.ResolveTop):
        a.r = _resolve_top(state, info)
    elif isinstance(a, A.PutTopFaceDown):
        top_ids = state.zones.get(zone_key(a.player or actor, "library"), [])[: a.count]
        spots: list[tuple[float, float]] = []
        for _ in top_ids:
            spots.append(placement.free_spot(state, zone_key(actor, "battlefield"), "creature", spots))
        a.r = A.MoveData(positions=dict(zip(top_ids, spots, strict=True)))
    return response.wrap(state, a)


ID_FIELDS = ("card_id", "to", "attacker_id", "source_id")


def _resolve_placeholders(state: GameState, a: A.Action, actor: str) -> None:
    """Replace anonymous placeholder ids the client used with the real card ids."""
    ids = getattr(a, "card_ids", None)
    if isinstance(ids, list):
        a.card_ids = [resolve_placeholder(state, cid, actor) for cid in ids]  # type: ignore[union-attr]
    for name in ID_FIELDS:
        value = getattr(a, name, None)
        if isinstance(value, str):
            setattr(a, name, resolve_placeholder(state, value, actor))


def _rng_int(rng: Any, lo: int, hi: int) -> int:
    return int(rng.randint(lo, hi))


def _token_def(spec: A.TokenSpec, info: CardInfo) -> TokenDef:
    if spec.card_id:
        data = info.get(spec.card_id)
        if data is None:
            raise ActionError("Unknown token card")
        faces = data.get("faces") or []
        front = faces[0] if faces else data
        return TokenDef(
            name=str(front.get("name") or data["name"]),
            card_id=data["id"],
            power=front.get("power"),
            toughness=front.get("toughness"),
            colors=list(front.get("colors") or data.get("colors") or []),
            type_line=str(front.get("type_line") or data.get("type_line") or "Token"),
            text=str(front.get("oracle_text") or ""),
        )
    return TokenDef(
        name=spec.name,
        power=spec.power,
        toughness=spec.toughness,
        colors=list(spec.colors),
        type_line=spec.type_line,
        text=spec.text,
    )


def _resolve_move(state: GameState, a: A.Move, actor: str, info: CardInfo) -> A.MoveData:
    data = A.MoveData()
    if a.to.zone != "battlefield" or (a.x is not None and a.y is not None):
        return data
    taken: list[tuple[float, float]] = []
    for cid in a.card_ids:
        card = state.cards.get(cid)
        if card is None:
            continue
        pid = a.to.player or actor
        key = zone_key(pid, "battlefield")
        if card.zone == key:
            continue
        type_line = card.token.type_line if card.token else _face_type(info.get(card.card_id) if card.card_id else None, 0)
        spot = placement.free_spot(state, key, placement.row_for(type_line), taken)
        taken.append(spot)
        data.positions[cid] = spot
    return data


def _resolve_top(state: GameState, info: CardInfo) -> A.MoveData:
    stack = state.zones.get(STACK, [])
    data = A.MoveData()
    if not stack:
        return data
    top = state.cards[stack[-1]]
    if top.ability is not None:
        data.destinations[top.id] = "delete"
        return data
    type_line = top.token.type_line if top.token else _face_type(info.get(top.card_id) if top.card_id else None, top.face)
    if "Adventure" in type_line:
        data.destinations[top.id] = zone_key(top.owner, "exile")
    elif "Instant" in type_line or "Sorcery" in type_line:
        data.destinations[top.id] = zone_key(top.owner, "graveyard")
    else:
        key = zone_key(top.controller, "battlefield")
        data.destinations[top.id] = key
        data.positions[top.id] = placement.free_spot(state, key, placement.row_for(type_line))
    return data


def _resolve_macro(state: GameState, a: A.RunMacro, actor: str, info: CardInfo, rng: Any) -> list[dict[str, Any]]:
    """Expand the macro and resolve its steps one after another on a scratch copy of the table,
    so every step sees what the previous ones did (new token ids, moved cards, …)."""
    from app.game import engine  # engine → handlers; imported late to keep modules acyclic
    from app.game.macros import MacroError, expand

    try:
        payloads = expand(a.macro, actor=actor, order=state.seat_order, this=a.card_id, selected=list(a.selected))
    except MacroError as exc:
        raise ActionError(f"{a.macro.name}: {exc}") from exc
    scratch = state.model_copy(deep=True)
    steps: list[dict[str, Any]] = []
    for payload in payloads:
        child = A.parse_action(payload)
        resolved = resolve(scratch, child, actor=actor, cards=info, rng=rng)
        engine.apply(scratch, resolved)
        steps.append(resolved.model_dump(mode="json"))
    return steps
