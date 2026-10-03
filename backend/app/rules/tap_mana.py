"""-- mana riders (wave 5A) -- triggered mana abilities on tapping a permanent for mana, researched against CR 2026-09-25.

"Whenever you tap a land for mana, add one mana of any type that land produced." (Mirari's Wake, Zendikar
Resurgent), "Whenever you tap a nonland permanent for mana, add one mana of any type that permanent produced."
(Kinnan), "Whenever you tap a creature for mana, add an additional {G}." (Badgermole Cub), "Whenever you tap a Swamp
for mana, add an additional {B}." (Crypt Ghast, Nirkana Revenant), "Whenever you tap a land for mana while you're the
monarch, add an additional one mana of any color." (Regal Behemoth), "Whenever a player taps a land for mana, that
player adds one mana of any type that land produced." (Mana Flare, Heartbeat of Spring), and the spells "Until end of
turn, whenever a player taps an Island for mana, that player adds an additional {U}." (High Tide, Bubbling Muck).

* 106.12 / 106.12a: to tap a permanent for mana is to activate a mana ability of it with {T} in its cost; the ability
  triggers when such a mana ability resolves and produces mana (Kinnan ruling 2020-04-17).
* 605.1b / 605.4a: these are triggered mana abilities (no target, they trigger from a mana ability and add mana); they
  don't use the stack and resolve right after the mana ability. The engine adds the extra mana as part of that same
  activation (like app/rules/attached_mana.py), which is also what lets the payment solver count it (605.4a's example
  is Mana Flare paying for a spell).
* "you" is the trigger's controller: only permanents that player taps count; "a player … that player adds": anyone's,
  and the one who tapped gets it. "while you're the monarch" (725) is checked as the mana ability resolves.
* "one mana of any type that land produced" (106.1b: the six types, colorless included): one of the types the
  ability actually produced; with several, the player chooses one (Mirari's Wake ruling 2021-06-18). Restrictions or
  riders of the produced mana don't carry over to the extra mana (rulings): an ability whose mana is restricted
  ("Spend this mana only to …") is left to the player while such a trigger applies to it (as attached_mana does).
* "Until end of turn, whenever …" (a spell): a delayed triggered mana ability for the rest of the turn (603.7; 514.2:
  it ends in the cleanup step), kept in ``RulesState.tap_mana`` as {"turn", "controller", "def"}.

Definition: ``{"kind": "triggered", "trigger": "tap_for_mana", "who": "you"|"any", "sel": <selector key>,
"extra": [[mana…], …] | "produced", "monarch": bool, "effects": []}`` — never put on the stack.
"""

from __future__ import annotations

import re
from itertools import product
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules import mana as M
    from app.rules.characteristics import CardInfo
    from app.rules.plan import Plan

COLORS = ("W", "U", "B", "R", "G")
_LINE = re.compile(r"^Whenever (?P<who>you tap|a player taps) (?P<what>an? [^,]+?) for mana(?P<mon> while you're the monarch)?, "
                   r"(?P<adds>add|that player adds) (?P<m>.+?)\.(?: \(The types of mana are white, blue, black, red, green, and "
                   r"colorless\.\))?$")
_SPELL = re.compile(r"^Until end of turn, (?P<rest>whenever .+)$")


def definition(text: str) -> dict[str, Any] | None:
    from app.rules import selectors

    m = _LINE.match(text.strip())
    if m is None or (m["who"] == "you tap") != (m["adds"] == "add"):
        return None
    what = re.sub(r"^an? ", "", m["what"])
    if what.startswith(("this ", "~")):
        return None
    sel = selectors.parse(what)
    if sel is None or sel.player is not None or sel.zones not in ((), ("battlefield",)):
        return None
    add = m["m"]
    extra: Any
    if mm := re.fullmatch(r"(?:an additional )?(?P<s>(?:\{[WUBRGC]\})+)", add):
        extra = [re.findall(r"\{([WUBRGC])\}", mm["s"])]
    elif add in ("an additional one mana of any color", "one mana of any color"):
        extra = [[c] for c in COLORS]
    elif re.fullmatch(r"one mana of any type that (?:land|permanent|creature|artifact|artifact token) produced", add):
        extra = "produced"
    else:
        return None
    return {"kind": "triggered", "trigger": "tap_for_mana", "who": "you" if m["who"] == "you tap" else "any",
            "sel": sel.key(), "extra": extra, "monarch": bool(m["mon"]), "optional": False, "target": None, "effects": []}


def spell_effect(text: str) -> dict[str, Any] | None:
    """"Until end of turn, whenever a player taps an Island for mana, that player adds an additional {U}." as an
    instruction of a spell (``{"do": "tap_mana_until_eot", "def": …}``)."""
    m = _SPELL.match(text.strip())
    if m is None:
        return None
    rest = m["rest"].rstrip(".") + "."
    d = definition(rest[0].upper() + rest[1:])
    return {"do": "tap_mana_until_eot", "def": d} if d is not None else None


