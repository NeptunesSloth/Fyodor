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
# -- mana replacements (wave 49A) -- 106.12b: "Until end of turn, if you tap a land [you control] for mana, it produces {U} instead of any other type." (Deep Water),
# "… one mana of a color of your choice instead of any other type and amount." (Harvest Mage), "… if a player taps a nonbasic land for mana, it produces
# colorless mana instead of any other type." (Pale Moon): an effect for the rest of the turn (514.2), kept with the High Tide records (tap_mana.until_eot)
_UNTIL = re.compile(r"^Until end of turn, if (?:you tap (?P<mine>a land)(?: you control)?|a player taps (?P<any>a nonbasic land|a land)) for mana, it produces "
                    r"(?P<to>\{[WUBRGC]\}|colorless mana|one mana of a color of your choice) instead of any other type(?P<amount> and amount)?\.$")
# "If tapped for mana, Plains produce {R}, Islands produce {G}, … instead of any other type." (Naked Singularity, Reality Twist): the color follows the
# permanent's basic land types, the tapping player choosing one when it has several (ruling 2013-04-15); the amount stays
_MAP = re.compile(r"^If tapped for mana, (?P<m>(?:(?:Plains|Islands|Swamps|Mountains|Forests) produce \{[WUBRG]\}(?:, and |, | and )?)+) instead of any other type\.$")
_TYPES = {"Plains": "Plains", "Islands": "Island", "Swamps": "Swamp", "Mountains": "Mountain", "Forests": "Forest"}


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
    if (m := _MAP.match(text)) is not None:  # (wave 49A)
        return static("any", "permanent", {"do": "map", "map": {_TYPES[a]: b for a, b in re.findall(r"(\w+) produce \{(\w)\}", m["m"])}})
    return None


def spell_effect(text: str) -> dict[str, Any] | None:
    """(wave 49A) "Until end of turn, if … taps a land for mana, it produces …" as the instruction that records it for this turn."""
    from app.rules import selectors

    m = _UNTIL.match(text.strip())
    if m is None or (m["to"][0] == "o" and not m["amount"]):  # (a color of your choice is one mana: only "and amount")
        return None
    to = "C" if m["to"] == "colorless mana" else "choice" if m["to"][0] == "o" else m["to"][1]
    sel = selectors.parse("nonbasic land" if m["any"] == "a nonbasic land" else "land")
    op = {"do": "fixed", "mana": to} if m["amount"] else {"do": "recolor", "to": to}
    return {"do": "tap_mana_until_eot", "def": {"kind": "static", "static": "mana_replace", "who": "you" if m["mine"] else "any",
                                                 "sel": sel.key() if sel else "", "op": op, "effects": []}}


def _template(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules.scripts import _NoMatch

    if (found := spell_effect("U" + m.group(0)[1:].rstrip(".") + ".")) is None:
        raise _NoMatch
    return [found], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(re.compile(r"^until end of turn, if (?:you tap|a player taps) .+ for mana, it produces .+$"), _template)]


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
            if not re.search(r"mana, (?:it produces|\w+ produce)", chars.of(c, info).oracle_text) and c.copy_of is None \
                    and (r is None or r.object_id(c.id) not in copies):
                continue
            ch = derive(state, c, copiable(state, c, info), info)
            for d in scripts.definitions(ch).values():
                if d.get("static") == "mana_replace":
                    out.append((c.controller, d))
    if r is not None and state.turn.phase != "cleanup":  # (wave 49A) this turn's effects of resolved spells and abilities (514.2: they end in the cleanup step)
        out += [(str(x["controller"]), x["def"]) for x in r.tap_mana if x["def"].get("static") == "mana_replace" and x.get("turn") == state.turn.number]
    return out


def in_play(state: GameState, info: CardInfo) -> bool:
    return bool(_statics(state, info))


def _applies(state: GameState, info: CardInfo, card: CardInstance, owner: str, d: dict[str, Any]) -> bool:
    from app.rules import selectors
    from app.rules.plan import Plan

    if d["who"] == "you" and owner != card.controller:
        return False
    plan = Plan.view(state, owner, info)
    return selectors.matches(plan, selectors.from_key(d["sel"]), card, plan.ch(card), owner) \
        and (d["op"]["do"] != "map" or bool(_map_colors(d["op"], plan.ch(card).subtypes)))  # (wave 49A) a Plains permanent, say


def _map_colors(op: dict[str, Any], subtypes: Any) -> list[str]:
    return list(dict.fromkeys(c for t, c in op["map"].items() if t in subtypes))


def _apply(op: dict[str, Any], option: tuple[str, ...], subtypes: Any = ()) -> list[tuple[str, ...]]:
    mana = tuple(option)
    if op["do"] == "mul":
        return [mana * int(op["n"])]
    if op["do"] == "map":  # (wave 49A) one color per mapped basic land type it has; all its mana is of the one chosen
        return [tuple(c for _ in mana) for c in _map_colors(op, subtypes)]
    if op["do"] == "fixed":
        return [(c,) for c in COLORS] if op["mana"] == "choice" else [(op["mana"],)]
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
    from app.rules.plan import Plan

    subtypes = Plan.view(state, card.controller, info).ch(card).subtypes  # (wave 49A) for a "map"
    out = []
    for index, ab in found:
        if not ab.tap:
            out.append((index, ab))
            continue
        if len(statics) > 1 or ab.spend_only is not None or ab.count is not None or ab.instead_if:
            continue
        options = tuple(dict.fromkeys(new for opt in ab.options for new in _apply(statics[0]["op"], opt, subtypes)))
        out.append((index, replace(ab, options=options)))
    return out
