"""-- trigger other (wave 52B) -- players who reveal the top card of their library, lose life equal to a revealed card's mana value, and put theirs into hand.

"At the beginning of your upkeep, you and target opponent each reveal the top card of your library. You each lose life equal to the mana value of the card revealed by the
other player. You each put the card you revealed into your hand." (Keen Duelist); the same for "two target players" (Parker Luck); "Each player reveals the top card of
their library, loses life equal to that card's mana value, then puts it into their hand." (Duskmantle Seer).

* 701.20a: the cards are revealed to everyone, all of them before anyone loses life; 119.3 / 118.2: each loses the life at once (one life-loss event, replacements
  apply); 202.3: a card in a library has its printed mana value (an X is 0, 202.3e); 400.7: a revealed card that is no longer on the top of that library (or in it) when it
  is taken is not put into a hand.
* A player with no card to reveal reveals nothing: the other player (who would lose life equal to its mana value) loses none, and nothing is put into a hand.
* Three instructions: ``trade_reveal`` (binds the cards, ``as``, and the players in the trade, ``as`` + "p"), the life loss (effects.lose_life with a per-player
  amount ``{"revealed_mv": name, "of": "own" | "other"}``, values.py), ``trade_take`` (each revealed card into its owner's hand). Nothing here executes card text.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import context

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

_KEEN = re.compile(r"^you and target opponent each reveal the top card of your library\. You each lose life equal to the mana value of the card revealed by the other "
                   r"player\. You each put the card you revealed into your hand\.$")
_TWO = re.compile(r"^two target players each reveal the top card of their library\. They each lose life equal to the mana value of the card revealed by the other "
                  r"player\. Then they each put the card they revealed into their hand\.$")
_EACH = re.compile(r"^each player reveals the top card of their library, loses life equal to that card's mana value, then puts it into their hand\.$")


def parse(body: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None] | None:
    """The three wordings as (effects, the target group or None), or None."""
    from app.rules import language

    if _EACH.match(body):
        trade, other, group = {"who": "each_player", "with": None}, "own", None
    elif _KEEN.match(body):
        trade, other, group = {"who": "target", "with": "you"}, "other", language.target_group("target opponent")
    elif _TWO.match(body):
        trade, other, group = {"who": "target", "with": None}, "other", language.target_group("two target players")
    else:
        return None
    effects: list[dict[str, Any]] = [{"do": "trade_reveal", "as": "tr", **trade},
               {"do": "lose_life", "who": "ref:trp", "n": {"per_player": {"revealed_mv": "tr", "of": other}}},
               {"do": "trade_take", "of": "tr"}]
    return effects, group


def trade_reveal(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import _players

    players = _players(plan, ctx, e["who"])
    if e.get("with") == "you":
        players = [ctx["controller"], *[p for p in players if p != ctx["controller"]]]
    shown: list[str] = []
    for pid in players:
        library = plan.state.zones.get(f"{pid}:library", [])
        if library:
            plan.do({"type": "reveal_top", "player": pid, "count": 1, **({"source": str(ctx["name"])[:200]} if ctx.get("name") else {})}, actor=pid)
            shown.append(library[0])
    context.bind_objects(plan, ctx, e["as"], shown)
    context.bind_players(ctx, e["as"] + "p", players)  # (a player with no card still loses life equal to the other's card: "you each lose life …")
    return True


def revealed_mv(plan: Plan, ctx: Context, v: dict[str, Any]) -> int:
    """The mana value of the card(s) the named trade revealed that its recipient (``controller``) owns ("own") or that someone else does ("other")."""
    total = 0
    for ref in context._object_refs(ctx, v["revealed_mv"]):
        card = plan.state.cards.get(ref.card)
        if card is not None and (card.owner == ctx["controller"]) == (v["of"] == "own"):
            total += int(plan.ch(card).mana_value)
    return total


def trade_take(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for cid in context.objects(plan, ctx, e["of"]):
        card = plan.state.cards[cid]
        if card.zone == f"{card.owner}:library":
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "hand"}}, actor=card.owner)
    return True


PRIMITIVES: dict[str, Any] = {"trade_reveal": trade_reveal, "trade_take": trade_take}
