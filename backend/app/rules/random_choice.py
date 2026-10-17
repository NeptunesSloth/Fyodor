# -- random choices (wave 47B) --
"""Random choices among public things: "Choose an opponent at random." (Vial Smasher, Ruhan of the Fomori, Strax), "… an opponent chosen at
random" (Zaffai). Researched against CR 2026-09-25 and the rulings (Vial Smasher the Fierce 2020-11-10, Strax 2023-10-13).

* The Comprehensive Rules have no rule for "at random": nobody chooses, the game picks without bias. The pick is made while the ability
  resolves (Vial Smasher ruling), from the players still in the game (800.4a); with one opponent left that opponent is it.
* The pick comes from the table's entropy source (plan.rng, as dice and coin flips) and is recorded: the player lands in the resolution
  context (a decision's resume, the saved rules state) and every instruction after it is a recorded step, so a replay or a load never draws
  again. The pick is public (players are), and logged.
* "Choose an opponent at random. ~ deals damage … to that player or a planeswalker that player controls." (Vial Smasher): after the pick,
  its controller chooses the player or one of that player's planeswalkers (ruling); no player may act between the two.

Not read (manual): a pick among objects, cards or modes (their own systems), "didn't attack during your last combat" (Territorial Hellkite).
"""

from __future__ import annotations

import json
import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules import context
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_CLAUSE = re.compile(r"choose (?P<w>an opponent|a player) at random")
_OR_PW = re.compile(r"(?<=\. )(?P<d>[^.]*?) to that player or a planeswalker that player controls\.")
INLINE = "random_opponent"  # the group token of "an opponent chosen at random" (scripts: post() makes it a pick and a binding)


def clause(text: str) -> tuple[list[dict[str, Any]], None] | None:
    """"choose an opponent at random" / "choose a player at random" (one instruction, no final period)."""
    m = _CLAUSE.fullmatch(text)
    return None if m is None else ([{"do": "choose_random", "pool": "opponent" if m["w"] == "an opponent" else "player"}], None)


def strip_pw(body: str) -> tuple[str, bool]:
    """"Choose an opponent at random. ~ deals N damage to that player or a planeswalker that player controls." (Vial Smasher): the
    sentence read as "… to that player." and the pick marked (``post(pw=True)``) to be followed by the controller's choice."""
    if not re.search(r"(?i)\bchoose (?:an opponent|a player) at random\. ", body):
        return body, False
    new = _OR_PW.sub(lambda m: f"{m['d']} to that player.", body)
    return new, new != body


def post(got: Any, pw: bool = False) -> Any:
    """"… to an opponent chosen at random" (the group token ``INLINE`` as an instruction's ``who``): the pick is made right before the
    instruction (inside its "if" gate, if it has one), bound as ``ref:rp<k>``. The token anywhere else keeps the card manual."""
    if got is None:
        return got
    effects = got[0]
    if pw:  # (the one pick of the ability: ``strip_pw`` found a single sentence)
        picks = [e for e in effects if e.get("do") == "choose_random"]
        if len(picks) != 1:
            return None
        picks[0]["pw"] = True
    k = 0
    while k < len(effects):
        if effects[k].get("who") == INLINE:
            effects[k] = {**effects[k], "who": f"ref:rp{k}"}
            effects.insert(k, {"do": "choose_random", "pool": "opponent", "as": f"rp{k}"})
            for j, g in enumerate(effects[:k]):  # (the gate of an "If …, …" now covers one more instruction)
                if g.get("do") == "only_if" and j < k <= j + int(g.get("skip", 0)):
                    g["skip"] = int(g["skip"]) + 1
            k += 1
        k += 1
    return None if INLINE in json.dumps(effects) else got


def choose_random(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The table picks one player of the pool (an opponent of the controller, or any player) at random and binds it as ``as``."""
    me = ctx["controller"]
    pool = [p for p in plan.live() if e["pool"] == "player" or p != me]
    pick = (plan.rng or secrets.SystemRandom()).choice(pool) if pool else None
    if pick is not None:
        plan.note(f"{ctx.get('name') or 'It'}: {plan.name(pick)} is chosen at random", actor=me)
    if e.get("as"):
        context.bind_players(ctx, e["as"], [pick] if pick is not None else [])
    if pick is not None and e.get("pw") and (walkers := _planeswalkers(plan, pick)):
        decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose {plan.name(pick)} or a planeswalker they control",
               options=[DecisionOption(id=pick, label=plan.name(pick)),
                        *(DecisionOption(id=c, label=plan.state.cards[c].name or "Planeswalker", card_id=c) for c in walkers)],
               resume={"step": "choose_random", "ctx": ctx, "e": e, "pick": pick})
        return False
    return True


def _planeswalkers(plan: Plan, pid: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.zone == f"{pid}:battlefield" and "Planeswalker" in plan.ch(c).types]


def resume_choose_random(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The controller's choice of the player or one of that player's planeswalkers (Vial Smasher ruling 2020-11-10)."""
    from app.rules.effects import continue_effects

    ctx, e, pick = d.resume["ctx"], d.resume["e"], d.resume["pick"]
    if chosen[0] != pick:
        if chosen[0] not in _planeswalkers(plan, pick):
            raise ValueError("not that player's planeswalker")
        context.bind_objects(plan, ctx, e["as"], [chosen[0]])
    plan.note(f"{plan.name(d.player)} chooses {plan.state.cards[chosen[0]].name if chosen[0] != pick else plan.name(pick)}")
    continue_effects(plan, ctx)


PRIMITIVES = {"choose_random": choose_random}
RESUME: dict[str, Any] = {"choose_random": resume_choose_random}
