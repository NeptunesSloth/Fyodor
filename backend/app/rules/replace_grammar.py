"""The wordings of replacement and prevention statics that app/rules/replace.py applies (CR 614, 615).

A static line either matches one of these templates exactly or stays manual (never a guess). Each
template becomes ``{"kind": "static", "static": "replace", "event": <event>, "match": {...}, "op":
{...}}`` — which event it watches for (614.1), which of those events it applies to, and how it
modifies them — or ``{"kind": "static", "static": "enters_tapped_others", "who": [...]}`` for "[Objects]
enter tapped" (614.1d). ``~`` is the permanent's own name (``scripts.self_text``).

Events and their ops (researched against CR 2026-09-25):

* ``tokens`` (111, 614.16): ``mul`` N (Parallel Lives, Doubling Season, Ojer Taq), ``add`` 1 of the
  same token (Xorn). "those tokens plus a [different token]" (Chatterfang, Peregrin Took), "may
  instead" (Jinnie Fay) and copies (Esix) stay manual.
* ``counters`` on permanents (122.6, 614.16): ``mul`` / ``add`` (Hardened Scales, Winding
  Constrictor, Doubling Season: "If an effect would put …" is ``effect_only``, Vizier of Remedies:
  ``add`` -1). "If you would put …" wordings (the player putting the counters: Vorinclex, Doc
  Samson) stay manual.
* ``player_counters``: "If you would get one or more counters" (Winding Constrictor).
* ``draw`` (121.6, 614.11): ``win`` (Laboratory Maniac), ``skip`` (Living Conundrum), ``steal``
  ("instead that player skips that draw and you draw a card": Notion Thief), ``draw`` N (Thought
  Reflection); "except the first one [they] draw in each of [their] draw steps" (504.1) is part of
  the match. "may instead", reveal / look / dredge wordings stay manual.
* ``life`` gain (119.10): ``mul`` (Boon Reflection), ``add`` (Angel of Vitality), ``set`` 0
  (Sulfuric Vortex), ``lose`` ("that player loses that much life instead": Tainted Remedy).
* ``damage`` (120.4b, 614.1a, 615.10): replacement ops ``mul`` / ``add`` / ``sub`` / ``half`` and
  prevention ops ``prevent`` N / ``prevent_all_but`` N / ``prevent_all`` (``prevention``: True,
  615 — kept apart from 614 replacements). Redirection (614.9), "prevent … and [rider]" (615.5)
  and conditional amounts stay manual.
"""

from __future__ import annotations

import re
from typing import Any

from app.rules import selectors

Definition = dict[str, Any]

_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_TYPES = {"creature": "Creature", "artifact": "Artifact", "enchantment": "Enchantment", "land": "Land",
          "planeswalker": "Planeswalker", "instant": "Instant", "sorcery": "Sorcery"}
_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_TOKEN_SUBTYPES = ("Treasure", "Food", "Clue", "Blood", "Map", "Gold", "Powerstone")


def _num(word: str) -> int | None:
    word = word.strip().lower()
    if word.isdigit():
        return int(word)
    return _NUMBERS.get(word)


def _static(event: str, match: dict[str, Any], op: dict[str, Any]) -> Definition:
    return {"kind": "static", "static": "replace", "event": event, "match": match, "op": op, "effects": []}


def _object(phrase: str) -> dict[str, Any] | None:
    """"~" (the permanent itself), "equipped / enchanted creature" (what it's attached to), or "a /
    an / another <group>" as a selector key (battlefield objects only)."""
    phrase = phrase.strip().replace(" your team controls", " you control")  # (102.4: outside a team game "your team" is you: Pir)
    if phrase == "~":
        return {"self": True}
    if phrase in ("equipped creature", "enchanted creature"):
        return {"attached": True}
    m = re.fullmatch(r"(?P<det>a|an|another) (?P<rest>.+)", phrase)
    if m is None:
        return None
    rest = m["rest"]
    if m["det"] == "another":
        rest = "other " + rest
    sel = selectors.parse(rest)
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card:
        return None
    if m["det"] == "another" and not sel.other:
        return None
    return {"sel": sel.key()}


