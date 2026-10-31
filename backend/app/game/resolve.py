"""Turns client intents into deterministic, replayable actions.

This is the only place that uses randomness or consults the card database. Everything it
decides (shuffle orders, dice results, new ids, default placements, resolution
destinations) is recorded on the action so that ``engine.apply`` stays pure.
"""

from __future__ import annotations

import re
import secrets
import time
from typing import TYPE_CHECKING, Any, Protocol

from app.game import actions as A
from app.game import placement
from app.game.errors import ActionError
from app.game.handlers import response
from app.game.state import STACK, GameState, TokenDef, zone_key
from app.game.views import resolve_placeholder

if TYPE_CHECKING:
    from app.game.rules_state import ObjectRef

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
            trusted: bool = False, shuffle_retained: tuple[ObjectRef, ...] = ()) -> A.Action:
    """Return a copy of ``action`` with server-owned fields filled in."""
    info = cards or NoCardInfo()
    a = action.model_copy(deep=True)
    a.actor = actor
    a.ts = time.time()
    _resolve_placeholders(state, a, actor)
    if hasattr(a, "r"):
        a.r = None  # never trust client-supplied resolution data
    if hasattr(a, "opening"):
        a.opening = None
    if hasattr(a, "keep_ids") and not trusted:
        a.keep_ids = False  # -- review (face-down ids) -- only the rules engine defers the renumbering (Plan.renumber_face_down)
    if isinstance(a, A.CopyCard) and a.saved_stack is not None and not trusted:
        raise ActionError("Only the rules engine can copy a preserved spell")
    if isinstance(a, A.ResponseOpen):
        raise ActionError("Response checks are opened by the server")
    if a.type in A.SERVER_ONLY_TYPES and not trusted:
        raise ActionError("Only the rules engine can do that")
    if a.type in A.INTENT_TYPES:
        from app.rules.engine import compile_intent  # rules → game; imported late to stay acyclic

        a.r = compile_intent(state, a, actor=actor, info=info, rng=rng)  # type: ignore[union-attr]
        return a
    if isinstance(a, A.RulesSticker101):
        from app.rules import characteristics, layers

        current = state.cards.get(a.card_id)
        if current is None:
            raise ActionError('The sticker recipient is unavailable')
        a.types101 = sorted(layers.derive(state, current, characteristics.of(current, info), info).types)
        return a
    if isinstance(a, A.Configure):
        from app.rules.reconcile import compile_reconcile, needs_reconcile  # rules → game; imported late

        if needs_reconcile(state, a):
            a.r = compile_reconcile(state, a, actor=actor, info=info, rng=rng)
    if isinstance(a, A.RestoreState) and not trusted:
        raise ActionError("Restoring is done through snapshots or history")

    if isinstance(a, A.Shuffle):
        pid = a.player or actor
        pool = list(a.card_ids) if a.card_ids is not None else list(state.zones.get(zone_key(pid, a.zone), []))
        retained = {ref.card for ref in shuffle_retained if a.zone == 'library' and a.card_ids is None
                    and state.rules is not None and (card := state.cards.get(ref.card)) is not None
                    and card.zone == ref.zone == zone_key(pid, 'library') and state.rules.object_id(card.id) == ref.object_id}
        indices = [index for index, cid in enumerate(pool) if cid in retained]
        a.r = shuffle_data(len(pool) - len(indices), rng)
        a.r.retained_indices = indices
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

        a.r = {pid: shuffle_data(library_size_after_reset(state, pid, set(a.keep)), rng) for pid in state.seat_order}
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
    elif isinstance(a, A.Merge | A.Meld):
        a.r = A.NewIds(ids=[new_id()])
    elif isinstance(a, A.SetFace):
        card = state.cards.get(a.card_id)
        data = info.get(card.card_id) if card and card.card_id else None
        faces = len(data.get("faces") or []) if data else 0
        a.faces = max(1, faces or 2)
    elif isinstance(a, A.Move):
        a.r = _resolve_move(state, a, actor, info)
    elif isinstance(a, A.ResolveTop):
        a.r = _resolve_top(state, info, a.card_id)
    elif isinstance(a, A.RevealUntil | A.Cascade):
        a.r = _dig(state, a, actor, info)
    elif isinstance(a, A.LoadDeck):
        # a fresh id for every card, and the library's shuffle (over the main deck's cards)
        main = sum(c.quantity for c in a.cards if c.section == "main")
        perm = list(range(main))
        rng.shuffle(perm)
        a.r = A.LoadDeckData(ids=[new_id() for _ in range(sum(c.quantity for c in a.cards if c.section in _DECK_ZONES))], perm=perm)
    elif isinstance(a, A.FetchCard):
        pid = a.player or actor
        library_ids = state.zones.get(zone_key(pid, "library"), [])
        want = a.name.strip().lower()
        found = next((cid for cid in library_ids if (state.cards[cid].name or "").lower() == want), None)
        if found is None:
            raise ActionError(f"There's no {a.name.strip()} in that library")
        inner = A.Move(card_ids=[found], to=A.ZoneRef(zone=a.to, player=pid if a.to == "battlefield" else None), actor=actor, ts=a.ts)
        if a.to == "battlefield":
            card = state.cards[found]
            inner.x, inner.y = placement.free_spot(state, zone_key(pid, "battlefield"), placement.row_for(_face_type(info.get(card.card_id) if card.card_id else None, 0)))
        inner.r = _resolve_move(state, inner, actor, info)
        a.r = A.FetchData(move=inner, shuffle=shuffle_data(len(library_ids) - 1, rng))
    elif isinstance(a, A.DiscardRandom):
        pid = a.player or actor
        in_hand = list(state.zones.get(zone_key(pid, "hand"), []))
        if not in_hand:
            raise ActionError("That hand is empty")
        picked = rng.sample(in_hand, min(a.count, len(in_hand)))
        inner = A.Move(card_ids=picked, to=A.ZoneRef(zone="graveyard"), actor=actor, ts=a.ts)
        inner.r = _resolve_move(state, inner, actor, info)
        a.r = inner
    elif isinstance(a, A.PutTopFaceDown):
        top_ids = state.zones.get(zone_key(a.player or actor, "library"), [])[: a.count]
        spots: list[tuple[float, float]] = []
        for _ in top_ids:
            spots.append(placement.free_spot(state, zone_key(actor, "battlefield"), "creature", spots))
        a.r = A.MoveData(positions=dict(zip(top_ids, spots, strict=True)))
    if isinstance(a, A.MulliganPowder):  # -- opening hand (wave 18C) -- 103.5b
        from app.rules.opening_hand import powder_ok

        card = state.cards.get(a.card_id)
        data = info.get(card.card_id) if card is not None and card.card_id else None
        a.verified = powder_ok(data)
    if isinstance(a, A.MulliganKeep | A.MulliganBottom | A.MulliganFinish):
        a.opening = _opening_steps(state, a, info, rng)
    return response.wrap(state, a)


