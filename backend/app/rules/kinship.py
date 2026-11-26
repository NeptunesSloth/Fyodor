"""-- kinship (wave 9C) -- "At the beginning of your upkeep, you may look at the top card of your library. If it shares a
creature type with this creature, you may reveal it. If you do, [effect]." (Wolf-Skull Shaman, Winnower Patrol, …).
Researched against CR 2026-09-25.

* 701.20e — looking at a card shows it to the looking player alone; 701.20a/b — revealing shows it to every player and
  leaves it where it is (kinship never moves the card).
* 205.3m / 702.73a — a creature type is a subtype shared by creatures and kindreds; a changeling is every creature type
  everywhere (its derived subtypes hold them all, characteristics.changeling), so it shares with any card that has one.
* 207.2c — "Kinship" is an ability word with no rules meaning.

The look is the controller's private choice, and so is the reveal, which only a card that shares a creature type can be
revealed for. Both are asked whatever the top card is, so nobody learns from whether a question appeared that the card
shares a type (the hidden-information rule of top_library.private_gate); an empty library has no top card: nothing to
look at. "If you do" is the reveal: the instructions after it happen only when the card was revealed.
"""

from __future__ import annotations

import re
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import Plan, decide

_BODY = re.compile(r"^(?:[Yy]ou may )?look at the top card of your library\. If it shares a creature type with "
                   r"(?:this creature|~), you may reveal it\. If you do, (?P<rest>.+)$")


def split(body: str) -> str | None:
    """The "If you do" instructions of a kinship ability's text, or None."""
    m = _BODY.match(body.strip())
    return m["rest"] if m else None


def bind(then: tuple[list[dict[str, Any]], Any, bool] | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The kinship effects: the look-and-reveal step, then the instructions behind its "If you do" gate."""
    if then is None:
        return None
    effects, groups, optional = then
    if groups or optional or not effects:
        return None  # (no targets and nothing optional of its own in what the reveal enables)
    flag = "kinship"
    return [{"do": "kinship", "flag": flag}, {"do": "only_if", "cond": {"flag": flag}, "skip": len(effects)},
            *effects], None, False


def shares(plan: Plan, top: str, source_card: str | None) -> bool:
    from app.rules.creature_types import CREATURE_TYPES

    src = plan.state.cards.get(source_card or "")
    if src is None:
        return False
    mine = plan.ch(src).subtypes & CREATURE_TYPES
    return bool(mine & plan.ch(plan.state.cards[top]).subtypes)


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Ask whether to look; then (the look is private) whether to reveal. False while a decision is open."""
    from app.rules import context

    me = ctx["controller"]
    library = plan.state.zones.get(f"{me}:library", [])
    if not library:
        context.bind_flag(ctx, e["flag"], False)
        return True
    decide(plan, player=me, kind="choose_cards", prompt="Look at the top card of your library?",
           options=[DecisionOption(id="look", label="Look at it")], min_choices=0, max_choices=1,
           resume={"step": "kinship_look", "ctx": ctx, "e": e})
    return False


def resume_look(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    me = ctx["controller"]
    library = plan.state.zones.get(f"{me}:library", [])
    if not chosen or not library:
        context.bind_flag(ctx, e["flag"], False)
        continue_effects(plan, ctx)
        return
    top = library[0]
    plan.do({"type": "look_top", "player": me, "count": 1}, actor=me)  # 701.20e: shown to the looking player alone
    can = shares(plan, top, ctx.get("source_card"))
    decide(plan, player=me, kind="choose_cards",
           prompt=f"{plan.state.cards[top].name or 'The card'} is on top of your library. Reveal it?",
           # (playtest nov 18: the card is shown either way, an answer only when it shares a type — top_library's looked-at cards)
           options=[DecisionOption(id=top, label=plan.state.cards[top].name or "Card", card_id=top)] if can else [],
           min_choices=0, max_choices=1 if can else 0, resume={"step": "kinship_reveal", "ctx": ctx, "e": e, "top": top},
           display={"kind": "looked", "cards": [top], "ineligible": "shares no creature type", **({"take": "Reveal it"} if can else {})})


def resume_reveal(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    me = ctx["controller"]
    top = d.resume["top"]
    ok = bool(chosen) and plan.state.zones.get(f"{me}:library", [])[:1] == [top]
    if ok:
        plan.do({"type": "reveal", "card_ids": [top]}, actor=me)  # 701.20a: to everyone; it stays on top (701.20b)
        ctx["looked"], ctx["looked_owner"] = [top], me  # -- turn state (wave 100H) -- "that card" (Leaf-Crowned Elder's free play)
    context.bind_flag(ctx, e["flag"], ok)
    continue_effects(plan, ctx)