# -- tokens (111.2, 614.16, 701.7b) -----------------------------------------------------------------
_TOKENS_MULT = re.compile(
    r"^If (?:an effect would create one or more (?P<k1>[a-z]+ )?tokens(?P<y1> under your control)?, it creates "
    r"(?P<m1>twice|three times) that many of those tokens instead"
    r"|one or more (?P<k2>[a-z]+ )?tokens would be created(?P<y2> under your control)?, (?P<m2>twice|three times) "
    r"that many of those tokens are created instead)\.$")
_TOKENS_PLUS = re.compile(r"^If you would create one or more (?P<sub>[A-Z][a-z]+) tokens, instead create those tokens "
                          r"plus an additional (?P<sub2>[A-Z][a-z]+) token\.$")


def _tokens(text: str) -> Definition | None:
    m = _TOKENS_MULT.match(text)
    if m:
        kind = (m["k1"] or m["k2"] or "").strip()
        match: dict[str, Any] = {"who": "you" if (m["y1"] or m["y2"]) else "any"}
        if kind:
            if kind not in _TYPES:
                return None
            match["types"] = [_TYPES[kind]]
        return _static("tokens", match, {"do": "mul", "n": 2 if (m["m1"] or m["m2"]) == "twice" else 3})
    m = _TOKENS_PLUS.match(text)
    if m and m["sub"] == m["sub2"] and m["sub"] in _TOKEN_SUBTYPES:  # (a different token: Worldwalker Helm, manual)
        return _static("tokens", {"who": "you", "subtypes": [m["sub"]]}, {"do": "add", "n": 1})
    return None


# -- counters (122.6, 614.16) -----------------------------------------------------------------------
_COUNTERS = re.compile(
    r"^If one or more (?P<kind>\+1/\+1 |-1/-1 )?counters would be put on (?P<on>.+?), "
    r"(?P<how>that many plus one|twice that many|that many) (?:(?P<kind2>\+1/\+1 |-1/-1 )counters(?P<minus> minus one)?"
    r"|of each of those kinds of counters) are put on (?:it|that creature|that permanent) instead\.$")
_DOUBLING_SEASON = re.compile(r"^If an effect would put one or more counters on (?P<on>.+?), it puts twice that many of "
                              r"those counters on that permanent instead\.$")
_PLAYER_COUNTERS = re.compile(r"^If you would get one or more counters, you get that many plus one of each of those "
                              r"kinds of counters instead\.$")


# -- counter putters (wave 22C) -- "If you / an opponent would put one or more counters on …" (Vorinclex, Lae'zel): the
# replacement applies to the counters a given player puts (122.6a: an entering permanent's controller puts its counters;
# 120.3d: wither / infect damage has its source's controller put -1/-1 counters; 120.3b / 120.3g poison "given" by the source's
# controller is put by them too: review 22C, see replace._putter_ok).
_PUTTER = re.compile(r"^If (?P<who>you|an opponent) would put one or more counters on (?P<on>.+?), (?:put|they put) "
                     r"(?P<how>twice that many|half that many|that many plus one) of each of those kinds of counters on "
                     r"that permanent or player instead(?P<down>, rounded down)?\.$")
_PUTTER_OPS: dict[str, dict[str, Any]] = {"twice that many": {"do": "mul", "n": 2}, "that many plus one": {"do": "add", "n": 1}, "half that many": {"do": "half"}}


def _putter(m: re.Match[str]) -> Definition | None:
    if (m["how"] == "half that many") != bool(m["down"]):  # ("half" reads only with "rounded down")
        return None
    on, players = m["on"], None
    if on == "a permanent or player":
        on, players = "a permanent", "any"
    elif on.endswith(" or on yourself") and m["who"] == "you":
        on, players = on[: -len(" or on yourself")], "you"
    obj = _object(on)
    if obj is None:
        return None
    match: dict[str, Any] = {"on": obj, "putter": "you" if m["who"] == "you" else "opponent"}
    if players:
        match["players"] = players
    return _static("counters", match, _PUTTER_OPS[m["how"]])


