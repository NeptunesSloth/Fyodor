"""-- Room doors (wave 110D) -- "unlock a locked door of a Room you control" (Ghostly Dancers, 709.5f) and "Lock or unlock a door of target Room you
control" (Marina Vendrell, 709.5f-g). The door is chosen as the effect resolves; unlocking goes through rooms.unlock (709.5h triggers fire)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

DANCERS = "When this creature enters, return an enchantment card from your graveyard to your hand or unlock a locked door of a Room you control."
MARINA = "{T}: Lock or unlock a door of target Room you control. Activate only as a sorcery."
_SIDE = {1: "left", 2: "right"}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text == DANCERS:
        d = scripts.define(replace(ability, text="When this creature enters, draw a card."), ch)
        if d is not None:
            d["effects"] = [{"do": "dancers110d"}]
        return d
    if ability.text == MARINA:
        d = scripts.define(replace(ability, text="{T}: Tap target Room you control. Activate only as a sorcery."), ch)
        if d is not None:
            d["effects"] = [{"do": "door110d", "src": "target"}]
        return d
    return None


def _ask(plan: Any, ctx: dict[str, Any], options: list[Any], prompt: str, step: str, extra: dict[str, Any]) -> bool:
    from app.rules import effects

    if not options:
        return True
    effects.decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'Room'}: {prompt}", options=options,
                   min_choices=1, max_choices=1, resume={"step": step, "ctx": ctx, "ids": [o.id for o in options], **extra})
    return False


def dancers(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import rooms

    me = ctx["controller"]
    opts = [DecisionOption(id=c.id, label=f"Return {c.name} to your hand", card_id=c.id) for c in plan.state.cards.values()
            if c.zone == f"{me}:graveyard" and "Enchantment" in plan.ch(c).types]
    for c in plan.state.cards.values():
        if c.zone.endswith(":battlefield") and c.controller == me and plan.ch(c).doors is not None:
            have = rooms.doors_of(plan, c.id)
            opts += [DecisionOption(id=f"{c.id}|{n}", label=f"Unlock the {_SIDE[n]} door of {c.name}", card_id=c.id) for n in (1, 2) if n not in have]
    return _ask(plan, ctx, opts, "return an enchantment card or unlock a door?", "dancers110d", {})


def door(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects, rooms

    rooms_ = [c for c in effects._cards(plan, ctx, e["src"]) if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")]
    if not rooms_ or plan.ch(plan.state.cards[rooms_[0]]).doors is None:
        return True  # (608.2b: the target is gone or no longer a Room)
    c = plan.state.cards[rooms_[0]]
    have = rooms.doors_of(plan, c.id)
    opts = [DecisionOption(id=f"{c.id}|{n}", label=f"{'Lock' if n in have else 'Unlock'} the {_SIDE[n]} door of {c.name}", card_id=c.id) for n in (1, 2)]
    return _ask(plan, ctx, opts, "lock or unlock which door?", "door110d", {})


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects, rooms

    if len(chosen) != 1 or chosen[0] not in d.resume["ids"]:
        raise ActionError("Choose one of those options")
    pick = chosen[0]
    if "|" not in pick:  # return: an enchantment card from the graveyard
        effects._return_to_hands(plan, [pick], d.player)
    else:
        cid, n = pick.split("|")
        if int(n) in rooms.doors_of(plan, cid):  # 709.5g: lock = lose the designation
            plan.rules.unlocked[plan.oid(cid)] = [x for x in rooms.doors_of(plan, cid) if x != int(n)]
        else:
            rooms.unlock(plan, cid, int(n))
    effects.continue_effects(plan, d.resume["ctx"])


PRIMITIVES: dict[str, Any] = {"dancers110d": dancers, "door110d": door}
RESUME: dict[str, Any] = {"dancers110d": resume, "door110d": resume}
