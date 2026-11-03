"""Land/nonland choice followed by a reveal-until, including Abundance's draw replacement."""
from __future__ import annotations

import re
from typing import Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules.plan import Plan, decide


def parse(text: str) -> list[dict[str, Any]] | None:
    m = re.fullmatch(r"choose land or nonland and reveal cards from the top of your library until you reveal a card of the chosen kind\. "
                     r"Put that card into your hand and put all other cards revealed this way on the bottom of your library in (?P<order>any|a random) order\.", text, re.IGNORECASE)
    if m is None:  # (-- if you do / instead (wave 111B) -- "in a random order": Pavel Chekov, First Posting, 401.4)
        return None
    return [{"do": "choose_land_nonland"}, {"do": "reveal_chosen_kind"},
            {"do": "pick_looked", "which": "that", "require_found": True, "to": "hand"},
            {"do": "rest_looked", "to": "bottom_random" if m["order"].lower() == "a random" else "bottom_any"}]


def choose(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose land or nonland",
           options=[DecisionOption(id="land", label="Land"), DecisionOption(id="nonland", label="Nonland")],
           resume={"step": "choose_land_nonland", "ctx": ctx})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if len(chosen) != 1 or chosen[0] not in ("land", "nonland"):
        raise ActionError("Choose land or nonland")
    ctx = d.resume["ctx"]
    ctx["library_kind"] = chosen[0]
    plan.note(f"{plan.name(d.player)} chose {chosen[0]}", actor=d.player)
    effects.continue_effects(plan, ctx)


def reveal(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, selectors

    kind = ctx.pop("library_kind", None)
    if kind not in ("land", "nonland"):
        raise ActionError("A library reveal needs its land or nonland choice")
    sel = selectors.Selector(zones=(), card=True, types=("Land",)) if kind == "land" else selectors.Selector(zones=(), card=True, not_types=("Land",))
    return effects.look_top(plan, ctx, {"do": "look_top", "n": 0, "reveal": True, "until": sel.key()})


PRIMITIVES = {"choose_land_nonland": choose, "reveal_chosen_kind": reveal}
RESUME = {"choose_land_nonland": resume}