def _counters(text: str) -> Definition | None:
    m = _PUTTER.match(text)
    if m:
        return _putter(m)
    m = _DOUBLING_SEASON.match(text)
    if m:
        on = _object(m["on"])
        if on is None:
            return None
        return _static("counters", {"on": on, "effect_only": True}, {"do": "mul", "n": 2})
    m = _PLAYER_COUNTERS.match(text)
    if m:
        return _static("player_counters", {"who": "you"}, {"do": "add", "n": 1})
    m = _COUNTERS.match(text)
    if not m:
        return None
    kind = (m["kind"] or "").strip() or None
    kind2 = (m["kind2"] or "").strip() or None
    if kind != kind2:  # "+1/+1 counters … that many plus one of each of those kinds": not a template here
        return None
    on = _object(m["on"])
    if on is None:
        return None
    how = m["how"]
    if m["minus"]:
        if how != "that many":
            return None
        op = {"do": "add", "n": -1}  # "that many -1/-1 counters minus one" (Vizier of Remedies)
    elif how == "that many plus one":
        op = {"do": "add", "n": 1}
    elif how == "twice that many":
        op = {"do": "mul", "n": 2}
    else:
        return None
    match: dict[str, Any] = {"on": on}
    if kind:
        match["counter"] = kind
    return _static("counters", match, op)


# -- draw (121.6, 614.11) ---------------------------------------------------------------------------
_EXCEPT_FIRST = {"you": " except the first one you draw in each of your draw steps",
                 "opponent": " except the first one they draw in each of their draw steps",
                 "any": " except the first one they draw in each of their draw steps"}
# (-- draw bodies (wave 28B) -- "while you have no cards in hand": 614.11, checked as each draw would happen)
_DRAW = re.compile(r"^If (?P<who>you|an opponent|a player) would draw a card(?P<exc> except the first one (?:you|they) draw "
                   r"in each of (?:your|their) draw steps)?(?P<empty> while your library has no cards in it)?"
                   r"(?P<nohand> while you have no cards in hand)?, (?P<rest>.+)\.$")


def _draw_body(rest: str) -> tuple[str, bool] | None:
    """-- draw bodies (wave 28B) -- "instead <effects>", "<effects> instead[. <more>]" or "you may <effects> instead": the effects text
    and whether the affected player may decline (616.1: a replacement the player isn't made to apply)."""
    if rest.startswith("instead "):
        body, optional = rest[len("instead "):], False
    else:
        first, dot, tail = rest.partition(". ")
        if not first.endswith(" instead"):
            return None
        body, optional = first[: -len(" instead")] + (dot + tail if dot else ""), False
    if body.startswith("you may ") and body.count("you may ") == 1:
        body, optional = body[len("you may "):], True
    return (body, optional) if "instead" not in body else None


def _draw(text: str) -> Definition | None:
    m = _DRAW.match(text)
    if not m:
        return None
    who = {"you": "you", "an opponent": "opponent", "a player": "any"}[m["who"]]
    if m["exc"] and m["exc"] != _EXCEPT_FIRST[who]:
        return None
    if (m["empty"] or m["nohand"]) and who != "you":
        return None
    match: dict[str, Any] = {"who": who}
    if m["exc"]:
        match["not_first_in_draw_step"] = True  # 504.1: the draw step's turn-based draw is the first
    if m["empty"]:
        match["library_empty"] = True  # 614.11 / 121.6a: applies even though no card could be drawn
    if m["nohand"]:
        match["hand_empty"] = True  # (Phial of Galadriel, Blood Scrivener: no cards in hand as the draw would happen)
    rest = m["rest"]
    if rest == "you win the game instead" and who == "you":
        return _static("draw", match, {"do": "win"})
    if rest in ("skip that draw instead", "that player skips that draw instead"):
        if (rest == "skip that draw instead") != (who == "you"):
            return None
        return _static("draw", match, {"do": "skip"})
    if rest == "you may skip that draw instead" and who == "you":  # (Obstinate Familiar: its player chooses)
        return _static("draw", match, {"do": "skip", "optional": True})
    if rest == "instead that player skips that draw and you draw a card" and who == "opponent":
        return _static("draw", match, {"do": "steal"})
    m2 = re.fullmatch(r"draw (?P<n>two|three) cards instead", rest)
    if m2 and who == "you" and not m["empty"]:
        return _static("draw", match, {"do": "draw", "n": _NUMBERS[m2["n"]]})
    if who == "you" and (got := _draw_body(rest)) is not None:
        from app.rules import draw_bodies  # (a leaf module over the effect grammar)

        effects = draw_bodies.parse(got[0])
        if effects is not None:
            return _static("draw", match, {"do": "body", "effects": effects, **({"optional": True} if got[1] else {})})
    return None


