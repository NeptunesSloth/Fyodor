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
    phrase = phrase.strip()
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


def _counters(text: str) -> Definition | None:
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
_DRAW = re.compile(r"^If (?P<who>you|an opponent|a player) would draw a card(?P<exc> except the first one (?:you|they) draw "
                   r"in each of (?:your|their) draw steps)?(?P<empty> while your library has no cards in it)?, "
                   r"(?P<rest>.+)\.$")


def _draw(text: str) -> Definition | None:
    m = _DRAW.match(text)
    if not m:
        return None
    who = {"you": "you", "an opponent": "opponent", "a player": "any"}[m["who"]]
    if m["exc"] and m["exc"] != _EXCEPT_FIRST[who]:
        return None
    if m["empty"] and who != "you":
        return None
    match: dict[str, Any] = {"who": who}
    if m["exc"]:
        match["not_first_in_draw_step"] = True  # 504.1: the draw step's turn-based draw is the first
    if m["empty"]:
        match["library_empty"] = True  # 614.11 / 121.6a: applies even though no card could be drawn
    rest = m["rest"]
    if rest == "you win the game instead" and who == "you":
        return _static("draw", match, {"do": "win"})
    if rest in ("skip that draw instead", "that player skips that draw instead"):
        if (rest == "skip that draw instead") != (who == "you"):
            return None
        return _static("draw", match, {"do": "skip"})
    if rest == "instead that player skips that draw and you draw a card" and who == "opponent":
        return _static("draw", match, {"do": "steal"})
    m2 = re.fullmatch(r"draw (?P<n>two|three) cards instead", rest)
    if m2 and who == "you" and not m["empty"]:
        return _static("draw", match, {"do": "draw", "n": _NUMBERS[m2["n"]]})
    return None


# -- life gain (119.10) -----------------------------------------------------------------------------
_LIFE = re.compile(r"^If (?P<who>you|an opponent|a player) would gain life, (?P<rest>.+) instead\.$")


def _life(text: str) -> Definition | None:
    m = _LIFE.match(text)
    if not m:
        return None
    who = {"you": "you", "an opponent": "opponent", "a player": "any"}[m["who"]]
    rest = m["rest"]
    if who == "you":
        if rest == "you gain twice that much life":
            return _static("life", {"who": who}, {"do": "mul", "n": 2})
        if rest == "you gain three times that much life":
            return _static("life", {"who": who}, {"do": "mul", "n": 3})
        m2 = re.fullmatch(r"you gain that much life plus (?P<n>\d+|one|two|three)", rest)
        if m2:
            n = _num(m2["n"])
            return _static("life", {"who": who}, {"do": "add", "n": n}) if n else None
        return None
    if rest == "that player gains no life":
        return _static("life", {"who": who}, {"do": "set", "n": 0})
    if rest == "that player loses that much life":
        return _static("life", {"who": who}, {"do": "lose"})
    return None


# -- damage (120.4b, 614.1a, 615.10) ----------------------------------------------------------------
_DAMAGE = re.compile(r"^If (?P<src>.+?) would deal (?P<kind>combat |noncombat )?damage(?: to (?P<to>.+?))?, (?P<rest>.+)\.$")
_BACK = (r"(?: to (?:that permanent or player|that player or permanent|that player|that creature|that permanent|"
         r"that planeswalker|it|~|equipped creature|enchanted creature))?")
_DAMAGE_OPS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?:it|that source) deals (?P<m>double|triple) that damage" + _BACK + r" instead$"), "mul"),
    (re.compile(r"^(?:it|that source) deals twice that much damage" + _BACK + r" instead$"), "mul2"),
    (re.compile(r"^(?:it|that source) deals that much damage plus (?P<n>\d+|one|two|three)" + _BACK + r" instead$"), "add"),
    (re.compile(r"^(?:it|that source) deals that much damage minus (?P<n>\d+|one|two)" + _BACK + r" instead$"), "sub"),
    (re.compile(r"^(?:it|that source) deals half that damage, rounded down," + _BACK + r" instead$"), "half"),
    (re.compile(r"^prevent (?P<n>\d+|one|two|three) of that damage$"), "prevent"),
    (re.compile(r"^prevent all but (?P<n>\d+|one) of that damage$"), "prevent_all_but"),
    (re.compile(r"^prevent that damage$"), "prevent_all"),
    (re.compile(r"^prevent half that damage, rounded up$"), "prevent_half_up"),  # -- damage wordings (wave 6B) --
)
_SOURCE = re.compile(r"^(?P<det>a|an|any|another) (?:(?P<words>[A-Za-z ]+?) )?(?P<noun>source|spell|creature|artifact)"
                     r"(?P<ctrl> you control| an opponent controls)?$")


def _source(phrase: str) -> dict[str, Any] | None:
    """The damage source a static watches for (609.7c: permanents with the property, and sources
    elsewhere that have it): its colors, card types, subtypes, whether it's a spell, its controller."""
    phrase = phrase.strip()
    if phrase == "~":
        return {"self": True}
    if phrase in ("equipped creature", "enchanted creature"):
        return {"attached": True}
    m = _SOURCE.match(phrase)
    if m is None:
        return None
    out: dict[str, Any] = {}
    if m["det"] == "another":
        out["other"] = True
    if m["ctrl"]:
        out["controller"] = "you" if m["ctrl"] == " you control" else "opponent"
    if m["noun"] == "spell":
        out["spell"] = True
    elif m["noun"] == "creature":
        out["types"] = ["Creature"]
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


def _damage(text: str) -> Definition | None:
    m = _DAMAGE.match(text)
    if not m:
        return None
    src = _source(m["src"])
    to = _recipient(m["to"])
    if src is None or to is None:
        return None
    rest = m["rest"]
    if m["to"] == "you" and rest.endswith(" to you instead"):  # -- kicked / instead (wave 4G) -- "… deals double that
        rest = rest[: -len(" to you instead")] + " instead"  # damage to you instead" (Goldnight Castigator): the same recipient
    for pattern, kind in _DAMAGE_OPS:
        m2 = pattern.match(rest)
        if not m2:
            continue
        match: dict[str, Any] = {"source": src, "to": to}
        if m["kind"]:
            match["combat"] = m["kind"] == "combat "
        if kind == "mul":
            return _static("damage", match, {"do": "mul", "n": 2 if m2["m"] == "double" else 3})
        if kind == "mul2":
            return _static("damage", match, {"do": "mul", "n": 2})
        if kind == "half":
            return _static("damage", match, {"do": "half"})
        if kind in ("prevent_all", "prevent_half_up"):
            return _static("damage", match, {"do": kind, "prevention": True})
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
_ENTER_TAPPED = re.compile(r"^(?P<what>[A-Z][a-z]+?(?:, [a-z ]+?)*,? (?:and [a-z ]+? )?|[A-Z][a-z ]+? )"
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


PARSERS = (_tokens, _counters, _draw, _life, _damage, _enters_tapped, _enter_extra)


def parse(text: str) -> Definition | None:
    """A static replacement / prevention line (``~`` for the card's own name) → its definition, or None."""
    for fn in PARSERS:
        d = fn(text)
        if d is not None:
            return d
    return None
