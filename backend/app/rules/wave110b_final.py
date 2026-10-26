"""-- wave 110B final pass -- exact Oracle wordings of single cards, read as a wording the grammar already reads plus the smallest change to its definition.

* Lukka, Coppercoat Outcast: +1 gives each exiled creature card a permission to be cast for as long as it remains exiled and you control a Lukka planeswalker
  (611.2b, 113.6m; the 2020-04-17 rulings: any Lukka planeswalker counts); -2 reveals until a creature card with greater mana value than the exiled creature's, as it last
  existed (608.2h; X is 0 in a card in a library or on the battlefield: 107.3g).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

Def = dict[str, Any]

_LUKKA_PLUS = ('+1: Exile the top three cards of your library. Creature cards exiled this way gain "You may cast this card from exile as long as you control a Lukka planeswalker."')
_LUKKA_MINUS = ("−2: Exile target creature you control, then reveal cards from the top of your library until you reveal a creature card with greater mana value. "
                "Put that card onto the battlefield and the rest on the bottom of your library in a random order.")


def _lukka_plus(d: Def) -> Def:
    from app.rules import conditions, permissions

    cond = conditions.parse("you control a Lukka planeswalker")
    assert cond is not None
    return {**d, "effects": [{**e, "filter": permissions.spell_filter("creature"), "when": cond} if e.get("do") == "grant_play" else e for e in d["effects"]]}


def _lukka_minus(d: Def) -> Def:
    out: list[Def] = []
    for e in d["effects"]:
        if e.get("do") == "exile":
            e = {**e, "as": "gone110b"}
        elif e.get("do") == "look_top":
            e = {"do": "greater_dig110b", "gone": "ref:gone110b", "dig": e}
        out.append(e)
    return {**d, "effects": out}


_BUILD: dict[str, tuple[str, Any]] = {
    _LUKKA_PLUS: ('+1: Exile the top three cards of your library. For as long as they remain exiled, you may cast those cards.', _lukka_plus),
    _LUKKA_MINUS: ("−2: Exile target creature you control. Reveal cards from the top of your library until you reveal a creature card. "
                   "Put that card onto the battlefield and the rest on the bottom of your library in a random order.", _lukka_minus),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def greater_dig(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """The reveal-until instruction with its card required to have greater mana value than the creature the binding names (as it last existed)."""
    from app.rules import context, selectors

    gone = context.info(plan, ctx, e["gone"].removeprefix("ref:"))
    if gone is None:
        return True  # (nothing was exiled: no creature, nothing to compare with: 608.2b)
    dig = e["dig"]
    until = selectors.replace(selectors.from_key(dig["until"]), compare=(("mv", ">", int(gone[1].mana_value)),))
    ctx["effects"][ctx["next"]:ctx["next"]] = [{**dig, "until": until.key()}]
    return True


PRIMITIVES: dict[str, Any] = {"greater_dig110b": greater_dig}
