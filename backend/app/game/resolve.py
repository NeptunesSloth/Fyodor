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
from app.game.state import STACK, BattlefieldRow, GameState, TokenDef, zone_key
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
    # (-- big boards (playtest B3) -- the rules engine's own rules_sync carries a fresh dump of the rules state that nothing else holds:
    # copying it deep again cost as much as the intent's own work on a big table)
    a = action.model_copy() if trusted and action.type == "rules_sync" else action.model_copy(deep=True)
    a.actor = actor
    a.ts = time.time()
    _resolve_placeholders(state, a, actor)
    if hasattr(a, "r"):
        a.r = None  # never trust client-supplied resolution data
    if hasattr(a, "opening"):
        a.opening = None
    if hasattr(a, "keep_ids") and not trusted:
        a.keep_ids = False  # -- review (face-down ids) -- only the rules engine defers the renumbering (Plan.renumber_face_down)
    if isinstance(a, A.CreateToken) and not trusted:  # -- engine token art -- a picture passed on is the engine's (a token copy's), never a client's
        _clear_art(a.token)
    if isinstance(a, A.RevealTop) and not trusted:  # -- public reveals -- the notice's words (the source, "until … found") are the engine's only
        a.source, a.until, a.found = None, False, False  # (a manual reveal is plain: no client text reaches the log or the notice)
    if isinstance(a, A.CopyCard) and a.saved_stack is not None and not trusted:
        raise ActionError("Only the rules engine can copy a preserved spell")
    if isinstance(a, A.ResponseOpen):
        raise ActionError("Response checks are opened by the server")
    if a.type in A.SERVER_ONLY_TYPES and not trusted:
        raise ActionError("Only the rules engine can do that")
    if a.type in ("phase", "next_turn") and not trusted and _out_of_the_game(state, actor):
        # 104.3a / 104.5 / 800.4a: a player who conceded or lost has left the game; the players still in it
        # move the turn on (their own intents are refused in compile_intent). Checked here, not in engine.apply,
        # so recorded history from before this check still replays; the engine's own steps (trusted) still
        # end the turn of an active player who just left.
        from app.game.out_of_game import refusal  # (one wording with the session's check, which runs first)

        raise ActionError(refusal(state, actor, a.type) or "You have left this game: the players still in it move the turn and its steps")
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
        if a.stacked and state.rules is not None and state.settings.automation != "off":
            a.stacked = False  # -- token stacks (gap 2) -- the rules count, tap and sacrifice tokens one object each (app/rules/token_stacks.py)
        if a.quantity is not None:  # -- engine token stacks -- only the rules engine makes one (docs/TOKEN_STACKS.md)
            if not trusted:
                raise ActionError("Only the rules engine makes a token stack this way")
            a.stacked, a.count = True, 1
        if not a.stacked and a.count > A.MAX_SEPARATE_TOKENS:  # -- big token counts -- more than that is one card ×N
            raise ActionError(_too_many(state, f"{a.count:,} tokens", A.MAX_SEPARATE_TOKENS))
        a.r = A.NewIds(ids=[new_id() for _ in range(1 if a.stacked else a.count)])
        a.resolved_token = _token_def(a.token, info, _source_printing(state, a.source_id, actor))
        if a.x is None or a.y is None:
            pid = a.player or actor
            a.x, a.y = placement.free_spot(state, zone_key(pid, "battlefield"), placement.row_for(a.resolved_token.type_line))
    elif isinstance(a, A.CopyCard | A.CreateAbility):
        count = a.count if isinstance(a, A.CopyCard) else 1
        if isinstance(a, A.CopyCard):  # -- big token counts -- one card standing for many copies, made by hand
            if a.stacked:
                if state.rules is not None and state.settings.automation != "off":
                    raise ActionError(_too_many(state, f"{a.count:,} copies", A.MAX_SEPARATE_COPIES))
                if a.saved_stack is not None or a.last_known or a.zone is not None:
                    raise ActionError("Only a copy on the battlefield can be a stack")
                count = 1
            elif a.count > A.MAX_SEPARATE_COPIES:
                raise ActionError(_too_many(state, f"{a.count:,} copies", A.MAX_SEPARATE_COPIES))
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
        from app.rules.token_stacks import (
            INDIVIDUAL_LIMIT,  # -- engine token stacks -- never one object per token for a huge stack
        )

        if card is not None and card.quantity > INDIVIDUAL_LIMIT and state.rules is not None and state.settings.automation != "off":
            raise ActionError(f"{card.name} ×{card.quantity:,} is too big to spread into separate tokens with rules automation on "
                              f"(at most {INDIVIDUAL_LIMIT}): split some off instead")
        a.r = A.NewIds(ids=[new_id() for _ in range(max(0, (card.quantity if card else 1) - 1))])
    elif isinstance(a, A.Roll):
        if not trusted:  # (only the rules engine ignores rolls: a player's own table roll is shown as rolled)
            a.ignore_lowest, a.because = 0, None
        a.r = A.DiceData(results=[_rng_int(rng, 1, a.sides) for _ in range(a.count)])
    elif isinstance(a, A.Coin):
        a.r = A.DiceData(results=[_rng_int(rng, 0, 1) for _ in range(a.count)])
    elif isinstance(a, A.Cannon):  # -- table toys -- every die's number and who it is fired at (app/game/handlers/toys.py)
        from app.game.handlers.toys import resolve_cannon

        a.r = resolve_cannon(state, a, actor, lambda lo, hi: _rng_int(rng, lo, hi))
    elif isinstance(a, A.BagDraw):  # -- table toys -- which chit, at random (the bag's contents never leave the server)
        if not state.bag.chits:
            raise ActionError("The draw bag is empty")
        a.r = A.BagDrawData(index=_rng_int(rng, 0, len(state.bag.chits) - 1))
    elif isinstance(a, A.PlanarRollAction):  # -- planechase -- the planar die's face (app/game/handlers/planechase.py)
        from app.game.handlers import planechase

        if (why := planechase.roll_refusal(state, actor)) is not None:
            raise ActionError(why)
        a.r = A.PlanarRollData(face=planechase.face_of(_rng_int(rng, 1, planechase.DIE_FACES)))
    elif isinstance(a, A.PlanarStart):  # -- planechase -- a new planar deck, dealt from the card database's planes
        from app.game.handlers import planechase

        a.r = A.PlanarDeckData(cards=planechase.deal(planechase.pool_of(info), a.count, a.phenomena, rng))
    elif isinstance(a, A.PlanarDeckOp) and a.r is None:  # -- planechase deck (wave D) -- a random order, decided here (app/rules/planar_deck.py)
        pc = state.planechase
        size = len(a.random) if a.op == "arrange" else max(0, len(pc.deck) - pc.face_count) if a.op == "shuffle" and pc is not None else 0
        perm = list(range(size))
        rng.shuffle(perm)
        a.r = A.PlanarDeckOpData(perm=perm)
    elif isinstance(a, A.Merge | A.Meld):
        a.r = A.NewIds(ids=[new_id()])
    elif isinstance(a, A.SetFace):
        card = state.cards.get(a.card_id)
        data = info.get(card.card_id) if card and card.card_id else None
        faces = len(data.get("faces") or []) if data else 0
        a.faces = max(1, faces or 2)
    elif isinstance(a, A.Move):
        a.r = _resolve_move(state, a, actor, info)
    elif isinstance(a, A.SetPosition):
        a.learned_rows = _learned_rows(state, a, actor, info) or None
    elif isinstance(a, A.ResolveTop):
        a.r = _resolve_top(state, info, a.card_id, (a.x, a.y) if a.x is not None and a.y is not None else None)
    elif isinstance(a, A.RevealUntil | A.Cascade):
        a.r = _dig(state, a, actor, info)
    elif isinstance(a, A.LoadDeck | A.AddBot):  # (-- test opponent -- its deck, as LoadDeck's)
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
            inner.x, inner.y = placement.free_spot(state, zone_key(pid, "battlefield"),
                                                   placement.entry_row(state, pid, card, _face_type(info.get(card.card_id) if card.card_id else None, 0)))
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
    if isinstance(a, A.RestartGame) and a.first is None:  # (Karn Liberated's restart is an engine step: its own plan goes on, 727)
        a.opening = _first_turn_steps(state, a, info, rng)
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


