"""-- if you do (wave 8C) -- "put your choice of a +1/+1, first strike, or trample counter on that creature" (Assaultron
Dominator, T-45 Power Armor, Me, the Immortal): the controller chooses one of the kinds named as the instruction is
carried out (608.2d: a choice the effect offers) and puts one counter of it on the object (122.6, through the counter
choke point). A keyword counter gives its keyword (122.1b, 613.1f). Only +1/+1 and the keyword counters are kinds the
engine models (values.UNMODELED_COUNTERS), so any other kind in the list leaves the ability manual.

The chosen kind replaces this instruction in the resolution (an ordinary ``add_counters`` then runs in its place, so a
replacement-order choice (616.1) can pause it like any other counter placement)."""

from __future__ import annotations

import re
from typing import Any

from app.game.errors import ActionError
from app.game.rules_state import KEYWORD_COUNTERS, DecisionOption
from app.rules.plan import Plan, decide

Context = dict[str, Any]
STEP = "pick_counter"
_ITEM = re.compile(r"^(?:an? )?(?P<kind>\+1/\+1|[a-z]+(?: [a-z]+)?)$")
_WHO = {"~": "self", "this creature": "self", "it": "it", "that creature": "it"}


def parse(kinds: str, who: str) -> list[dict[str, Any]] | None:
    """The instruction for "[a/an] X, Y, or Z [counter]" on ``who``, or None (not read)."""
    items = [i.strip() for i in re.split(r", or |, | or ", kinds.strip()) if i.strip()]
    found = []
    for item in items:
        m = _ITEM.match(re.sub(r" counters?$", "", item))
        if m is None or (m["kind"] != "+1/+1" and m["kind"] not in KEYWORD_COUNTERS):
            return None
        found.append(m["kind"])
    if len(found) < 2 or len(set(found)) != len(found) or who not in _WHO:
        return None
    return [{"do": "pick_counter", "who": _WHO[who], "kinds": found}]


def pick_counter(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    if not effects._cards(plan, ctx, e["who"]):  # (nothing to put them on)
        return True
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Choose'}: choose a kind of counter",
           options=[DecisionOption(id=k, label=f"{k} counter") for k in e["kinds"]],
           resume={"step": STEP, "ctx": ctx, "e": e}, source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    if len(chosen) != 1 or chosen[0] not in e["kinds"]:
        raise ActionError("Choose one of the kinds offered")
    plan.note(f"{plan.name(d.player)} chooses a {chosen[0]} counter", actor=d.player)
    put = {"do": "add_counters", "who": e["who"], "kind": chosen[0], "n": 1}
    at = ctx["next"] - 1
    ctx["effects"] = [*ctx["effects"][:at], put, *ctx["effects"][at + 1:]]
    ctx["next"] = at
    effects.continue_effects(plan, ctx)
