"""-- discover (wave 9A) -- "Discover 5." / "discover X, where X is that creature's toughness." (Trumpeting Carnosaur,
Geological Appraiser, Monstrous Vortex, Hurl into History …)

701.57a: to discover N, the player exiles cards from the top of their library until they exile a nonland card with mana
value N or less, may cast it without paying its mana cost (if the resulting spell's mana value is N or less), and
otherwise puts it into their hand; the other exiled cards go to the bottom of the library in a random order.
701.57c: that last card is "the discovered card" however it ended up. N is worked out as the instruction is carried out
(608.2h); a "where X is …" X is the ability's own (107.3c).

It is cascade's process (effects.cascade: the same free-cast offer, 608.2g) with "N or less" and a hand instead of the
bottom for the card that isn't cast. Only an instruction that ends its ability is read (the cast happens as the ability
finishes, like cascade's): scripts.define refuses a discover followed by anything else ("If the discovered card's …").
Researched against CR 2026-09-25.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

_PATTERN = re.compile(r"^(?:you )?discover (?P<n>\d+|X)(?:, where X is (?P<xdef>.+))?$")


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import scripts

    if m["n"] == "X":
        if m["xdef"] is None:
            raise scripts._NoMatch  # (a bare X is some cost's, not read here)
        n: Any = scripts._x_amount(m["xdef"])
    elif m["xdef"] is not None:
        raise scripts._NoMatch
    else:
        n = int(m["n"])
    return [{"do": "discover", "n": n}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_PATTERN, _build)]


def discover(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import characteristics as chars
    from app.rules import effects

    pid = ctx["controller"]
    n = effects._amount(plan, ctx, e["n"])
    missed: list[str] = []
    hit: str | None = None
    for _ in range(len(plan.state.zones.get(zone_key(pid, "library"), []))):
        library = plan.state.zones.get(zone_key(pid, "library"), [])
        if not library:
            break
        top = library[0]
        plan.do({"type": "move", "card_ids": [top], "to": {"player": pid, "zone": "exile"}}, actor=pid)
        ch = chars.of(plan.state.cards[top], plan.info)
        if not ch.is_land and ch.mana_value <= n:
            hit = top
            break
        missed.append(top)
    order = list(missed)
    plan.rng.shuffle(order)  # (random order, 701.57a)
    for cid in order:
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": "library"}, "position": "bottom"}, actor=pid)
    if hit is None:
        plan.note(f"Discover {n} found nothing")
        return True
    plan.rules.free_casts.append(hit)
    card = plan.state.cards[hit]
    decide(plan, player=pid, kind="choose_one", prompt=f"Discover {n}: cast {card.name} without paying its mana cost?",
           options=[DecisionOption(id="yes", label="Cast it"), DecisionOption(id="no", label="Put it into your hand")],
           resume={"step": "suspend_cast", "ctx": ctx, "card": hit, "decline": "hand"}, source=card)
    return False


PRIMITIVES = {"discover": discover}
