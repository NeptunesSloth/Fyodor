"""Native discrete stickers: owner access, ticket payment, public persistence and layers (CR123)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

PUBLIC = frozenset({"battlefield", "graveyard", "exile", "command", "phased", "stack"})


def words(name: str) -> list[str]:
    """123.6a: a printed blank is not a word; punctuation/hyphens do not split words."""
    return [word for word in name.split() if word.strip("_")]


def available(plan: Plan, pid: str, kind: str | None = None) -> list[dict[str, Any]]:
    used = {
        placement.sticker.id
        for c in plan.state.cards.values()
        for placement in c.stickers101
        if placement.owner == pid
    }
    return [
        sticker.model_dump()
        for sheet in plan.state.players[pid].sticker_sheets101
        for sticker in sheet.stickers
        if sticker.id not in used and (kind is None or sticker.kind == kind)
    ]


def _find(state: GameState, pid: str, sticker_id: str) -> Any:
    return next(
        (
            sticker
            for sheet in state.players[pid].sticker_sheets101
            for sticker in sheet.stickers
            if sticker.id == sticker_id
        ),
        None,
    )


def problem(state: GameState, pid: str, cid: str, sticker_id: str, *, free: bool = False) -> str | None:
    card = state.cards.get(cid)
    if card is None or card.owner != pid:
        return "A sticker can be put only on an object you own"
    if card.zone.split(":")[-1] not in PUBLIC:
        return "A sticker cannot be retained in a hidden zone"
    sticker = _find(state, pid, sticker_id)
    if sticker is None:
        return "That sticker is not on an accessible sheet"
    if any(
        p.owner == pid and p.sticker.id == sticker_id for c in state.cards.values() for p in c.stickers101
    ):
        return "That discrete sticker is already on an object"
    if not free and state.players[pid].resources.get("ticket", 0) < sticker.cost:
        return "Not enough tickets for that sticker"
    return None


def can_place(plan: Plan, pid: str, cid: str, sticker_id: str, *, free: bool = False) -> bool:
    return problem(plan.state, pid, cid, sticker_id, free=free) is None


def place(
    plan: Plan, controller: str, cid: str, sticker_id: str, position: int = 0, *, free: bool = False
) -> None:
    from app.game.errors import ActionError

    if (message := problem(plan.state, controller, cid, sticker_id, free=free)) is not None:
        raise ActionError(message)
    if position > len(words(plan.ch(plan.state.cards[cid]).name)):
        raise ActionError("Choose a position in the current name")
    plan.do(
        {
            "type": "rules_sticker101",
            "card_id": cid,
            "sticker_id": sticker_id,
            "position": position,
            "free": free,
        },
        actor=controller,
    )


def apply_action(state: GameState, action: Any) -> None:
    """Ticket cost and application are atomic and replayable; definitions come from public sheets."""
    from app.game.errors import ActionError
    from app.game.state import StickerPlacement101

    pid = action.actor
    if (message := problem(state, pid, action.card_id, action.sticker_id, free=action.free)) is not None:
        raise ActionError(message)
    sticker = _find(state, pid, action.sticker_id)
    assert sticker is not None
    if not action.free:
        state.players[pid].resources["ticket"] = state.players[pid].resources.get("ticket", 0) - sticker.cost
    rules = state.rules
    if rules is not None:
        rules.timestamp += 1
    state.cards[action.card_id].stickers101.append(
        StickerPlacement101(
            sticker=sticker.model_copy(deep=True),
            owner=pid,
            position=action.position,
            object_seq=rules.next_object if rules is not None else state.seq,
            timestamp=rules.timestamp if rules is not None else state.seq,
        )
    )

    if rules is not None:
        from app.game.rules_state import emit

        rules.pin_collection110i = rules.pin_collection110i or state.cards[action.card_id].name == "Pin Collection"  # -- cards (wave 110I) --
        emit(
            state,
            "designation",
            counter="sticker101:" + sticker.kind,
            actor=pid,
            player=pid,
            card=action.card_id,
            object_id=rules.object_id(action.card_id),
            types=list(action.types101),
            sticker101={**sticker.model_dump(), "owner": pid, "position": action.position},
        )


def name_change(ch: Characteristics, text: str, position: int) -> Characteristics:
    from dataclasses import replace

    from app.rules.copying import renamed

    parts = words(ch.name)
    parts.insert(min(position, len(parts)), text)
    new = " ".join(parts)
    return replace(
        ch,
        name=new,
        oracle_text=renamed(ch.oracle_text, ch.name, new),
        abilities=tuple(
            replace(
                a,
                text=renamed(a.text, ch.name, new),
                cost=renamed(a.cost, ch.name, new) if a.cost else a.cost,
            )
            for a in ch.abilities
        ),
    )


def continuous(state: GameState, card: CardInstance, *, pt: bool = False) -> list[Any]:
    """Noncopiable native effects regenerated from the physical object's persistent markers."""
    from app.game.rules_state import ContinuousEffect
    from app.rules.oracle import parse_abilities

    out = []
    # -- cards (wave 110I) -- Pin Collection (613.1f): its equipped creature has all abilities of the ability stickers on the Equipment too.
    # ponytail: keyed by name (the only card with that text); a second card needs the text read from its static instead.
    equipment = [c for c in state.cards.values() if c.attached_to == card.id and c.name == "Pin Collection" and c.zone.endswith(":battlefield")] \
        if not pt and state.rules is not None and state.rules.pin_collection110i else []
    for source, placement in [(card, p) for p in card.stickers101] + [(c, p) for c in equipment for p in c.stickers101]:
        sticker = placement.sticker
        if sticker.kind != ("pt" if pt else "ability"):
            continue
        out.append(
            ContinuousEffect(
                id=f"sticker101:{placement.owner}:{sticker.id}" + ("" if source is card else ":equipped"),
                affected=[state.rules.object_id(card.id) if state.rules is not None else card.id],
                layer="7b" if pt else "6",
                source=None,
                controller=placement.owner,
                duration="permanent",
                timestamp=placement.timestamp,
                object_seq=placement.object_seq,
                power=sticker.power if pt else None,
                toughness=sticker.toughness if pt else None,
                add_abilities=[] if pt else [sticker.text],
                add_keywords=[]
                if pt
                else [
                    keyword
                    for ability in parse_abilities(sticker.text)
                    for keyword in ability.keywords
                    if keyword != "flanking"
                ],
                label=sticker.label,
            )
        )
    return out


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if (
        text
        == "~'s power is equal to the number of permanents you control with an art sticker plus the number of cards in your graveyard with an art sticker."
    ):
        return {
            "kind": "static",
            "static": "cda",
            "effects": [],
            "p": {"sticker_art_count101": True},
            "t": None,
        }
    return None


