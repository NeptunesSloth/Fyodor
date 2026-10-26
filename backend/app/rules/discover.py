"""-- discover (wave 9A) -- "Discover 5." / "discover X, where X is that creature's toughness." (Trumpeting Carnosaur,
Geological Appraiser, Monstrous Vortex, Hurl into History …)

701.57a: to discover N, the player exiles cards from the top of their library until they exile a nonland card with mana
value N or less, may cast it without paying its mana cost (if the resulting spell's mana value is N or less), and
otherwise puts it into their hand; the other exiled cards go to the bottom of the library in a random order.
701.57c: that last card is "the discovered card" however it ended up. N is worked out as the instruction is carried out
(608.2h); a "where X is …" X is the ability's own (107.3c).

It is cascade's process (effects.cascade: the same free-cast offer, 608.2g) with "N or less" and a hand instead of the
bottom for the card that isn't cast. Ordinary discover instructions still finish their ability as before. A typed
follow-up may opt into continuing the original resolution after casting, declining, or cancelling the discovered card;
the discovered binding keeps its last public mana value, and a successful cast can be found under CR 400.7h.
Researched against CR 2026-09-25.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.state import zone_key

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
    if e.get("as"):
        from app.rules import context

        context.bind_objects(plan, ctx, e["as"], [])
    n = effects._amount(plan, ctx, e["n"])
    from app.game.rules_state import emit

    emit(plan.state, "designation", counter="discover", player=pid, amount=n)  # -- discover (wave 110B) -- "Whenever you discover" (701.57)
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
    effects.bottom_at_random(plan, pid, missed)  # (random order, 701.57a; review 29B: one move, its order unreadable, 401.4)
    if hit is None:
        plan.note(f"Discover {n} found nothing")
        return True
    if e.get("as"):
        from app.rules import context

        context.bind_objects(plan, ctx, e["as"], [hit])
        context.refs(ctx)[e["as"]]["discovered_mv"] = ch.mana_value
    # -- granted casts (wave 29B) -- "if the resulting spell's mana value is less than or equal to N" (701.57a): each half / face
    from app.rules import granted_casts

    done = granted_casts.ask(plan, ctx, player=pid, cid=hit, head=f"Discover {n}", no="Put it into your hand", decline="hand", at_most=n)
    if not done and e.get("continue_resolution") and plan.rules.decision is not None and plan.rules.decision.resume is not None:
        plan.rules.decision.resume["continue_resolution"] = True
    return done


PRIMITIVES = {"discover": discover}
