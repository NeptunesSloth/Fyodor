"""-- legend rule (wave 10B) -- "The "legend rule" doesn't apply to permanents you control." (Mirror Box), "… to tokens you
control." (Cadric, Soul Kindler), "… to creatures you control." (Council of Reeds), "The "legend rule" doesn't apply."
(Mirror Gallery). Researched against CR 2026-09-25.

* 704.5j: if a player controls two or more legendary permanents with the same name, that player chooses one of them
  and the rest are put into their owners' graveyards. A static ability saying the rule doesn't apply to some permanents
  takes those permanents out of the check: they are not counted among the same-named ones (so a Mirror Box's controller
  keeps any number of legendary permanents, while the opponent's, whom it doesn't name, still lose all but one).
* The static applies while its source is on the battlefield (611.3a); "you" is its controller. Read lazily, only when
  a player controls two or more legendary permanents with one name (app/rules/sba.py).
* Not read: a condition ("If there are exactly two permanents named Brothers Yamazaki …").
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

KIND = "no_legend_rule"
_TEXT = re.compile(r'^The "legend rule" doesn\'t apply(?: to (?P<what>permanents|tokens|creatures) you control)?\.$')


def static_definition(text: str) -> dict[str, Any] | None:
    m = _TEXT.match(text.strip().replace("“", '"').replace("”", '"'))
    if m is None:
        return None
    return {"kind": "static", "static": KIND, "scope": m["what"] or "all", "effects": []}


def exempt_cards(plan: Plan, group: list[CardInstance]) -> set[str]:
    """The cards of one same-named group the rule doesn't apply to."""
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    out: set[str] = set()
    for src in plan.state.cards.values():
        if not src.zone.endswith(":battlefield") or src.face_down or not plan.in_game(src) or plan.manual(src):
            continue
        ch = plan.ch(src)
        skip = conditional_lines(ch)  # (a leveler's / Class's level lines: the level isn't tracked)
        for i, d in scripts.definitions(ch).items():
            if i in skip or d.get("kind") != "static" or d.get("static") != KIND:
                continue
            for card in group:
                if d["scope"] == "all":
                    out.add(card.id)
                elif card.controller == src.controller and (
                        d["scope"] == "permanents" or (d["scope"] == "tokens" and card.is_token)
                        or (d["scope"] == "creatures" and plan.ch(card).is_creature)):
                    out.add(card.id)
    return out