# -- life gain (119.10) -----------------------------------------------------------------------------
_LIFE = re.compile(r"^If (?P<who>you|an opponent|a player) would gain life(?P<cap> while you have (?P<n>\d+) or less life)?, "
                   r"(?P<rest>.+) instead\.$")


def _life(text: str) -> Definition | None:
    m = _LIFE.match(text)
    if not m:
        return None
    who = {"you": "you", "an opponent": "opponent", "a player": "any"}[m["who"]]
    rest = m["rest"]
    match: dict[str, Any] = {"who": who}
    if m["cap"]:
        if who != "you":
            return None
        match["life_max"] = int(m["n"])  # (-- life modifiers (wave 28B) -- Phial of Galadriel: as the gain would happen)
    if who == "you":
        if rest == "you gain twice that much life":
            return _static("life", match, {"do": "mul", "n": 2})
        if rest == "you gain three times that much life":
            return _static("life", match, {"do": "mul", "n": 3})
        m2 = re.fullmatch(r"you gain that much life plus (?P<n>\d+|one|two|three)", rest)
        if m2:
            n = _num(m2["n"])
            return _static("life", match, {"do": "add", "n": n}) if n else None
        return None
    if rest == "that player gains no life":
        return _static("life", match, {"do": "set", "n": 0})
    if rest == "that player loses that much life":
        return _static("life", match, {"do": "lose"})
    return None


# -- life loss (wave 28B) -- "If an opponent would lose life during your turn, they lose twice that much life instead." (Bloodletter of Aclazotz)
_LOSS = re.compile(r"^If (?P<who>an opponent|a player) would lose life(?P<turn> during your turn)?, "
                   r"(?:they|that player) lose(?:s)? (?P<how>twice) that much life instead\.$")


def _loss(text: str) -> Definition | None:
    m = _LOSS.match(text)
    if not m:
        return None
    match: dict[str, Any] = {"who": "opponent" if m["who"] == "an opponent" else "any"}
    if m["turn"]:
        match["turn"] = "yours"  # (the turn of the effect's controller)
    return _static("life_loss", match, {"do": "mul", "n": 2})


# -- damage (120.4b, 614.1a, 615.10) ----------------------------------------------------------------
_DAMAGE = re.compile(r"^If (?P<src>.+?) would deal (?:(?P<min>\d+) or more )?(?P<kind>combat |noncombat )?damage(?: to (?P<to>.+?))?, (?P<rest>.+)\.$")  # (min: wave 20B)
_BACK = (r"(?: to (?:that permanent or player|that player or permanent|that player|that creature|that permanent|"
         r"that planeswalker|it|~|equipped creature|enchanted creature))?")