MOVERS = frozenset(
    {
        "destroy",
        "destroy_all",
        "exile",
        "sacrifice",
        "bounce",
        "return_card",
        "return_choice",
        "return_yours",
        "to_library",
        "shuffle_library",
        "delayed_move",
        "counter",
        "exile_until",
        "blink",
    }
)


def _retainers(card: CardInstance, dest: str, rest: str | None = None) -> list[str]:
    if dest not in PUBLIC or dest in ("battlefield", "phased", "stack"):
        return []
    if dest == "command" and rest in ("hand", "library"):
        return [part.id for part in card.merged if part.commander_key]
    return [part.id for part in card.merged]


def prepare_move(plan: Plan, payload: dict[str, Any]) -> dict[str, Any]:
    """Called after actual zone replacements, before the native move is recorded."""
    if payload.get("type") != "move":
        return payload
    recipients = dict(payload.get("sticker_recipients101") or {})
    for cid in payload.get("card_ids") or []:
        card = plan.state.cards.get(cid)
        if (
            card is None
            or not card.merged
            or not card.stickers101
            or not card.zone.endswith((":battlefield", ":phased"))
        ):
            continue
        target = (payload.get("routes") or {}).get(cid, payload.get("to") or {})
        dest = target.get("zone", "")
        options = _retainers(card, dest, payload.get("rest_zone"))
        if not options:
            continue
        oid = plan.oid(card)
        if plan.probe_stickers101 is not None:
            plan.probe_stickers101.append((cid, oid, options))
            recipients[cid] = options[0]  # Scratch look-ahead only, never a real default choice.
        elif oid in plan.rules.sticker_splits101:
            recipients[cid] = plan.rules.sticker_splits101.pop(oid)
        elif len(options) == 1:
            recipients[cid] = options[0]
    return {**payload, "sticker_recipients101": recipients} if recipients else payload


