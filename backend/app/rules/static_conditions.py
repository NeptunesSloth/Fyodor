"""Conditions of conditional static abilities ("as long as …", wave 4B), researched against CR 2026-09-25.

app/rules/statics.py reads "As long as <condition>, <subject> <predicate>." and "<subject> <predicate> as long
as <condition>."; this module adds the condition shapes that only a static's own context can answer (604.2,
611.3a: a static applies at any moment its condition is true, never locked in):

* ``{"static": "attached_is", "sel": <selector key>, "noun": "creature" | "permanent" | …}`` — "as long as
  equipped creature is legendary", "enchanted creature is white", "enchanted permanent is an Equipment": the
  object the source is attached to (301.5a, 303.4b) matches the selector (read as it is now);
* ``{"static": "designation", "is": "monstrous" | "renowned"}`` — the source has the designation
  (701.37b, 702.112b: kept until it leaves the battlefield); ``{"static": "self", "test": "modified"}``
  (700.9) is answered by statics.holds;
* ``{"static": "zone", "zone": "graveyard"}`` — "as long as this card is in your graveyard": the ability
  states the zone it functions from (113.6b, 604.2); "you" is the card's owner (108.4a);
* ``{"static": "opp_graveyard", "n": N}`` — "an opponent has N or more cards in their graveyard" (some one
  opponent);
* ``{"static": "opp_life", "op": "<=", "n": N}`` — "an opponent has N or less life" (some one opponent);
* ``{"static": "life_vs_start", "op": ">=" | ">" | "<=" | "<", "plus": N, "half": bool}`` — your life total
  against your starting life total (119.1, 903.7: 40 in Commander; the game's setting is read);
* ``{"static": "all", "conds": [...]}`` — "this card is in your graveyard and you control a Mountain".
* (wave 35D) ``ring_bearer`` (701.54e), ``self_attached`` / ``host_attached`` (a count of the Equipment or Auras attached to the source, or to
  the object it is attached to), ``dealt_damage`` (120.3: it has dealt damage since it became this object), ``was_cast`` (a permanent that was
  cast as a spell), ``single_graveyard``, ``exile_owned``, ``blocked_by``, ``transformed`` (701.27g), ``doors`` (709.5): reads of the table.

Devotion ("your devotion to red is less than five", 700.5) is a plain ``conditions`` value condition
(``{"value": {"devotion": ["R"]}, "op": "<=", "n": 4}``). Anything else parses to None (manual).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import selectors, values

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

Condition = dict[str, Any]

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_ADJECTIVES = frozenset({"legendary", "white", "blue", "black", "red", "green", "colorless", "multicolored", "snow",
                         "attacking", "blocking", "tapped", "untapped"})  # (wave 9B: "enchanted creature is attacking")
_ATTACHED = re.compile(r"(?P<who>equipped|enchanted) (?P<noun>creature|permanent|land|artifact) (?P<neg>is not|isn't|is) (?P<desc>.+)")
# -- as long as (wave 25A) -- "As long as you control enchanted creature" / "As long as another player controls enchanted creature" (Mishra's
# Domination, Dog Umbra): the controller of the object the source is attached to, against the source's controller (301.5, 303.4)
_ATTACHED_CONTROLLER = re.compile(r"(?P<who>you|another player) controls? (?P<what>enchanted|equipped) (?P<noun>creature|permanent|land|artifact)")
# "~ is a creature" / "it's a Wall" / "this permanent isn't a creature": the source's own types now (305.7, 613.1d)
_SELF_IS = re.compile(r"(?:~|it|this creature|this permanent|this artifact)(?P<neg> is not| isn't| is|'s) (?P<desc>(?:a|an) .+)")
_ATTACHED_CTRL = re.compile(r"(?:its|(?:equipped|enchanted) (?:creature|permanent|land)'s) controller (?P<rest>(?:controls|has) .+)")
_ATTACHED_STAT = re.compile(r"(?:its|(?:equipped|enchanted) (?:creature|permanent)'s) (?P<stat>power|toughness) is (?P<n>\w+) or "
                            r"(?P<cmp>less|greater|more|fewer)")
# -- static_other (wave 42A) -- "~'s power is 1 or less" (Stature, Technodrome: "her / his / its power", written "~'s" by statics.parse): the source's own power or
# toughness, 613.4, as the rules pass has it after layer 7 (layers._with_rules), for a rule-only static ("can't be blocked", "can't attack or block")
_SELF_STAT = re.compile(r"~'s (?P<stat>power|toughness) is (?P<n>\w+) or (?P<cmp>less|greater|more|fewer)")
_DESIGNATION = re.compile(r"(?:~ is|it's|it is) (?P<is>monstrous|renowned)")
_MODIFIED = re.compile(r"(?:~ is|it's|it is) modified")
_IN_GRAVEYARD = re.compile(r"this card is in your graveyard(?: and (?P<rest>.+))?")
_OPP_GRAVEYARD = re.compile(r"an opponent has (?P<n>\w+) or more cards in their graveyard")
_OPP_LIFE = re.compile(r"an opponent has (?P<n>\w+) or less life")
_DEVOTION = re.compile(r"your devotion to (?P<c1>white|blue|black|red|green)(?: and (?P<c2>white|blue|black|red|green))? "
                       r"is less than (?P<n>\w+)")
_START = "your starting life total"
_LIFE_VS_START = {
    f"your life total is greater than {_START}": (">", 0, False),
    f"your life total is greater than or equal to {_START}": (">=", 0, False),
    f"your life total is less than or equal to half {_START}": ("<=", 0, True),
    f"your life total is less than {_START}": ("<", 0, False),  # (-- trailing & intervening ifs (wave 38A) -- Resolute Archangel)
}
_LIFE_MORE = re.compile(r"you have at least (?P<n>\w+) life more than your starting life total"
                        r"|your life total is at least (?P<m>\w+) greater than your starting life total")
# -- as long as (wave 25A) -- "there are three or more cards exiled with this creature" / "four or more card types among cards exiled with ~"
# (Veteran Survivor, Keen-Eyed Curator): the cards its linked exiling ability put into exile and that are still those objects there (607.2a, 400.7)
_EXILED_COUNT = re.compile(r"there are (?P<n>\w+) or more (?P<what>cards|card types among cards) exiled with (?:~|this \w+)")
# -- as long as (wave 25A) -- "the top card of your library is black / a creature card / an artifact or creature card" (Vampire Nocturnus, Mul Daya
# Channelers): the top card of the controller's library as it is now (a static that reveals it, "Play with the top card of your library revealed":
# the fact is public)
_TOP_CARD = re.compile(r"the top card of your library is (?:(?:a|an) (?P<sel>.+? card)|(?P<color>white|blue|black|red|green))")
_SELF_COUNTERS = re.compile(r"there are (?P<n>\w+) or more (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters on ~")
# -- as long as (wave 35D) -- the shapes below read the table and the source (or the object it is attached to) and nothing else, so they are as
# safe in a static as the ones above. Each says "~" for the source: statics.parse writes "it" as "~" where the subject is the source itself
_RING_BEARER = re.compile(r"(?:~|it) is your Ring-bearer|it's your Ring-bearer")
_ATTACH_COUNT = re.compile(r"(?:(?P<a>another|an?)|(?P<n>\w+) or more) (?P<sub>Equipment|Auras?) (?:is|are) attached to "
                           r"(?:(?P<self>~)|(?P<who>equipped|enchanted) (?P<noun>creature|permanent|land))")
_ENCHANTED_BY = re.compile(r"~ is (?:enchanted|equipped) by (?:(?P<ex>exactly) (?P<n>\w+)|(?P<m>\w+) or more) (?P<sub>Auras?|Equipment)")
_DEALT = re.compile(r"~ (?:hasn't|haven't) dealt (?P<c>combat )?damage yet")
_SINGLE_GRAVEYARD = re.compile(r"there are (?P<n>\w+) or more cards in a single graveyard")
_EXILE_OWNED = re.compile(r"(?P<who>you|an opponent) owns? an? card in exile(?P<adv> that has an Adventure)?")
_BLOCKED_BY = re.compile(r"(?P<n>\w+) or more creatures are blocking ~")
_COUNTER_ON_ANY = re.compile(r"an? (?P<sel>[a-z]+) has an? (?P<kind>\+1/\+1|-1/-1|[a-z]+) counter on it")
_DOORS = re.compile(r"there are (?P<n>\w+) or more unlocked doors among Rooms you control")


def _num(word: str | None) -> int | None:
    if word is None:
        return None
    w = word.lower()
    return int(w) if w.isdigit() else values.NUMBERS.get(w)


def attached_selector(desc: str) -> str | None:
    """"legendary" / "white" / "a Human or an Angel" / "a creature" / "an Equipment" / "a basic Mountain" →
    a selector key for one object on the battlefield (no "you": the test is about the object alone)."""
    phrase = re.sub(r"\b(?:a|an) ", "", desc.strip())
    words = phrase.split()
    if not words:
        return None
    if all(w in _ADJECTIVES for w in words):
        phrase += " permanent"
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card or sel.other \
            or sel.controller is not None or sel.owner is not None or sel.extras:
        return None
    if sel.key() == selectors.Selector().key():
        return None  # ("is a permanent": says nothing)
    return sel.key()


def parse(text: str) -> Condition | None:
    """A condition only a static ability's context answers, or None (statics.py tries the others)."""
    t = text.strip()
    if t in ("~ is paired with another creature", "this creature is paired with another creature"):  # -- soulbond (wave 24B) -- 702.95b
        return {"static": "paired"}
    m = _ATTACHED.fullmatch(t)
    if m and m["desc"] == "attacking alone":  # -- as long as (wave 35D) -- 506.5: the object it is attached to is the only attacking creature
        alone: Condition = {"static": "host_test", "test": "attacking_alone", "who": m["who"], "noun": m["noun"]}
        return {"static": "not", "cond": alone} if m["neg"] in ("is not", "isn't") else alone
    if m:
        key = attached_selector(m["desc"])
        found: Condition = {"static": "attached_is", "sel": key, "noun": m["noun"], "who": m["who"]}
        return None if not key else {"static": "not", "cond": found} if m["neg"] in ("is not", "isn't") else found
    m = _ATTACHED_CONTROLLER.fullmatch(t)
    if m:
        return {"static": "attached_ctrl_is", "you": m["who"] == "you", "who": m["what"], "noun": m["noun"]}
    m = _SELF_IS.fullmatch(t)
    if m and (key := attached_selector(m["desc"])) is not None:
        own: Condition = {"static": "self_is", "sel": key}
        return {"static": "not", "cond": own} if m["neg"] in (" is not", " isn't") else own
    m = _ATTACHED_CTRL.fullmatch(t)
    if m:
        from app.rules import conditions

        inner = conditions.parse("you " + m["rest"])
        return {"static": "attached_ctrl", "cond": inner} if inner is not None else None
    m = _ATTACHED_STAT.fullmatch(t)
    if m:
        n = _num(m["n"])
        if n is None:
            return None
        return {"static": "attached_stat", "stat": m["stat"], "n": n, "op": "<=" if m["cmp"] in ("less", "fewer") else ">="}
    m = _SELF_STAT.fullmatch(t)
    if m and (n := _num(m["n"])) is not None:
        return {"static": "self_stat", "stat": m["stat"], "n": n, "op": "<=" if m["cmp"] in ("less", "fewer") else ">="}
    m = _DESIGNATION.fullmatch(t)
    if m:
        return {"static": "designation", "is": m["is"]}
    if _MODIFIED.fullmatch(t):
        return {"static": "self", "test": "modified"}
    m = _IN_GRAVEYARD.fullmatch(t)
    if m:
        zone: Condition = {"static": "zone", "zone": "graveyard"}
        if not m["rest"]:
            return zone
        from app.rules import statics

        rest = statics.condition(m["rest"])
        if rest is None or rest.get("static") in ("self", "self_counter", "attached_is", "designation", "zone"):
            return None  # (a card in a graveyard is never tapped, attached or monstrous)
        return {"static": "all", "conds": [zone, rest]}
    m = _OPP_GRAVEYARD.fullmatch(t)
    if m:
        n = _num(m["n"])
        return {"static": "opp_graveyard", "n": n} if n is not None else None
    m = _OPP_LIFE.fullmatch(t)
    if m:
        n = _num(m["n"])
        return {"static": "opp_life", "op": "<=", "n": n} if n is not None else None
    m = _DEVOTION.fullmatch(t)
    if m:
        n = _num(m["n"])
        if n is None or n < 1:
            return None
        colors = [_COLORS[c] for c in (m["c1"], m["c2"]) if c]
        return {"value": {"devotion": colors}, "op": "<=", "n": n - 1}  # 700.5: "less than N"
    if t in _LIFE_VS_START:
        op, plus, half = _LIFE_VS_START[t]
        return {"static": "life_vs_start", "op": op, "plus": plus, "half": half}
    m = _LIFE_MORE.fullmatch(t)
    if m:
        n = _num(m["n"] or m["m"])
        return {"static": "life_vs_start", "op": ">=", "plus": n, "half": False} if n is not None else None
    m = _TOP_CARD.fullmatch(t)
    if m:
        sel = selectors.parse(m["sel"] or f"{m['color']} card")
        if sel is not None and not sel.zones and sel.card and sel.player is None and not sel.extras:
            return {"static": "top_card", "sel": sel.key()}
        return None
    m = _EXILED_COUNT.fullmatch(t)
    if m and (n := _num(m["n"])) is not None:
        return {"static": "exiled_count", "n": n, "types": m["what"] != "cards"}
    m = _SELF_COUNTERS.fullmatch(t)
    if m:
        n = _num(m["n"])
        return {"static": "self_counter", "counter": m["kind"], "op": ">=", "n": n} if n is not None else None
    m = _ANY_PLAYER.fullmatch(t)
    if m:  # "any player controls a black permanent" (Knight of Grace): whoever controls it
        sel = selectors.parse(m["sel"])
        if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card or sel.controller is not None \
                or sel.owner is not None or sel.other:
            return None
        return {"value": {"count": sel.key()}, "op": ">=", "n": 1}
    m = _MOST_COMMON.fullmatch(t)  # -- as long as (wave 20B) -- the Djinns (Zanam Djinn): counted over the permanents
    if m:
        return {"static": "most_common_color", "color": _COLORS[m["c"]]}
    if t == "you have more cards in hand than each opponent":  # -- as long as (wave 20B) -- (Secretkeeper, Okina Nightwatch)
        return {"static": "hand_most"}
    if t == "an opponent has no cards in hand":  # (Guul Draz Specter: some one opponent)
        return {"static": "opp_hand", "op": "==", "n": 0}
    if t == "a player has no cards in hand":  # -- static_other (wave 27A) -- (Lupine Prototype: any one player, you included)
        return {"static": "any_hand", "n": 0}
    if t == "an opponent is poisoned":  # 122.1f: has one or more poison counters (Viridian Betrayers)
        return {"value": {"player_counters": "poison"}, "op": ">=", "n": 1, "per_opponent": True}
    return _parse_35d(t)