_DAMAGE_OPS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?:it|that source) deals (?P<m>double|triple) that damage" + _BACK + r" instead$"), "mul"),
    (re.compile(r"^(?:it|that source) deals twice that much damage" + _BACK + r" instead$"), "mul2"),
    (re.compile(r"^(?:it|that source) deals that much damage plus (?P<n>\d+|one|two|three)" + _BACK + r" instead$"), "add"),
    # -- as long as (wave 9B) -- "instead it deals that much damage plus X, where X is Hawkeye's power" / "… plus an amount of
    # damage equal to the number of fire counters on this enchantment instead": the amount is read as the damage is dealt
    (re.compile(r"^(?:instead )?(?:it|that source) deals that much damage plus (?P<x>X, where X is (?:~'s|this creature's) power|"
                r"an amount of damage equal to the number of (?P<k>[a-z+/-]+) counters on (?:~|this \w+))" + _BACK + r"(?: instead)?$"),
     "add_value"),
    (re.compile(r"^(?:it|that source) deals that much damage minus (?P<n>\d+|one|two)" + _BACK + r" instead$"), "sub"),
    (re.compile(r"^(?:it|that source) deals half that damage, rounded down," + _BACK + r" instead$"), "half"),
    # -- instead (wave 20B) -- "If a source would deal 4 or more damage to a permanent or player, that source deals 3 damage to that
    # permanent or player instead." (Divine Presence): the threshold is in the condition (``at_least``), the amount is the cap
    (re.compile(r"^(?:it|that source) deals (?P<n>\d+|one|two|three) damage" + _BACK + r" instead$"), "cap"),
    (re.compile(r"^prevent (?P<n>\d+|one|two|three) of that damage$"), "prevent"),
    (re.compile(r"^prevent all but (?P<n>\d+|one) of that damage$"), "prevent_all_but"),
    (re.compile(r"^prevent that damage$"), "prevent_all"),
    (re.compile(r"^prevent half that damage, rounded up$"), "prevent_half_up"),  # -- damage wordings (wave 6B) --
)
_SUBTYPE_LIST = re.compile(r"^(?:a|an) (?P<list>[A-Z][a-z]+(?:, [A-Z][a-z]+)*,? or [A-Z][a-z]+)(?P<ctrl> you control| an opponent controls)$")
_SOURCE = re.compile(r"^(?P<det>a|an|any|another) (?:(?P<words>[A-Za-z ]+?) )?(?P<noun>source|spell|creature|artifact|planeswalker)"
                     r"(?P<ctrl> you control| an opponent controls)?$")


def _source(phrase: str) -> dict[str, Any] | None:
    """The damage source a static watches for (609.7c: permanents with the property, and sources
    elsewhere that have it): its colors, card types, subtypes, whether it's a spell, its controller."""
    phrase = phrase.strip()
    if phrase == "~":
        return {"self": True}
    if phrase in ("equipped creature", "enchanted creature"):
        return {"attached": True}
    # -- as long as (wave 9B) -- "a Lizard, Mouse, Otter, or Raccoon you control" (Valley Flamecaller): sources of any of the
    # creature types; "a red instant or sorcery spell you control or a red planeswalker you control" (Pyromancer's Gauntlet):
    # either description (609.7c), each with its own controller
    kinds = _SUBTYPE_LIST.fullmatch(phrase)
    if kinds is not None:
        return {"controller": "you" if kinds["ctrl"] == " you control" else "opponent",
                "subtypes": re.split(r",? or |, ", kinds["list"])}
    halves = re.split(r" or (?=an? )", phrase)
    if len(halves) > 1:
        alts = [_source(h) for h in halves]
        return {"alts": alts} if all(a is not None and "alts" not in a for a in alts) else None
    # -- instead (wave 20B) -- "a Wizard you control" (Kuja): a source of that creature type, as "a Wizard source you control"
    one = re.fullmatch(r"(?P<det>an?) (?P<sub>[A-Z][a-z]+)(?P<ctrl> you control| an opponent controls)", phrase)
    if one is not None:
        from app.rules.creature_types import CREATURE_TYPES

        if one["sub"] not in CREATURE_TYPES:
            return None
        phrase = f"{one['det']} {one['sub']} source{one['ctrl']}"
    m = _SOURCE.match(phrase)
    if m is None:
        return None
    colorful = (m["words"] or "").split(" or ")
    if len(colorful) > 1 and not re.fullmatch(r"(?:[a-z]+ )?instant or sorcery", m["words"] or ""):
        # "a red or artifact source you control" (Mechanized Warfare): either property
        alts = [_source(f"{m['det']} {w} {m['noun']}{m['ctrl'] or ''}") for w in colorful]
        return {"alts": alts} if all(a is not None and "alts" not in a for a in alts) else None
    out: dict[str, Any] = {}
    if m["det"] == "another":
        out["other"] = True
    if m["ctrl"]:
        out["controller"] = "you" if m["ctrl"] == " you control" else "opponent"
    if m["noun"] == "spell":
        out["spell"] = True
    elif m["noun"] == "creature":
        out["types"] = ["Creature"]
    elif m["noun"] == "planeswalker":  # -- as long as (wave 9B) -- a planeswalker's loyalty ability is its source (609.7c)
        out["types"] = ["Planeswalker"]
    elif m["noun"] == "artifact":  # -- damage wordings (wave 6B) -- "If an artifact would deal damage to you" (609.7c)
        if m["words"]:
            return None
        out["types"] = ["Artifact"]
    words = (m["words"] or "").split()
    colors: list[str] = []
    types: list[str] = []
    subtypes: list[str] = []
    joined = False
    for i, w in enumerate(words):
        low = w.lower()
        if low == "or":
            # only "instant or sorcery" (two card types): "red or artifact" is a union the matcher doesn't read
            if not (0 < i < len(words) - 1 and words[i - 1].lower() in ("instant",) and words[i + 1].lower() == "sorcery"):
                return None
            joined = True
            continue
        if low in _COLORS:
            colors.append(_COLORS[low])
        elif low in _TYPES:
            types.append(_TYPES[low])
        elif low == "noncreature":
            out["not_types"] = ["Creature"]
        elif w[:1].isupper() and w.isalpha():
            subtypes.append(w)
        else:
            return None
    if len(colors) > 1:
        return None  # ("a red and white source": not a template here)
    if colors:
        out["colors"] = colors
    if types:
        if m["noun"] == "creature" or (len(types) > 1 and not joined):
            return None
        out["types"] = types
    if subtypes:
        out["subtypes"] = subtypes
    return out


