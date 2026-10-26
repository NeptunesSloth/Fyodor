"""The wordings of replacement and prevention statics that app/rules/replace.py applies (CR 614, 615).

A static line either matches one of these templates exactly or stays manual (never a guess). Each
template becomes ``{"kind": "static", "static": "replace", "event": <event>, "match": {...}, "op":
{...}}`` — which event it watches for (614.1), which of those events it applies to, and how it
modifies them — or ``{"kind": "static", "static": "enters_tapped_others", "who": [...]}`` for "[Objects]
enter tapped" (614.1d). ``~`` is the permanent's own name (``scripts.self_text``).

Events and their ops (researched against CR 2026-09-25):

* ``tokens`` (111, 614.16): ``mul`` N (Parallel Lives, Doubling Season, Ojer Taq), ``add`` 1 of the
  same token (Xorn). "those tokens plus a [different token]" (Chatterfang, Peregrin Took), "may
  instead" (Jinnie Fay) and copies (Esix) are read by token_creation_replacements.
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
_MELIRA110G = "If you would get one or more poison counters, instead you get one poison counter and you can't get additional poison counters this turn."
_ENERGY_COUNTERS = re.compile(r"^If you would get one or more \{E\}, you get "
                             r"(?P<how>that many plus one|twice that many) \{E\} instead\.$")


# -- counter putters (wave 22C) -- "If you / an opponent would put one or more counters on …" (Vorinclex, Lae'zel): the
# replacement applies to the counters a given player puts (122.6a: an entering permanent's controller puts its counters;
# 120.3d: wither / infect damage has its source's controller put -1/-1 counters; 120.3b / 120.3g poison "given" by the source's
# controller is put by them too: review 22C, see replace._putter_ok).
_PUTTER = re.compile(r"^If (?P<who>you|an opponent) would put one or more counters on (?P<on>.+?), (?:put|they put) "
                     r"(?P<how>twice that many|half that many|that many plus one) of each of those kinds of counters on "
                     r"that permanent(?P<orp> or player)? instead(?P<down>, rounded down)?\.$")
_PUTTER_OPS: dict[str, dict[str, Any]] = {"twice that many": {"do": "mul", "n": 2}, "that many plus one": {"do": "add", "n": 1}, "half that many": {"do": "half"}}


def _putter(m: re.Match[str]) -> Definition | None:
    if (m["how"] == "half that many") != bool(m["down"]):  # ("half" reads only with "rounded down")
        return None
    on, players = m["on"], None
    if on == "a permanent or player":
        on, players = "a permanent", "any"
    elif on.endswith(" or on yourself") and m["who"] == "you":
        on, players = on[: -len(" or on yourself")], "you"
    if bool(m["orp"]) != bool(players):  # (-- counter putters (wave 28B) -- "on a permanent you control, … on that permanent instead": Doc Samson)
        return None
    obj = _object(on)
    if obj is None:
        return None
    match: dict[str, Any] = {"on": obj, "putter": "you" if m["who"] == "you" else "opponent"}
    if players:
        match["players"] = players
    return _static("counters", match, _PUTTER_OPS[m["how"]])


def _counters(text: str) -> Definition | None:
    # CR 107.14, 614.1a: energy symbols denote energy counters, not every counter kind.
    if m := _ENERGY_COUNTERS.fullmatch(text):
        return _static("player_counters", {"who": "you", "counter": "energy"},
                       {"do": "mul" if m["how"] == "twice that many" else "add",
                        "n": 2 if m["how"] == "twice that many" else 1})
    m = _PUTTER.match(text)
    if m:
        return _putter(m)
    m = re.fullmatch(r"If you would put one or more (?P<k>\+1/\+1) counters on (?P<on>a creature you control), put that many plus one (?P=k) counters on it instead\.", text)
    if m and (on_obj := _object(m["on"])) is not None:  # -- instead (wave 100K) -- Prairie Dog: one kind of counter, put by you (122.6a, review 22C)
        return _static("counters", {"on": on_obj, "putter": "you", "counter": m["k"]}, {"do": "add", "n": 1})
    m = re.fullmatch(r"If a modular triggered ability would put one or more (?P<k>\+1/\+1) counters on (?P<on>a creature you control), that many plus one (?P=k) counters are put on it instead\.", text)
    if m and (on_obj := _object(m["on"])) is not None:  # -- (wave 110O) -- 702.43a: only the counters a modular triggered ability puts (replace.put_counters tags them); Zabaz
        return _static("counters", {"on": on_obj, "counter": m["k"], "modular110o": True}, {"do": "add", "n": 1})
    m = _DOUBLING_SEASON.match(text)
    if m:
        on = _object(m["on"])
        if on is None:
            return None
        return _static("counters", {"on": on, "effect_only": True}, {"do": "mul", "n": 2})
    m = _PLAYER_COUNTERS.match(text)
    if m:
        return _static("player_counters", {"who": "you"}, {"do": "add", "n": 1})
    if text == _MELIRA110G:  # -- (wave 110G) -- Melira, the Living Cure: 614.1a; the "can't get additional" half is prohibitions.cant_get_counters
        return _static("player_counters", {"who": "you", "counter": "poison"}, {"do": "set", "n": 1, "once110g": True})
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
_DRAW = re.compile(r"^(?P<ms>As long as you have max speed, if|If) (?P<who>you|an opponent|a player) would draw a card(?P<exc> except the first one (?:you|they) draw "
                   r"in each of (?:your|their) draw steps)?(?P<empty> while your library has no cards in it)?"
                   r"(?P<nohand> while you have no cards in hand)?, (?P<rest>.+)\.$")


def _draw_body(rest: str) -> tuple[str, bool] | None:
    """-- draw bodies (wave 28B) -- "instead <effects>", "<effects> instead[. <more>]" or "you may <effects> instead": the effects text
    and whether the affected player may decline (616.1: a replacement the player isn't made to apply)."""
    if rest.startswith("you may instead "):  # -- piles (wave 53D) -- Parallel Thoughts: "you may instead put the top card of the pile you exiled into your hand"
        body, optional = rest[len("you may instead "):], True
    elif rest.startswith("instead "):
        body, optional = rest[len("instead "):], False
    else:
        first, dot, tail = rest.partition(". ")
        if not first.endswith(" instead"):
            return None
        body, optional = first[: -len(" instead")] + (dot + tail if dot else ""), False
    if body.startswith("you may ") and body.count("you may ") == 1:
        body, optional = body[len("you may "):], True
    return (body, optional) if "instead" not in body else None


_FIRST_TIME = "The first time you would draw a card each turn, "


def _draw(text: str) -> Definition | None:
    first = text.startswith(_FIRST_TIME)  # -- draws (wave 110C) -- Scion of Halaster's grant: only the first draw event each turn (121.6, 614.11)
    if first:  # one card is left to put back, so "in any order" is vacuous (the body grammar reads "the rest ... in any order")
        text = "If you would draw a card, " + text[len(_FIRST_TIME):]
        text = text.replace(" and the other back on top of your library.", " and the rest back on top of your library in any order.")
    d = _draw_plain(text)
    if first and d is not None:
        d["match"]["first_time_turn"] = True
    return d


def _draw_plain(text: str) -> Definition | None:
    m = _DRAW.match(text)
    if not m:
        return None
    who = {"you": "you", "an opponent": "opponent", "a player": "any"}[m["who"]]
    if m["exc"] and m["exc"] != _EXCEPT_FIRST[who]:
        return None
    if (m["empty"] or m["nohand"] or m["ms"] != "If") and who != "you":
        return None
    match: dict[str, Any] = {"who": who}
    if m["ms"] != "If":
        match["max_speed"] = True  # (-- draw bodies (wave 28B) -- "Max speed — …" is "As long as you have max speed, …": 702.178a, speed.py)
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


# -- draw counts (wave 28B) -- 121.2a / 616.1g: replacements that refer to the number of cards an instruction draws are applied first
_DCOUNT_PLUS = re.compile(r"^As long as you have one or fewer cards in hand, if you would draw one or more cards, you draw that many "
                          r"cards plus one instead\.$")
_DCOUNT_EACH = "If an opponent would draw two or more cards, instead you and that player each draw a card."


def _draw_count(text: str) -> Definition | None:
    if _DCOUNT_PLUS.match(text):
        return _static("draw_count", {"who": "you", "min": 1, "hand_max": 1}, {"do": "add", "n": 1})
    if text == _DCOUNT_EACH:
        return _static("draw_count", {"who": "opponent", "min": 2}, {"do": "each_one"})
    return None


# -- life gain (119.10) -----------------------------------------------------------------------------
_LIFE = re.compile(r"^If (?P<who>you|an opponent|a player) would gain life(?P<cap> while you have (?P<n>\d+) or less life)?, "
                   r"(?P<rest>.+) instead\.$")


def _life(text: str) -> Definition | None:
    if text == "If a spell or ability would cause its controller to gain life, that player loses that much life instead.":
        # -- life gain (wave 110H) -- Rain of Gore: only a gain its source's controller gets (lifelink's source is a permanent: 702.15)
        return _static("life", {"who": "any", "by_controller": True}, {"do": "lose"})
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
        if rest == "draw that many cards":  # -- life gain (wave 110I) -- Lich: 614.1a, the gain doesn't happen; that many cards are drawn (through the draw replacements)
            return _static("life", match, {"do": "draw"})
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


# -- life floor (wave 35C) -- "Damage that would reduce your life total to less than 1 reduces it to 1 instead." (Fortune Thief, Ali from Cairo,
# Sustaining Spirit), "If you control a creature, damage that would …" (Worship, Serra the Benevolent's emblem). 120.3a: the damage dealt stays what it was;
# only the life it makes the player lose is replaced (the Gatherer rulings: lifelink and "deals damage" triggers see all of it, "lose life" and paying life
# bypass it, and nothing applies to a player already below 1 life). Event ``life_loss`` of damage (``damage``: True), op ``floor``.
_FLOOR = re.compile(r"^(?:If (?P<cond>[^,]+), d|As long as you have (?P<k>[2-9]|\d\d+) or more life, d|D)amage that would reduce your life total to less than (?P<n>\d+) reduces it to (?P=n) instead\.$")


def _floor(text: str) -> Definition | None:
    m = _FLOOR.match(text)
    if not m:
        return None
    match: dict[str, Any] = {"who": "you", "damage": True}
    if (m["k"] or m["n"] != "1") and m["k"] != m["n"]:
        return None  # (only "As long as you have N or more life, … less than N reduces it to N" (Elderscale Wurm) beyond the floor of 1)
    if m["k"]:
        return _static("life_loss", match, {"do": "floor", "to": int(m["k"])})
    if m["cond"]:
        from app.rules import conditions

        cond = conditions.parse(m["cond"])
        if cond is None or conditions.needs_event(cond) or conditions.objects_in(cond):
            return None  # (a condition of the game as the damage would be dealt: you control a creature)
        match["if"] = cond
    return _static("life_loss", match, {"do": "floor"})


# -- keyword actions (wave 35C) -- 614.1a, 701.22 / 701.44 / 701.50: "If you would scry a number of cards, draw that many cards instead." (Eligeth),
# "If a creature you control would explore, instead it explores, then it explores again." (Topography Tracker), "… instead you scry 1, then that creature
# explores." (Twists and Turns), "If a creature you control would connive, instead you draw a card, then that creature connives." (Leader, Super-Genius).
# The action is the event (``scry`` / ``explore`` / ``connive``); op ``draw`` takes its place, ``again`` does it twice, ``before`` puts instructions
# in front of it. What the replacement makes carries it as applied (614.5), so two Trackers explore four times and two Leaders draw twice.
_ACTION = re.compile(r"^If a creature you control would (?P<verb>explore|connive), instead (?P<body>.+), then (?:that creature|it) (?P=verb)s(?P<again> again)?\.$")


def _keyword_action(text: str) -> Definition | None:
    if text == "If you would scry a number of cards, draw that many cards instead.":
        return _static("scry", {"who": "you"}, {"do": "draw"})
    if text == "If you would scry a number of cards, scry that many cards plus one instead.":  # -- keyword actions (wave 50G) -- Kenessos, Priest of Thassa
        return _static("scry", {"who": "you"}, {"do": "plus"})
    if text == "If you would proliferate, proliferate twice instead.":  # -- keyword actions (wave 50F) -- Tekuthal, Inquiry Dominus: two proliferates, neither replaced again by this effect (614.5)
        return _static("proliferate", {"who": "you"}, {"do": "again"})
    m = _ACTION.match(text)
    if not m:
        return None
    if m["body"] == "it explores" and m["again"] and m["verb"] == "explore":
        return _static("explore", {"who": "you"}, {"do": "again"})
    if m["again"]:
        return None
    from app.rules import draw_bodies

    effects = draw_bodies.parse(m["body"]) if m["verb"] in ("explore", "connive") else None
    if not effects or any(e["do"] not in ("draw", "scry") or e.get("who", "you") != "you" for e in effects):
        return None
    return _static(m["verb"], {"who": "you"}, {"do": "before", "effects": effects})


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
    if phrase == "a source controlled by one of the chosen players":  # -- wave 110E -- Bitter Feud (wave110e_pair)
        return {"chosen_pair110e": True}
    if phrase == "~":
        return {"self": True}
    if phrase in ("equipped creature", "enchanted creature"):
        return {"attached": True}
    if (fresh := re.fullmatch(r"(?P<src>.+?) that entered this turn", phrase)) is not None:
        # -- counters (wave 44C) -- "a creature you control that entered this turn" (Neriv, Heart of the Storm): the source entered the battlefield this turn (608.2h: as it last existed)
        inner = _source(fresh["src"])
        return None if inner is None or "alts" in inner else {**inner, "entered": True}
    if (kind := re.fullmatch(r"(?P<src>.+?) of the chosen type", phrase)) is not None:
        # -- instead (wave 51C) -- "sources you control of the chosen type" (Collective Inferno): the creature type its permanent chose as it entered (614.12a; replace._source_matches)
        inner = _source(kind["src"])
        return None if inner is None or "alts" in inner else {**inner, "chosen_type": True}
    if (counted := re.fullmatch(r"(?P<src>.+?) with (?:a|one or more) (?:(?P<kind>\+1/\+1|-1/-1) )?counters? on (?:it|them)", phrase)) is not None:
        # -- counters (wave 41A) -- "a creature you control with a counter on it" (Raphael, the Muscle): the source has a counter of any kind on it as it would deal the damage
        # (wave 51C: of that kind, "with a +1/+1 counter on it", Uncivil Unrest)
        inner = _source(counted["src"])
        return None if inner is None or "alts" in inner else {**inner, **({"has_counter": counted["kind"]} if counted["kind"] else {"has_counters": True})}
    if (par := re.fullmatch(r"(?P<src>.+?) with an? (?P<par>odd|even) mana value", phrase)) is not None:
        # -- cant restrictions (wave 46A) -- "a source you control with an odd mana value" (Obosh, the Preypiercer): the source's mana value as it would deal the damage
        # (an X spell on the stack counts its X, any other object has X as 0: 202.3e)
        inner = _source(par["src"])
        return None if inner is None or "alts" in inner else {**inner, "mv_parity": par["par"]}
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
    if phrase == "the other chosen player or a permanent that player controls":  # -- wave 110E -- Bitter Feud (wave110e_pair)
        return {"chosen_pair110e": True}
    if phrase == "the chosen player or a permanent they control":
        return {"chosen_player_or_controlled": True}
    if phrase is None or phrase in ("a permanent or player", "a player or permanent", "any target"):
        return {}
    players = {"you": "you", "an opponent": "opponent", "a player": "any"}
    if phrase == "enchanted player":  # -- instead (wave 100K) -- Curse of Bloodletting: the player this Aura enchants (702.5d)
        return {"players": "enchanted"}
    if phrase in players:
        return {"players": players[phrase]}
    m = re.fullmatch(r"(?P<p>you|an opponent|a player) or (?P<o>.+)", phrase)
    out: dict[str, Any] = {}
    if m:
        out["players"] = players[m["p"]]
        phrase = m["o"]
        if phrase in ("battle", "planeswalker"):  # -- commanders (wave 50C) -- "a player or battle" (Rankle and Torbran): the bare noun after "or"
            phrase = f"a {phrase}"
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
_RIDER = re.compile(r"^prevent that damage(?:\. | and |, )(?P<rider>.+?)\.?$")  # (wave 42A: ", remove that many … and create that many …", Sekki)


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


# -- damage bodies (wave 35C) -- 614.1a: "If damage would be dealt to this creature, put that many +1/+1 counters on it instead." (Phytohydra; -1/-1:
# Lichenthrope), "If damage would be dealt to you, put that many depletion counters on this enchantment instead." (Force Bubble), "If damage would be dealt
# to a player, that player exiles that many cards from the top of their library instead." (Crumbling Sanctuary), "If a source you control would deal noncombat
# damage to a creature an opponent controls, put that many -1/-1 counters on that creature instead." (Soul-Scar Mage), "If Szadek would deal combat damage
# to a player, instead put that many +1/+1 counters on Szadek and that player mills that many cards." The damage is never dealt (614.6: nothing that needs it
# triggers or happens: no lifelink, no "deals damage"); the instructions count it ("that many": the damage as the replacement applies, 616.1 after any
# doubling) and happen once the rest of the batch has been dealt — the prevention riders' machinery (615.5, app/rules/source_shields.py), op ``body``.
_BODY_TO = re.compile(r"^If (?P<kind>combat |noncombat )?damage would be dealt to (?P<to>[^,]+?), (?P<rest>.+)\.$")
_BODY_FROM = re.compile(r"^If (?P<src>[^,]+?) would deal (?P<kind>combat |noncombat )?damage to (?P<to>[^,]+?), (?P<rest>.+)\.$")
_EXILE_THEIRS = re.compile(r"^that player exiles that many cards from the top of their library$")


def _damage_body(text: str) -> Definition | None:
    from app.rules import source_shields

    m = _BODY_TO.match(text)
    src: dict[str, Any] | None = {}
    if m is None and (m := _BODY_FROM.match(text)) is not None:
        src = _source(m["src"])
    if m is None or src is None:
        return None
    rest = m["rest"]
    if rest.startswith("instead "):
        rest = rest[len("instead "):]
    elif rest.endswith(" instead"):
        rest = rest[: -len(" instead")]
    else:
        return None
    to = _recipient(m["to"].replace("this creature", "~").replace("this permanent", "~"))
    if to is None or "instead" in rest or not (to.get("objects") or to.get("players")) or (to.get("players") and to.get("objects")):
        return None  # (a recipient we read, one kind of it: "you or a creature …" would need the rider to say which)
    players = bool(to.get("players"))
    rest = _EXILE_THEIRS.sub("exile the top that many cards of that player's library", rest)
    it = None if players else "self" if to["objects"].get("self") else "to"
    effects = source_shields.rider_body(rest, it, to_player=players and to["players"] == "any")
    if not effects:
        return None
    match: dict[str, Any] = {"source": src, "to": to}
    if m["kind"]:
        match["combat"] = m["kind"] == "combat "
    return _static("damage", match, {"do": "body", "rider": {"effects": effects, "if": False}})


_MAX_SPEED_IF = "As long as you have max speed, if "


def _damage(text: str) -> Definition | None:
    banded = re.fullmatch(r"As long as ~ is attacking, prevent all damage (?P<kind>[A-Z][a-z]+s) would deal to ~ and to creatures banded with ~\.", text)
    if banded is not None:
        sel = selectors.parse(banded["kind"])
        if sel is None or len(sel.subtypes) != 1 or sel.types or sel.extras:
            return None
        return _static("damage", {"attacking": True, "source": {"subtypes": list(sel.subtypes)},
                                  "to": {"objects": {"band_of_source": True}}},
                       {"do": "prevent_all", "prevention": True})
    if text.startswith(_MAX_SPEED_IF):  # -- damage sized by a count (wave 34D) -- 702.178a "As long as you have max speed, if a source you control would deal
        # damage to an opponent …, it deals that much damage plus 1 instead." (Far Fortune): the same replacement, in force only at max speed
        d = _damage_plain("If " + text[len(_MAX_SPEED_IF):])
        return None if d is None else {**d, "match": {**d["match"], "max_speed": True}}
    return _damage_plain(text)


def _damage_plain(text: str) -> Definition | None:
    floor = re.fullmatch(r"If (?P<src>.+?) would deal an amount of (?P<kind>combat |noncombat )?damage less than "
                         r"(?P<value>~'s (?P<stat>power|toughness)) to (?P<to>.+?), that source deals damage equal to (?P=value) instead\.", text)
    if floor is not None:
        src, to = _source(floor["src"]), _recipient(floor["to"])
        if src is None or to is None:
            return None
        floor_value = {floor["stat"]: "self"}
        return _static("damage", {"source": src, "to": to, "below_value": floor_value,
                                  **({"combat": floor["kind"] == "combat "} if floor["kind"] else {})},
                       {"do": "set_value", "value": floor_value})
    # -- counters (wave 41A) -- "Double all damage that creatures you control with counters on them would deal." (Raphael, the Muscle) is "If a creature you control with a
    # counter on it would deal damage to a permanent or player, it deals double that damage instead." (every recipient there is)
    if (dbl := re.fullmatch(r"Double all damage that (?P<src>creatures|creature sources|sources) (?P<ctl>you control|an opponent controls)(?P<with> with counters on them)?(?P<chosen> of the chosen type)? would deal\.", text)) is not None:
        noun = "source" if dbl["src"] == "sources" else "creature"  # (wave 44C: "creature sources", Absorbing Man and Titania)
        text = (f"If a {noun} {dbl['ctl']}{' with a counter on it' if dbl['with'] else ''}{dbl['chosen'] or ''} would deal damage to a permanent or player, "
                "it deals double that damage instead.")
    if text == "Double all damage ~ would deal.":  # -- commanders (wave 47A) -- Wolverine, Best There Is: "If ~ would deal damage to a permanent or player, it deals double that damage instead." (every recipient there is)
        text = "If ~ would deal damage to a permanent or player, it deals double that damage instead."
    if (d := _damage_to(text)) is not None:
        return d
    m = _DAMAGE.match(text.replace("to a creature, battle, or opponent,", "to an opponent or a creature or battle,"))  # (wave 110F: Disciples of the Inferno; the comma list would split the match)
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
            return _static("damage", match, {"do": "cap", "n": cap}) if cap else None  # (-- one-card wordings (wave 110B) -- 614.1a: it sets the amount whenever the threshold is met; Equal Treatment "1 or more" -> 2)
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
                           r"(?P<ctrl>your opponents control |you control |an opponent controls )?enter (?P<un>un)?tapped\.$")  # (wave 45A: "enter untapped")