def _parse_35d(t: str) -> Condition | None:
    """-- as long as (wave 35D) -- see the module docstring."""
    if _RING_BEARER.fullmatch(t):
        return {"static": "ring_bearer"}
    m = _ATTACH_COUNT.fullmatch(t)
    if m:
        n = 1 if m["a"] else _num(m["n"])
        if n is None:
            return None
        sub = "Equipment" if m["sub"] == "Equipment" else "Aura"
        if m["self"]:
            return {"static": "self_attached", "sub": sub, "op": ">=", "n": n, "other": m["a"] == "another"}
        return {"static": "host_attached", "sub": sub, "op": ">=", "n": n, "other": m["a"] == "another", "who": m["who"], "noun": m["noun"]}
    m = _ENCHANTED_BY.fullmatch(t)
    if m and (n := _num(m["n"] or m["m"])) is not None:
        return {"static": "self_attached", "sub": "Equipment" if m["sub"] == "Equipment" else "Aura", "op": "==" if m["ex"] else ">=", "n": n,
                "other": False}
    m = _DEALT.fullmatch(t)
    if m:
        return {"static": "not", "cond": {"static": "dealt_damage", "combat": bool(m["c"])}}
    if t == "~ was cast":
        return {"static": "was_cast"}
    m = _SINGLE_GRAVEYARD.fullmatch(t)
    if m and (n := _num(m["n"])) is not None:
        return {"static": "single_graveyard", "n": n}
    m = _EXILE_OWNED.fullmatch(t)
    if m:
        adv = selectors.parse("card that has an Adventure in exile") if m["adv"] else None  # 715.1 (the selector reads the printing)
        return {"static": "exile_owned", "you": m["who"] == "you", "sel": adv.key() if adv is not None else None}
    m = _BLOCKED_BY.fullmatch(t)
    if m and (n := _num(m["n"])) is not None:
        return {"static": "blocked_by", "n": n}
    if t == "you control a transformed permanent":
        return {"static": "transformed"}
    m = _DOORS.fullmatch(t)
    if m and (n := _num(m["n"])) is not None:
        return {"static": "doors", "n": n}
    if t == "you control a permanent of each color":  # 105.1: all five colors are among the permanents you control
        from app.rules import conditions

        return conditions.parse("there are five colors among permanents you control")
    m = _CONTROL_NAMED.fullmatch(t)  # 201.2: a permanent with this name (as it is now)
    if m:
        return {"static": "named", "name": m["name"]}
    m = _COUNTER_ON_ANY.fullmatch(t)  # "a creature has a -1/-1 counter on it": some permanent of any controller (Tenacious Hunter)
    if m:
        sel = selectors.parse(f"{m['sel']} with a {m['kind']} counter on it")
        if sel is not None and sel.zones == ("battlefield",) and sel.player is None and not sel.card and sel.controller is None:
            return {"value": {"count": sel.key()}, "op": ">=", "n": 1}
    return None