def _recipient(phrase: str | None) -> dict[str, Any] | None:
    """What the damage would be dealt to: players ("you", "an opponent", "a player") and/or
    permanents (a selector, "~", what it's attached to); None: any recipient."""
    if phrase is None or phrase in ("a permanent or player", "a player or permanent", "any target"):
        return {}
    players = {"you": "you", "an opponent": "opponent", "a player": "any"}
    if phrase in players:
        return {"players": players[phrase]}
    m = re.fullmatch(r"(?P<p>you|an opponent|a player) or (?P<o>.+)", phrase)
    out: dict[str, Any] = {}
    if m:
        out["players"] = players[m["p"]]
        phrase = m["o"]
    obj = _object(phrase)
    if obj is None:
        return None
    if "sel" in obj and m is None and not obj["sel"]:
        return None
    out["objects"] = obj
    return out


# -- prevention riders (wave 17A) -- "If damage would be dealt to this creature, prevent that damage. Remove a +1/+1 counter from it."
# (Phantom Nishoba), "If damage would be dealt to another creature you control, prevent that damage. Put a +1/+1 counter on that
# creature for each 1 damage prevented this way." (Vigor), "If ~ would be dealt damage while it has a +1/+1 counter on it, prevent that
# damage and remove that many +1/+1 counters from it." (Polukranos): the recipient (and its state) in the match, the additional effect (615.5)
# as the prevention's rider (app/rules/source_shields.py)
_DAMAGE_TO = re.compile(r"^If (?P<kind>combat |noncombat )?damage would be dealt to (?P<to>.+?)(?P<cond> while [^,]+)?, (?P<rest>.+)$")
_DAMAGE_BE = re.compile(r"^If (?P<to>.+?) would be dealt (?P<kind>combat |noncombat )?damage(?P<cond> while [^,]+)?, (?P<rest>.+)$")
_CONDS: dict[str, dict[str, Any]] = {" while it has a +1/+1 counter on it": {"counter": "+1/+1"},
                                     " while you're the monarch": {"monarch": True}}
_RIDER = re.compile(r"^prevent that damage(?:\. | and )(?P<rider>.+?)\.?$")


def _prevention_rider(rest: str, it: str | None) -> Definition | None:
    from app.rules import source_shields

    m = _RIDER.match(rest)
    effects = source_shields.rider_body(m["rider"][:1].lower() + m["rider"][1:], it) if m else None
    return {"effects": effects, "if": False} if effects else None


