"""-- mana replacements (wave 9C) -- replacement effects on the mana a permanent produces when it is tapped for mana:
"If you tap a permanent for mana, it produces three times as much of that mana instead." (Nyxbloom Ancient), "twice as
much" (Mana Reflection), "If you tap a basic land for mana, it produces three times …" (Virtue of Strength), "If a land
is tapped for mana, it produces {B} instead of any other type [and amount]." (Infernal Darkness, Contamination),
"… colorless mana instead of any other type." (Ritual of Subdual), "If a land is tapped for two or more mana, it produces
{C} instead of any other type and amount." (Damping Sphere), "If a basic land you control is tapped for mana, it
produces mana of a color of your choice instead of any other type." (Pulse of Llanowar). Researched against CR 2026-09-25.

* 106.12 / 106.12b — to tap a permanent for mana is to activate a mana ability of it with {T} in its cost; a replacement
  effect that applies to a permanent "tapped for mana" modifies the mana production event while the ability resolves.
  Mana from an ability without {T} in its cost (a Treasure's sacrifice) is untouched.
* 106.6a — a replacement that increases the mana produced: restrictions on the mana apply to all of it. (An ability whose
  mana is restricted, counted ("for each …"), or conditional on the table "instead" is left to the player: not read.)
* 614.5 / 616.1 — each replacement applies to the event once; when several apply to one ability the order matters and the
  affected player chooses it (616.1): not modelled, so an ability two such statics apply to is left to the player.
* 106.7 — what a land "could produce" takes replacement effects into account: Reflecting Pool / Exotic Orchard are left
  to the player while one of these statics is on the battlefield.
* 605.4a / 106.12a — triggered mana abilities of "tapped for mana" (Wild Growth, Mirari's Wake) trigger from the
  replaced production and add their own mana after it (tap_mana.extend, attached_mana.extend run after this).

Definition: ``{"kind": "static", "static": "mana_replace", "who": "you"|"any", "sel": <selector key>, "op": {...},
"effects": []}`` with op ``{"do": "mul", "n": k}`` (each type k times), ``{"do": "recolor", "to": "B"|"C"|"choice"}``
(every mana becomes that type; "choice": one of the five colors for the whole production), ``{"do": "fixed", "mana":
"B"}`` (exactly one such mana) or ``{"do": "collapse", "min": 2, "to": "C"}`` (a production of that many mana or more
becomes one such mana). Applied to the options of a mana ability by :func:`extend` (casting.mana_abilities).
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules import mana as M
    from app.rules.characteristics import CardInfo

COLORS = ("W", "U", "B", "R", "G")
_TIMES = {"twice": 2, "three times": 3}
_MULT = re.compile(r"^If you tap (?P<what>a permanent|a basic land) for mana, it produces (?P<k>twice|three times) as much of "
                   r"that mana instead\.$")
_LAND = re.compile(r"^If a land is tapped for mana, it produces (?P<sym>\{[WUBRGC]\}|colorless mana) instead of any other "
                   r"type(?P<amount> and amount)?\.$")
_TWO = re.compile(r"^If a land is tapped for two or more mana, it produces \{C\} instead of any other type and amount\.$")
_CHOICE = re.compile(r"^If a basic land you control is tapped for mana, it produces mana of a color of your choice instead "
                     r"of any other type\.$")


def definition(text: str) -> dict[str, Any] | None:
    from app.rules import selectors

    def static(who: str, what: str, op: dict[str, Any]) -> dict[str, Any] | None:
        sel = selectors.parse(what)
        if sel is None:
            return None
        return {"kind": "static", "static": "mana_replace", "who": who, "sel": sel.key(), "op": op, "effects": []}

    text = text.strip()
    if (m := _MULT.match(text)) is not None:
        return static("you", "permanent" if m["what"] == "a permanent" else "basic land", {"do": "mul", "n": _TIMES[m["k"]]})
    if (m := _LAND.match(text)) is not None:
        to = "C" if m["sym"] == "colorless mana" else m["sym"][1]
        return static("any", "land", {"do": "fixed", "mana": to} if m["amount"] else {"do": "recolor", "to": to})
    if _TWO.match(text):
        return static("any", "land", {"do": "collapse", "min": 2, "to": "C"})
    if _CHOICE.match(text):
        return static("you", "basic land", {"do": "recolor", "to": "choice"})
    return None


def _statics(state: GameState, info: CardInfo) -> list[tuple[str, dict[str, Any]]]:
    """(controller, definition) of every such static in play right now."""
    from app.rules import characteristics as chars
    from app.rules import scripts
    from app.rules.copying import copy_index
    from app.rules.layers import copiable, derive

    r = state.rules
    copies = copy_index(r)
    out: list[tuple[str, dict[str, Any]]] = []
    for key, ids in state.zones.items():
        if not key.endswith(":battlefield"):
            continue
        for cid in ids:
            c = state.cards[cid]
            if c.face_down or (r is not None and r.card_mode(c.id) == "manual"):
                continue
            # (a cheap first look: the printed text, or a copy effect giving other copiable values, 613.2c)
            if "mana, it produces" not in chars.of(c, info).oracle_text and c.copy_of is None \
                    and (r is None or r.object_id(c.id) not in copies):
                continue
            ch = derive(state, c, copiable(state, c, info), info)
            for d in scripts.definitions(ch).values():
                if d.get("static") == "mana_replace":
                    out.append((c.controller, d))
    return out


def in_play(state: GameState, info: CardInfo) -> bool:
    return bool(_statics(state, info))


def _applies(state: GameState, info: CardInfo, card: CardInstance, owner: str, d: dict[str, Any]) -> bool:
    from app.rules import selectors
    from app.rules.plan import Plan

    if d["who"] == "you" and owner != card.controller:
        return False
    plan = Plan.view(state, owner, info)
    return selectors.matches(plan, selectors.from_key(d["sel"]), card, plan.ch(card), owner)


def _apply(op: dict[str, Any], option: tuple[str, ...]) -> list[tuple[str, ...]]:
    mana = tuple(option)
    if op["do"] == "mul":
        return [mana * int(op["n"])]
    if op["do"] == "fixed":
        return [(op["mana"],)]
    if op["do"] == "collapse":
        return [(op["to"],)] if len(mana) >= int(op["min"]) else [mana]
    if op["to"] == "choice":
        return [tuple(c for _ in mana) for c in COLORS]
    return [tuple(op["to"] for _ in mana)]


def extend(state: GameState, card: CardInstance, info: CardInfo,
           found: list[tuple[int, M.ManaAbility]]) -> list[tuple[int, M.ManaAbility]]:
    """The permanent's mana abilities with each {T} ability's options as the replacements that apply to it make them
    (106.12b). An ability whose mana the engine can't replace (restricted, counted, conditional, or two statics that
    apply) is left out: the player adds that mana by hand."""
    if not any(ab.tap for _, ab in found):
        return found
    statics = [d for owner, d in _statics(state, info) if _applies(state, info, card, owner, d)]
    if not statics:
        return found
    out = []
    for index, ab in found:
        if not ab.tap:
            out.append((index, ab))
            continue
        if len(statics) > 1 or ab.spend_only is not None or ab.count is not None or ab.instead_if:
            continue
        options = tuple(dict.fromkeys(new for opt in ab.options for new in _apply(statics[0]["op"], opt)))
        out.append((index, replace(ab, options=options)))
    return out