def until_eot(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The spell's instruction: the trigger exists for the rest of this turn (its controller: the spell's)."""
    plan.rules.tap_mana = [*[r for r in plan.rules.tap_mana if r.get("turn") == plan.state.turn.number],
                           {"turn": plan.state.turn.number, "controller": ctx["controller"], "def": e["def"]}]
    return True


def _triggers(state: GameState, info: CardInfo) -> list[tuple[str, dict[str, Any]]]:
    """(controller, definition) of every such trigger in play right now."""
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
            if "for mana" not in chars.of(c, info).oracle_text and c.copy_of is None \
                    and (r is None or r.object_id(c.id) not in copies):
                continue
            ch = derive(state, c, copiable(state, c, info), info)
            for d in scripts.definitions(ch).values():
                if d.get("trigger") == "tap_for_mana":
                    out.append((c.controller, d))
    if r is not None and state.turn.phase != "cleanup":  # (514.2: "until end of turn" ends in the cleanup step)
        out += [(str(x["controller"]), x["def"]) for x in r.tap_mana if x.get("turn") == state.turn.number]
    return out


def _applies(state: GameState, info: CardInfo, card: CardInstance, owner: str, d: dict[str, Any]) -> bool:
    from app.rules import selectors
    from app.rules.plan import Plan

    if d["who"] == "you" and owner != card.controller:
        return False
    if d.get("monarch") and state.table.monarch != owner:
        return False
    plan = Plan.view(state, owner, info)
    return selectors.matches(plan, selectors.from_key(d["sel"]), card, plan.ch(card), owner)


def _extra(d: dict[str, Any], option: tuple[str, ...]) -> list[tuple[str, ...]]:
    if d["extra"] == "produced":
        return [(m,) for m in dict.fromkeys(option)]
    return [tuple(x) for x in d["extra"]]


def extend(state: GameState, card: CardInstance, info: CardInfo,
           found: list[tuple[int, M.ManaAbility]]) -> list[tuple[int, M.ManaAbility]]:
    """The permanent's mana abilities with each {T} ability's options carrying the extra mana of the triggers that
    apply to it (605.4a: added right after, with the ability's own)."""
    if not any(ab.tap for _, ab in found):
        return found
    triggers = [d for owner, d in _triggers(state, info) if _applies(state, info, card, owner, d)]
    if not triggers:
        return found
    from dataclasses import replace

    out = []
    for index, ab in found:
        if not ab.tap:
            out.append((index, ab))
            continue
        if ab.spend_only is not None:
            continue  # (restricted mana with unrestricted extra: by hand)
        options = tuple(dict.fromkeys(tuple(opt) + tuple(m for part in combo for m in part)
                                      for opt in ab.options for combo in product(*[_extra(d, opt) for d in triggers])))
        out.append((index, replace(ab, options=options)))
    return out


def _template(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules.scripts import _NoMatch

    found = spell_effect("U" + m.group(0)[1:])
    if found is None:
        raise _NoMatch
    return [found], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(re.compile(r"^until end of turn, whenever .+ for mana, .+$"), _template)]


# -- triggers on tapping for mana that aren't mana abilities (605.5a: a target, or no mana) --------------------------------------
# "Whenever you tap this land for mana, target opponent creates a 1/1 colorless Spirit creature token." (Forbidden
# Orchard), "Whenever you tap this creature for mana, it deals 1 damage to each opponent." (Zhur-Taa Druid), "Whenever a
# player taps a land for mana, this enchantment deals 1 damage to that player." (Manabarbs): ordinary triggered abilities
# (603), put on the stack the next time a player would receive priority (603.3) — after the spell being paid for is cast.
# The event is a mana ability with {T} in its cost resolving and producing mana (106.12a): app/rules/casting.py emits
# "mana_added" with counter "tap"; app/rules/triggers.py reads it as the fact "tapped_for_mana" (its player: who tapped).
_CONDITION = re.compile(r"(?P<p>you|a player) taps? (?P<o>~|an? [^,]+?) for mana")


def condition(c: str) -> dict[str, Any] | None:
    from app.rules import selectors

    m = _CONDITION.fullmatch(c)
    if m is None:
        return None
    if m["o"] == "~":
        return {"event": "tapped_for_mana", "subject": "self"} if m["p"] == "you" else None
    sel = selectors.parse(re.sub(r"^an? ", "", m["o"]))
    if sel is None or sel.player is not None or sel.zones not in ((), ("battlefield",)):
        return None
    return {"event": "tapped_for_mana", "subject": "player", "player": "you" if m["p"] == "you" else "any", "obj": sel.key()}


def adds_mana(d: dict[str, Any]) -> bool:
    """A "tapped for mana" trigger that would add mana is a triggered mana ability (605.1b), never a stack trigger: the
    ones this module doesn't read stay manual."""
    import json

    cond = d.get("cond") or {}
    return d.get("kind") == "triggered" and cond.get("event") == "tapped_for_mana" and '"add_mana"' in json.dumps(d)