def _enters_tapped(text: str) -> Definition | None:
    """"Creatures your opponents control enter tapped.", "Artifacts, creatures, and lands your
    opponents control enter tapped.", "Permanents enter tapped." — each item a group of the
    permanent as it would exist on the battlefield (614.12), under the player it would enter under."""
    # -- commander sweep (wave 49B) -- "As long as ~ is tapped, other permanents enter tapped." (Archelos): the same replacement while the source is (un)tapped
    # (611.3a; "other" is vacuous: the source isn't on the battlefield as it would enter itself, 614.12 and its ruling 2020-11-10)
    if text == "Each creature without mana value of the chosen quality enters tapped.":
        text = "Creatures without mana value of the chosen quality enter tapped."
    held = re.fullmatch(r"As long as ~ is (un)?tapped, other (permanents enter (?:un)?tapped\.)", text)
    if held is not None and (own := _enters_tapped(held[2].capitalize())) is not None:
        return {**own, "conditions": [{"static": "self", "test": "untapped" if held[1] else "tapped"}]}
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
    # -- most-played cards II (wave 45A) -- "Lands you control enter untapped." (Horizon Explorer, The Wandering Minstrel), "Gates you control enter untapped." (Gond Gate): the same
    # replacement effect the other way (614.1d; replacements.entry_plan: it wins over a "tapped" the entering permanent would get)
    return {"kind": "static", "static": "enters_untapped_others" if m["un"] else "enters_tapped_others", "who": keys, "effects": []} if keys else None


