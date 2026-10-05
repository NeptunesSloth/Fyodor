"""-- if you do (wave 25C) -- "At the beginning of each player's upkeep, that player may choose any number of tapped nongreen creatures they
control and pay {2} for each creature chosen this way. If the player does, untap those creatures." (Dream Tides, Mudslide, Magnetic
Mountain, Thelon's Curse), researched against CR 2026-09-25.

* 118.12 / 608.2d: the player the step is about (the trigger's player) chooses, as it resolves, which of their tapped creatures of that
  kind to pay for — none, some or all — and then is offered the total ({2} for each: the cost repeated once per creature, 118.12: paid in
  full or not at all, 118.3). Choosing creatures and paying are two steps; a player who chooses more than they can pay is simply not offered
  the payment (``optional_payment`` offers it only while it is payable) and nothing is untapped.
* "If the player does": the payment was made (608.2c). The creatures are the ones chosen, still the same objects (400.7).
* Public information only: tapped creatures are on the table, so no decision hides anything.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
STEP = "pay_untap"
_CHOOSE = re.compile(r"^that player may choose any number of tapped (?P<sel>[^.]+?) they control and pay "
                     r"(?P<cost>(?:\{[^}]+\})+) for each creature chosen this way$", re.IGNORECASE)
_THEN = re.compile(r"^if the player does, untap those creatures$", re.IGNORECASE)


def sentences(texts: list[str], i: int) -> tuple[list[dict[str, Any]], int] | None:
    """The two sentences above as one instruction, with how many sentences it read (None: not this wording)."""
    from app.rules import selectors

    m = _CHOOSE.match(texts[i].rstrip(".").strip())
    if m is None or i + 1 >= len(texts) or _THEN.match(texts[i + 1].rstrip(".").strip()) is None:
        return None
    sel = selectors.parse(f"tapped {m['sel']} you control")
    if sel is None or not sel.tapped or sel.controller != "you" or sel.types != ("Creature",):
        return None
    return [{"do": STEP, "who": "event_player", "sel": sel.key(), "cost": m["cost"]}], 2


def pay_untap(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects, selectors

    players = effects._players(plan, ctx, e["who"])
    if len(players) != 1:
        return True
    pid = players[0]
    pool = sorted(selectors.candidates(plan, selectors.from_key(e["sel"]), pid, ctx.get("source_card")))
    if not pool:
        return True
    effects.decide(plan, player=pid, kind="choose_cards",
                   prompt=f"{ctx.get('name') or 'It'}: choose tapped creatures to untap, paying {e['cost']} for each",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in pool],
                   min_choices=0, max_choices=len(pool), resume={"step": STEP, "ctx": ctx, "e": e, "player": pid})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects, selectors

    ctx, e = d.resume["ctx"], d.resume["e"]
    pid = d.resume["player"]
    pool = set(selectors.candidates(plan, selectors.from_key(e["sel"]), pid, ctx.get("source_card")))
    cards = [c for c in chosen if c in pool]  # (still there, still tapped and matching)
    if not cards:
        effects.continue_effects(plan, ctx)
        return
    at = ctx["next"]
    name = f"pu{at}"
    context.bind_objects(plan, ctx, name, cards)
    added = [{"do": "optional_payment", "who": f"player:{pid}", "cost": e["cost"] * len(cards), "bind": f"{name}_pay"},
             {"do": "only_if", "cond": {"succeeded": f"{name}_pay"}, "skip": 1},
             {"do": "untap", "who": f"ref:{name}"}]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]  # (a new list: the definition's own may be shared)
    effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP: pay_untap}
