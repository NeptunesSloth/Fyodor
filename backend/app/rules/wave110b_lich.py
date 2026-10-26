"""-- (wave 110B) -- Havengul Lich: "{1}: You may cast target creature card in a graveyard this turn. When you cast it this turn, this creature gains all
activated abilities of that card until end of turn."

* 603.7a: the cast is a delayed trigger, created as the ability resolves and watching for that one card (it triggers once, 603.7b).
* Ruling 2019-10-04: the Lich gains the activated abilities of the card as it existed in the graveyard while it is still a spell on the stack: they are read
  once, when the trigger resolves, and last until end of turn (613.1f layer 6) even after the spell becomes a permanent.
* Ruling 2011-01-22: nothing is gained if the card isn't cast that turn.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
TEXT = ("You may cast target creature card in a graveyard this turn. When you cast it this turn, this creature gains all activated abilities of that "
        "card until end of turn.")
_LINKED = re.compile(r"\bchosen\b|\bnoted\b|exiled with|\bnamed\b|\bchoose\b", re.I)  # 607.5: linked to something the lender holds: never automated


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    if body.strip().replace("~ gains", "this creature gains") != TEXT:
        return None
    first = scripts.parse_effects(TEXT.split(". When")[0] + ".")
    if first is None:
        return None
    return [*first[0], {"do": "lich_watch110b"}], first[1], False  # (the grant_play effect asks "may" itself)


def watch(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import delayed
    from app.rules.effects import _cards

    cards = _cards(plan, ctx, "target")
    if cards:
        cond = {"event": "cast", "subject": "player", "player": "you", "spell": 'sel:{"zones":["stack"]}', "card110b": cards[0]}
        head = {"kind": "watch", "cond": cond, "text": "you cast the targeted card"}
        wrapped = delayed.wrap_when([{"do": "lich_borrow110b"}], head, this_turn=True)
        wrapped[0]["once"] = True
        ctx["effects"][ctx["next"]:ctx["next"]] = wrapped
    return True


def borrow(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import abilities_of, context, layers

    me = plan.state.cards.get(ctx.get("source_card") or "")
    spells = [plan.state.cards[c] for c in context.objects(plan, ctx, context.EVENT) if plan.state.cards[c].zone == "stack"]
    if me is None or not me.zone.endswith(":battlefield") or plan.oid(me) != ctx.get("source_object") or not spells:
        return True
    lent = abilities_of._lent(plan, spells[0], no_mana=False)
    texts = tuple(a.text for a in lent if not _LINKED.search(a.text.partition(":")[2]))
    for a in lent:
        if _LINKED.search(a.text.partition(":")[2]):
            plan.note(f"{me.name}: \"{a.text}\" refers to a choice of {spells[0].name}; use it by hand")
    if texts:
        layers.add_effect(plan, affected=[plan.oid(me)], layer="6", source=ctx.get("source_object"), controller=ctx["controller"],
                          add_abilities=texts, duration="end_of_turn", label=f"activated abilities of {spells[0].name} (Havengul Lich)")
    return True


PRIMITIVES = {"lich_watch110b": watch, "lich_borrow110b": borrow}
