"""-- reveal until (wave 13E) -- "Reveal cards from the top of your library until you reveal a creature card. Put that card
onto the battlefield and the rest on the bottom of your library in a random order." (Gamekeeper's, Avenging Druid's, Thicket
Elemental's, Aspiring Champion's wording), researched against CR 2026-09-25.

* 701.20a: to reveal a card is to show it to all players; the cards stay in the library, on top, until an instruction moves
  them (701.20b), so "shuffle the rest into your library" is a shuffle of the library and a card that isn't put anywhere
  (a failed search for a land in a library with none) simply stays in it.
* 701.20 / 608.2c: the cards are revealed one at a time from the top until the stated number of matching cards is revealed
  or the library is out of cards; each revealed card is public (everyone sees them), nothing below the last one is looked at.
* "In a random order" is the table's randomness (``plan.rng``): the player doesn't choose (401.4).
* "You may reveal …. If you do, put …" (Avenging Druid, Thicket Elemental): the reveal is the optional action, asked first.
  Declining reveals nothing and puts nothing anywhere.

Only the shapes above are read: a count of one to three, one kind of card, and the three tails ("the rest on the bottom of
your library in a random order", "put all other cards revealed this way into your graveyard", "shuffle the rest into your
library"). A sized count ("X creature cards"), a kind that depends on the game ("with mana value equal to …"), exiling instead
of revealing, damage or counters from the revealed cards, and free casts stay manual.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_COUNT = {"a": 1, "an": 1, "two": 2, "three": 3}
# "…until you reveal a land card. If you do, put that card …" / "…reveal a creature card. Put that card …": one instruction
_JOIN = re.compile(r"(until you reveal (?:an?|two|three) [a-z -]+? cards?)\. (?:If you do, )?[Pp]ut ")
_PATTERN = re.compile(
    r"^(?P<may>you may )?reveal cards from the top of your library until you reveal (?P<n>an?|two|three) (?P<kind>[a-z -]+?) cards?; "
    r"put (?:that card|those cards) (?P<dest>into your hand|onto the battlefield(?P<tapped> tapped)?)"
    r"(?P<rest>,? then shuffle the rest into your library| and the rest on the bottom of your library in a random order"
    r"| and put all other cards revealed this way into your graveyard| and shuffle all other cards revealed this way into your library)$")


def rewrite(body: str) -> str:
    return _JOIN.sub(r"\1; put ", body) if "until you reveal" in body else body


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import scripts, selectors

    n = _COUNT[m["n"]]
    sel = selectors.parse(f"{m['kind']} cards")
    if sel is None or not sel.card or sel.zones or sel.player is not None or sel.other or sel.extras:
        raise scripts._NoMatch
    rest = "shuffle" if "shuffle" in m["rest"] else "graveyard" if "graveyard" in m["rest"] else "bottom"
    dest = "hand" if m["dest"] == "into your hand" else "battlefield_tapped" if m["tapped"] else "battlefield"
    return [{"do": "reveal_until", "sel": sel.key(), "n": n, "to": dest, "rest": rest, **({"may": True} if m["may"] else {})}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_PATTERN, _build)]


def reveal_until(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    if e.get("may"):
        decide(plan, player=ctx["controller"], kind="confirm",
               prompt=f"{ctx.get('name') or 'It'}: reveal cards from the top of your library?",
               options=[DecisionOption(id="yes", label="Reveal"), DecisionOption(id="no", label="Don't")],
               resume={"step": "reveal_until_may", "ctx": ctx, "e": e})
        return False
    _run(plan, ctx, e)
    return False


def resume_may(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    if chosen[0] == "yes":
        _run(plan, ctx, e)
        return
    plan.note(f"{plan.name(d.player)} chose not to reveal", actor=d.player)
    continue_effects(plan, ctx)


def _run(plan: Plan, ctx: Context, e: dict[str, Any]) -> None:
    from app.rules import characteristics as chars
    from app.rules import selectors
    from app.rules.effects import _finish_search

    pid = ctx["controller"]
    sel = selectors.from_key(e["sel"])
    shown: list[str] = []
    found: list[str] = []
    for cid in list(plan.state.zones.get(zone_key(pid, "library"), [])):
        shown.append(cid)
        if selectors.matches(plan, sel, plan.state.cards[cid], chars.of(plan.state.cards[cid], plan.info), pid):
            found.append(cid)
            if len(found) == e["n"]:
                break
    if shown:
        plan.do({"type": "reveal", "card_ids": shown}, actor=pid)  # 701.20a: to everyone
    rest = [c for c in shown if c not in found]
    if e["rest"] == "graveyard" and rest:
        plan.do({"type": "move", "card_ids": rest, "to": {"player": pid, "zone": "graveyard"}}, actor=pid)
    elif e["rest"] == "bottom":
        plan.rng.shuffle(rest)  # (a random order: 401.4)
        for cid in rest:
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": "library"}, "position": "bottom"}, actor=pid)
    _finish_search(plan, ctx, {"to": e["to"], "shuffle": e["rest"] == "shuffle"}, pid, found, {c: e["to"] for c in found})


PRIMITIVES = {"reveal_until": reveal_until}