# -- counters (wave 5H) -- "Each other creature you control enters with an additional +1/+1 counter on it." (Renata,
# Called to the Hunt), "Colorless creatures you control enter with two additional +1/+1 counters on them.", "… for each
# Angel you already control" (Giada), "… a number of additional +1/+1 counters on it equal to ~'s toughness" (Arwen):
# a replacement effect on how the permanent enters (614.1c), applied to the counters event of an entering permanent
# (122.6) — even one that would enter with none of that kind (Renata's ruling, 2020-01-24) — so the 616.1 loop orders
# it against Hardened Scales / Doubling Season. Judged as the permanent would exist on the battlefield (614.12): only
# permanents already there give it (a creature entering with Renata doesn't get one: ruling).
_ENTER_EXTRA = re.compile(
    r"^(?:Each (?P<one>.+?) enters|(?P<many>[A-Z].+?) enter) with (?:(?P<n>an|one|two|three|four|five) additional "
    r"(?P<k>\+1/\+1|loyalty|flying|deathtouch|haste|hexproof|indestructible|lifelink|menace|reach|shadow|trample|vigilance) counters?"  # (33C: Tayam's keyword counter, 122.1b)
    r"|a number of additional (?P<k2>\+1/\+1|loyalty) counters) on (?:it|them)"
    r"(?: for each (?P<each>.+?)| equal to (?P<eq>~'s|this creature's) (?P<stat>power|toughness))?\.$")


