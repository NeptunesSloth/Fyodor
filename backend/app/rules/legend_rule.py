"""-- legend rule (wave 10B) -- "The "legend rule" doesn't apply to permanents you control." (Mirror Box), "… to tokens you
control." (Cadric, Soul Kindler), "… to creatures you control." (Council of Reeds), "The "legend rule" doesn't apply."
(Mirror Gallery). Researched against CR 2026-09-25.

* 704.5j: if a player controls two or more legendary permanents with the same name, that player chooses one of them
  and the rest are put into their owners' graveyards. A static ability saying the rule doesn't apply to some permanents
  takes those permanents out of the check: they are not counted among the same-named ones (so a Mirror Box's controller
  keeps any number of legendary permanents, while the opponent's, whom it doesn't name, still lose all but one).
* The static applies while its source is on the battlefield (611.3a); "you" is its controller. Read lazily, only when
  a player controls two or more legendary permanents with one name (app/rules/sba.py).
* (wave 42A) "If there are exactly two permanents named Brothers Yamazaki on the battlefield, the "legend rule" doesn't apply to them.": checked each time
  the rule is (611.3a): with exactly two permanents of that name on the battlefield, whoever controls them, those two are not counted (one player controlling both
  keeps both); with a third, or one, the rule is the ordinary one for all of them. Any other condition is not read.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

KIND = "no_legend_rule"
_TEXT = re.compile(r'^The "legend rule" doesn\'t apply(?: to (?P<what>permanents|tokens|creatures) you control)?\.$')
_KIND = re.compile(r'^The "legend rule" doesn\'t apply to (?P<what>[A-Za-z ]+?) you control\.$')  # (wave 49B) "… to Slivers you control." (Sliver Gravemother), "… to creature tokens you control." (The Master, Multiplied)


_NAMED_TWO = re.compile(r'^If there are exactly two permanents named (?P<name>~|this creature|[A-Z][^\n]+?) on the battlefield, the "legend rule" doesn\'t apply to them\.$')


def static_definition(text: str) -> dict[str, Any] | None:
    t = text.strip().replace("“", '"').replace("”", '"')
    if (named := _NAMED_TWO.match(t)) is not None:
        return {"kind": "static", "static": KIND, "scope": "named_two", "effects": [],
                **({'name': named['name']} if named['name'] not in ('~', 'this creature') else {})}
    m = _TEXT.match(t)
    if m is None:
        from app.rules import selectors

        k = _KIND.match(t)
        sel = selectors.parse(f"{k['what']} you control") if k is not None else None
        return {"kind": "static", "static": KIND, "scope": "sel", "sel": sel.key(), "effects": []} \
            if sel is not None and sel.controller == "you" and sel.zones == ("battlefield",) and sel.player is None else None
    return {"kind": "static", "static": KIND, "scope": m["what"] or "all", "effects": []}


def exempt_cards(plan: Plan, group: list[CardInstance]) -> set[str]:
    """The cards of one same-named group the rule doesn't apply to."""
    from app.rules import card_names, scripts, selectors
    from app.rules.conditional_copy_sources import NO_LEGEND
    from app.rules.replace import conditional_lines

    out: set[str] = {card.id for effect in plan.rules.effects if NO_LEGEND in effect.imposes
                     for card in group if card.controller == effect.controller}
    for src in plan.state.cards.values():
        if not src.zone.endswith(":battlefield") or src.face_down or not plan.in_game(src) or plan.manual(src):
            continue
        ch = plan.ch(src)
        skip = conditional_lines(ch)  # (a leveler's / Class's level lines: the level isn't tracked)
        for i, d in scripts.definitions(ch).items():
            if i in skip or d.get("kind") != "static" or d.get("static") != KIND:
                continue
            if d["scope"] == "named_two":  # (wave 42A) exactly two permanents with the source's name on the battlefield: those two
                # Spy Kit (wave 110J) needs no name_test here: it adds names only of nonlegendary creature cards, and the legend rule (704.5j) needs legendary permanents.
                name = d.get('name', ch.name)
                same = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.in_game(c)
                        and name in card_names.names_of(plan.ch(c))]
                out |= {card.id for card in group if card.id in same} if len(same) == 2 else set()
                continue
            for card in group:
                if d["scope"] == "sel":  # (wave 49B) the permanents the selector names, the source's controller's (704.5j: "you control")
                    if selectors.matches(plan, selectors.from_key(d["sel"]), card, plan.ch(card), src.controller, src.id):
                        out.add(card.id)
                    continue
                if d["scope"] == "all" or card.controller == src.controller and (
                        d["scope"] == "permanents" or (d["scope"] == "tokens" and card.is_token)
                        or (d["scope"] == "creatures" and plan.ch(card).is_creature)):
                    out.add(card.id)
    return out