def _damage_to(text: str) -> Definition | None:
    m = _DAMAGE_TO.match(text) or _DAMAGE_BE.match(text)
    if m is None or (m["cond"] and m["cond"] not in _CONDS):
        return None
    to = _recipient(m["to"].replace("this creature", "~").replace("this permanent", "~"))
    if to is None or not (to.get("objects") and not to.get("players") or to == {"players": "you"}):
        return None  # (a permanent, or you: "If noncombat damage would be dealt to you, prevent that damage. You gain life …")
    match: dict[str, Any] = {"source": {}, "to": to}
    if m["kind"]:
        match["combat"] = m["kind"] == "combat "
    if m["cond"]:
        if _CONDS[m["cond"]] == {"monarch": True}:
            match["monarch"] = True
        else:
            to["objects"] = {**dict(to["objects"]), **_CONDS[m["cond"]]}
    rest = m["rest"].strip()
    if rest in ("prevent that damage.", "prevent that damage"):
        return _static("damage", match, {"do": "prevent_all", "prevention": True})
    rider = _prevention_rider(rest, None if "objects" not in to else "self" if to["objects"].get("self") else "to")
    return _static("damage", match, {"do": "prevent_all", "prevention": True, "rider": rider}) if rider else None


def _damage(text: str) -> Definition | None:
    if (d := _damage_to(text)) is not None:
        return d
    m = _DAMAGE.match(text)
    if not m:
        return None
    src = _source(m["src"])
    to = _recipient(m["to"])
    if src is None or to is None:
        return None
    rest = m["rest"]
    if (rider := _prevention_rider(rest, None if "objects" not in to else "self" if to["objects"].get("self") else "to")) is not None:
        match0: dict[str, Any] = {"source": src, "to": to, **({"combat": m["kind"] == "combat "} if m["kind"] else {})}
        return _static("damage", match0, {"do": "prevent_all", "prevention": True, "rider": rider})
    if m["to"] == "you" and rest.endswith(" to you instead"):  # -- kicked / instead (wave 4G) -- "… deals double that
        rest = rest[: -len(" to you instead")] + " instead"  # damage to you instead" (Goldnight Castigator): the same recipient
    for pattern, kind in _DAMAGE_OPS:
        m2 = pattern.match(rest)
        if not m2:
            continue
        match: dict[str, Any] = {"source": src, "to": to}
        if m["kind"]:
            match["combat"] = m["kind"] == "combat "
        if (kind == "cap") != (m["min"] is not None):
            return None  # ("deals 3 damage instead" only after "would deal N or more damage", and that only with it)
        if m["min"]:
            match["at_least"] = int(m["min"])
        if kind == "cap":
            cap = _num(m2["n"])
            return _static("damage", match, {"do": "cap", "n": cap}) if cap and cap < match["at_least"] else None
        if kind == "mul":
            return _static("damage", match, {"do": "mul", "n": 2 if m2["m"] == "double" else 3})
        if kind == "mul2":
            return _static("damage", match, {"do": "mul", "n": 2})
        if kind == "half":
            return _static("damage", match, {"do": "half"})
        if kind in ("prevent_all", "prevent_half_up"):
            return _static("damage", match, {"do": kind, "prevention": True})
        if kind == "add_value":
            value: dict[str, Any] = {"counters": m2["k"], "on": "self"} if m2["k"] else {"power": "self"}
            return _static("damage", match, {"do": "add", "n": 0, "value": value})
        n = _num(m2["n"])
        if not n:
            return None
        if kind in ("prevent", "prevent_all_but"):
            return _static("damage", match, {"do": kind, "n": n, "prevention": True})
        return _static("damage", match, {"do": kind, "n": n})
    return None


# -- "[Objects] enter tapped" (614.1d, 614.12) ------------------------------------------------------
# (-- review (wave 6R) -- lazy items: greedy ones swallowed "your opponents control" into the last item, so in "Creatures
# and nonbasic lands your opponents control enter tapped." (Thalia, Heretic Cathar) only the lands were the opponents')
_ENTER_TAPPED = re.compile(r"^(?P<what>[A-Z][a-z]+?(?:, [a-z ]+?)*,? (?:and [a-z ]+? )?|[A-Z][A-Za-z -]+? )"  # (wave 21A: "Non-Phyrexian creatures")
                           r"(?P<ctrl>your opponents control |you control |an opponent controls )?enter tapped\.$")