_MOST_COMMON = re.compile(r"(?P<c>white|blue|black|red|green) is the most common color among all permanents or is tied for most common")
_ANY_PLAYER = re.compile(r"any player controls (?:a|an) (?P<sel>.+)")
_PLAIN = frozenset({"opp_graveyard", "opp_life", "opp_hand", "life_vs_start", "any_hand"})
_HOST = frozenset({"attached_is", "host_test"})  # -- as long as (wave 35D) -- "enchanted creature is blocking and you control a snow land" (Snow Devil)


def compound(text: str) -> Condition | None:
    """"you have 30 or more life and an opponent has 10 or less life" (Blood Baron of Vizkopa): both halves are
    conditions about players (never about the source or an attached object, whose "it" a group subject could
    claim). Tried only after the other grammars gave up."""
    from app.rules import statics

    for piece in re.finditer(" and ", text):
        left, right = text[: piece.start()], text[piece.end():]
        a, b = statics.condition(left), statics.condition(right)
        if a is None or b is None:
            continue
        if all(c.get("static") is None or c.get("static") in _PLAIN or c.get("static") in _HOST for c in (a, b)):  # (wave 35D: _HOST)
            return {"static": "all", "conds": [a, b]}
    return None


_YOU_CONTROL_OR = re.compile(r"you control (?P<a>(?:an?|\d+) .+?) or (?P<b>(?:an?|\d+) .+)")
_COMMANDER_OR = re.compile(r"you control an? commander that's an? (?P<a>creature|planeswalker|artifact|enchantment) or (?P<b>creature|planeswalker|artifact|enchantment)")
_CONTROL_NAMED = re.compile(r"you control an? permanent named (?P<name>(?:(?! or an? permanent named ).)+)")