def _first_turn_steps(state: GameState, a: A.RestartGame, info: CardInfo, rng: Any) -> list[dict[str, Any]] | None:
    """-- first turn (S7) -- a restart (Start over) with the rules on and no mulligans: the steps that carry the new game past its first
    untap step (502.4: no priority there), compiled against the table as the restart leaves it (app/rules/engine.py compile_first_turn).
    A restart that deals opening hands again leaves a pregame: its end does it instead (opening_hand.finish)."""
    if state.rules is None or state.settings.automation == "off":
        return None
    from app.game.engine import apply
    from app.rules.engine import compile_first_turn

    sim = state.model_copy(deep=True)
    try:
        apply(sim, a)
    except ActionError:
        return None  # (the real application raises the same error)
    return compile_first_turn(sim, info, rng)


def _out_of_the_game(state: GameState, actor: str) -> bool:
    """With rules automation on, whether ``actor`` conceded or lost (a dormant rules state doesn't count)."""
    r = state.rules
    return state.settings.automation != "off" and r is not None and (actor in r.conceded or actor in r.lost)


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


def _source_printing(state: GameState, source_id: str | None, actor: str) -> str | None:
    """-- engine token art -- the printing of the card that made a token (its Scryfall related tokens picture it first), when every
    player can see that card (a face-down or hidden source's printing would show through the picture chosen)."""
    if not source_id:
        return None
    from app.game import ops

    source = state.cards.get(resolve_placeholder(state, source_id, actor))
    return source.card_id if source is not None and not source.face_down and ops.visible_to_all_players(state, source) else None