_DECK_ZONES = ("commander", "companion", "main", "sideboard", "attractions")


def _has_type(type_line: str, wanted: str) -> bool:
    """Does a type line include this card type, supertype or subtype ("Creature", "Basic Land", "Elf")?"""
    return re.search(rf"(?<![A-Za-z]){re.escape(wanted.strip())}(?![A-Za-z])", type_line, re.IGNORECASE) is not None


def _dig(state: GameState, a: A.RevealUntil | A.Cascade, actor: str, info: CardInfo) -> A.DigData:
    """How far down the library the reveal goes: up to and including the first card that qualifies (the card
    database knows types and mana values; the client never sees the library)."""
    pid = a.player or actor
    lib = state.zones.get(zone_key(pid, "library"), [])
    if not lib:
        raise ActionError("That library is empty")
    count, hit = len(lib), False
    for i, cid in enumerate(lib):
        card = state.cards[cid]
        data = info.get(card.card_id) if card.card_id else None
        line = _face_type(data, 0)
        if isinstance(a, A.RevealUntil):
            ok = _has_type(line, a.card_type)
        else:  # 702.85a: a nonland card with lesser mana value
            ok = bool(line) and not _has_type(line.split("—")[0], "Land") and float((data or {}).get("cmc") or 0) < a.below
        if ok:
            count, hit = i + 1, True
            break
    move = None
    if isinstance(a, A.Cascade):
        move = A.Move(card_ids=list(lib[:count]), to=A.ZoneRef(zone="exile", player=pid), actor=actor, ts=a.ts)
        move.r = _resolve_move(state, move, actor, info)
    return A.DigData(count=count, hit=hit, move=move)


def _opening_steps(state: GameState, a: A.MulliganKeep | A.MulliganBottom | A.MulliganFinish, info: CardInfo,
                   rng: Any) -> list[dict[str, Any]] | None:
    """-- opening hand (wave 18C) -- 103.6: if this action ends the mulligans, the first opening-hand decision, compiled against
    the table as the action leaves it (app/rules/opening_hand.py)."""
    if state.rules is None or state.settings.automation == "off" or state.pregame is None or state.pregame.finished:
        return None
    from app.game.engine import apply
    from app.rules.engine import compile_opening

    sim = state.model_copy(deep=True)
    try:
        apply(sim, a)
    except ActionError:
        return None  # (the real application raises the same error)
    if sim.pregame is None or not sim.pregame.finished:
        return None
    return compile_opening(sim, a.actor, info, rng)


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
        mana_cost=spec.mana_cost,  # (wave 49D)
        back=_token_def(spec.back, info) if spec.back is not None else None,  # -- wave 3F -- a double-faced token (111.10i)
    )


def _resolve_move(state: GameState, a: A.Move, actor: str, info: CardInfo) -> A.MoveData:
    data = A.MoveData()
    if (a.to.zone != "battlefield" and not a.routes) or (a.x is not None and a.y is not None):
        return data
    taken: list[tuple[float, float]] = []
    for cid in a.card_ids:
        card = state.cards.get(cid)
        if card is None:
            continue
        route = (a.routes or {}).get(cid, a.to)
        if route.zone != "battlefield":
            continue
        pid = (a.controllers or {}).get(cid) or route.player or actor
        key = zone_key(pid, "battlefield")
        if card.zone == key:
            continue
        type_line = card.token.type_line if card.token else _face_type(info.get(card.card_id) if card.card_id else None, 0)
        spot = placement.free_spot(state, key, placement.row_for(type_line), taken)
        taken.append(spot)
        data.positions[cid] = spot
    return data


def _resolve_top(state: GameState, info: CardInfo, card_id: str | None = None) -> A.MoveData:
    stack = state.zones.get(STACK, [])
    data = A.MoveData()
    if not stack:
        return data
    top = state.cards[card_id if card_id in stack else stack[-1]]  # (card_id: wave 3R5, 608.2g)
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