def either(text: str) -> Condition | None:
    """-- as long as (wave 35D) -- "you control an artifact creature or a Plan" (Doctor Doom), "you control a commander that's a creature or
    planeswalker" (Gray Harbor Merfolk), "you control a permanent named A or a permanent named B" (Liu Bei): the first half that holds. Each
    half is a count of permanents, so the whole is as safe as one (a half that reads the source or an attached object isn't taken)."""
    from app.rules import statics

    m = _COMMANDER_OR.fullmatch(text)
    pieces = [f"you control a {m['a']} commander", f"you control a {m['b']} commander"] if m else None
    if pieces is None:
        m = _YOU_CONTROL_OR.fullmatch(text)
        pieces = [f"you control {m['a']}", f"you control {m['b']}"] if m else None
    if pieces is None:
        return None
    found = [statics.condition(p) for p in pieces]
    if any(c is None or not (c.get("static") == "named" or (c.get("static") is None and "value" in c)) for c in found):
        return None
    return {"static": "either", "conds": found}


KINDS = frozenset({"top_card", "exiled_count", "attached_ctrl_is", "self_is", "attached_ctrl", "attached_stat", "attached_is", "designation", "zone", "opp_graveyard", "opp_life", "opp_hand", "life_vs_start", "all",
                    "most_common_color", "hand_most", "paired", "any_hand",  # (wave 20B)
                    "ring_bearer", "self_attached", "host_attached", "dealt_damage", "was_cast", "single_graveyard", "exile_owned", "blocked_by",
                    "transformed", "doors", "named", "either", "host_test", "self_stat"})  # (wave 35D; 42A: self_stat)