def _clear_art(spec: A.TokenSpec) -> None:
    while spec is not None:
        spec.art_id, spec.art_face = None, 0
        spec = spec.back


def _token_art(spec: A.TokenSpec, info: CardInfo, source_printing: str | None) -> dict[str, Any]:
    """-- engine token art -- a described token's picture: the matching token printing (app/cards/token_match.py), looked up once
    here so the recorded action keeps it (replays, undo and saves show the same picture whatever the card database says later). A
    picture the engine passes on (a token copy of a pictured token: the copied token's own, ``spec.art_id``) comes first."""
    if spec.art_id and info.get(spec.art_id) is not None:
        return {"art_id": spec.art_id, "art_face": spec.art_face}
    find = getattr(info, "token_art", None)
    if find is None:
        return {}
    try:
        found = find(source_printing, spec.name, spec.type_line, spec.power, spec.toughness, list(spec.colors))
    except Exception:  # noqa: BLE001 - a picture is a nicety: no card database (or a broken one) leaves the token's proxy
        return {}
    return {"art_id": found[0], "art_face": found[1]} if found else {}


def _token_def(spec: A.TokenSpec, info: CardInfo, source_printing: str | None = None) -> TokenDef:
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
        back=_token_def(spec.back, info, source_printing) if spec.back is not None else None,  # -- wave 3F -- a double-faced token (111.10i)
        **_token_art(spec, info, source_printing),
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
        spot = placement.free_spot(state, key, placement.entry_row(state, pid, card, type_line, face_down=bool(a.face_down)), taken)
        taken.append(spot)
        data.positions[cid] = spot
    return data


def _learned_rows(state: GameState, a: A.SetPosition, actor: str, info: CardInfo) -> dict[str, BattlefieldRow | None]:
    """-- saved rows -- a player who drags their own permanent from one row into another (a mana rock into the lands, a
    creature-land among the lands) teaches its deck where that card goes: decided here, where card data is at hand, and recorded
    on the action so replay never needs it. Back in its type's row, the lesson is forgotten. Nudges within a row teach nothing,
    and neither does a batch of lands alone: "Tidy my lands" (frontend game/tidy.ts) piles them upward from the near edge, and
    a big mana base's upper piles reach the creature row's height without anyone choosing that row for them."""
    learned: dict[str, BattlefieldRow | None] = {}
    key = zone_key(actor, "battlefield")
    if len(a.moves) > 1 and all((c := state.cards.get(cid)) is not None and placement.row_for(
            _face_type(info.get(c.card_id) if c.card_id else None, c.face)) == "land" for cid, _x, _y in a.moves):
        return learned
    rows = state.players[actor].row_overrides if actor in state.players else {}
    for cid, _x, y in a.moves:
        card = state.cards.get(cid)
        if card is None or card.zone != key or card.owner != actor or card.attached_to or not placement.learns_row(card):
            continue
        row = placement.row_at(y)
        if row == placement.row_at(card.y):
            continue
        default = placement.row_for(_face_type(info.get(card.card_id) if card.card_id else None, 0))
        want = None if row == default else row
        if rows.get(card.name) != want:
            learned[card.name] = want
    return learned


def _resolve_top(state: GameState, info: CardInfo, card_id: str | None = None, at: tuple[float, float] | None = None) -> A.MoveData:
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
        data.positions[top.id] = at if at is not None else placement.free_spot(state, key, placement.entry_row(state, top.controller, top, type_line))
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


def _too_many(state: GameState, what: str, limit: int) -> str:
    """-- big token counts -- the refusal for more separate objects than one action makes."""
    if state.rules is not None and state.settings.automation != "off":
        return (f"{what} is too many to make by hand while rules automation is on: each one is its own object, at most {limit:,} at a time. "
                "Pause automation to make them as one card ×N.")
    return f"{what} is more than {limit:,} separate cards: make them as one card ×N (a token stack)."