def _enter_extra(text: str) -> Definition | None:
    if text == "Each other colorless creature you control has bloodthirst 2.":  # -- bloodthirst grant (wave 110A) -- 702.54a, as counters
        d = _enter_extra("Each other colorless creature you control enters with two additional +1/+1 counters on it.")
        if d is not None:
            d["match"]["bloodthirst110a"] = True  # replace._counters_applies: only if an opponent was dealt damage this turn
        return d
    # Thunderous Velocipede: both branches describe one entry replacement,
    # whose amount uses the entering permanent's characteristics (614.12).
    threshold = re.fullmatch(
        r"(.+?) if its mana value is (\d+) or less\. Otherwise, it enters with "
        r"(one|two|three|four|five) additional \+1/\+1 counters? on it\.", text)
    if threshold:
        base = _enter_extra(threshold[1] + ".")
        if base is None or base["match"].get("counter") != "+1/+1" or base["op"]["n"] != 1:
            return None
        base["op"]["times"] = {"entering_mana_value": int(threshold[2]), "otherwise": _num(threshold[3])}
        return base
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

        each = re.sub(r' spent to cast them$', ' spent to cast it', m['each'])
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


PARSERS = (_tokens, _counters, _draw, _draw_count, _life, _loss, _floor, _keyword_action, _mill, _damage, _damage_body, _enters_tapped, _enter_extra)


def parse(text: str) -> Definition | None:
    """A static replacement / prevention line (``~`` for the card's own name) → its definition, or None."""
    for fn in PARSERS:
        d = fn(text)
        if d is not None:
            return d
    return None