def _probe(plan: Plan) -> Plan:
    from app.rules.plan import Plan

    probe = Plan.__new__(Plan)
    probe.__dict__.update(plan.__dict__)
    probe.state = plan.state.model_copy(deep=True)
    probe.steps = list(plan.steps)
    probe.moved = dict(plan.moved)
    probe.began = dict(plan.began) if plan.began is not None else None
    probe.probe_stickers101 = []
    return probe


def _ask(plan: Plan, rows: list[tuple[str, str, list[str]]], ctx: dict[str, Any] | None) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    for cid, oid, options in rows:
        card = plan.state.cards.get(cid)
        if (
            card is None
            or plan.oid(card) != oid
            or not card.merged
            or len(options) < 2
            or oid in plan.rules.sticker_splits101
        ):
            continue
        labels = {part.id: part.name for part in card.merged}
        decide(
            plan,
            player=card.owner,
            kind="choose_one",
            prompt="Choose which resulting object retains all stickers (123.5c)",
            options=[DecisionOption(id=part, label=labels[part][:200]) for part in options],
            source=card,
            resume={"step": "sticker_split101", "card": cid, "object": oid, "ctx": ctx, "parts": options},
        )
        return True
    return False


def ask_first(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    if (
        plan.probe_stickers101 is not None
        or effect.get("do") not in MOVERS
        or not any(
            c.merged and c.stickers101 and c.zone.endswith(":battlefield") for c in plan.state.cards.values()
        )
    ):
        return False
    import copy

    from app.rules.effects import PRIMITIVES

    probe = _probe(plan)
    saved = copy.deepcopy(ctx)
    saved["next"] = int(saved.get("next") or 0) + 1
    try:
        PRIMITIVES[effect["do"]](probe, saved, copy.deepcopy(effect))
    except Exception:  # noqa: BLE001 -- Scratch preparation only; the real caller reports its own errors.
        return False
    return _ask(plan, probe.probe_stickers101 or [], ctx)


def ask_sba(plan: Plan, cards: list[str]) -> bool:
    if plan.probe_stickers101 is not None or not any(
        plan.state.cards[c].merged and plan.state.cards[c].stickers101 for c in cards
    ):
        return False
    probe = _probe(plan)
    try:
        probe.do({"type": "move", "card_ids": cards, "to": {"zone": "graveyard"}})
    except Exception:  # noqa: BLE001 -- Any other native replacement gets its existing choice first.
        return False
    return _ask(plan, probe.probe_stickers101 or [], None)


def resume_split(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects, engine

    data = decision.resume
    card = plan.state.cards.get(data["card"])
    if card is not None and plan.oid(card) == data["object"] and chosen[0] in data["parts"]:
        plan.rules.sticker_splits101[data["object"]] = chosen[0]
    if data.get("ctx") is not None:
        prior = plan.actor
        plan.actor = data["ctx"]["controller"]
        try:
            effects.continue_effects(plan, data["ctx"])
        finally:
            plan.actor = prior
    else:
        engine.advance(plan)


RESUME = {"sticker_split101": resume_split}