def _enters_tapped(text: str) -> Definition | None:
    """"Creatures your opponents control enter tapped.", "Artifacts, creatures, and lands your
    opponents control enter tapped.", "Permanents enter tapped." — each item a group of the
    permanent as it would exist on the battlefield (614.12), under the player it would enter under."""
    m = _ENTER_TAPPED.match(text)
    if not m:
        return None
    what = m["what"].strip().rstrip(",")
    items = [w.strip() for w in re.split(r",\s*(?:and\s+)?|\s+and\s+", what) if w.strip()]
    ctrl = (m["ctrl"] or "").strip()
    keys = []
    for item in items:
        low = item[:1].lower() + item[1:]
        sel = selectors.parse(f"{low} {ctrl}".strip())
        if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card or sel.other:
            return None
        keys.append(sel.key())
    return {"kind": "static", "static": "enters_tapped_others", "who": keys, "effects": []} if keys else None


# -- counters (wave 5H) -- "Each other creature you control enters with an additional +1/+1 counter on it." (Renata,
# Called to the Hunt), "Colorless creatures you control enter with two additional +1/+1 counters on them.", "… for each
# Angel you already control" (Giada), "… a number of additional +1/+1 counters on it equal to ~'s toughness" (Arwen):
# a replacement effect on how the permanent enters (614.1c), applied to the counters event of an entering permanent
# (122.6) — even one that would enter with none of that kind (Renata's ruling, 2020-01-24) — so the 616.1 loop orders
# it against Hardened Scales / Doubling Season. Judged as the permanent would exist on the battlefield (614.12): only
# permanents already there give it (a creature entering with Renata doesn't get one: ruling).
_ENTER_EXTRA = re.compile(
    r"^(?:Each (?P<one>.+?) enters|(?P<many>[A-Z].+?) enter) with (?:(?P<n>an|one|two|three|four|five) additional "
    r"(?P<k>\+1/\+1|loyalty) counters?|a number of additional (?P<k2>\+1/\+1|loyalty) counters) on (?:it|them)"
    r"(?: for each (?P<each>.+?)| equal to (?P<eq>~'s|this creature's) (?P<stat>power|toughness))?\.$")


def _enter_extra(text: str) -> Definition | None:
    m = _ENTER_EXTRA.match(text)
    if not m or bool(m["k2"]) != bool(m["eq"]):  # ("a number of" goes with "equal to", and only it)
        return None
    group = m["one"] or m["many"]
    group = group[:1].lower() + group[1:]
    sel = selectors.parse(group)
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card:
        return None
    op: dict[str, Any] = {"do": "add", "n": 1 if m["n"] in (None, "an") else _num(m["n"]), "entering": True}
    if m["eq"]:
        op["times"] = {m["stat"]: "self"}
    elif m["each"]:
        from app.rules import values  # (values → selectors: no cycle back here)

        each = m["each"]
        already = re.fullmatch(r"(?P<w>.+) you already control", each)
        times = values.parse_count(f"{already['w']} you control" if already else each)
        if not isinstance(times, dict) or (already and "count" not in times):
            return None
        op["times"] = {"already": times["count"]} if already else times
    return _static("counters", {"on": {"sel": sel.key()}, "counter": m["k"] or m["k2"], "entering_only": True}, op)
# -- end counters (wave 5H) --


# -- mill counts (wave 28B) -- "If an opponent would mill one or more cards, they mill twice that many cards instead." (Bruvac the
# Grandiloquent), "… they mill that many cards plus four instead." (The Water Crystal): the count the instruction says (701.17a)
_MILL = re.compile(r"^If (?P<who>you|an opponent|a player) would mill one or more cards, (?:you|they) mill "
                   r"(?:(?P<mul>twice) that many cards|that many cards plus (?P<add>\d+|one|two|three|four|five)) instead\.$")


def _mill(text: str) -> Definition | None:
    m = _MILL.match(text)
    if not m:
        return None
    who = {"you": "you", "an opponent": "opponent", "a player": "any"}[m["who"]]
    if m["mul"]:
        return _static("mill", {"who": who}, {"do": "mul", "n": 2})
    n = _num(m["add"])
    return _static("mill", {"who": who}, {"do": "add", "n": n}) if n else None


PARSERS = (_tokens, _counters, _draw, _life, _loss, _mill, _damage, _enters_tapped, _enter_extra)


def parse(text: str) -> Definition | None:
    """A static replacement / prevention line (``~`` for the card's own name) → its definition, or None."""
    for fn in PARSERS:
        d = fn(text)
        if d is not None:
            return d
    return None