def attached_object(plan: Plan, source: CardInstance) -> CardInstance | None:
    target = plan.state.cards.get(source.attached_to or "")
    if target is None or not target.zone.endswith(":battlefield") or not source.zone.endswith(":battlefield"):
        return None
    return target


def holds(plan: Plan, cond: Condition, *, source: CardInstance, controller: str) -> bool:
    """Is one of this module's conditions true right now (611.3a)?"""
    from app.rules import statics

    kind = cond["static"]
    if kind == "all":
        return all(statics.holds(plan, c, source=source, controller=controller) for c in cond["conds"])
    if kind == "paired":  # -- soulbond (wave 24B) -- 702.95b (app/rules/pairing.py)
        from app.rules import pairing

        return pairing.is_paired(plan, source)
    if kind == "zone":  # 113.6b: the card is in its owner's graveyard
        return source.zone == f"{source.owner}:graveyard"
    if kind == "attached_is":
        target = attached_object(plan, source)
        if target is None:
            return False
        ch = plan.ch(target)
        if cond["noun"] == "creature" and not ch.is_creature:
            return False
        if cond["noun"] == "land" and not ch.is_land:
            return False
        if cond["noun"] == "artifact" and "Artifact" not in ch.types:
            return False
        return selectors.matches(plan, selectors.from_key(cond["sel"]), target, ch, controller, source.id)
    if kind == "top_card":  # -- as long as (wave 25A) --
        library = plan.state.zones.get(f"{controller}:library", [])
        top = plan.state.cards.get(library[0]) if library else None
        return top is not None and selectors.matches(plan, selectors.from_key(cond["sel"]), top, plan.ch(top), controller, source.id)
    if kind == "exiled_count":  # -- as long as (wave 25A) -- the cards exiled with the source (exiled_with.cards), their types counted as they are in exile
        r = plan.rules
        found = [state_card for oid in (r.exiled_with.get(r.object_id(source.id), []) if r is not None else [])
                 if (state_card := plan.state.cards.get(oid.rsplit(".", 1)[0])) is not None and state_card.zone.endswith(":exile")
                 and plan.oid(state_card.id) == oid]
        if cond["types"]:
            return len({t for c in found for t in plan.ch(c).types}) >= cond["n"]
        return len(found) >= cond["n"]
    if kind == "attached_ctrl_is":  # -- as long as (wave 25A) -- the host's controller is (or isn't) the source's controller
        host = attached_object(plan, source)
        return host is not None and (host.controller == controller) == cond["you"]
    if kind == "self_is":  # -- as long as (wave 25A) -- the source's own types as they are now
        return source.zone.endswith(":battlefield") and selectors.matches(plan, selectors.from_key(cond["sel"]), source, plan.ch(source), controller, source.id)
    if kind == "attached_ctrl":  # -- as long as (wave 16F) -- "its controller controls another creature": the attached object's controller
        host = attached_object(plan, source)
        from app.rules import conditions

        return host is not None and conditions.holds(plan, {"controller": host.controller, "source_card": host.id}, cond["cond"])
    if kind == "attached_stat":  # "its power is 3 or less": the attached object's power / toughness now (613.4)
        host = attached_object(plan, source)
        if host is None:
            return False
        from app.rules import sba

        ch = plan.ch(host)
        got = sba.power(host, ch) if cond["stat"] == "power" else sba.toughness(host, ch)
        return got is not None and (got <= cond["n"] if cond["op"] == "<=" else got >= cond["n"])
    if kind == "self_stat":  # -- static_other (wave 42A) -- the source's power / toughness, read by layers._with_rules for its own rule (None anywhere else)
        from app.rules import layers

        got = layers.rule_pt(source.id, cond["stat"])
        return got is not None and (got <= cond["n"] if cond["op"] == "<=" else got >= cond["n"])
    if kind == "designation":  # 701.37b / 702.112b: a designation of this object (a new object has none, 400.7)
        r = plan.rules
        if r is None or not source.zone.endswith(":battlefield"):
            return False
        return r.object_id(source.id) in (r.monstrous if cond["is"] == "monstrous" else r.renowned)
    if kind in _HOLDS_35D:
        return _holds_35d(plan, cond, source, controller)
    opponents = [p for p in plan.live() if p != controller]
    if kind == "most_common_color":  # a permanent of two colors counts for each (105.2); colors as they are now (layer 5 is done first)
        tally = {c: 0 for c in "WUBRG"}
        for c in plan.state.cards.values():
            if c.zone.endswith(":battlefield") and plan.in_game(c):
                for col in plan.ch(c).colors:
                    if col in tally:
                        tally[col] += 1
        return tally[cond["color"]] > 0 and tally[cond["color"]] == max(tally.values())
    if kind == "hand_most":
        mine = len(plan.state.zones.get(f"{controller}:hand", ()))
        return bool(opponents) and all(mine > len(plan.state.zones.get(f"{p}:hand", ())) for p in opponents)
    if kind == "opp_graveyard":
        return any(len(plan.state.zones.get(f"{p}:graveyard", ())) >= cond["n"] for p in opponents)
    if kind == "opp_life":
        return any(plan.state.players[p].life <= cond["n"] for p in opponents)
    if kind == "any_hand":  # (wave 27A) some player in the game has exactly n cards in hand
        return any(len(plan.state.zones.get(f"{p}:hand", ())) == cond["n"] for p in plan.live())
    if kind == "opp_hand":
        return any(len(plan.state.zones.get(f"{p}:hand", ())) == cond["n"] for p in opponents)
    if kind == "life_vs_start":
        return life_vs_start(plan, cond, controller)
    return False


