"""-- wishes (wave 52C) -- "You may reveal a sorcery card you own from outside the game and put it into your hand. Exile Burning Wish." (the Wishes), "You may reveal an artifact
card you own from outside the game or choose a face-up artifact card you own in exile. Put that card into your hand." (Karn, the Great Creator, Coax from the Blind Eternities),
"You may put a card you own from outside the game into your hand." (Death Wish).

The cards a player owns outside the game are the ones of their sideboard (the zone the table keeps for them, hidden from the other players, game/state.OWNER_VISIBLE_ZONES). The
player chooses a matching card (608.2d: as the instruction is carried out; none is allowed, "you may"), reveals it (701.20a: to everyone; "put … into your hand" reveals nothing)
and it goes to their hand; a face-up card of theirs in exile may be chosen too where the card says so (Karn, Coax: public, so not revealed). The question is asked even when
nothing matches, so that whether it appears tells the other players nothing about the sideboard.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules import characteristics as chars
from app.rules import selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_WHAT = r"(?:an?|the) (?:[A-Za-z' -]+? )?card"
_REVEAL = re.compile(rf"you may reveal (?P<what>{_WHAT}) you own from outside the game(?: and put it into your hand|(?: or choose a face-up (?P<again>(?:[A-Za-z' -]+? )?card) you own in exile)?)")
_PUT = re.compile(r"you may put a card you own from outside the game into your hand")


def sentence(texts: list[str], i: int, text: str) -> tuple[list[dict[str, Any]], int] | None:
    """(the effects, the sentences read) for a wish at sentence ``i`` (``text``: it, first letter lowered), or None."""
    if _PUT.fullmatch(text):
        return [{"do": "wish", "sel": selectors.parse("card").key(), "reveal": False}], 1  # type: ignore[union-attr]
    m = _REVEAL.fullmatch(text)
    if m is None:
        return None
    sel = selectors.parse(re.sub(r"^(?:an?|the) ", "", m["what"]))
    if sel is None:
        return None
    if m["again"] is None:
        return ([{"do": "wish", "sel": sel.key()}], 1) if text.endswith("hand") else None
    # "… or choose a face-up artifact card you own in exile. Put that card into your hand." (two sentences, one choice among both places)
    if m["again"] != re.sub(r"^(?:an?|the) ", "", m["what"]) or i + 1 >= len(texts) \
            or texts[i + 1].rstrip(".").strip().lower() != "put that card into your hand":
        return None
    return [{"do": "wish", "sel": sel.key(), "exile": True}], 2


def _options(plan: Plan, ctx: Context, e: dict[str, Any]) -> list[str]:
    pid = ctx["controller"]
    sel = selectors.from_key(e["sel"])
    zones = [f"{pid}:sideboard", *([f"{pid}:exile"] if e.get("exile") else [])]
    found = []
    for z in zones:
        for c in plan.state.zones.get(z, []):
            card = plan.state.cards[c]
            if card.owner != pid or (z.endswith(":exile") and (card.face_down or card.token is not None)):
                continue  # (a card you own: a stolen one is another's; face down, it is not "face-up")
            if selectors.matches(plan, sel, card, chars.of(card, plan.info), pid, ctx.get("source_card")):
                found.append(c)
    return found


def wish(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import decide

    options = _options(plan, ctx, e)
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: choose a card from outside the game"
           + (" or from exile" if e.get("exile") else ""),
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in options],
           min_choices=0, max_choices=1, resume={"step": "wish", "ctx": ctx, "e": e})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    pid = ctx["controller"]
    picked = [c for c in chosen[:1] if c in set(_options(plan, ctx, e))]
    for c in picked:
        if e.get("reveal", True) and plan.state.cards[c].zone.endswith(":sideboard"):
            plan.do({"type": "reveal", "card_ids": [c]}, actor=pid)  # to everyone (701.20a)
        plan.do({"type": "move", "card_ids": [c], "to": {"player": pid, "zone": "hand"}}, actor=pid)
    continue_effects(plan, ctx)