def life_vs_start(plan: Plan, cond: Condition, controller: str) -> bool:
    """119.1, 903.7: ``controller``'s life total against the game's starting life total (also read by an ability's own "if", conditions.holds)."""
    life = plan.state.players[controller].life
    start = plan.state.settings.starting_life
    if cond.get("half"):  # "less than or equal to half your starting life total" (no rounding needed: compare doubled)
        return 2 * life <= start
    want = start + int(cond.get("plus") or 0)
    return {">": life > want, ">=": life >= want, "<=": life <= want, "<": life < want}[cond["op"]]


_HOLDS_35D = frozenset({"ring_bearer", "self_attached", "host_attached", "dealt_damage", "was_cast", "single_graveyard", "exile_owned",
                        "blocked_by", "transformed", "doors", "named", "either", "host_test"})


def _holds_35d(plan: Plan, cond: Condition, source: CardInstance, controller: str) -> bool:
    """-- as long as (wave 35D) -- the conditions of the module docstring, read now (611.3a). Nothing here reads a hidden card: a count of
    cards (public), the state of permanents (public), the printing of a card in exile its controller (its owner) may look at."""
    kind, state, r = cond["static"], plan.state, plan.rules
    on_field = source.zone.endswith(":battlefield")
    if kind == "ring_bearer":  # 701.54e
        from app.rules import designations

        return on_field and designations.ring_bearer_of(state, source) and source.controller == controller
    if kind in ("self_attached", "host_attached"):  # 301.5, 303.4: what is attached to it (an Aura or Equipment on a host), the source apart if "another"
        host = source if kind == "self_attached" else attached_object(plan, source)
        if host is None or not on_field:
            return False
        found = sum(1 for c in state.cards.values() if c.attached_to == host.id and c.zone.endswith(":battlefield")
                    and not (cond["other"] and c.id == source.id) and cond["sub"] in plan.ch(c).subtypes)
        return found == cond["n"] if cond["op"] == "==" else found >= cond["n"]
    if kind == "dealt_damage":  # 120.3: since it became this object (400.7), more than 0 damage (prevented damage is not dealt, 615.1)
        return r is not None and on_field and r.object_id(source.id) + ("+combat" if cond["combat"] else "") in r.dealt_damage
    if kind == "was_cast":  # 608.3: the permanent remembers how its spell was paid (app/rules/engine.py), a copy's record is not a cast
        record = r.payments.get(r.object_id(source.id)) if r is not None else None
        return on_field and record is not None and record.cast_from is not None
    if kind == "single_graveyard":  # 404.1: each player's graveyard is a zone of its own
        return any(len(state.zones.get(f"{p}:graveyard", ())) >= cond["n"] for p in state.players)
    if kind == "exile_owned":  # 406.1: exile is a zone of its owner's; a card's owner is the player whose zone it is in
        owners = [controller] if cond["you"] else [p for p in plan.live() if p != controller]
        sel = selectors.from_key(cond["sel"]) if cond["sel"] else None
        return any((c := state.cards.get(cid)) is not None and (sel is None or (not c.unseen and selectors.matches(
            plan, sel, c, plan.ch(c), controller, source.id))) for p in owners for cid in state.zones.get(f"{p}:exile", ()))
    if kind == "blocked_by":  # 509.1: the creatures that block it (a creature blocking more than one attacker blocks each)
        return on_field and sum(1 for c in state.cards.values() if c.zone.endswith(":battlefield") and c.blocks(source.id)) >= cond["n"]
    if kind == "transformed":  # 701.27g: a double-faced permanent with its back face up (a merged or melded permanent never is)
        from app.rules import characteristics as chars

        return any(c.controller == controller and c.zone.endswith(":battlefield") and c.face == 1 and not c.face_down and not c.melded
                   and not c.merged and chars.transformable(c, plan.info) for c in state.cards.values())
    if kind == "host_test":  # a test of the source ("attacking alone") made of the object it is attached to (301.5, 303.4)
        host = attached_object(plan, source)
        from app.rules import statics

        return host is not None and statics.holds(plan, {"static": "self", "test": cond["test"]}, source=host, controller=controller)
    if kind == "either":
        from app.rules import statics

        return any(statics.holds(plan, c, source=source, controller=controller) for c in cond["conds"])
    if kind == "named":
        return any(c.controller == controller and c.zone.endswith(":battlefield") and plan.ch(c).name == cond["name"] for c in state.cards.values())
    if kind == "doors":  # 709.5c: the unlocked doors of the Rooms you control
        from app.rules import rooms

        return sum(len(rooms.doors_of(plan, c.id)) for c in state.cards.values()
                   if c.controller == controller and c.zone.endswith(":battlefield") and "Room" in plan.ch(c).subtypes) >= cond["n"]
    return False


def modified(plan: Plan, card: CardInstance) -> bool:
    """700.9: it has a counter on it, it's equipped, or it's enchanted by an Aura its controller controls."""
    if any(n > 0 for n in card.counters.values()):
        return True
    for c in plan.state.cards.values():
        if c.attached_to != card.id or not c.zone.endswith(":battlefield"):
            continue
        subtypes = plan.ch(c).subtypes
        if "Equipment" in subtypes or ("Aura" in subtypes and c.controller == card.controller):
            return True
    return False
