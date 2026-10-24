"""A small grammar for Oracle effect sentences: VERB + SUBJECT/OBJECT (selectors) + AMOUNT (value
expressions) + DESTINATION.

It's the fallback behind the literal templates in app/rules/scripts.py: one pattern per *verb*
(draw, gain/lose life, discard, mill, sacrifice, damage, destroy/exile/tap/untap, return, put and
remove counters, pump / grant until end of turn), each accepting any subject or object phrase
the selector grammar (app/rules/selectors.py) reads and any amount the value grammar
(app/rules/values.py) reads, including "for each …" and "where X is …".

``parse_sentence`` returns ``(effects, targets)`` or None when any part of the sentence isn't
understood (the card then stays manual: never a guess). ``targets`` is None, a selector key (one
"target [something]" with one target), or target group(s) (CR 115.1, 601.2c): a dict or a list
of dicts ``{"what": key, "min": n, "max": n, "divide": …, "another": key}`` for "up to two target
creatures", "one or two targets", "target creature and target artifact" (two groups: two
instances of the word "target", 115.3), "N damage divided as you choose among …" (601.2d).
Effects name a group with "target" (the sentence's first) or "target:<k>" (its k-th); "it" and
"them" are pronouns, resolved against the ability's groups by scripts.resolve_it.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.game import actions as A
from app.rules import characteristics as chars
from app.rules import chosen as _chosen  # -- chosen filters (wave 53B) --
from app.rules import (  # (this_way: wave 4A; sized_damage: wave 4E; token_grammar: wave 30P)
    selectors,
    sized_damage,
    this_way,
    token_grammar,
    values,
)
from app.rules.card_names import (
    WHAT_RX as _NAME_WHAT,  # -- card names (wave 22B) -- "Choose a nonland card name."
)

Effects = list[dict[str, Any]]
AMT = values.AMOUNT
KEYWORDS = "|".join(k for k in selectors.KEYWORDS if k not in ("protection",))

# Legacy selector keys the rest of the engine already uses (targets.SELECTORS).
_LEGACY_TARGETS = {
    "any target": "any", "target player": "player", "target opponent": "opponent",
    # -- target forms (agent T) --  a player, or any planeswalker (whoever controls it)
    "target player or planeswalker": "player_or_planeswalker", "target opponent or planeswalker": "opponent_or_planeswalker",
    "target player or battle": "player_or_battle", "target opponent or battle": "opponent_or_battle",  # (wave 42D: Onakke Javelineer, Ayara)
    "target permanent or player": "permanent_or_player",  # -- counter kinds (wave 24C) -- a permanent, or a player (115.1)
}
# -- activated other (wave 21E) -- "Choose target opponent who has more life than you do as you activate this ability.": the
# condition is read as the ability is put on the stack (601.2c) and not again on resolution (608.2b only asks for an opponent)
_OPP_AS_CONDS = {"has more life than you do": "life", "controls more creatures than you do": "creatures",
                 "has at least two more cards in hand than you do": "hand2"}
_OPP_AS_ACTIVATED = re.compile(rf"target opponent who (?P<c>{'|'.join(map(re.escape, _OPP_AS_CONDS))}) as you activate this ability")
# Player phrases. The pronouns are placeholders resolved by scripts.resolve_it against what the
# ability named earlier: "that player" → the target player (or the trigger event's player),
# "its controller" / "its owner" → the controller / owner of the object the previous instruction
# was about — as it was then, from last known information once it has left (608.2h, 108.4a).
PLAYER_GROUPS = {"you": "you", "each player": "each_player", "each opponent": "each_opponent",
                  "each of your opponents": "each_opponent", "that player": "that_player",
                  "its controller": "it.controller", "its owner": "it.owner",
                  "that creature's controller": "it.controller", "that permanent's controller": "it.controller",
                  "that opponent": "that_player",  # (wave 19B: the opponent the trigger event names)
                  "that card's owner": "it.owner", "that creature's owner": "it.owner",
                  "the chosen player": "chosen_player",  # (-- chosen player (wave 4J) --: app/rules/chosen.py)
                  "defending player": "defending_player"}  # (-- defending player (wave 6D) --: app/rules/defending.py)
# -- damage wordings (wave 6B) -- "Destroy target land. ~ deals 2 damage to that land's controller.", "Counter target
# spell. ~ deals 2 damage to that spell's controller.": the object the previous instruction was about, like "its"
PLAYER_GROUPS.update({f"{the} {kind}'s controller": "it.controller" for the in ("that", "the")
                      for kind in ("land", "artifact", "enchantment", "spell", "planeswalker", "Equipment")})
# "~ deals 3 damage to target player or planeswalker. That player or that planeswalker's controller discards two cards."
# (Blightning): the target player, or the target planeswalker's controller (app/rules/effects._players)
PLAYER_GROUPS["that player or that planeswalker's controller"] = "target_player_or_controller"
PLAYER_GROUPS["that permanent's controller or that player"] = "target_player_or_controller"  # -- activated other (wave 52D) -- Acorn Catapult: the same, for "any target"
PLAYER_GROUPS["enchanted player"] = "enchanted_player"
PLAYER_GROUPS["each player other than that player"] = "each_other_than_event"  # -- trigger other (wave 51C) -- "each other player" in a trigger about a player (Zenith Chronicler): every player but the one the event is about, you included
PLAYER_GROUPS["each of that player's opponents"] = "event_opponents"  # -- player groups (wave 51G) -- every player but the one the trigger event names (Heartwood Storyteller, Standstill)
PLAYER_GROUPS["an opponent chosen at random"] = "random_opponent"  # -- random choices (wave 47B) -- app/rules/random_choice.py (scripts: the pick is made right before it)
PLAYER_GROUPS["the exiled card's owner"] = "it.owner"  # -- resolution memory (wave 22D) -- 607.2a (exiled_with.linked_cards binds the card)
# "Whenever ~ blocks or becomes blocked by a creature, ~ deals 3 damage to that creature and 3 damage to that creature's
# controller" (Assembled Alphas): the creature on the other side of the block (509.3c-d; the trigger event's ``other``)
OTHER_SIDE = "the creature on the other side of the block"
PLAYER_GROUPS[OTHER_SIDE + "'s controller"] = "ref:event_other.controller"
PLAYER_GROUPS.update({"enchanted creature's controller": "host_controller", "enchanted permanent's controller": "host_controller"})  # -- block events (wave 53C) -- the controller of what the source Aura enchants, fixed when first read (effects._players)
# -- end damage wordings (wave 6B) --
PLAYER_PHRASES = "|".join(sorted(PLAYER_GROUPS, key=len, reverse=True))


class _Fail(Exception):
    pass


MAX_TARGETS = A.MAX_TARGETS  # "any number of target …": at most this many (the intents' limit; wave 29C: 250, as a trigger's, not 20)
_QTY = r"one hundred|one|two|three|four|five|six|seven|eight|nine|ten|\d+"  # (wave 41B: "up to one hundred target creatures", Baldin)
# -- target forms (agent T) --  "up to one other target creature", "each of up to two other targets",
# "any number of other target nonland permanents you control": "other" inside a counted group
_GROUP = re.compile(rf"^(?:each of )?(?:up to (?P<upto>{_QTY}|X)|(?P<range>one or two|one, two, or three)|"  # (X: wave 4K)
                    rf"(?P<any>any number of)|(?P<more>one or more)|(?P<n>{_QTY}|X)) (?P<other>(?:an)?other )?(?P<rest>targets|target .+)$")


def _qty(word: str) -> int:
    return int(word) if word.isdigit() else 100 if word == "one hundred" else values.NUMBERS[word]


def simple(group: dict[str, Any]) -> bool:
    """One "target [something]" with exactly one target: what definitions write as "target"."""
    return (group["min"], group["max"]) == (1, 1) and not ({"divide", "another", "distinct_from", "same_graveyard", "total", "different",
                                                            "kicked", "per_kick_targets", "opponent_group", "random"} & set(group))  # (random: wave 47B) -- kicked / instead (wave 4G) -- ("kicked"; wave 23A: a group for each opponent, per_opponent.FLAG)


def target_group(phrase: str) -> dict[str, Any] | None:
    """A target phrase → a target group (115.1; 601.2c: the number of targets): "target creature"
    (1), "up to two target creatures" (0-2), "two target creatures" (2), "one or two targets"
    (1-2), "any number of target creatures" (0-MAX_TARGETS). "another target creature" also
    carries "another": its selector without "another" (scripts: when an earlier target of the
    same ability exists, "another" means distinct from it). None if it isn't a target phrase."""
    p = phrase.strip()
    mixed = re.fullmatch(r"up to (?P<n>one|two|three|four|five|\d+) other target creatures from the battlefield and/or creature cards from graveyards", p)
    if mixed is not None:
        battlefield = selectors.parse('other creature')
        graveyard = selectors.parse('creature card in a graveyard')
        maximum = _qty(mixed['n'])
        if battlefield is None or graveyard is None or not 1 <= maximum <= MAX_TARGETS:
            raise _Fail
        both = selectors.Selector(zones=('battlefield', 'graveyard'), either=(battlefield.key(), graveyard.key()))
        return {'what': both.key(), 'min': 0, 'max': maximum}
    if (p.startswith("target ") or p == "any target chosen at random") and p.endswith(" chosen at random"):  # -- random choices (wave 47B) -- "target opponent chosen at random": a target all the same (115.1), but the table
        one = target_group(p[:-len(" chosen at random")])  # picks it as the ability goes on the stack (Scab-Clan Giant ruling 2013-04-15): each legal target equally likely
        return {**one, "random": True} if one is not None and one["min"] == one["max"] == 1 and "another" not in one else None
    if p == "target opponent, creature an opponent controls, or planeswalker an opponent controls":
        return {"what": "opponent_or_creature_or_planeswalker_opp", "min": 1, "max": 1}
    if p in _LEGACY_TARGETS:
        return {"what": _LEGACY_TARGETS[p], "min": 1, "max": 1}
    if m := _OPP_AS_ACTIVATED.fullmatch(p):  # -- activated other (wave 21E) -- (targets.legal_targets: only as it is chosen)
        return {"what": f"opponent_as:{_OPP_AS_CONDS[m['c']]}", "min": 1, "max": 1}
    if m := re.fullmatch(r"any target that isn't an? (commander|[A-Z][a-z]+)", p):  # -- activated sweep (wave 17B) -- "any target that
        return {"what": f"any_not:{m[1]}", "min": 1, "max": 1}  # isn't a commander / a Dragon" (targets.legal_targets)
    if p in ("another target", "any other target"):  # 115.4 (Arc Trail): any target other than the earlier one
        return {"what": "", "min": 1, "max": 1, "another": "any", **({"any_other": True} if p == "any other target" else {})}  # (wave 34D)
    if p.startswith(("target ", "another target ")):
        what, _ = _group_constraints(_target_key(p))  # (one target: "a single graveyard" is vacuous)
        group: dict[str, Any] = {"what": what, "min": 1, "max": 1}
        if p.startswith("another "):
            group["another"] = _group_constraints(_target_key(p[len("another "):]))[0]
        return group
    m = _GROUP.match(p)
    if not m:
        return None
    rest, total = m["rest"], None
    tm = _TOTAL.fullmatch(rest)  # -- refused zones/sized (wave 3R4) -- "… with total mana value 3 or less …" (601.2c)
    if tm is not None:
        rest, total = tm["a"] + (tm["b"] or ""), [_TOTAL_STATS[tm["stat"]], "X" if tm["n"] == "X" else int(tm["n"])]
    dm = _DIFFERENT.fullmatch(rest)  # (wave 3R4) "… target creature cards with different names …" (201.2, 202.3)
    if dm is not None:
        rest = dm["a"] + (dm["b"] or "")
    rm = _SHARES.fullmatch(rest) or _CONTROLLERS.fullmatch(rest)  # -- group relations (wave 51A) -- "two target creatures that share a creature type" / "… controlled by different players" (601.2c)
    if rm is not None:
        if (m["n"] or m["upto"] or m["range"]) not in ("two", "2", "one or two"):
            raise _Fail  # ponytail: pairs only; for more targets, what a relation that stops holding on resolution makes illegal (608.2b) is unsettled
        rest = rm["a"] + (rm["b"] or "")
    what, constraints = ("any", {}) if rest == "targets" else _group_constraints(_target_key(rest))
    if total is not None:
        constraints = {**constraints, "total": total}  # (checked by targets.choose_groups)
    if dm is not None:
        constraints = {**constraints, "different": "name" if dm["k"] == "names" else "mana_value"}
    if rm is not None:
        constraints = {**constraints, **({"shares": rm["k"] + "_type"} if "k" in rm.groupdict() else {"controllers": "different"})}
    if m["other"]:  # "up to two other target creatures": other than the source, or than an earlier target
        if rest == "targets":
            what, constraints = "", {"another": "any"}  # ("each of up to two other targets": than the earlier one)
        else:
            constraints = {**constraints, "another": what}
            what = _group_constraints(_target_key("another " + rest))[0]
    if "X" in (m["upto"], m["n"]):  # -- X sized by a count (wave 4K) -- "X target creatures", "up to X target …": the
        # number of targets is the X announced as it's cast (601.2b, before 601.2c); targets.group_limits reads it
        lo, hi = 0, MAX_TARGETS
        constraints = {**constraints, "x_count": "upto" if m["upto"] else "exact"}
    elif m["upto"]:
        lo, hi = 0, _qty(m["upto"])
    elif m["range"]:
        lo, hi = 1, 2 if m["range"] == "one or two" else 3
    elif m["any"]:
        lo, hi = 0, MAX_TARGETS
    elif m["more"]:  # (wave 26A) 601.2c: at least one, as many as there are legal targets
        lo, hi = 1, MAX_TARGETS
    else:
        lo = hi = _qty(m["n"])
    if not 1 <= hi <= MAX_TARGETS:
        raise _Fail
    # -- counters (wave 21D) -- "one or two target creatures an opponent controls": each target must be a permanent some opponent controls
    # (115.1, 601.2c: each target is judged against the printed restriction on its own; no word asks for the same opponent)
    each_opponents = what.startswith(selectors.PREFIX) and re.search(r"\ban opponent controls\b", rest) is not None \
        and selectors.from_key(what).controller == "opponent" and selectors.from_key(what).zones == ("battlefield",)
    if hi > 1 and not each_opponents and re.search(r"\ban opponent(?:'s)?\b", rest):
        # -- activated other (wave 48A) -- "two target cards from an opponent's graveyard" (Deadeye Tracker, Spurnmage Advocate): all in the graveyard of one opponent (rulings
        # 2018-01-19 "You can't activate … without targeting two cards in a single opponent's graveyard"); any other wording naming an opponent stays refused
        if not (what.startswith(selectors.PREFIX) and selectors.from_key(what).zones == ("graveyard",) and selectors.from_key(what).zone_owner == "opponent"
                and rest.endswith("from an opponent's graveyard")):
            raise _Fail
        constraints = {**constraints, "same_graveyard": True}
    if hi > 1 and what.startswith(selectors.PREFIX) and selectors.from_key(what).controller == "defending":
        raise _Fail  # "two target creatures defending player controls": one specific defending player (508.5a)
    return {"what": what, "min": lo, "max": hi, **constraints}


_TOTAL = re.compile(r"(?P<a>.+?) with total (?P<stat>mana value|power) (?P<n>\d+|X) or less(?P<b> .+)?")  # (wave 3R4; 34C: X, the one announced)
_TOTAL_STATS = {"mana value": "mana_value", "power": "power"}
_DIFFERENT = re.compile(r"(?P<a>.+?) with different (?P<k>names|mana values)(?P<b> .+)?")  # (wave 3R4)
_SHARES = re.compile(r"(?P<a>.+?) that share an? (?P<k>creature|card|permanent) type(?P<b> .+)?")  # (wave 51A) 205.2, 205.3m
_CONTROLLERS = re.compile(r"(?P<a>.+?) controlled by different players(?P<b> .+)?")  # (wave 51A)


def _group_constraints(key: str) -> tuple[str, dict[str, Any]]:
    """A selector key → (the key without group-level constraints, those constraints): "from a
    single graveyard" is a constraint on the targets together (all from one graveyard — one
    owner, 400.1), not on each card: ``{"same_graveyard": True}`` (checked by targets.choose_groups)."""
    if not key.startswith(selectors.PREFIX):
        return key, {}
    sel = selectors.from_key(key)
    if "single_graveyard" not in sel.extras:
        return key, {}
    plain = selectors.replace(sel, extras=tuple(x for x in sel.extras if x != "single_graveyard"))
    return plain.key(), {"same_graveyard": True}


def _out(groups: list[dict[str, Any]]) -> Any:
    """A sentence's targets as parse_sentence returns them: None, a plain selector key (one
    simple target, as before multi-target groups), one group, or a list of groups."""
    if not groups:
        return None
    if len(groups) == 1:
        return groups[0]["what"] if simple(groups[0]) else groups[0]
    return groups


def _divided(phrase: str, what: str, total: Any) -> dict[str, Any]:
    """601.2d: "… divided as you choose among one, two, or three targets" / "distribute N
    counters among …": each target gets at least one, so at least one target and at most
    ``total`` of them; (wave 41B) a total counted as the ability goes on the stack may be 0, so there the group says how few: "any number of" / "up to"
    allow none (115.6; Yannik's ruling of 2020-04-17)."""
    group = target_group(phrase)
    x_plus = isinstance(total, dict) and set(total) == {"plus"} and total["plus"][0] == {"x": 1} and isinstance(total["plus"][1], int)  # (wave 34C: "X plus 1")
    # (-- distribute (wave 12A) -- "any number of other target creatures you control": other than the source, 115.3)
    # -- damage sized by a count (wave 34D) -- a total "where X is <a count>" (scripts._where_x makes it the group's ``value``, read as the spell is cast)
    if group is None or group.get("another") == "any" or group["max"] < 2 and "another" in group \
            or not (isinstance(total, int) or total == {"x": 1} or x_plus or (isinstance(total, dict) and not _has_x(total))):
        raise _Fail
    counted = not (isinstance(total, int) or total == {"x": 1} or x_plus)  # (a count: the total is read as the spell is cast, targets.divide_x)
    group = {**group, "min": group["min"] if counted else max(1, group["min"]), "divide": {"what": what, "total": {"x": 1}, "value": total} if counted
             else {"what": what, "total": total}}
    if isinstance(total, int):
        if total < 1:
            raise _Fail
        group["max"] = min(group["max"], total)
    return group


def _target_key(phrase: str) -> str:
    if phrase in _LEGACY_TARGETS:
        return _LEGACY_TARGETS[phrase]
    m = re.match(r"^(another )?target (.+)$", phrase)
    if not m:
        raise _Fail
    sel = selectors.parse(("another " if m[1] else "") + m[2]) or (None if m[1] else selectors.parse_either(m[2])
                                                                   or selectors.parse_spell_or(m[2])
                                                                   or selectors.parse_stack_union(m[2]))  # (wave 15A; 17C: spell or permanent; 23B: ability or spell)
    if sel is None or any(isinstance(c[2], str) and c[2].startswith(selectors.RESOLUTION_STAT) for c in sel.compare):
        raise _Fail
    return sel.key()


_THEM = ("them", "each of them", "they", "those creatures", "those permanents", "those cards", "those tokens")
# "cards exiled this way", "creatures sacrificed this way", "the exiled card": the objects a
# particular earlier instruction of this ability moved (400.7j: found where it put them)
_THIS_WAY = re.compile(r"^(?:the )?(?:cards?|creatures?|permanents?|tokens?|artifacts?|enchantments?|lands?) "
                       r"(?P<verb>exiled|sacrificed|destroyed|discarded|milled|returned) this way$")
_THE_VERBED = re.compile(r"^the (?P<verb>exiled|sacrificed|destroyed|discarded|milled|returned) "
                         r"(?P<what>card|creature|permanent|token|cards|creatures|permanents|tokens)$")


_KINDS_EACH = re.compile(r"for each kind of counter on (?P<of>target permanent(?: or player)?), (?:give (?P<to>that permanent or player|that permanent) "
                         r"another counter of that kind|(?P<alt>put another counter of that kind on it or remove one from it))")
_KINDS_ONE = re.compile(r"choose a counter on (?P<of>target permanent(?: or player)?|a permanent you control), then (?:give (?P<to>that permanent or player|that permanent) "
                        r"another counter of that kind|put a counter of that kind on (?P<to2>target permanent you control) if it doesn't have a counter "
                        r"of that kind on it)")


def _counter_kinds(text: str, rider: Any) -> tuple[Effects, Any] | None:
    """-- counter kinds (wave 24C) -- "for each kind of counter on target permanent or player, give that permanent or player another
    counter of that kind", "… put another counter of that kind on it or remove one from it", "choose a counter on …, then give …"
    (app/rules/counter_kinds.py); "remove any number of counters from target creature you control"."""
    if rider is not None:
        return None
    m = _KINDS_EACH.fullmatch(text)
    if m is not None:
        of = ref(m["of"])
        player = " or player" in m["of"]
        if of[0] != "target" or (m["alt"] is not None and player) or (m["to"] is not None and (m["to"] == "that permanent") == player):
            raise _Fail
        return [{"do": "counter_kinds", "of": "target", "pick": "each", "then": "give_or_remove" if m["alt"] else "give"}], _one(of[2])
    m = _KINDS_ONE.fullmatch(text)
    if m is not None:
        if m["to2"] is not None:  # Aven Courier: the kinds on any permanent you control; put on the target if it has none of that kind
            sel = selectors.parse("permanents you control")
            to = ref(m["to2"])
            if sel is None or to[0] != "target" or m["of"] != "a permanent you control":
                raise _Fail
            return [{"do": "counter_kinds", "of": sel.key(), "to": "target", "pick": "one", "then": "give", "unless_has": True}], _one(to[2])
        of = ref(m["of"])
        if of[0] != "target" or (m["to"] == "that permanent") == (" or player" in m["of"]):
            raise _Fail
        return [{"do": "counter_kinds", "of": "target", "pick": "one", "then": "give"}], _one(of[2])
    m = re.fullmatch(r"remove any number of counters from (?P<o>target (?:creature|permanent) you control)", text)
    if m is not None:
        of = ref(m["o"])
        if of[0] != "target":
            raise _Fail
        return [{"do": "remove_any_counters", "who": "target"}], _one(of[2])
    return None


def ref(phrase: str) -> tuple[str, str, dict[str, Any] | None]:
    """An object or player phrase → ("target", selector key, target group) | ("each", selector
    key, None) | ("self", "", None) | ("players", "you" / "each_player" / "each_opponent", None) |
    a pronoun ("it" / "them", with the verb it names for "… exiled this way")."""
    p = phrase.strip()
    if p in ("~", "this creature", "this permanent", "this saga"):  # (-- transform, wave 11A -- "Exile this Saga, then …")
        return "self", "", None
    if p in ("it", "that creature", "that permanent", "that card", "that token", "that artifact"):  # (wave 20E: "Untap that artifact")
        return "it", "", None  # a pronoun: resolved against its antecedent (scripts.resolve_it)
    if p == OTHER_SIDE:  # -- damage wordings (wave 6B) -- (scripts._define writes it for a block trigger's "that creature")
        return "each", "ref:event_other", None
    if p == "that land":  # -- recursion & tutors (wave 4M) -- "… put it onto the battlefield tapped, then shuffle. Then if
        return "it", "", None  # you control four or more lands, untap that land." (Fabled Passage): the land found
    if p in _THEM:
        return "them", "", None  # the objects just named (scripts.resolve_it)
    if p in ("the chosen cards", "the chosen card"):  # -- "this way" outcomes (wave 4A) -- a "Choose target …" sentence's
        return ("them" if p.endswith("s") else "it"), "chosen", None
    if (moved := this_way.objects_who(p)) is not None:  # -- resolution memory (wave 22D) -- "each card put into a graveyard this way"
        return "them", moved[len("them:"):], None
    m = _THIS_WAY.match(p) or _THE_VERBED.match(p)
    if m:
        plural = "what" not in m.groupdict() or m["what"].endswith("s")
        return ("them" if plural else "it"), m["verb"], None  # (resolved to that instruction's objects)
    if re.fullmatch(r"(?:enchanted|equipped) creature and other creatures that share a creature type with it", p):  # -- attached events (wave 25D) --
        return "host_kin", "", None  # the Crowns (effects._host_kin); a kind no other wording reads, so only the effects that name it use it
    if p in ("enchanted creature", "equipped creature", "enchanted permanent", "enchanted land", "enchanted artifact", "enchanted planeswalker") \
            or re.fullmatch(r"enchanted (?:Plains|Island|Swamp|Mountain|Forest)", p):  # (wave 25D: the Genju: "Enchant Forest")
        return "host", "", None  # what the source Aura / Equipment is attached to
    if p == "your Ring-bearer":  # -- random choices (wave 47B) -- 701.54a: the creature the Ring chose for its controller, if it still is (effects._cards)
        return "each", "ring_bearer", None
    if p in PLAYER_GROUPS:
        return "players", PLAYER_GROUPS[p], None
    group = target_group(p)
    if group is not None:
        return "target", group["what"], group
    m = re.match(r"^(?:each|all) (other )?(.+)$", p)
    if m:
        sel = selectors.parse(("other " if m[1] else "") + m[2])
        if sel is None:
            raise _Fail
        return "each", (selectors.replace(sel, controller=selectors.DEFENDED) if _untargeted_defending(sel) else sel).key(), None
    if selectors.is_plural(p):  # "creatures you control get …", "other Elves you control …"
        sel = selectors.parse(p)
        if sel is not None and sel.player is None:
            return "each", (selectors.replace(sel, controller=selectors.DEFENDED) if _untargeted_defending(sel) else sel).key(), None
    raise _Fail


def _untargeted_defending(sel: selectors.Selector) -> bool:
    """"Creatures defending player controls get -1/-1": not targeted, so nobody picks which
    defending player it is; that's the player the triggering attacker is attacking (508.5), which
    may not be the ability's source ("Whenever a Dragon you control attacks, …") — the selector
    only knows the source, so a non-targeted "defending player" could hit the wrong player's
    creatures in a multiplayer game: manual. Targeted forms are fine: the chooser picks one
    defending player's permanent (508.5a)."""
    return sel.controller == "defending"


def _who(kind: str, key: str) -> str:
    if kind in ("it", "them"):
        return f"{kind}:{key}" if key else kind  # "them:exiled": the objects the exile instruction moved
    return {"target": "target", "self": "self", "host": "host", "host_kin": "host:kin", "players": key, "each": key}[kind]


# -- dynamic values (agent F) -------------------------------------------------------------------
_STATS = {"power": "power", "toughness": "toughness", "mana value": "mana_value"}
_DIFF = re.compile(r"the difference between (?P<a>that creature's power|its power|~'s power) and (?P<b>its toughness|that creature's toughness|~'s toughness|toughness)")


def _stat(phrase: str, its: str = "it") -> Any:
    """"its power" / "that creature's toughness" / "its mana value": a value read from the object
    the previous instruction was about — as it is, or as it last existed (608.2h). A placeholder
    ("it") until scripts.resolve_it binds it; ``its`` is what "its" means when the sentence has
    its own subject ("~ deals damage equal to its power": ~'s). Also any quantity the value
    grammar reads ("the number of lands you control", "your devotion to red", "twice its power":
    app/rules/values.py), and "~'s power" (the source's, 608.2h)."""
    if (d := _DIFF.fullmatch(phrase)) is not None:
        # -- most-played cards II (wave 45A) -- "the difference between that creature's power and its toughness" (Jaws of Defeat): how far apart they are, one object's own (608.2h)
        a, b = d["a"], d["b"]
        if b == "toughness" or b.startswith("its ") and not a.startswith("its "):  # (wave 47A: Doran, "its power and toughness")
            b = a.rsplit(" ", 1)[0] + " toughness"  # ("that creature's power and its toughness": the same creature)
        return {"diff": [_stat(a, its), _stat(b, its)]}
    m = re.fullmatch(r"the sacrificed (?:creature|artifact|permanent|land|enchantment)'s (?P<stat>power|toughness|mana value)", phrase)
    if m:  # -- sized amounts (wave 3D) -- what the cost sacrificed (an activated ability only: scripts.define checks)
        return {_STATS[m["stat"]]: "cost:sacrificed"}
    if (m := re.fullmatch(r"(?P<n>\d+|one|two|three) plus (?P<v>the (?:power|toughness|mana value) of target .+)", phrase)) is not None:
        return {"plus": [_stat(m["v"], its), values.parse_amount(m["n"])]}  # -- block events (wave 53C) -- Sentinel: "1 plus the power of target creature blocking or blocked by ~"
    if (m := re.fullmatch(r"(?P<v>the (?:power|toughness|mana value) of target .+) minus (?P<n>\d+|one|two|three)", phrase)) is not None:
        return {"minus": [_stat(m["v"], its), values.parse_amount(m["n"])]}  # (Sworn Defender: "the toughness of target creature … minus 1", 107.1b: no less than 0)
    if (m := re.fullmatch(r"the (?P<stat>power|toughness|mana value) of the creature tapped this way", phrase)) is not None:
        return {_STATS[m["stat"]]: "cost:tapped"}  # -- activated sweep (wave 26C) -- the one creature a cost tapped (an activated ability only: scripts.define checks)
    if (m := re.fullmatch(r"the revealed card's (?P<stat>power|toughness|mana value)", phrase)) is not None:
        return {_STATS[m["stat"]]: "cost:revealed"}  # -- static_other sweep (wave 17C) -- the card a spell's additional cost revealed
    if (m := re.fullmatch(r"the discarded card's (?P<stat>power|toughness|mana value)|the (?P<stat2>mana value) of the discarded card",
                          phrase)) is not None:  # -- as long as (wave 9B) -- the card a discard (instruction or cost) put into the graveyard
        return {_STATS[m["stat"] or m["stat2"]]: "it:discarded"}
    if (m := re.fullmatch(r"(?P<n>\d+|one|two|three) plus (?P<v>the (?:discarded card's|sacrificed (?:creature|artifact|permanent|land|enchantment)'s) "
                          r"(?:power|toughness|mana value))", phrase)) is not None:  # "2 plus the sacrificed permanent's mana value"
        return {"plus": [_stat(m["v"], its), values.parse_amount(m["n"])]}
    if (m := re.fullmatch(r"the (?:exiled (?:creature )?card's|exiled creature's) (?P<stat>power|toughness|mana value)|the (?P<stat2>power|toughness|mana value) of (?:the exiled card|the card you exiled)",
                          phrase)) is not None:  # (wave 19F: also after an exile instruction of this ability, scripts._bind_stats)
        return {_STATS[m["stat"] or m["stat2"]]: "cost:exiled"}  # -- if you do (wave 8C) -- bound to the payment (pay_objects.bind)
    if (m := re.fullmatch(r"the milled card's (?P<stat>power|toughness|mana value)|the (?P<stat2>mana value) of the milled card", phrase)) is not None:
        return {_STATS[m["stat"] or m["stat2"]]: "it:milled"}  # -- X sized by a count (wave 19F) -- the card a mill instruction milled (701.17)
    if (m := re.fullmatch(r"the (?P<stat>mana value) of (?:that|the) spell|the spell's (?P<stat2>mana value)", phrase)) is not None:
        return {"mana_value": "that_spell"}  # (wave 19F: a cast trigger's spell, or the one a counter instruction just countered)
    if (m := re.fullmatch(r"the (?P<stat>power|toughness|mana value) of the (?:card|creature|permanent|artifact|enchantment|land|creature card) (?P<verb>exiled|returned|milled|destroyed) this way", phrase)) is not None:  # -- value grammar (wave 23C) -- "the mana value of the permanent exiled this way": the one object an earlier instruction moved
        return {_STATS[m["stat"]]: "it:" + m["verb"]}  # (scripts._bind_stats binds it to that instruction, else the line stays manual; 608.2h)
    if (m := re.fullmatch(r"the (?P<stat>power|toughness|mana value) of the creature that died", phrase)) is not None:  # -- value grammar (wave 23C) -- 603.10a, 608.2h
        return {_STATS[m["stat"]]: "event", "died": 1}  # (the dying creature as it last existed; scripts._event_refs_ok: only a "dies" trigger's)
    if phrase in ("the number of colors that spell is", "the number of colors it is"):  # -- value grammar (wave 23C) -- how many colors an object is (105.1)
        return {"colors": "that_spell" if "spell" in phrase else its}
    # (wave 4K: "this creature's power" is the source's own, like "~'s")
    m = re.fullmatch(r"(?:(?P<its>its)|(?:that|the(?! card)) (?P<noun>creature|permanent|card|artifact|enchantment|land|planeswalker)(?P<cd> card)?'s|"  # (wave 26A: "that creature card's toughness"; wave 48A: "the artifact's mana value" reads as "that artifact's", Viashino Heretic)
                     r"(?P<spell>that spell's)|(?P<self>~'s|this creature's)) (?P<stat>power|toughness|mana value)", phrase)
    if m and (m["noun"] == "card" or m["cd"]):
        # -- damage sized by a count (wave 20A) -- "gets +X/+0, where X is that card's mana value" (Goblin Machinist): the card an earlier instruction
        # revealed, never the creature that is pumped (``_bind_its`` leaves the placeholder for scripts.resolve_it)
        return _Ante({_STATS[m["stat"]]: "it"})
    if m:
        # -- refused copy/mana (wave 3R3) -- "that spell's": a cast/copy trigger's spell even after an instruction
        # named another object (Deekah: "create a … token. Put X +1/+1 counters on it, where X is that spell's mana
        # value"); scripts._bind_stats binds it ("it" where no trigger spell is meant)
        return {_STATS[m["stat"]]: "self" if m["self"] else (its if m["its"] else "that_spell" if m["spell"] else "it")}
    # -- static_other sweep (wave 16B) -- "the power of target creature you control" / "target creature's toughness": the sentence's own
    # target (115.1: declared with it), the object whose characteristic it is (608.2h: as it is, or as it last existed)
    m = re.fullmatch(r"the (?P<stat>power|toughness|mana value) of target (?P<sel>.+)|target (?P<sel2>[^']+)'s (?P<stat2>power|toughness|mana value)", phrase)
    if m:
        sel = selectors.parse(m["sel"] or m["sel2"])
        if sel is None or sel.player is not None or sel.zones not in ((), ("battlefield",)) or sel.other:
            raise _Fail
        return {_STATS[m["stat"] or m["stat2"]]: "target", "target_sel": sel.key()}
    if (m := re.fullmatch(r"(?P<a>(?:its|that creature's) (?:power|toughness|mana value)) plus (?P<b>its (?:power|toughness|mana value))", phrase)) is not None:
        return {"plus": [_stat(m["a"], its), _stat(m["b"], its)]}  # -- value grammar (wave 30N) -- Phthisis: "its power plus its toughness" (608.2h: both as the object last existed)
    m = re.fullmatch(r"(?:twice|(?P<k>two|three|four) times) (?P<v>.+)", phrase)  # (wave 23C: "three times this creature's power")
    if m:
        return {"times": [values.NUMBERS[m["k"]] if m["k"] else 2, _stat(m["v"], its)]}
    if (tw := this_way.parse(phrase)) is not None:  # -- "this way" outcomes (wave 4A) --
        return tw
    # -- damage sized by a count (wave 4E) -- "the number of charge counters on it": "it" is the sentence's subject when it
    # has one (``its``: "~ deals damage equal to the number of … counters on it"), else a placeholder bound by resolve_it
    v = values.parse_count(phrase, it=its)
    if v is None:  # -- value grammar (wave 30N) -- the count of what a named player controls: "creatures they control" / "artifacts target opponent controls"
        v = values.target_relative(phrase) or values.player_relative(phrase)  # (scripts._value_targets / _that_players_hand bind the player or refuse)
    if v is None:
        raise _Fail
    return v


# The instruction joiners scripts._clause splits a sentence on (mirrored here, so a sentence with
# one "where X is …" for two instructions is read whole before it would be split)
_JOINER = (r", then | and (?=(?:you|target|each|~|it|that player|draw|lose|gain|put|return|exile|destroy|tap|untap|"
           r"create|sacrifice|discard|mill|scry|surveil|get)\b)"
           r"| and (?=~ deals )")  # -- damage sized by a count (wave 4E) -- ("\b" never follows "~")


def _has_x(v: Any) -> bool:
    """Does an effect (or value) use the placeholder X?"""
    if isinstance(v, list):
        return any(_has_x(x) for x in v)
    return isinstance(v, dict) and (v == {"x": 1} or any(_has_x(x) for x in v.values()))


def _bind_x(v: Any, value: Any) -> Any:
    """The effect with every X replaced by what "where X is …" defines."""
    if isinstance(v, list):
        return [_bind_x(x, value) for x in v]
    if isinstance(v, dict):
        return value if v == {"x": 1} else {k: _bind_x(x, value) for k, x in v.items()}
    return v


def _wants_target_player(v: Any) -> bool:
    """Does a value read a target player ("cards in target player's hand", "target player's life total")?"""
    if isinstance(v, list):
        return any(_wants_target_player(x) for x in v)
    if not isinstance(v, dict):
        return False
    return v.get("hand") == "target" or v.get("life") == "target" or any(_wants_target_player(x) for x in v.values())


def _pop_target_sel(v: Any) -> str | None:
    """The selector of the "target …" a value names (``_stat``), taken out of it."""
    if not isinstance(v, (list, dict)):
        return None
    if isinstance(v, dict) and "target_sel" in v:
        return str(v.pop("target_sel"))
    # (every one is taken out: -- block events (wave 53C) -- two values of one sentence name the same target)
    found = {k for k in [_pop_target_sel(x) for x in (v if isinstance(v, list) else v.values())] if k is not None}
    if len(found) > 1:  # -- review 53 -- two different "target …" in one amount: not one target (115.1), not read
        raise _Fail
    return next(iter(found), None)


def _value_target(n: Any, target: str | None) -> str | None:
    """The sentence's target once its amount is known: a value reading "target player" is that
    sentence's one target (115.1) — declared here so it's chosen on casting and checked on
    resolution — unless the sentence already targets something else (then it's not read)."""
    if (own := _pop_target_sel(n)) is not None:  # -- static_other sweep (wave 16B) -- "equal to the power of target creature you control"
        if target is not None:
            raise _Fail  # (a second target: which one does the amount read?)
        return own
    if not _wants_target_player(n):
        return target
    if target is None:
        return "player"
    if target in ("player", "opponent"):
        return target
    raise _Fail


# "… and target artifact", "… and up to one target creature", "… and another target creature"
_AND_TARGET = (r" and (?=(?:each of )?(?:another |up to \w+ |any number of |one or two |two |three )?(?:(?:an)?other )?targets?\b"
               r"|any (?:other )?target)")


# -- static_other sweep (wave 26A) -- "each creature target opponent controls", "all nonland permanents target player controls",
# "creatures target player controls": the permanents of the one player the sentence targets (115.1: the target is the player; the
# objects are not targeted). Read when the sentence resolves (effects._controlled_by); the player is a target group of its own.
_TARGET_CONTROLS = re.compile(r"^(?:(?:each|all) )?(?P<sel>.+?) (?P<t>target (?:player|opponent)) controls$")


def target_controls(part: str, groups: list[dict[str, Any]]) -> str | None:
    """The ``who`` of a [group] "target player controls" phrase (its target group appended to ``groups``), else None."""
    m = _TARGET_CONTROLS.fullmatch(part)
    if m is None or (not part.startswith(("each ", "all ")) and not selectors.is_plural(m["sel"])):
        return None
    sel = selectors.parse(m["sel"])
    if sel is None or sel.player is not None or sel.controller is not None or sel.card or sel.zones != ("battlefield",):
        raise _Fail
    who = "target" if not groups else f"target:{len(groups)}"
    groups.append(target_group(m["t"]) or {})
    return f"controlled:{who}|{sel.key()}"


def _objects(o: str) -> tuple[list[str], list[dict[str, Any]]]:
    """"target creature and target artifact" → (who per part, target groups): each "target" is
    its own group (115.3), named "target" (the first) / "target:<k>"."""
    whos: list[str] = []
    groups: list[dict[str, Any]] = []
    for part in re.split(_AND_TARGET, o):
        if (controlled := target_controls(part, groups)) is not None:
            whos.append(controlled)
            continue
        kind, key, group = ref(part)
        if group is not None:
            whos.append("target" if not groups else f"target:{len(groups)}")
            groups.append(group)
        else:
            whos.append(_who(kind, key))
    return whos, groups


def _tap_it_and_all(verb: str, o: str) -> tuple[Effects, Any] | None:
    """-- trigger damage (wave 39B) -- "untap it and all Samurai you control" (Godo): no target in either part, so one instruction for each, in the order
    given (608.2c); "it" is bound like any pronoun. Anything else (a target, a plural of something else) is not read here."""
    both = re.fullmatch(r"(?P<a>~|it|this creature) and (?P<b>(?:all|each) .+)", o) if verb in ("tap", "untap") else None
    if both is None:
        return None
    one, many = ref(both["a"]), ref(both["b"])
    if one[0] not in ("it", "self") or one[2] is not None or many[0] != "each" or many[2] is not None:
        return None
    return [{"do": verb, "who": _who(one[0], one[1])}, {"do": verb, "who": _who(many[0], many[1])}], None


RESTRICTIONS = {"block": ["cant_block"], "attack": ["cant_attack"], "attack or block": ["cant_attack_or_block"],
                "be blocked": ["cant_be_blocked"]}

# -- attack restrictions (wave 32B) -- 508.1c-d: restrictions on whom a creature may attack, aimed at the controller of the effect ("you"), as a one-shot
# effect with a duration (611.2a): this turn / this combat / "during their next turn" (a player's, ``their_turn``) -- or, with "unless their controller pays
# {2} for each of those creatures", an attack cost (508.1d, 508.1h-j: app/rules/combat_rules.py)
_CANT_ATTACK_YOU = re.compile(r"(?P<o>.+?) can't attack (?P<t>you|you or planeswalkers you control|you or permanents you control)"
                              r"(?: unless their controller pays (?P<cost>(?:\{[^}]+\})+|[1-9]\d* life) for each of those creatures)?"  # (wave 49D: life, Sivitri)
                              r" (?P<d>this turn|this combat|during their next turn)")
_ATTACK_YOU = {"you": "cant_attack_player", "you or planeswalkers you control": "cant_attack_player_pw",
               "you or permanents you control": "cant_attack_player_perm"}
_TAX_YOU = {"you": "attack_tax", "you or planeswalkers you control": "attack_tax_pw"}
_DURATION_YOU = {"this turn": {}, "this combat": {"duration": "end_of_combat"}, "during their next turn": {"duration": "their_turn"}}
_THAT_PLAYERS_CREATURES = re.compile(r"(?:each )?creatures? (?:that player|they) controls?")


def _cant_attack_you(m: re.Match[str]) -> tuple[Effects, Any]:
    """"[Creatures / that player / creatures that player controls] can't attack you [or planeswalkers / permanents you control] [this turn / this
    combat / during their next turn]": a rule-modifying effect on the creatures the subject names (effects.restrict). A player ("that player";
    a bare "they" is the objects just named, ``ref``) is the creatures they control, read when the attack is declared: a creature that changes hands is restricted
    by its new controller."""
    if m["cost"]:  # (508.1d: nobody has to pay, so this never forces an attack; one rule per source, so two of them cost twice)
        from app.rules import mana as M

        cost = M.parse_cost("{0}" if m["cost"].endswith(" life") else m["cost"])  # -- life attack costs (wave 49D) -- 508.1g-h, 119.4: "pays 2 life for each of those creatures"
        if m["t"] not in _TAX_YOU or cost.unsupported or (cost.is_free and not m["cost"].endswith(" life")) or cost.x:
            raise _Fail
        rules = [f"{_TAX_YOU[m['t']]}:@you:{m['cost']}:@src"]
    else:
        rules = [f"{_ATTACK_YOU[m['t']]}:@you"]
    extra = _DURATION_YOU[m["d"]]
    if m["o"] == "that player" or _THAT_PLAYERS_CREATURES.fullmatch(m["o"]):
        who = f"controlled:that_player|{selectors.Selector(types=('Creature',)).key()}"
        return [{"do": "restrict", "who": who, "rules": rules, **extra}], None
    whos, groups = _objects(m["o"])
    if len(whos) != 1 or whos[0] in PLAYER_GROUPS.values() or (m["d"] == "during their next turn" and not whos[0].startswith("controlled:")):
        raise _Fail
    return [{"do": "restrict", "who": whos[0], "rules": rules, **extra}], _out(groups)


def _amount(word: str) -> Any:
    v = values.parse_amount(word)
    if v is None:
        raise _Fail
    return v


def _with_rider(text: str) -> tuple[str, Any]:
    """Split "…, where X is the number of …" / "… for each …" off the sentence: the multiplier or
    the value of X (None if there's none). A rider may read the object the sentence is about
    ("where X is its power", "for each +1/+1 counter on it"): a placeholder "it", bound by
    scripts.resolve_it for an amount, or by the pump grammar to its own subject."""
    # -- counters (wave 21D) -- "put a number of +1/+1 counters on it equal to that creature's power" is "put X … counters on it, where X is …"
    # (-- counters (wave 33C) -- "put +1/+1 counters on that creature equal to its power" (Experiment Twelve): "a number of" left out)
    n = re.fullmatch(r"(put) (?:a number of )?([+-]\d+/[+-]\d+|[a-z]+) counters on (.+?) equal to (.+)", text)
    if n:
        return f"put X {n[2]} counters on {n[3]}", ("x", _rider_value(n[4]))
    # -- counters (wave 41A) -- "manifest a number of cards from the top of your library equal to the number of counters on it" (Omarthis, Ghostfire Initiate):
    # "manifest the top X cards of your library, where X is …" (701.40a)
    n = re.fullmatch(r"manifest a number of cards from the top of your library equal to (.+)", text)
    if n:
        return "manifest the top x cards of your library", ("x", _rider_value(n[1]))
    m = re.search(r",? where [xX] is (.+)$", text)  # (Oracle writes X; the lowercase form is the older tests')
    if m:
        return text[: m.start()], ("x", _rider_value(m[1]))
    # -- any number as an additional cost (wave 48B) -- "loses 2 life plus 2 life for each Spirit sacrificed this way" (Devouring Greed): the first amount, and the second counted
    m = re.fullmatch(r"(.+? \d+ life) plus (?:an additional )?(\d+) life for each (.+)", text)
    if m:
        return m[1], ("plus", (int(m[2]), _rider_value(m[3])))
    m = re.search(r" for each (.+)$", text)
    if m:
        return text[: m.start()], ("each", _rider_value(m[1]))
    return text, None


def _rider_value(phrase: str) -> Any:
    """A rider's quantity: "its power" / "that creature's toughness" / "~'s power" (app: _stat),
    else any counted phrase (values.parse_count; "counters on it" with "it" as a placeholder)."""
    if phrase == "the total amount of mana paid this way":  # -- trigger other (wave 25B) -- join forces (app/rules/join_forces.py)
        return {"paid_x": "jf"}
    if phrase == "its power minus ~'s power":  # -- counters (wave 41A) -- Drizzt Do'Urden's "the difference" (107.1b: never below 0; scripts._define words it so)
        return {"minus": [_stat("its power"), _stat("~'s power")]}
    if phrase == "the damage dealt":  # -- triggers (wave 30J) -- Primo: "a number of +1/+1 counters on it equal to the damage dealt": the trigger event's amount
        return {"event_amount": 1}
    if re.fullmatch(r"(?:(?:\d+|one|two|three) plus )?the sacrificed (?:creature|artifact|permanent|land|enchantment)'s "
                    r"(?:power|toughness|mana value)", phrase):  # -- amounts (wave 12C) --
        return _stat(phrase)
    if re.fullmatch(r"(?:its|that (?:creature|permanent|card|artifact|enchantment|land|planeswalker)'s|that spell's|~'s|this creature's|"
                    r"the sacrificed (?:creature|artifact|permanent|land)'s|the discarded card's|the milled card's|the spell's|"
                    r"the exiled (?:creature )?card's|the exiled creature's) (?:power|toughness|mana value)", phrase) or re.fullmatch(
                        r"the mana value of (?:that spell|the spell|the milled card)|the (?:power|toughness|mana value) of (?:the exiled card|the card you exiled)", phrase):  # (wave 19F; 34C: "the power of the exiled card")
        return _stat(phrase)
    if _DIFF.fullmatch(phrase):  # (wave 47A: Doran, "where X is the difference between its power and toughness")
        return _stat(phrase)
    if phrase in ("of its colors", "of that spell's colors"):  # -- value grammar (wave 23C) -- "for each of its colors": how many colors the object is (105.1)
        return {"colors": "that_spell" if "spell" in phrase else "it"}
    if phrase in ("the number of colors that spell is", "the number of colors it is") or re.fullmatch(
            r"the (?:power|toughness|mana value) of the creature that died|the (?:power|toughness) of the creature tapped this way|"
            r"the (?:power|toughness|mana value) of the (?:card|creature|permanent|artifact|enchantment|land|creature card) (?:exiled|returned|milled|destroyed) this way", phrase) or re.fullmatch(
            r"(?:two|three|four) times (?:its|~'s|this creature's|that creature's) (?:power|toughness|mana value)", phrase):  # -- value grammar (wave 23C) -- 105.1
        return _stat(phrase)
    if (tw := this_way.parse(phrase)) is not None:  # -- "this way" outcomes (wave 4A) --
        return tw
    if (mult := re.fullmatch(r"(?:twice|(?P<k>two|three|four) times) (?P<v>the number of .+ this way)", phrase)) is not None and (tw := this_way.parse(mult["v"])) is not None:
        return {"times": [values.NUMBERS[mult["k"]] if mult["k"] else 2, tw]}  # (wave 48B: Corpseweft, "twice the number of cards exiled this way")
    v = values.parse_count(phrase, it="it")
    if v is None:
        v = values.target_relative(phrase)  # -- value grammar (wave 23C) -- "creature target opponent controls": scripts._value_targets
    if v is None:
        v = sized_damage.per_player(phrase)  # -- damage sized by a count (wave 4E) -- (damage only: parse_sentence checks)
    if v is None:
        raise _Fail
    return v


def x_definition(phrase: str) -> Any | None:
    """-- X sized by a count (wave 4K) -- what "where X is <phrase>" defines X as, for a grammar outside this module
    (token creation): any rider quantity but one read per recipient player (damage only), else None. A pronoun's
    stat stays the placeholder "it" for scripts.resolve_it to bind (or refuse)."""
    try:
        v = _rider_value(phrase.strip())
    except _Fail:
        return None
    return None if sized_damage.has_per_player({"n": v}) else v


def _apply(n: Any, rider: Any) -> Any:
    if rider is None:
        return n
    kind, v = rider
    if kind == "x":
        if n != {"x": 1}:
            raise _Fail  # "where X is" with no X in the sentence
        return v
    if kind == "plus":  # (wave 48B: n, and k more for each v)
        return {"plus": [n, v[1] if v[0] == 1 else {"times": [v[0], v[1]]}]}
    return v if n == 1 else {"times": [n, v]}


# -- most-played cards II (wave 45A) -- "Any number of target players each mill two cards." (Court of Cunning), "Two target players each draw a card." (Gleaming Splendor): one
# target group of players (115.1, 601.2c), every chosen player does it (effects._players: "target" is the whole group)
_MULTI_PLAYERS = r"(?:any number of|up to (?:one|two|three|four)|two|three|four) target (?:players|opponents) each"
_SUBJ = rf"(?:(?P<s>{_MULTI_PLAYERS}|target player|target opponent|{PLAYER_PHRASES}) )?"


def _subject(m: re.Match[str]) -> tuple[str, str | None]:
    """(who, target key)"""
    if m["s"] is None and re.match(r"^\w+s\b", m.string):
        raise _Fail  # "discards a card" with no subject: someone else's (the lead's subject), not "you"
    s = m["s"] or "you"
    if s in ("target player", "target opponent"):
        return "target", _LEGACY_TARGETS[s]
    if s.endswith(" each") and "target" in s:  # (wave 45A: the group of players, not one)
        return "target", _one(target_group(s.removesuffix(" each")))
    return PLAYER_GROUPS[s], None


# -- tutors (wave 3T) -- one grammar for a library search: what is searched for (a selector, a name,
# a mana value that may be X), whether it is revealed, where it goes (one place, or "one … and the
# other …"), and whether the library is shuffled (701.23, 701.24).
_PRON = r"(?:it|them|that card|those cards|the card|the cards)"
_PLACE = r"(?:into (?:your|their) hand|onto the battlefield tapped|onto the battlefield|into your graveyard)"
# Who searches: the player themself ("you may" is read before this), or a named player who may search
# their own library ("Its controller may search their library for a basic land card …": Path to Exile).
_SEARCHERS = {**{k: v for k, v in PLAYER_GROUPS.items() if k in ("its controller", "that player", "that creature's controller",
                                                                   "that permanent's controller")},
              "that land's controller": "it.controller", "that artifact's controller": "it.controller",
              "that enchantment's controller": "it.controller",
              # -- other players' choices (wave 12D) -- "Each opponent may search their library …" (effects.search: one search
              # per player, in turn order, 101.4)
              "each opponent": "each_opponent", "each other player": "each_opponent", "each player": "each_player"}
_SEARCH = re.compile(
    rf"(?:(?P<who>{'|'.join(sorted(_SEARCHERS, key=len, reverse=True))}) (?:may |(?=searches ))?)?"  # (wave 19E: "searches")
    rf"searche?s? (?P<lib>your|their) library for (?:(?P<upto>up to) )?(?P<n>any number of|{AMT}) (?P<sel>.+?)(?:,? and |, )"
    rf"(?:(?P<reveal>reveal {_PRON})(?:,? and |, ))?"
    rf"(?:puts? (?:(?P<one>one)(?: of them)? (?P<d1>{_PLACE}) and the other (?P<d2>{_PLACE})|{_PRON} (?P<dest>{_PLACE})(?: attached to (?P<host>~|this creature|this equipment|target player|target opponent|target creature(?: you control)?))?"  # (wave 53C: a target host, Bitterheart Witch)
    rf"(?P<cond> if it's (?P<cq>an? [a-z ]+? card) and (?P<els>{_PLACE}) otherwise)?)(?P<shuf>, then shuffles?)?"  # (cond: wave 50I)
    rf"|(?P<exile>exile {_PRON}(?P<fd> face down)?)(?P<shuf2>, then shuffle)?"
    rf"|then shuffles? and puts? {_PRON} (?:on top(?: in any order)?|(?P<third>third from the top)))")  # (wave 42C: "searches …, then shuffles and puts that card on top")  # ("in any order": wave 3R4; third: wave 20D)
_DESTS = {"into your hand": "hand", "into their hand": "hand", "onto the battlefield tapped": "battlefield_tapped", "onto the battlefield": "battlefield",
          "into your graveyard": "graveyard"}
_MV_X = re.compile(r"(?P<rest>.+?),? (?:with|that (?:each )?have) mana value [xX](?P<less> or less)?")  # (wave 20D: Uncage the Menagerie)
# -- tutor (wave 20D) -- a number: "with mana value 4 or 5" (Transit Mage), "that have mana value 9" (Grozoth), "… 3 or less"
_MV_N = re.compile(r"(?P<rest>.+?),? (?:with|that (?:each )?have) mana value (?P<a>\d+)(?: or (?P<b>\d+|less))?")
_NAMED = re.compile(r"(?P<rest>card|cards) named (?P<name>.+)")
_MV_EQUAL = re.compile(r"(?P<rest>.+?),? with mana value equal to (?:(?P<n>\d+|one|two) plus )?(?P<v>the sacrificed \w+'s mana value)"
                       r"(?: plus (?P<n2>\d+|one|two))?")  # (wave 3R4)
_MV_CMP = re.compile(r"(?P<rest>(?:.+? )?cards?),? with mana value (?P<op>less than or equal to|less than|equal to) "
                     r"(?P<v>the number of .+|your devotion to .+|~'s power|the greatest .+)")  # (wave 4M)
_MV_OPS = {"less than or equal to": "<=", "less than": "<", "equal to": "=="}  # (wave 4M)


def _card_selector(text: str) -> str | None:
    """One phrase for cards in the library ("creature card", "Island card") as a selector key."""
    sel = selectors.parse(text)
    if sel is None or sel.player is not None or not sel.card:
        return None
    return selectors.replace(sel, zones=("library",), zone_owner="you", card=True).key()


def _search_selectors(text: str, one: bool) -> dict[str, Any]:
    """What a search is for: one selector ("creature card"), or - when the whole phrase isn't one -
    alternatives ("a basic land card or a Desert card": any matches) or, for several, a card for
    each part ("a Forest card and a Plains card": a card of each kind, a stated quality so each may be
    missing). Anything with a qualifier shared across the parts is refused."""
    whole = _card_selector(text)
    if whole is not None:
        return {"sel": whole}
    # -- recursion & tutors (wave 4M) -- "up to two basic land cards and/or Gate cards" (Circuitous Route): each card
    # found is either; "an Aura card and/or an Equipment card" (Axgard Armory): a card of each kind, each optional
    # (701.23b: a stated quality); "an instant card or a card with flash" (Mystical Teachings): alternatives, each a
    # whole card phrase of its own (no qualifier shared across them)
    if " and/or " in text:
        halves = text.split(" and/or ")
        if len(halves) == 2 and re.fullmatch(r"(?!an? )\S.* card", halves[0]) and re.fullmatch(r"an? \S.* card", halves[1]) and one:
            keys = [_card_selector(re.sub(r"^an? ", "", h)) for h in halves]
            if None in keys:
                raise _Fail
            return {"sel": keys[0], "parts": keys}
        if len(halves) == 2 and all(re.fullmatch(r"(?!an? )\S.* cards", h) for h in halves) and not one:
            keys = [_card_selector(h[: -len("s")]) for h in halves]
            if None in keys:
                raise _Fail
            return {"sel": keys[0], "alts": keys}
        raise _Fail
    if " with " in text:
        alts = re.split(r",? or (?=an? )", text)
        if len(alts) < 2 or not all(re.fullmatch(r"(?:an? )?(?:\S+ )*?card(?: with .+)?", a) for a in alts):
            raise _Fail
        keys = [_card_selector(re.sub(r"^an? ", "", a)) for a in alts]
        if None in keys:
            raise _Fail
        return {"sel": keys[0], "alts": keys}
    # -- end recursion & tutors (wave 4M) --
    parts = re.split(r"(?:, and |, | and )(?=an? )", text)
    if len(parts) > 1 and one and not re.search(r", or an? ", text):  # (wave 20D: "a snow permanent card, a legendary card, or a Saga card" are alternatives)
        keys = [_card_selector(re.sub(r"^an? ", "", x)) for x in parts]
        if None in keys:
            raise _Fail
        return {"sel": keys[0], "parts": keys}
    alts = re.split(r", or | or |, ", text)
    if len(alts) > 1 and " or " in text:
        keys = [_card_selector(re.sub(r"^an? ", "", x) if re.search(r"\b(?:card|cards)$", x) else re.sub(r"^an? ", "", x) + " card")
                for x in alts]
        if None in keys:
            raise _Fail
        return {"sel": keys[0], "alts": keys}
    raise _Fail


# -- static_other sweep (wave 26A) -- "Search target opponent's library for a creature card and put that card onto the battlefield under
# your control." (Bribery, Acquire), "… up to three creature cards and put them into their graveyard." (Life's Finale), "… for a card and
# exile it." (Extract, Bitter Ordeal): the searcher is the ability's controller, the library is the target player's (701.23a); the cards
# found are the library owner's, so they go to that owner's graveyard or exile, or enter under the searcher's control
_SEARCH_THEIRS = re.compile(r"search (?P<t>target opponent|target player|that player)'s library for (?P<mid>.+?)(?:,? and |, )"  # (-- player-relative selectors (wave 53A) -- "that player's": the trigger event's player; "face down": Praetor's Grasp; ", exile them": Sadistic Sacrament)
                            r"(?:put (?:that card|it|them|those cards) (?:(?P<bf>onto the battlefield under your control)|(?P<gy>into (?:their|that player's) graveyard))"
                            r"|exile (?P<pl>it|them)(?P<fd> face down)?)")
SELECTORS_TARGET = {"target opponent": "opponent", "target player": "player"}
# -- activated other (wave 42C) -- "Target player searches their library for a card, then shuffles and puts that card on top." (Varragoth): the target player is the
# searcher (701.23a) and chooses the card from their own library (hidden from the rest); read as "each player searches …", aimed at the one target
_SEARCH_TARGET = re.compile(r"(?P<t>target player|target opponent) (?P<rest>searches their library for .+)")


def _search(text: str) -> tuple[Effects, str | None] | None:
    """701.23: "Search your library for [up to N] [card selector], [reveal it,] put it [where], then
    shuffle" (or "…, reveal it, then shuffle and put that card on top"; "exile it [face down]";
    "put one onto the battlefield and the other into your hand"). A card "named …", or with "mana
    value X or less" (the X the spell or ability has), is searched for too. Without "then shuffle"
    the library is not shuffled (701.24 shuffles only when told to)."""
    # CR 122.6: counters specified by the search instruction are entry counters.
    marked = "onto the battlefield with an additional +1/+1 counter on it"
    if marked in text:
        if text.count(marked) != 1:
            raise _Fail
        found = _search(text.replace(marked, "onto the battlefield"))
        if found is None or len(found[0]) != 1 or found[0][0].get("do") != "search" \
                or found[0][0].get("to") != "battlefield" or found[0][0].get("to2"):
            raise _Fail
        return [{**found[0][0], "counter": "+1/+1", "counter_n": 1}], found[1]
    if (tt := _SEARCH_TARGET.fullmatch(text)) is not None:  # (wave 42C)
        found = _search(f"each player {tt['rest']}")
        if found is None or found[0][0].get("who") != "each_player" or found[0][0].get("parts") or found[0][0].get("to2"):
            raise _Fail
        return [{**found[0][0], "who": "target"}], SELECTORS_TARGET[tt["t"]]
    if (theirs := _SEARCH_THEIRS.fullmatch(text)) is not None:  # -- static_other sweep (wave 26A) -- another player's library (701.23)
        std = {"b": "put it onto the battlefield", "g": "put it into your graveyard", "x": f"exile {theirs['pl']}" + (theirs["fd"] or "")}[
            "b" if theirs["bf"] else "g" if theirs["gy"] else "x"]
        found = _search(f"search your library for {theirs['mid']}, {std}")
        if found is None or found[0][0].get("who", "you") != "you" or found[0][0].get("parts") or found[0][0].get("to2"):
            raise _Fail
        if theirs["t"] == "that player":  # -- player-relative selectors (wave 53A) -- the player the trigger event names (scripts.resolve_it binds it)
            return [{**found[0][0], "library": "that_player"}], None
        return [{**found[0][0], "library": "target"}], SELECTORS_TARGET[theirs["t"]]
    # -- recursion & tutors (wave 4M) -- "… then shuffle. You may search your library for a basic land card, put it onto the
    # battlefield, then shuffle." (Demolition Field, mid-ability): searching is the controller's choice, asked first; one
    # who doesn't search doesn't shuffle (effects.search, as for "Its controller may search …")
    if text.startswith("you may search your library for "):
        found = _search(text[len("you may "):])
        if found is None or found[0][0].get("who", "you") != "you" or found[0][0].get("may"):
            raise _Fail
        return [{**found[0][0], "may": True, "optional": True}], None
    # -- recursion & tutors (wave 4M) -- "Search your library for up to X basic land cards, where X is the number of
    # lands you control, put them onto the battlefield tapped, then shuffle." (Boundless Realms): how many cards may be
    # found is the count, read as the search begins (107.3c: X defined by the ability's text)
    sized = re.fullmatch(r"(?P<a>(?:(?:each player|each opponent) )?search(?:es)? (?:your|their) library for up to [xX] "  # (wave 25B: "each player searches")
                         r"(?!.*\bwith mana value [xX]\b).+?),? where [xX] is (?P<v>.+?), (?P<b>(?:puts?|reveal) .+)", text)
    if sized:
        found = _search(f"{sized['a']}, {sized['b']}")
        if found is None or found[0][0].get("max") != {"x": 1}:
            raise _Fail
        return [{**found[0][0], "max": _rider_value(sized["v"])}], None
    # -- resolution memory (wave 22D) -- "Search your library for a creature card with mana value X or less, where X is 2 plus the
    # sacrificed creature's mana value, put it onto the battlefield, then shuffle." (Eldritch Evolution): X is defined by the ability's
    # text (107.3c) and read as the search is made (608.2h; the sacrificed creature as it last existed)
    mvx = re.fullmatch(r"(?P<a>search your library for (?!up to ).+? mana value [xX](?: or less)?),? where [xX] is (?P<v>.+?), "
                       r"(?P<b>(?:put|reveal) .+)", text)
    if mvx:
        found = _search(f"{mvx['a']}, {mvx['b']}")
        if found is None or not _has_x(found[0]):
            raise _Fail
        return _bind_x(found[0], _rider_value(mvx["v"])), found[1]
    # -- end recursion & tutors (wave 4M) --
    m = _SEARCH.fullmatch(text)
    if not m:
        return None
    if (m["who"] is None) != (m["lib"] == "your"):
        raise _Fail  # ("their library" is a named player's; "your library" is the one who controls the effect's)
    forced = " searches " in text  # -- search (wave 19E) -- "Each player searches their library …, puts it …, then shuffles." (no "may")
    if not forced and "into their hand" in text and m["who"] in ("each opponent", "each other player", "each player"):
        return None  # -- search into their hand (wave 50G) -- "Each player may search their library … into their hand" is each_may's (101.4: all answer first; only searchers shuffle)
    if forced and (m["exile"] or " put " in text or text.count(" shuffle") != text.count(" shuffles")):
        raise _Fail
    extra: dict[str, Any] = {}
    sel_text = m["sel"]
    # -- refused zones/sized (wave 3R4) -- "up to three Aura cards with different names": the cards found must
    # all have different names (checked as the searcher chooses: effects.resume_search)
    # -- recursion & tutors (wave 4M) -- "up to two basic land cards that share a land type" (Myriad Landscape): the
    # cards found must have a land type in common (205.3i; checked as the searcher chooses: recursion.check_found)
    share = re.fullmatch(r"(?P<rest>.+? land cards) that share a land type", sel_text)
    if share:
        if m["n"] in ("a", "an", "one"):
            raise _Fail
        sel_text = share["rest"]
        extra["share_land_type"] = True
    # -- end recursion & tutors (wave 4M) --
    distinct = re.fullmatch(r"(?P<rest>.+?) (?:with|that each have) different names(?P<tail>(?: that .+)?)", sel_text)
    if distinct:
        if m["n"] in ("a", "an", "one"):
            raise _Fail
        sel_text = distinct["rest"] + distinct["tail"]
        extra["distinct_names"] = True
    total = re.fullmatch(r"(?P<rest>.+?) with total mana value (?P<n>\d+) or less", sel_text)
    if total:  # -- tutor (wave 20D) -- Protean Hulk: the cards found have this much mana value in all (checked as the searcher chooses: effects.resume_search)
        if m["n"] != "any number of":
            raise _Fail
        sel_text = total["rest"]
        extra["total_mv"] = int(total["n"])
    named = _NAMED.fullmatch(sel_text)
    if named:
        if re.search(r" or an? |and/or |\bnamed\b", named["name"]):  # -- wave 3S: "a card named X or an Equipment card" (alternatives): not read --
            # (-- if you do (wave 15C) -- nor "a card named X and/or a card named Y": two names, not one)
            raise _Fail
        extra["name"] = named["name"]
        sel_text = named["rest"]
    # -- tutor (wave 26D) -- "a card with the same name as that creature / target creature / another creature you control / a card in your
    # graveyard" (app/rules/same_name.py); "that creature" is the trigger event's (scripts: only in a trigger about an object)
    same = re.fullmatch(r"(?P<rest>.+?) with the same name as (?P<ref>that creature|that card|target [^,]+|another creature you control|a card in your graveyard)",
                        sel_text)
    target_found = None
    if same:
        ref, sel_text = same["ref"], same["rest"]
        if ref.startswith("target "):
            group = target_group(ref)
            if group is None or not str(group["what"]).startswith(selectors.PREFIX):
                raise _Fail
            extra["name_as"], target_found = "target", _one(group)
        elif ref.startswith("that "):
            extra["name_as"] = "it"
        else:
            sel_ref = selectors.parse("another creature you control" if ref.startswith("another") else "card from your graveyard")
            if sel_ref is None:
                raise _Fail
            extra["name_as"] = {"sel": sel_ref.key()}
    mv = _MV_X.fullmatch(sel_text)
    if mv:
        extra["mv"] = ["<=" if mv["less"] else "==", _amount("x")]
        sel_text = mv["rest"]
    mvn = None if mv else _MV_N.fullmatch(sel_text)
    if mvn:
        extra["mv"] = ["<=", int(mvn["a"])] if mvn["b"] == "less" else ["in", [int(mvn["a"]), int(mvn["b"])]] if mvn["b"] else ["==", int(mvn["a"])]
        sel_text = mvn["rest"]
        mv = mvn
    # -- refused zones/sized (wave 3R4) -- "with mana value equal to 1 plus the sacrificed creature's mana value"
    # (Birthing Pod; the sacrificed creature is read from the cost's payment record: scripts.define checks it is one)
    pod = None if mv else _MV_EQUAL.fullmatch(sel_text)
    if pod:
        base = _stat(pod["v"])
        if not (isinstance(base, dict) and base.get("mana_value") == "cost:sacrificed"):
            raise _Fail
        k = pod["n"] or pod["n2"]
        extra["mv"] = ["==", {"plus": [base, int(k) if k.isdigit() else values.NUMBERS[k]]} if k else base]
        sel_text = pod["rest"]
        mv = pod
    # -- recursion & tutors (wave 4M) -- "a card with mana value less than or equal to the number of lands you control"
    # (Beseech the Queen), "… less than Sisay's power", "… equal to the number of verse counters on Yisan": the count
    # is read as the search is made (608.2h)
    cmp = None if mv else _MV_CMP.fullmatch(sel_text)
    if cmp:
        extra["mv"] = [_MV_OPS[cmp["op"]], _rider_value(cmp["v"])]
        sel_text = cmp["rest"]
        mv = cmp
    # -- end recursion & tutors (wave 4M) --
    anything = m["n"] == "any number of"
    n = 999 if anything else _amount(m["n"])
    single = m["n"] in ("a", "an", "one")
    extra.update(_search_selectors(sel_text, single))
    if "parts" in extra and (m["one"] or named or mv):
        raise _Fail
    if "parts" in extra:
        n = len(extra["parts"])
    if m["one"]:
        if n != 2 or anything:
            raise _Fail
        to, extra["to2"] = _DESTS[m["d1"]], _DESTS[m["d2"]]
    elif m["exile"]:
        to = "exile"
    elif m["dest"]:
        to = _DESTS[m["dest"]]
    else:
        to = "top"
        if m["third"]:  # -- tutor (wave 20D) -- Long-Term Plans: after the shuffle, the third card from the top (401.4; fewer cards: the bottom)
            if n != 1 or anything:
                raise _Fail
            extra["depth"] = 3
        if n != 1:
            extra["top_order"] = True  # -- refused zones/sized (wave 3R4) -- several on top: the searcher orders them (401.4)
    if m["host"]:  # -- if you do (wave 25C) -- "put it onto the battlefield attached to this creature" (303.4f / 301.5e: effects._attached_entries)
        if not to.startswith("battlefield") or n != 1 or m["one"]:
            raise _Fail
        extra["host"] = "self"
        if m["host"].startswith("target "):  # -- block events (wave 53C) -- "…attached to target player": a target of the ability, chosen with it (115.1); a Curse is attached to a player (303.4c)
            if target_found is not None or (group := target_group(m["host"])) is None:
                raise _Fail
            extra["host"], target_found = "target", _one(group)
    if m["cond"]:  # -- most-played modal spells (wave 50I) -- "Put it onto the battlefield tapped if it's a land card. Otherwise, put it into your hand." (Archdruid's Charm): the card found
        # goes where its kind says (701.23, 608.2c); it is revealed, so where it goes is public
        kind = _card_selector(re.sub(r"^an? ", "", m["cq"]))
        if kind is None or n != 1 or anything or m["one"] or m["host"] or "parts" in extra or not m["reveal"]:
            raise _Fail
        extra["to_if"] = {"sel": kind, "to": to}
        to = _DESTS[m["els"]]
    if to != "top" and not (m["shuf"] or m["shuf2"]):
        extra["shuffle"] = False  # (only when the text says so: 701.23e)
    return [{"do": "search", "who": _SEARCHERS[m["who"]] if m["who"] else "you", "label": m["sel"], "max": n,
             "to": to, "reveal": bool(m["reveal"]), "upto": bool(m["upto"]) or anything,
             **({"face_down": True} if m["fd"] else {}), **({"may": True} if m["who"] and not forced else {}), **extra}], target_found


# -- refused zones/sized (wave 3R4) -- "Search your library and/or graveyard for a card named …, reveal it, and
# put it into your hand. If you search your library this way, shuffle." (Finale of Devastation, the planeswalker
# deck cards): the searcher chooses to search the library and the graveyard, or the graveyard only (701.23a: a
# search looks at all the cards in that zone); the second sentence (``gy_search_shuffle``, joined to the search
# by scripts._gy_shuffle) shuffles only a library that was searched (701.24). One card, one destination.
# -- if you do (wave 15C) -- also "your graveyard, hand, and/or library" (any of them, 701.23a) and "your graveyard, hand, and
# library" (all three), the zones in any order; "…, then shuffle" after the destination
_GY_ZONES = (r"(?P<zones>library and/or graveyard|graveyard and/or library|(?:graveyard|library), hand,? (?:and/or|and) (?:library|graveyard)"
             r"|hand and/or library|library and/or hand)")
_SEARCH_GY = re.compile(rf"search your {_GY_ZONES} for (?P<q>(?:up to )?(?:{AMT})) (?P<sel>.+?)(?:,? and |, )"
                        rf"(?:(?P<reveal>reveal {_PRON})(?:,? and |, )(?:then )?)?put (?P<pron>{_PRON}) "
                        rf"(?P<dest>into your hand|onto the battlefield)(?P<host> attached to (?:~|this creature|this equipment|target creature(?: you control)?|target player|target opponent))?(?P<then>, then shuffle)?")  # (wave 53C: a target host, Arachnus Spinner)


_GAMBLE = re.compile(r"search your library for a card, put (?:that card|it) into your hand, (?P<first>shuffle, then )?"
                     r"discard a card at random(?P<last>, then shuffle)?")


def _search_gy(text: str) -> tuple[Effects, str | None] | None:
    gamble = _GAMBLE.fullmatch(text)  # (Gamble, Curse-Marred Demon: the found card may be the one discarded, 701.9b)
    if gamble is not None and bool(gamble["first"]) != bool(gamble["last"]):
        search = {"do": "search", "who": "you", "label": "card", "max": 1, "to": "hand", "reveal": False, "upto": False,
                  "sel": 'sel:{"card":true,"zone_owner":"you","zones":["library"]}',
                  "shuffle": bool(gamble["first"])}
        discard = {"do": "discard", "who": "you", "n": 1, "random": True}
        return ([search, discard] if gamble["first"] else [search, discard, {"do": "shuffle_library", "who": "you", "zones": []}]), None
    may = text.startswith("you may ")  # (mid-ability: "… You may search your library and/or graveyard …")
    m = _SEARCH_GY.fullmatch(text[len("you may "):] if may else text)
    if m is None:
        return None
    reveal = f"{m['reveal']}, " if m["reveal"] else ""
    found = _search(f"search your library for {m['q']} {m['sel']}, {reveal}put {m['pron']} {m['dest']}{m['host'] or ''}")
    if found is None:
        raise _Fail
    e = found[0][0]
    if e.get("parts") or e.get("to2") or e.get("who", "you") != "you" or e["max"] != 1:
        raise _Fail  # (several cards from two zones: not read)
    zones = [z for z in ("library", "hand", "graveyard") if z in m["zones"]]
    if " and/or " not in m["zones"] and len(zones) == 3:  # -- if you do (wave 15C) -- "your graveyard, hand, and library": all three
        if may or not m["then"]:
            raise _Fail  # (the library is searched, so it is shuffled: 701.24, only when told; a "may" is not read)
        return [{**e, "zones": zones, "shuffle": True}], found[1]
    if m["then"]:
        raise _Fail  # (a "may" search, "then shuffle": only the forced three zones, above)
    extra = {"search_zones": zones} if "hand" in zones else {}
    return [{**e, "graveyard": True, "shuffle": False, **extra, **({"may": True, "optional": True} if may else {})}], found[1]


# -- the top of a library (401, 701.20 reveal, 701.20e look, 701.24 shuffle) ----------------------
# Whose library: "your library" (default), a target player's (a target group), everyone's.
_LIB = r"(?P<lib>your|target player's|target opponent's|that player's|their|each player's|each opponent's|defending player's) library"  # (-- player-relative selectors (wave 53A) -- defending player's: 508.5)
_LIB_WHO = {"your": "you", "target player's": "target player", "target opponent's": "target opponent",
            "that player's": "that player", "their": "that player", "each player's": "each player", "each opponent's": "each opponent", "defending player's": "defending player"}
_SUBJECTS = r"(?P<subj>target player|target opponent|that player|its controller|that creature's controller|that permanent's controller|defending player|each player|each opponent|each of your opponents)"
_N_CARDS = rf"(?:(?P<n>{AMT}) cards|card)"
# (wave 26B: "reveal that many cards from the top of your library": the trigger event's amount, Ojer Kaslem)
_TOP = re.compile(rf"(?P<verb>look at|reveal) (?:the top {_N_CARDS}|(?P<nm>that many) cards from the top) of {_LIB}"
                  r"(?P<back>, then put them back in any order)?")
_SUBJ_TOP = re.compile(rf"{_SUBJECTS} (?P<verb>reveals|exiles) the top {_N_CARDS} of their library(?P<fd> face down)?")
_EXILE_TOP = re.compile(rf"exile the top {_N_CARDS} of {_LIB}(?P<fd> face down)?")
# -- hidden exile (wave 18A) -- "Put the top two cards of that player's library onto the battlefield face down under your control as
# 2/2 Cyberman artifact creatures." (Cybership), "Put any number of cards from your hand onto the battlefield face down as 5/5 artifact
# creatures." (Tezzeret, Cruel Machinist): facedown.put_down (708.2a: the characteristics come with the instruction)
# -- hidden exile (wave 18A) -- "Exile all creature cards from target player's graveyard in a face-down pile, shuffle that pile, then
# manifest those cards." (Ghastly Conscription), "exile it and the top card of your library in a face-down pile, …" (Jeskai Infiltrator),
# "Exile target nontoken creature you own and the top two cards of your library in a face-down pile, shuffle that pile, then cloak those
# cards [tapped]." (Become Anonymous): facedown.manifest_pile
_PILE = re.compile(rf"exile (?P<src>all creature cards from target player's graveyard|(?P<obj>it|target nontoken creature you own)"
                   rf"(?: and the top {_N_CARDS} of your library)?) in a face-down pile, shuffle that pile, then (?P<v>manifest|cloak) "
                   r"those cards(?P<tap> tapped)?")
_PUT_DOWN = re.compile(rf"put (?:the top {_N_CARDS} of {_LIB}|(?P<hand>any number of cards from your hand)) onto the battlefield face down"
                       r"(?P<under> under your control)?(?: as (?P<spec>.+))?")
# -- hidden exile (wave 18A) -- looking.join_down_piles: a face-down pile and a face-up pile (700.3), one clause
_DOWN = re.compile(rf"(?P<s>target opponent|an opponent|you) separates? the top {_N_CARDS} of your library into a face-down pile and a "
                   r"face-up pile, then (?P<tail>you put one pile into your hand and the other into your graveyard|an opponent chooses "
                   r"one of them, then you put that pile into your hand and the other into your graveyard)")
_UNTIL = re.compile(rf"(?P<verb>reveal|exile) cards from the top of {_LIB} until you (?P=verb) (?:(?P<cnt>two|three|four|five|six|seven|X) |an? )(?P<sel>.+?)(?:, where X is (?P<w>.+))?")  # (wave 51C: "until you reveal two land cards" / "X land cards, where X is the number of legendary creatures you control" (The Ring Goes South), the Nth match)
# -- look and distribute (wave 3L) -- where the picked / remaining cards go; a library may be "that library"
# / "that player's library" (the one looked at), a graveyard "their graveyard"
_LIBREF = r"(?:your|that|their|that player's) library"
_REST = (r"(?:the rest|the rest of (?:those|the)(?: revealed)? cards|the rest of them|the other|the others|the other cards|"
         r"all other cards revealed this way|"
         # -- refused look/cast-free (wave 3R5) -- after a free cast (608.2g): the cards it didn't cast
         r"all revealed cards not cast this way|the exiled cards not cast this way|the exiled cards that weren't cast this way|"
         r"all cards exiled this way that weren't cast|"
         r"all cards revealed this way that weren't put onto the battlefield) "  # (-- if you do (wave 15C) -- Genesis Wave)
         rf"(?P<rest>into (?:your|their) graveyard|into your hand|on the bottom(?: of {_LIBREF})? in (?:any|a random) order|"
         rf"on the bottom of {_LIBREF}|(?:back )?on top of {_LIBREF} in any order|back in any order)")  # (wave 26D: "put the rest back in any order")
_PICK_TO = ("into your hand|into their hand|onto the battlefield tapped and attacking|onto the battlefield tapped|onto the battlefield|into your graveyard|"
            "into their graveyard|into that player's graveyard|"  # (wave 20F: another player's library, its owner's graveyard, 404.1)
            "back on top of your library|on top of your library|on the bottom of your library|on the bottom of that player's library|"
            "on top of that player's library|on the bottom of that library|on top of that library")
_PICK_DESTS = {**_DESTS, "onto the battlefield tapped and attacking": "battlefield_attacking",  # (wave 3R5: 508.4)
               "on top of your library": "top", "on the bottom of your library": "bottom",
               "on the bottom of that player's library": "bottom", "on top of that player's library": "top",
               "on the bottom of that library": "bottom", "on top of that library": "top",
               "into their graveyard": "graveyard", "into that player's graveyard": "graveyard", "back on top of your library": "top",
               "into their hand": "hand"}
_PICK = re.compile(
    # (wave 43B: "If it's a permanent card, they put it onto the battlefield." (Chaos Warp), "…, that player puts it into their hand." (Goblin Guide): the
    # library's owner puts the revealed card — ``by_owner``; "the player may put it onto the battlefield" (Gate to the Aether))
    rf"(?:(?P<may>you may reveal) |(?P<mayput>you may put) |(?P<exile>(?:you may )?exile) |(?P<theyput>(?:they|that player|the player)(?P<theymay> may)? puts? )|put )"
    rf"(?:(?P<q>up to {AMT}|any number of|{AMT}|all)(?: (?:of them|of those cards|(?P<sel>.+?) (?:from among (?:them|the cards milled this way|the milled cards|those cards)|revealed this way|milled this way))"
    r"|(?= (?:into|on|onto) )| them(?= (?:into|on|onto) )| (?:them|those cards)(?=,| and |$))"  # (wave 26D: "exile any number of them / those cards")
    r"|(?P<that>that card|it|the revealed card|the nonland card)|(?P<all>those cards|them|the revealed cards|all cards revealed this way))"
    r"(?: and put (?:it|them|the revealed cards|that card|those cards))?"
    rf"(?:(?P<fd> face down)| (?P<to>{_PICK_TO}))?"
    rf"(?:,? (?:and |then )?(?:put )?{_REST})?")
# (-- damage sized by a count (wave 20A) -- "Put the revealed cards on the bottom of your library in a random order." after a reveal-until:
# all of them, the card found too, which hasn't moved)
_REST_ALONE = re.compile(rf"(?:put {_REST}|put the revealed cards (?P<rest2>on the bottom of {_LIBREF} in (?:a random|any) order)|"
                         r"exile (?P<exile>the rest|all other cards revealed this way))")
# -- refused look/cast-free (wave 3R5) -- "That player exiles cards from the top of their library until they exile an
# instant or sorcery card" (the subject's own library), and "Then that player puts the exiled cards that weren't
# cast this way on the bottom of their library in a random order" (random: who puts them doesn't matter)
_SUBJ_UNTIL = re.compile(rf"{_SUBJECTS} (?P<verb>reveals|exiles) cards from the top of their library until they "
                         r"(?:reveal|exile) (?:(?P<cnt>two|three|four|five|six|seven) |an? )(?P<sel>.+)")  # (wave 44B: "until they reveal four land cards", Mirko Vosk)
_REST_THEY = re.compile(rf"(?:that player|the player) puts {_REST}")
_OWNERS = r"(?:its owner's|their owner's|their owners'|your)"
_TO_LIBRARY = re.compile(r"put (?P<o>.+?) (?P<place>on top|on the bottom) of "
                         r"(?:(?:its owner's|their owner's|your) library|their owners' librar(?:y|ies))")
# -- block events (wave 53C) -- "Put ~ and each creature blocking or blocked by it on top of their owners' libraries, then those players shuffle." (Vortex Elemental):
# put into their owners' libraries and shuffled (701.24a): the cards go in, then each owner's library is shuffled, which is shuffling them into it
_TOP_SHUFFLE = re.compile(r"put (?:(?P<self>~) and )?(?P<o>each .+?) on top of their owners' libraries, then those players shuffle")
_NTH_FROM_TOP = re.compile(rf"put (?P<o>.+?) into {_OWNERS} library (?P<nth>second|third|fourth|fifth|sixth|seventh) from the top")
_SHUFFLE_INTO = re.compile(rf"shuffle (?P<o>.+?) into {_OWNERS} library")
# (the player whose card was chosen from the revealed hand: the card goes to its owner's library, 401.3 / 701.24)
_PLAYER_LIBRARY = re.compile(r"that player (?:shuffles (?:that card|it) into their library|puts (?:that card|it) into their library "
                             r"(?P<nth>second|third|fourth|fifth|sixth|seventh) from the top|(?P<bottom>(?P<rev>reveals and )?puts (?:that card|it) on the bottom of their library))")
_OWNER_SHUFFLES = re.compile(r"(?P<o>its|~'s|that card's|that creature's|that permanent's) owner shuffles it into their library")
# -- static_other sweep (wave 17C) -- "The owner of target creature or enchantment puts it into their library second from the top or on the
# bottom." (Lost Days, Temporal Cleansing): its owner's choice between the two places; "The owner of target artifact or enchantment an
# opponent controls shuffles it into their library." (Cathartic Parting)
_OWNER_SECOND = re.compile(r"(?:the owner of (?P<o>.+?)|(?P<o2>.+?)'s owner) puts it into their library second from the top or on the bottom")
# -- most-played cards (wave 43B) -- "…, then reveals the top card of their library" (Chaos Warp): that owner reveals from the library just shuffled
_OWNER_SHUFFLES_TARGET = re.compile(r"the owner of (?P<o>target .+?) shuffles it into their library(?P<reveal>, then reveals the top card of their library)?")
# -- ability words (wave 20C) -- "Put target card from a graveyard on your choice of the top or bottom of its owner's library." (Not
# Forgotten): the same two places, chosen by the player the instruction is given to (you), not the owner
_YOUR_CHOICE = re.compile(r"put (?P<o>.+?) on your choice of the top or bottom of (?:its|their) owner's library")
_OWNER_CHOICE = re.compile(r"(?:the owner of (?P<o>.+?)|(?P<o2>.+?)'s owner) puts it on their choice of the top or bottom of their library")
# (-- static_other sweep (wave 16B) -- "the cards from your hand": the hand alone, for a count of what was shuffled in)
# -- shuffle target cards (wave 46B) -- "Target player shuffles up to three target cards from their graveyard into their library." (Memory's Journey, Stream of
# Consciousness, Krosan Reclamation, Loaming Shaman): the cards are in that player's graveyard (the target group's "graveyard_of": targets.choose_groups)
_SHUFFLE_CARDS = re.compile(r"target player shuffles (?P<q>up to \w+|any number of) target cards from their graveyard into their library")
_SHUFFLE = re.compile(rf"(?:then )?(?:(?P<may>you may )?shuffle(?: your library)?|shuffle (?:your|the cards from your) (?P<z>graveyard|hand and graveyard|hand) into your library"
                      rf"|{_SUBJECTS} shuffles(?: their library| (?:their|the cards from their) (?P<z2>graveyard|hand and graveyard|hand) into their library)?)")


# -- refused look/cast-free (wave 3R5) -- one card of each listed kind, each a different card: "You may put a
# creature card and/or a land card from among them into your hand", "You may reveal an Angel card, a Demon card,
# and/or a Dragon card from among them and put them into your hand", "For each card type, you may put a card of
# that type from among the revealed cards into your hand" (205.2a: the card types a Commander deck can hold)
_KINDS = re.compile(r"(?P<verb>you may reveal|you may put) (?P<list>(?:(?:a|an) [a-zA-Z ]+? card, )*(?:a|an) [a-zA-Z ]+? card,? "
                    r"and/or (?:a|an) [a-zA-Z ]+? card) from among (?:them|the revealed cards)"
                    r"(?: and put (?:them|the revealed cards|those cards))? (?P<to>into your hand|onto the battlefield)")
_EACH_TYPE = re.compile(r"for each card type, you may (?P<verb>put|reveal) a card of that type from among (?:them|the revealed cards)"
                        r"(?: and put (?:it|them|the revealed cards|those cards))? into your hand")
_COMMANDER_CARD_TYPES = ("artifact", "battle", "creature", "enchantment", "instant", "kindred", "land", "planeswalker", "sorcery")


def _pick_kinds(text: str) -> tuple[Effects, Any] | None:
    m = _EACH_TYPE.fullmatch(text)
    if m:
        words = list(_COMMANDER_CARD_TYPES)
    else:
        m = _KINDS.fullmatch(text)
        if m is None:
            return None
        words = [re.sub(r"^(?:a|an) | card$", "", w.strip()) for w in re.split(r", and/or |,? and/or |, ", m["list"])]
    sels = []
    for w in words:
        sel = selectors.parse(f"{w} card")
        if sel is None or sel.player is not None or not sel.card:
            raise _Fail
        sels.append(sel.key())
    return [{"do": "pick_looked", "n": len(sels), "sel": None, "sels": sels, "to": "battlefield" if m.groupdict().get("to") == "onto the battlefield" else "hand",
             "optional": True, "reveal": m["verb"].endswith("reveal")}], None  # (-- triggers (wave 19B) -- also onto the battlefield)


# -- look top (wave 16F) -- one card that is any of several kinds: "You may reveal a Knight, Aura, Equipment, or legendary artifact card
# from among them and put it into your hand." (Acclaimed Contender), "a land card or a card with {X} in its mana cost" (Paradox
# Surveyor): the kinds are alternatives for the one card (the same listed-kinds filter, one pick)
_ALTS = re.compile(r"you may reveal (?P<list>(?:(?:an?|[a-z]+) )?[^.]+? or (?:an? )?[^.]+?) from among (?:them|those cards) "
                   r"and put (?:it|that card) into your hand")


def _pick_alts(text: str) -> tuple[Effects, Any] | None:
    m = _ALTS.fullmatch(text)
    if m is None or selectors.parse(re.sub(r"^(?:an?) ", "", m["list"])) is not None:
        return None  # (not a list of alternatives, or one selector the plain pick reads)
    words = [re.sub(r"^(?:an?) ", "", w.strip()) for w in re.split(r",? or |, ", m["list"])]
    if len(words) < 2 or any(re.search(r"\b(?:less|more|greater|that|who|which)\b|\d", w) for w in words):
        return None
    sels = []
    for w in words:
        sel = selectors.parse(w if w.endswith(" card") or " card " in w or w.startswith("card ") else f"{w} card")
        if sel is None or sel.player is not None or not sel.card:
            raise _Fail
        sels.append(sel.key())
    return [{"do": "pick_looked", "n": 1, "sel": None, "sels": sels, "to": "hand", "optional": True, "reveal": True}], None


def _rest(where: str) -> dict[str, Any]:
    if where.startswith("into "):
        to = where.split()[-1]
    elif "on top" in where or where == "back in any order":
        to = "top_any"
    else:
        to = "bottom_random" if "random" in where else "bottom_any"
    return {"do": "rest_looked", "to": to}


def _lib_owner(lib: str) -> tuple[str, dict[str, Any] | None]:
    """("you" / "each_player" / "target" …, the target group if a target player's library)."""
    kind, key, group = ref(_LIB_WHO[lib])
    return (_who(kind, key), group) if group is None else ("target", group)


def _card_sel(phrase: str) -> str:
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or not sel.card:
        raise _Fail
    return sel.key()


# -- look and distribute (wave 3L) --
_CHAIN_SPLIT = re.compile(r", (?:then |and )?")


def _chain(text: str) -> tuple[Effects, Any] | None:
    """Comma-joined steps of one look-and-distribute sentence: "look at the top four cards of target
    opponent's library, exile one of them face down, then put the rest on the bottom of that library
    in a random order" / "put one of them into your hand, put one of them on the bottom of your
    library, and exile one of them". Each piece is read on its own; every piece after the first must
    be a pick or a "the rest" step (no targets of its own: 115.3)."""
    if "," not in text or " where " in text or not re.match(r"^(?:(?:look at|reveal) the top|put|exile) ", text):
        return None
    parts = _CHAIN_SPLIT.split(text)
    if len(parts) < 2 or any(len(p) < 4 for p in parts):
        return None
    out: Effects = []
    group: Any = None
    for i, part in enumerate(parts):
        try:
            got = _looking(part)
        except _Fail:
            return None
        if got is None:
            return None
        effects, grp = got
        if i == 0 and re.match(r"^(?:put|exile) ", part) is None:
            group = grp
        elif grp is not None or any(x["do"] not in ("pick_looked", "rest_looked") for x in effects):
            return None
        out += effects
    return out, group


def _looking(text: str) -> tuple[Effects, Any] | None:
    """The top of a library: "look at the top N cards of your library" (private, 701.20e) and
    "reveal the top N cards" (public, 701.20a), "… then put them back in any order" (401.4: the
    order is the chooser's secret), "reveal cards from the top of your library until you reveal a
    creature card", "exile the top N cards of your library [face down]", and what follows: "put
    one of them / that card / all land cards revealed this way into your hand / onto the
    battlefield / into your graveyard", "you may reveal a creature card from among them and put
    it into your hand", "and the rest on the bottom of your library in a random order / in any
    order / into your graveyard", "exile the rest". Also "put target creature on top / on the
    bottom of its owner's library", "shuffle ~ into its owner's library", "shuffle [your graveyard
    into your library]"."""
    down = _DOWN.fullmatch(text) if has_primitive("piles_down") else None  # -- hidden exile (wave 18A) --
    if down is not None:
        if (down["s"] == "you") != down["tail"].startswith("an opponent"):
            raise _Fail
        pe: dict[str, Any] = {"do": "piles_down", "n": _amount(down["n"]) if down["n"] else 1,
                             "by": "you" if down["s"] == "you" else "opponent", "choose": "opponent" if down["s"] == "you" else "you"}
        if down["s"] == "target opponent":
            return [{**pe, "who": "target"}], {"what": "opponent", "min": 1, "max": 1}
        return [pe], None
    if text.endswith(' onto the battlefield with a shield counter on it'):
        shield_pick = _looking(text[:-len(' with a shield counter on it')])
        if shield_pick is not None and len(shield_pick[0]) == 1 and shield_pick[0][0].get('do') == 'pick_looked' \
                and shield_pick[0][0].get('to') == 'battlefield':
            return [{**shield_pick[0][0], 'counter': 'shield'}], shield_pick[1]
    chained = _chain(text)  # -- look and distribute (wave 3L) --
    if chained is not None:
        return chained
    text, rider = _with_rider(text) if re.match(r"^(?:look at|reveal|exile) the top", text) else (text, None)

    def count(m: re.Match[str]) -> Any:
        n = m["n"] or m.groupdict().get("nm")
        return _apply(_amount(n) if n else 1, rider)

    if text == "you may reveal the top card of your library":  # -- if you do (wave 15C) -- the revealing is the choice (701.20a)
        return [{"do": "look_top", "n": 1, "player": "you", "reveal": True, "optional": True}], None
    m = _TOP.fullmatch(text)
    if m:
        who, group = _lib_owner(m["lib"])
        out: Effects = [{"do": "look_top", "n": count(m), "player": who, "reveal": m["verb"] == "reveal"}]
        if m["back"]:
            if who not in ("you", "target", "that_player"):
                raise _Fail  # ("each player's library … put them back": who orders whose? not read)
            out.append({"do": "rest_looked", "to": "top_any"})
        return out, _one(group)
    # -- commander sweep (wave 49B) -- "target opponent exiles the top half of their library, rounded up" (Ulamog, the Defiler): 107.1a, half the library as it is now
    m = re.fullmatch(r"(?P<subj>target opponent|target player) exiles the top half of their library, rounded (?P<r>up|down)", text)
    if m and rider is None:
        kind, key, group = ref(m["subj"])
        return [{"do": "exile_top", "n": 0, "half": m["r"], "player": _who(kind, key)}], _one(group)
    m = _SUBJ_TOP.fullmatch(text)
    if m:
        kind, key, group = ref(m["subj"])
        do = "look_top" if m["verb"] == "reveals" else "exile_top"
        if m["fd"] and do == "look_top":
            raise _Fail
        return [{"do": do, "n": count(m), "player": _who(kind, key), **({"reveal": True} if do == "look_top" else {}),
                 **({"face_down": True} if m["fd"] else {})}], _one(group)  # (face down: wave 18A)
    m = _PILE.fullmatch(text)  # -- hidden exile (wave 18A) --
    if m and has_primitive("manifest_pile"):
        pile: dict[str, Any] = {"do": "manifest_pile", "kind": m["v"], "tapped": bool(m["tap"])}
        if not m["obj"]:
            kind, key, group = "players", "target", _chooser("target player")[1]
            return [{**pile, "gy": True, "who": "target"}], group
        kind, key, group = ref(m["obj"])
        if m["obj"] == "it" or kind != "target":
            return [{**pile, "who": "it", "top": count(m) if "top" in m["src"] else 0}], None
        return [{**pile, "who": "target", "top": count(m)}], group
    m = _PUT_DOWN.fullmatch(text)  # -- hidden exile (wave 18A) --
    if m and has_primitive("put_down"):
        spec = chars.parse_spec(m["spec"]) if m["spec"] else None
        if (m["spec"] and spec is None) or (m["lib"] and m["lib"] != "your" and not m["under"]):
            raise _Fail
        if m["hand"]:
            return [{"do": "put_down", "from": "hand", "spec": spec}], None
        who, group = _lib_owner(m["lib"])
        return [{"do": "put_down", "from": "library", "n": count(m), "player": who, "spec": spec}], _one(group)
    m = _EXILE_TOP.fullmatch(text)
    if m:
        who, group = _lib_owner(m["lib"])
        return [{"do": "exile_top", "n": count(m), "player": who, "face_down": bool(m["fd"])}], _one(group)
    if rider is not None:
        raise _Fail
    m = _SUBJ_UNTIL.fullmatch(text)  # -- refused look/cast-free (wave 3R5) --
    if m and (not m["subj"].startswith("each") or m["verb"] == "exiles"):  # (wave 44A: "each player exiles … until" keeps every library's cards)
        kind, key, group = ref(m["subj"])
        do = "look_top" if m["verb"] == "reveals" else "exile_top"
        if m["cnt"] and do != "look_top":
            raise _Fail
        return [{"do": do, "n": 0, "player": _who(kind, key), "until": _card_sel(m["sel"]),
                 **({"reveal": True} if do == "look_top" else {}), **({"need": values.NUMBERS[m["cnt"]]} if m["cnt"] else {})}], _one(group)
    m = _UNTIL.fullmatch(text)
    if m:
        who, group = _lib_owner(m["lib"])
        do = "look_top" if m["verb"] == "reveal" else "exile_top"
        if m["cnt"] and do != "look_top":
            raise _Fail
        if m["w"] and m["cnt"] != "X":
            raise _Fail
        need = (_rider_value(m["w"]) if m["w"] else {"x": 1}) if m["cnt"] == "X" else values.NUMBERS[m["cnt"]] if m["cnt"] else None
        return [{"do": do, "n": 0, "player": who, "until": _card_sel(m["sel"]), **({"reveal": True} if do == "look_top" else {}),
                 **({"need": need} if m["cnt"] else {})}], \
            _one(group)
    kinds = _pick_kinds(text) or _pick_alts(text)  # -- refused look/cast-free (wave 3R5) -- (_pick_alts: wave 16F)
    if kinds is not None:
        return kinds
    m = _PICK.fullmatch(text)
    # -- as long as (wave 9B) -- "look at the top card of that player's library, then exile it face down" (Edward Kenway): the
    # one card looked at is exiled face down (the validation in scripts.py refuses a pick with nothing looked at)
    if m and (m["exile"] and (m["to"] or not m["q"] and not m["fd"]) or not m["exile"] and (m["to"] is None or m["fd"])):
        m = None  # ("exile it" alone is the plain exile instruction, whatever "it" is: not a pick from among the cards looked at)
    if m and m["to"] == "into their hand" and not m["theyput"]:
        raise _Fail  # (wave 43B: "put it into their hand": whose hand? only the library's owner putting it is read)
    if m and m["theyput"] and (not m["that"] or m["to"] not in ("onto the battlefield", "onto the battlefield tapped", "into their hand", "into their graveyard") or m["rest"]):
        raise _Fail  # (wave 43B: the library's owner puts the one card looked at; a choice among several cards is not read)
    if m:
        optional = bool(m["may"] or m["mayput"] or m["theymay"] or (m["exile"] or "").startswith("you may"))
        e: dict[str, Any] = {"do": "pick_looked", "n": 1, "sel": None, "to": _PICK_DESTS[m["to"]] if m["to"] else "exile",
                             "optional": optional, "reveal": bool(m["may"]), **({"face_down": True} if m["fd"] else {}),
                             **({"by_owner": True} if m["theyput"] else {})}
        if m["q"]:
            q = m["q"]
            e["optional"] = optional or q.startswith(("up to", "any number"))
            e["n"] = 99 if q in ("any number of", "all") else _amount(q[6:] if q.startswith("up to ") else q)
            if m["sel"]:
                sel_text = m["sel"]
                if tm := re.fullmatch(r"(.+?) with total mana value (\d+) or less", sel_text):  # -- total mana value (wave 51A) -- "up to two creature cards with total mana
                    if e["n"] < 2:  # value 6 or less from among them" (Michelangelo's Technique): checked as they're picked (effects.resume_pick_looked)
                        raise _Fail
                    sel_text, e["total_mv"] = tm[1], int(tm[2])
                historic = bool(re.match(r"historic (?!.* or )", sel_text))  # (700.6: artifact, legendary or Saga; "a historic card")
                parsed = selectors.parse(sel_text[9:] if historic else sel_text)
                if parsed is None or parsed.player is not None:
                    raise _Fail
                if historic:
                    parsed = replace(parsed, extras=(*parsed.extras, "historic"))
                e["sel"] = parsed.key()
            elif q == "all":
                raise _Fail
        else:
            e["which"] = "that" if m["that"] else "all"
            if not m["that"]:
                e["n"] = 99  # (all of them: a pronoun for the cards moved names several, scripts.resolve_it)
        if e["to"] in ("top", "bottom") and (e.get("which") == "all" or e["n"] != 1):
            raise _Fail  # (several cards put into a library: their order is a choice not read here)
        out = [e]
        if m["rest"]:
            out.append(_rest(m["rest"]))
        return out, None
    m = _REST_THEY.fullmatch(text)  # -- refused look/cast-free (wave 3R5) --
    if m and "random" in m["rest"]:
        return [_rest(m["rest"])], None
    m = _REST_ALONE.fullmatch(text)
    if m:
        return [{"do": "rest_looked", "to": "exile"} if m["exile"] else _rest(m["rest"] or m["rest2"])], None
    if text == "shuffle that library":  # -- most-played cards III (wave 46C) -- the library the instruction before revealed from, found card or not (Polymorph, Transmogrify: 701.24a)
        return [{"do": "shuffle_library", "who": "looked_owner", "zones": []}], None
    m = _SHUFFLE_CARDS.fullmatch(text)
    if m:  # -- shuffle target cards (wave 46B) -- 701.24a: the target player's chosen graveyard cards go into their library, then it is shuffled (even with no card)
        cards = target_group(f"{m['q']} target cards from a graveyard")
        if cards is None:
            raise _Fail
        return [{"do": "shuffle_library", "who": "target", "zones": [], "cards": "target:1"}], [{"what": "player", "min": 1, "max": 1}, {**cards, "graveyard_of": 0}]
    m = _SHUFFLE.fullmatch(text)
    if m:
        who, group = ("you", None)
        if m["subj"]:
            kind, key, group = ref(m["subj"])
            who = _who(kind, key)
        zones = {"graveyard": ["graveyard"], "hand and graveyard": ["hand", "graveyard"], "hand": ["hand"]}.get(m["z"] or m["z2"] or "", [])
        return [{"do": "shuffle_library", "who": who, "zones": zones, **({"optional": True} if m["may"] else {})}], _one(group)
    # -- trigger tail (wave 16C) -- "Shuffle all creature cards from your graveyard into your library." (Barishi): those cards, then
    # the shuffle (701.24a; effects.shuffle_library with a selector)
    if text == "shuffle all cards from your graveyard into your library":  # (wave 18A: Inverter of Truth — all of it, as "your graveyard")
        return [{"do": "shuffle_library", "who": "you", "zones": ["graveyard"]}], None
    m = re.fullmatch(r"shuffle all (?P<what>[a-z ]+?) cards?(?P<of> of the chosen (?:type|color))? from your graveyard into your library", text)  # (wave 53B: "of the chosen type", Elvish Soultiller)
    sel = selectors.parse(f"{m['what']} card{m['of'] or ''} from your graveyard") if m else None
    if sel is not None and _graveyard_cards(sel.key()):
        return [{"do": "shuffle_library", "who": "you", "zones": ["graveyard"], "sel": sel.key()}], None
    found_lib = gy_to_library(text)  # -- refused zones/sized (wave 3R4) --
    if found_lib is not None:
        return found_lib
    ordered = re.fullmatch(r"put (?P<o>.+?) (?P<place>on top|on the bottom) of (?P<owner>your|their) library in any order", text)
    if ordered is not None:
        kind, key, group = ref(ordered['o'])
        sel = selectors.from_key(key) if key.startswith(selectors.PREFIX) else None
        if kind != 'target' or group is None or sel is None or not sel.card or sel.zones != ('graveyard',) \
                or sel.zone_owner != ('you' if ordered['owner'] == 'your' else 'opponent') \
                or (sel.zone_owner == 'opponent' and not group.get('same_graveyard')):
            raise _Fail
        return [{'do': 'to_library', 'who': _who(kind, key),
                 'place': 'top' if ordered['place'] == 'on top' else 'bottom', 'chooser': 'controller'}], _one(group)
    m = _NTH_FROM_TOP.fullmatch(text)  # -- trigger tail (wave 15B) -- "third from the top" (401.4: one card, the Nth from the top)
    if m:
        kind, key, group = ref(m["o"])
        if kind not in ("target", "self", "it", "host"):  # (wave 40B: "Put enchanted creature into its owner's library third from the top." — Shattered Ego)
            raise _Fail
        nth = ("second", "third", "fourth", "fifth", "sixth", "seventh").index(m["nth"]) + 2
        return [{"do": "to_library", "who": _who(kind, key), "place": nth}], _one(group)
    m = _TOP_SHUFFLE.fullmatch(text)
    if m:
        kind, key, group = ref(m["o"])
        if kind != "each":
            raise _Fail
        return [{"do": "to_library", "who": key, "place": "shuffle"}, *([{"do": "to_library", "who": "self", "place": "shuffle"}] if m["self"] else [])], None
    m = _TO_LIBRARY.fullmatch(text) or _SHUFFLE_INTO.fullmatch(text)
    if m:
        kind, key, group = ref(m["o"])
        if kind not in ("target", "self", "it", "them", "host") and not (kind == "each" and "place" in m.groupdict()):
            raise _Fail  # An untargeted selector is a fixed set; unspecified hand choices remain unread.
        place = "shuffle" if "place" not in m.groupdict() else ("top" if m["place"] == "on top" else "bottom")
        return [{"do": "to_library", "who": _who(kind, key), "place": place}], _one(group)
    m = _OWNER_SHUFFLES.fullmatch(text)
    if m:
        return [{"do": "to_library", "who": "self" if m["o"] == "~'s" else "it", "place": "shuffle"}], None
    m = _PLAYER_LIBRARY.fullmatch(text)  # -- static_other sweep (wave 26A) -- "That player shuffles that card into their library." (Perish the Thought)
    if m:
        where: int | str = ("second", "third", "fourth", "fifth", "sixth", "seventh").index(m["nth"]) + 2 if m["nth"] else "bottom" if m["bottom"] else "shuffle"  # (bottom: wave 44A, Vendilion Clique)
        return [{"do": "to_library", "who": "it", "place": where, **({"reveal": True} if m["rev"] else {})}], None
    m = _OWNER_CHOICE.fullmatch(text)
    if m:
        kind, key, group = ref(m["o"] or m["o2"])
        if kind not in ("target", "self", "it"):
            raise _Fail
        return [{"do": "to_library", "who": _who(kind, key), "place": "choice",
                 **({'owner_root_choice81': True} if text == "the owner of target creature puts it on their choice of the top or bottom of their library" else {})}], _one(group)
    m = _YOUR_CHOICE.fullmatch(text)
    if m:
        kind, key, group = ref(m["o"])
        if kind not in ("target", "self", "it"):
            raise _Fail
        return [{"do": "to_library", "who": _who(kind, key), "place": "choice_you"}], _one(group)
    m = _OWNER_SECOND.fullmatch(text)
    if m:
        kind, key, group = ref(m["o"] or m["o2"])
        if kind not in ("target", "self", "it"):
            raise _Fail
        return [{"do": "to_library", "who": _who(kind, key), "place": "choice_second"}], _one(group)
    m = _OWNER_SHUFFLES_TARGET.fullmatch(text)
    if m:
        kind, key, group = ref(m["o"])
        if kind != "target":
            raise _Fail
        shuffled: Effects = [{"do": "to_library", "who": _who(kind, key), "place": "shuffle"}]
        if m["reveal"]:  # (the owner as it was: 608.2h; a token's owner is the player it was put onto the battlefield under, and shuffles first)
            shuffled.append({"do": "look_top", "n": 1, "player": "it.owner", "reveal": True})
        return shuffled, _one(group)
    return None


def parse_sentence(text: str) -> tuple[Effects, Any] | None:
    try:
        found = _parse(text.strip())
    except _Fail:
        return None
    # -- damage sized by a count (wave 4E) -- an amount read per recipient player is a damage instruction's only
    # ("each player creates X tokens, where X is the number of lands they control": not read)
    if any(e.get("do") not in ("damage", "lose_life", "mill") and sized_damage.has_per_player(e) for e in found[0]):  # (wave 52D: mill)
        # -- value grammar (wave 30N) -- ... unless the recipient is one player ("You gain 1 life for each artifact that player controls",
        # "that player discards a card for each artifact they control"): the count is that player's, bound by scripts._that_players_hand
        if any(sized_damage.has_per_player(e) and not _one_recipient(e) for e in found[0]):
            return None
        return [_one_player(e) for e in found[0]], found[1]
    return found


def _one_recipient(e: dict[str, Any]) -> bool:
    who = str(e.get("who") or "you")
    return who in ("you", "event_player", "that_player") or who == "target" or who.startswith("target:")  # (that_player: scripts.resolve_it binds it)


def _one_player(v: Any) -> Any:
    """A per-recipient amount as the count of ONE named player (the marker scripts._that_players_hand binds or refuses)."""
    if isinstance(v, list):
        return [_one_player(x) for x in v]
    if not isinstance(v, dict):
        return v
    if sized_damage.PER_PLAYER in v:
        return {"for_player": "that_player", "of": v[sized_damage.PER_PLAYER]}
    return {k: _one_player(x) for k, x in v.items()}


def _one(group: dict[str, Any] | None) -> Any:
    return _out([group] if group is not None else [])


_ALL_AND_ALL = re.compile(r"^(?P<v>destroy|exile) (?P<q>all|each) (?P<a>creature|artifact|enchantment|land|planeswalker|battle)s?"
                          r"(?P<c>(?: you control| you don't control| your opponents control)?) and (?P=q) "
                          r"(?P<b>creature|artifact|enchantment|land|planeswalker|battle)s?(?P=c)$")


def _parse(text: str) -> tuple[Effects, Any]:
    if (emblem := _emblem(text)) is not None:  # -- emblems (wave 13A) --
        return emblem
    m = _CANT_ATTACK_YOU.fullmatch(text)  # (before the "for each …" rider is split off: the attack cost's)
    if m:  # -- attack restrictions (wave 32B) -- 508.1c: "Creatures can't attack you [or planeswalkers you control] this turn" ("until your next turn" is
        # the duration wrapper's: delayed.duration_clause)
        return _cant_attack_you(m)
    # -- static grants & selectors (wave 15A) -- "Destroy all creatures you don't control and all planeswalkers you don't control":
    # one group of the two kinds under one qualifier (the "or" the selectors already read), all at once (701.8)
    text = _ALL_AND_ALL.sub(lambda m: f"{m['v']} {m['q']} {m['a']}s or {m['b']}s{m['c']}", text)
    if '"' in text:  # -- quoted grants (wave 2D) -- the quoted abilities are read on their own
        return _quoted(text)
    lead = _EOT_LEAD.match(text)  # -- quoted grants (wave 2D) -- "Until end of turn, target creature gets +1/+0."
    if lead:
        return _end_of_turn_first(lead["rest"])
    # -- damage wordings (wave 6B) -- "If you control an Equipment, ~ also deals 2 damage to that creature's controller":
    # "also" says only that it adds to the instruction before it (another damage event, after it: 608.2c)
    text = re.sub(r"^(~|it) also deals ", r"\1 deals ", text)
    # "~ gets +1/+1 until end of turn and deals 1 damage to each opponent": one subject, two instructions in order
    both =re.fullmatch(r"(?P<s>~|it) (?P<g>gets [+−-]\d+/[+−-]\d+ until end of turn) and (?P<d>deals .+)", text)
    if both:
        first, second = _parse(f"{both['s']} {both['g']}"), _parse(f"{both['s']} {both['d']}")
        if first[1] is not None and second[1] is not None:
            raise _Fail  # (two targets: not this form)
        return first[0] + second[0], first[1] if first[1] is not None else second[1]
    found = _search(text) or _search_gy(text) or _looking(text)  # (_search_gy: refused zones/sized, wave 3R4)
    if found is not None:
        return found
    text, rider = _with_rider(text)
    kw_x = re.fullmatch(r"(?:you )?(?P<v>earthbend|incubate|empower Jace) [xX](?P<twice> twice)?", text) if rider is not None and rider[0] == "x" else None
    if kw_x:
        found = keyword_forms(f"{kw_x['v']} x{kw_x['twice'] or ''}")  # -- keyword actions & face-down (wave 3F) -- "earthbend X, where X is …"
        if found is None:
            raise _Fail
        return [_bind_x(e, rider[1]) for e in found[0]], found[1]
    if rider is not None and rider[0] == "x" and text == "manifest the top x cards of your library":  # -- counters (wave 41A) -- Omarthis
        found = keyword_forms(text)
        if found is None:
            raise _Fail
        return [_bind_x(e, rider[1]) for e in found[0]], found[1]
    if rider is not None and rider[0] == "x":
        # "Each opponent loses X life and you gain X life, where X is …": one X for both halves
        # (107.3c: X is defined by the text of the ability for the whole ability), so the halves
        # are read here, each with the rider, rather than split upstream with X unbound in one
        halves = re.split(_JOINER, text, maxsplit=1)
        if len(halves) != 2 and re.match(r"(?:target player|target opponent|each player|each opponent|that player) ", text):
            # (wave 4K: "target player draws X cards and loses X life": one player subject for both halves)
            halves = re.split(r" and (?=(?:draws|loses|gains|mills|discards) )", text, maxsplit=1)
        if len(halves) == 2 and not _GAIN_PUMP.fullmatch(text):  # (wave 4K: "gain trample and get +X/+X" is one instruction)
            # -- X sized by a count (wave 4K) -- "Target player draws X cards and loses X life, where X is …": the right
            # half's subject is the left's (one word "target": the same target player, 115.1)
            subj = re.match(r"^(target player|target opponent|each player|each opponent|that player) ", halves[0])
            same = subj is not None and re.match(r"^(?:draws|loses|gains|mills|discards)\b", halves[1]) is not None
            if same and subj is not None:
                halves[1] = f"{subj[1]} {halves[1]}"
            left, right = _parse(halves[0]), _parse(halves[1])
            if same and left[1] is not None and left[1] == right[1]:
                right = (right[0], None)
            if left[1] is not None and right[1] is not None:
                raise _Fail  # (two targets: not read here)
            if not all(_has_x(e) for e in (*left[0], *right[0])):
                raise _Fail  # ("… and draw a card, where X is …": which half X belongs to isn't read)
            return [_bind_x(e, rider[1]) for e in (*left[0], *right[0])], left[1] if left[1] is not None else right[1]
    # -- players ------------------------------------------------------------------------------
    m = re.fullmatch(rf"(?P<s>its controller|that creature's controller|that player) may draw (?:up to (?P<up>{AMT})|(?P<n>{AMT})) cards?", text)
    if m and rider is None:  # -- triggers (wave 19B) -- "its controller may draw a card": that player decides on resolution (608.2d)
        # (-- delayed draws (wave 51B) -- "may draw up to two cards" (Arcane Denial): that player chooses how many, 0 to N, as it resolves)
        return [{"do": "draw", "who": PLAYER_GROUPS[m["s"]], "n": _amount(m["up"] or m["n"]), **({"upto": True} if m["up"] else {"may": True})}], None
    # CR 608.2d, 115.1: the controller chooses this opponent on resolution;
    # the draw remains in the ordinary replacement pipeline.
    m = re.fullmatch(rf"an opponent draws (?P<n>{AMT}) cards?", text)
    if m and rider is None:
        return [{"do": "choose_opponent", "as": "copp"},
                {"do": "draw", "who": "ref:copp", "n": _amount(m["n"])}], None
    m = re.fullmatch(_SUBJ + rf"draws? (?:(?P<n>{AMT}) (?:additional )?cards?|cards equal to (?P<stat>.+))", text)
    if m:
        who, target = _subject(m)
        if m["stat"]:  # "draw cards equal to its power" (a trigger's object, or an earlier instruction's)
            if rider is not None:
                raise _Fail
            n = _stat(m["stat"])
            return [{"do": "draw", "who": who, "n": n}], _value_target(n, target)
        return [{"do": "draw", "who": who, "n": _apply(_amount(m["n"]), rider)}], target
    m = re.fullmatch(_SUBJ + rf"(?P<v>gains?|loses?) (?:(?P<n>{AMT}) life|life equal to (?P<stat>.+))", text)
    if m:
        who, target = _subject(m)
        verb = "gain_life" if m["v"].startswith("gain") else "lose_life"
        if m["stat"]:  # "… gains life equal to its toughness"
            if rider is not None:
                raise _Fail
            pp = sized_damage.per_player(m["stat"]) if verb == "lose_life" and who in ("each_opponent", "each_player") else None
            if pp is None and verb == "lose_life" and who == "target":  # (wave 50C: "target opponent loses life equal to the amount of life they lost this turn", Astarion: the old reading first, 'for_player')
                try:
                    _stat(m["stat"])
                except _Fail:
                    pp = sized_damage.per_player(m["stat"])
            if pp is not None:  # -- triggers (wave 17D) -- "each opponent loses life equal to the number of creatures attacking them"
                return [{"do": verb, "who": who, "n": pp}], target
            n = _stat(m["stat"])
            return [{"do": verb, "who": who, "n": n}], _value_target(n, target)
        return [{"do": verb, "who": who, "n": _apply(_amount(m["n"]), rider)}], target
    # -- activated wordings (wave 15D) -- 701.12c: "Exchange life totals with target opponent." (Magus of the Mirror), "Two target
    # players exchange life totals." (Soul Conduit): each gains or loses what it takes to equal the other's previous total
    m = re.fullmatch(r"exchange life totals with (?P<o>target opponent|target player)", text)
    if m and rider is None:
        return [{"do": "exchange_life", "who": "you", "with": "target"}], _one(target_group(m["o"]))
    # -- exchange (wave 19E) -- 701.12g: "Exchange target opponent's life total with this creature's toughness." (Tree of Perdition)
    m = re.fullmatch(r"exchange (?P<s>your|target opponent's) life total with (?:~|this creature)'s (?P<stat>power|toughness)", text)
    if m and rider is None:
        if m["s"] == "your":
            return [{"do": "exchange_life_stat", "who": "you", "stat": m["stat"]}], None
        return [{"do": "exchange_life_stat", "who": "target", "stat": m["stat"]}], _one(target_group("target opponent"))
    m = re.fullmatch(r"(?P<o>two target players) exchange life totals", text)
    if m and rider is None:
        return [{"do": "exchange_life", "who": "target"}], _one(target_group(m["o"]))
    # -- trigger tail (wave 16C) -- 119.5: "Target player's life total becomes 10." (Magister Sphinx), "Your life total becomes half your
    # starting life total, rounded up." (The Endstone): the player gains or loses the difference (effects.set_life)
    # (-- cost reductions paid with objects (wave 47C) -- "Up to one target player's life total becomes half their starting life total, rounded down." (Torgaar): 107.1a, 103.4)
    m = re.fullmatch(r"(?P<s>(?:up to one )?target (?:player|opponent)'s|your) life total becomes (?P<n>\d+|half (?:your|their) starting life total, rounded (?:up|down))", text)  # (wave 51G: "target opponent's", Sorin Markov)
    if m and rider is None:
        n = ("half_start_down" if m["n"].endswith("down") else "half_start") if m["n"][0] == "h" else int(m["n"])
        if m["s"] == "your":
            return [{"do": "set_life", "who": "you", "n": n}], None
        return [{"do": "set_life", "who": "target", "n": n}], _one(target_group("up to one target player")) if m["s"].startswith("up") else _LEGACY_TARGETS[m["s"][:-2]]
    # -- most-played cards IV (wave 51G) -- 119.5: "Each player's life total becomes the lowest life total among all players." (Repay in Kind): each higher total loses the difference
    if rider is None and text == "each player's life total becomes the lowest life total among all players":
        return [{"do": "set_life", "who": "each_player", "n": {"lowest_life": 1}}], None
    # -- most-played cards II (wave 45A) -- 701.10d: "Double target player's life total." (Beacon of Immortality), "Double your life total." (Revenge): the player
    # gains or loses what it takes to reach twice the total (119.5, effects.set_life: gain and loss events, so their triggers and replacements apply)
    m = re.fullmatch(r"double (?P<s>target player's|your) life total", text)
    if m and rider is None:
        if m["s"] == "your":
            return [{"do": "set_life", "who": "you", "n": {"times": [2, {"life": "you"}]}}], None
        return [{"do": "set_life", "who": "target", "n": {"times": [2, {"for_player": "target", "of": {"life": "you"}}]}}], _LEGACY_TARGETS["target player"]
    # -- trigger other (wave 25B) -- 119.5: "Your life total becomes the number of creatures you control" (Touch of the Eternal), "… the number of
    # charge counters on this artifact" (Eternity Vessel), "… the total toughness of creatures you control" (Loxodon Lifechanter): a counted amount
    m = re.fullmatch(r"(?P<s>target player's|your) life total becomes (?:equal to )?(?P<v>the (?:number|total) .+)", text)
    if m and rider is None and (v := values.parse_count(m["v"], it="it")) is not None and "'it'" not in str(v):
        if m["s"] == "your":
            return [{"do": "set_life", "who": "you", "n": v}], None
        return [{"do": "set_life", "who": "target", "n": v}], _LEGACY_TARGETS["target player"]
    # -- attached events (wave 8D) -- "that player loses half their life, rounded up" (119.3; half of the life total as it is
    # when the instruction is carried out, 107.1a; effects.lose_life)
    m = re.fullmatch(_SUBJ + r"loses? (?P<f>half|a third of) (?:their|your) life, rounded (?P<r>up|down)", text)
    if m and rider is None and (m["s"] in (None, "you")) == (text.endswith("your life, rounded " + m["r"])):
        who, target = _subject(m)  # (wave 16C: "a third of their life, rounded up", Dire Fleet Ravager)
        return [{"do": "lose_life", "who": who, "n": 0, "half": m["r"], **({"of": 3} if m["f"] != "half" else {})}], target
    m = re.fullmatch(_SUBJ + rf"discards? (?P<n>{AMT}) cards? at random", text)  # -- refused zones/sized (wave 3R4) --
    if m:  # 701.9b: the cards are chosen at random (effects.discard: the table picks; the move records which)
        who, target = _subject(m)
        return [{"do": "discard", "who": who, "n": _apply(_amount(m["n"]), rider), "random": True}], target
    # -- "this way" outcomes (wave 4A) -- "discard your hand" / "each player discards their hand" (701.9a: every card in
    # it; one choice-free discard, all at once, 101.4)
    m = re.fullmatch(_SUBJ + r"discards? (?:all the cards in )?(?:(?P<your>your)|their) hand", text)
    if m and rider is None and (m["your"] is not None) == (m["s"] in (None, "you")):
        who, target = _subject(m)
        return [{"do": "discard", "who": who, "n": 0, "all": True}], target
    # -- trigger tail (wave 15B) -- "discard up to two cards" / "discard any number of cards": the player chooses how many (701.9a)
    m = re.fullmatch(_SUBJ + rf"discards? (?:up to (?P<n>{AMT})|(?P<any>any number of)) cards?", text)
    if m and rider is None:
        who, target = _subject(m)
        return [{"do": "discard", "who": who, "n": 0 if m["any"] else _amount(m["n"]), "upto": True}], target
    # -- if you do (wave 21C) -- 701.9a: "discard a creature card" / "discard any number of creature cards": only cards of that kind
    # may be chosen (and as many as can be, if fewer match)
    m = re.fullmatch(_SUBJ + rf"discards? (?:(?P<one>an?)|up to (?P<up>{AMT})|(?P<any>any number of)|(?P<n>{AMT})) (?P<sel>[a-z -]+?) cards?", text)
    if m and rider is None and m["sel"] != "random":
        sel = selectors.parse(m["sel"] + " card")
        if sel is not None and sel.card and not sel.zones and sel.player is None:
            who, target = _subject(m)
            n = 1 if m["one"] else 0 if m["any"] else _amount(m["up"] or m["n"])
            return [{"do": "discard", "who": who, "n": n, "sel": sel.key(), **({"upto": True} if m["any"] or m["up"] else {})}], target
    # -- if you do (wave 15C) -- "target player mills half their library, rounded up" (107.1a: half of the cards in the
    # library as the instruction is carried out; 701.17a; effects.mill)
    m = re.fullmatch(_SUBJ + r"mills? half (?:(?P<your>your)|their) library, rounded (?P<r>up|down)", text)
    if m and rider is None and (m["your"] is not None) == (m["s"] in (None, "you")):
        who, target = _subject(m)
        return [{"do": "mill", "who": who, "n": 0, "half": m["r"]}], target
    # -- trigger other (wave 39A) -- "target opponent discards half the cards in their hand, rounded down" (Lord Xander): 107.1a, effects._discard_next
    m = re.fullmatch(_SUBJ + r"discards? half the cards in (?P<your>your|their) hand, rounded (?P<r>up|down)", text)
    if m and rider is None and (m["your"] == "your") == (m["s"] in (None, "you")):
        who, target = _subject(m)
        return [{"do": "discard", "who": who, "n": 0, "half": m["r"]}], target
    m = re.fullmatch(_SUBJ + rf"(?P<v>discards?|mills?) (?:(?P<n>{AMT}) cards?|cards equal to (?P<stat>.+))", text)
    if m:
        who, target = _subject(m)
        verb = "discard" if m["v"].startswith("discard") else "mill"
        if m["stat"]:
            if rider is not None:
                raise _Fail
            # -- activated other (wave 52D) -- "Each opponent mills cards equal to the number of cards in their hand." (Folio of Fancies): each one's own count (608.2h)
            if verb == "mill" and who in ("each_opponent", "each_player") and (pp := sized_damage.per_player(m["stat"])) is not None:
                return [{"do": verb, "who": who, "n": pp}], target
            n = _stat(m["stat"])
            return [{"do": verb, "who": who, "n": n}], _value_target(n, target)
        return [{"do": verb, "who": who, "n": _apply(_amount(m["n"]), rider)}], target
    # -- most-played modal spells (wave 50I) -- 701.22a, 701.25a: "Target player scries X, then draws a card." (Kozilek's Command): the named player looks (effects._look)
    m = re.fullmatch(rf"(?P<s>target player|target opponent) (?P<v>scries|surveils) (?P<n>{AMT})", text)
    if m and rider is None:
        who, target = _subject(m)
        return [{"do": m["v"][:-1] if m["v"] == "surveils" else "scry", "who": who, "n": _amount(m["n"])}], target
    # -- commanders (wave 50I) -- "Target player returns an artifact, instant, or sorcery card from their graveyard to their hand." (Donnie & April): that player chooses the card
    # from their own graveyard (608.2d), as "return a … card from your graveyard to your hand" reads for its controller (effects.return_choice, "chooser")
    m = re.fullmatch(r"(?P<s>target player|target opponent) returns (?P<rest>(?:an?|up to \w+) .+? cards? from their graveyard to their hand)", text)
    if m and rider is None:
        found = parse_sentence("return " + m["rest"].replace("their graveyard to their hand", "your graveyard to your hand"))
        if found is not None and found[1] is None and len(found[0]) == 1 and found[0][0]["do"] == "return_choice" and found[0][0]["to"] == "hand" \
                and not found[0][0].get("random") and not found[0][0].get("optional") and not found[0][0].get("who"):
            return [{**found[0][0], "chooser": "target"}], _LEGACY_TARGETS[m["s"]]
    m = re.fullmatch(_SUBJ + rf"sacrifices? (?P<n>{AMT}|another) (?P<sel>.+?)(?: of their choice)?", text)
    if m and rider is None:
        who, target = _subject(m)
        word, noun = m["n"], m["sel"]
        if word == "another":  # -- X sized by a count (wave 19F) -- "sacrifice another creature": one you control, not the source (701.21a)
            if who != "you":
                raise _Fail
            word, noun = "one", "another " + noun
        # -- damage wordings (wave 6B) -- "Each opponent sacrifices a creature with the greatest power among creatures
        # that player controls" (Crackling Doom): among the sacrificing player's own creatures (ties: their choice)
        sel = _greatest_own(noun) or selectors.parse(noun)  # (wave 26A: any stat, "creature or planeswalker", "among permanents they control")
        if sel is None or sel.player is not None:
            raise _Fail
        return [{"do": "sacrifice_choice", "who": who, "sel": sel.key(), "n": _amount(word)}], target
    # -- triggers (wave 19B) -- "Sacrifice any number of other permanents." (God-Eternal Bontu): the player's own choice, none allowed
    m = re.fullmatch(r"sacrifice any number of (?P<sel>.+)", text)
    if m and rider is None:
        phrase = m["sel"].replace(", and/or ", ", or ").replace(" and/or ", " or ")
        sel = selectors.parse(phrase) or selectors.parse_either(phrase)
        if sel is None or sel.player is not None or sel.controller not in (None, "you") or sel.zones != ("battlefield",):
            raise _Fail
        if any(selectors.from_key(k).controller not in (None, "you") for k in sel.either):
            raise _Fail
        return [{"do": "sacrifice_choice", "who": "you", "sel": sel.key(), "n": 10**6, "upto": True}], None
    # -- trigger other (wave 39A) -- "Sacrifice half the non-Demon permanents you control, rounded up." (Rakdos the Defiler): 107.1a, counted as it resolves
    m = re.fullmatch(r"sacrifice half the (?P<sel>.+?) you control, rounded (?P<r>up|down)", text)
    if m and rider is None:
        sel = selectors.parse(m["sel"])
        if sel is None or sel.player is not None or sel.controller is not None or sel.zones != ("battlefield",):
            raise _Fail
        return [{"do": "sacrifice_choice", "who": "you", "sel": sel.key(),
                 "n": {"half": {"count": selectors.replace(sel, controller="you").key()}, "round": m["r"]}}], None
    # -- trigger tail (wave 16C) -- "Exile a land you control." (Wormfang Newt, Turtle): you choose it as this resolves (608.2d),
    # then it's exiled (no sacrifice, 701.21a: sacrificing is putting into a graveyard); linked for "the exiled card" (607.2a)
    m = re.fullmatch(r"exile (?P<n>a|an|one|two|three|another|any number of) (?P<sel>(?!target )[A-Za-z -]+? you control)(?P<until> until ~ leaves the battlefield)?", text)
    if m and rider is None:
        return exile_own(m["n"], m["sel"], bool(m["until"]))
    # -- static grants & selectors (wave 15A) -- "Each player sacrifices all permanents they control that are one or more colors"
    # (701.21a: a player sacrifices only what they control; every match goes at once, 101.4: sacrifice_choice with no choice left)
    m = re.fullmatch(_SUBJ + r"sacrifices? all (?P<sel>.+?)(?: (?:they|you) control)?(?P<tail> that .+)?", text)
    if m and rider is None and not (m["tail"] and re.search(r"\b(?:they|you) control\b", m["tail"])):
        who, target = _subject(m)
        sel = selectors.parse(m["sel"] + (m["tail"] or ""))
        if sel is None or sel.player is not None or sel.controller is not None or sel.zones != ("battlefield",):
            raise _Fail
        return [{"do": "sacrifice_choice", "who": who, "sel": sel.key(), "n": 10**6}], target
    # -- grammar (wave 11C) -- "that player loses the game", "you lose the game", "target player loses the game" (104.3e)
    m = re.fullmatch(_SUBJ + r"loses? the game", text)
    if m and rider is None:
        who, target = _subject(m)
        return [{"do": "lose_game", "who": who}], target
    found = player_counters(text, rider) or (designation_instruction(text) if rider is None else None)  # (wave 3E)
    if found is not None:
        return found
    # -- damage ---------------------------------------------------------------------------------
    # -- sized amounts (wave 3D) -- "that creature deals damage equal to its power": the pronoun's creature (as "it")
    text = re.sub(r"^that creature deals ", "it deals ", text)
    if text in ("exile that card from your graveyard", "exile that card from their graveyard") and rider is None:  # (wave 17D: Necropotence)
        # -- review 32 -- the discarded card, only while it is in the graveyard: one a replacement put elsewhere (madness 702.35a, Rest in
        # Peace 614.1a) can't be exiled from there, so nothing is exiled, linked or "done" (118.12: Containment Construct, Bag of Holding)
        return [{"do": "exile", "who": "it", "from_zone": "graveyard"}], None
    # -- damage sized by a count (wave 4E) -- "Whenever Smaug attacks, he deals …": a named character's pronoun is the
    # card itself (its power: "his power"); "this enchantment deals … equal to the number of verse counters on it"
    text = re.sub(r"^(?:he|she) deals ", "~ deals ", text)
    if text.startswith("~ deals "):
        text = re.sub(r"\b(?:his|her) (power|toughness)\b", r"~'s \1", text)
    found = _sized_damage_forms(text, rider)
    if found is not None:
        return found
    # -- end damage sized by a count (wave 4E) --
    src: dict[str, Any] = {"src": "it"} if text.startswith("it ") else {}
    m = re.fullmatch(r"~ deals damage equal to (?:its|~'s) power divided as you choose among (?P<o>.+)", text)
    if m:  # -- damage sized by a count (wave 34D) -- 601.2d, 608.2d: its power as it is when the ability goes on the stack, or as it last existed (Orca)
        if rider is not None:
            raise _Fail
        return [{"do": "damage", "who": "target", "n": {"divided": 0}}], _divided(m["o"], "damage", {"power": "self"})
    m = re.fullmatch(rf"(?P<src>~|it) deals (?P<n>{AMT}) damage divided as you choose among (?P<o>.+)", text)
    if m:  # 601.2d: the division is announced as the spell is cast (each target gets at least 1)
        if rider is not None:
            raise _Fail
        return [{"do": "damage", "who": "target", "n": {"divided": 0}, **src}], _divided(m["o"], "damage", _amount(m["n"]))
    m = re.fullmatch(rf"(?P<src>~|it) deals (?P<n>{AMT}) damage to (?P<o1>.+?)(?:, (?P<k>{AMT}) damage to (?P<o3>.+?),)? and (?P<m>{AMT}) damage to (?P<o2>.+)", text)
    # -- damage sized by a count (wave 4E) -- "~ deals X damage to target creature and X damage to you, where X is …" (one X for
    # both: 107.3c), "… and X damage to itself" (~ itself: the source)
    if m and (rider is None or (rider[0] == "x" and m["n"].lower() == "x" == m["m"].lower())):
        effects: Effects = []
        groups: list[dict[str, Any]] = []
        for o, n in ((m["o1"], m["n"]), *(((m["o3"], m["k"]),) if m["k"] else ()), (m["o2"], m["m"])):  # (wave 50E: three, Cone of Flame)
            controlled = _that_player_controls(o) if groups else None  # -- damage wordings (wave 6B) -- "… and 1 damage
            # to each creature that player controls" (Radiating Lightning): the first part's target player's
            whos, parts = ([controlled], []) if controlled is not None else _objects("~" if o == "itself" and m["src"] == "~" else o)
            if len(whos) != 1:
                raise _Fail
            effects.append({"do": "damage", "who": whos[0] if not parts else ("target" if not groups else f"target:{len(groups)}"),
                            "n": _apply(_amount(n), rider), **src})
            groups += parts
        for joined in effects[:-1]:
            joined["with_next"] = True  # (dealt at once: one damage event)
        _check_per_player(effects, groups)  # -- damage sized by a count (wave 4E) --
        return effects, _out(groups)
    m = re.fullmatch(rf"(?P<src>~|it) deals (?:(?P<n>{AMT}) damage|damage equal to (?P<stat>.+?)) to (?P<o>.+)", text)
    if m is None:  # "~ deals damage to target creature equal to the number of lands you control" (the same, worded after)
        m = re.fullmatch(r"(?P<src>~|it) deals (?P<n>)damage to (?P<o>.+?) equal to (?P<stat>.+)", text)
    if m:
        if m["stat"] and rider is not None:
            raise _Fail
        # "~ deals damage equal to its power": its own (the subject's); "it deals … its power": it's
        # -- damage sized by a count (wave 4E) -- or an amount read for each player dealt damage ("… to each player equal to
        # the number of lands that player controls"): app/rules/sized_damage.py
        per_player = sized_damage.per_player(m["stat"]) if m["stat"] else None
        try:
            n = _stat(m["stat"], "self" if m["src"] == "~" else "it") if m["stat"] else _apply(_amount(m["n"]), rider)
        except _Fail:
            if per_player is None:
                raise
            n = per_player
        if per_player is not None and re.search(r"\beach (?:player|opponent)\b|\beach of your opponents\b", m["o"]):
            n = per_player  # (each recipient's own count, not one player's)
        # -- end damage sized by a count (wave 4E) --
        if _wants_target_player(n):
            raise _Fail  # (a second target the damage sentence would have to declare: not read)
        effects = []
        groups = []
        # -- sized amounts (wave 3D) -- "each opponent and each creature and planeswalker they control": the opponents'
        # (selectors read "or" for a list of types), and "each other player" is every opponent (102.2)
        recipients = m["o"].replace("each other player", "each opponent")
        if "any other target" in recipients and src:
            raise _Fail  # -- damage sized by a count (wave 34D) -- "it deals … to any other target": other than which creature? (scripts._add_groups reads only the source's own)
        if recipients == "itself" and m["src"] == "~":  # -- chosen player (wave 4J) -- "~ deals 1 damage to itself" (Stuffy Doll)
            recipients = "~"
        recipients = re.sub(r"^(each opponent and each .+?) they control$", r"\1 your opponents control", recipients)
        recipients = re.sub(r"^(target (?:player|opponent) and each .+?) they control$", r"\1 that player controls", recipients)  # (wave 49B: "target opponent and each creature they control", The Great Work)
        recipients = re.sub(r"(creatures?) and (planeswalkers?|battles?) (?=you control|your opponents control|an opponent controls)",
                            r"\1 or \2 ", recipients)
        # -- damage sized by a count (wave 4E) -- "each creature and planeswalker you don't control / that player controls"
        recipients = re.sub(r"(creatures?) and (planeswalkers?|battles?) (?=you don't control|that player controls)",
                            r"\1 or \2 ", recipients)
        for part in re.split(r" and (?=each |you$)|" + _AND_TARGET, recipients):
            if re.fullmatch(r"the player or planeswalker (?:it's|that creature is) attacking", part):  # -- most-played cards II (wave 45A) -- 508.5 (defending.attacked)
                effects.append({"do": "damage", "who": "attacked", "n": n, **src})
                continue
            if part == "each other opponent":  # -- sized amounts (wave 3D) -- the opponents besides the one the event named
                effects.append({"do": "damage", "who": "each_other_opponent", "n": n, **src})
                continue
            controlled = target_controls(part, groups) or _that_player_controls(part)  # -- damage sized by a count (wave 4E) --
            if controlled is not None:
                effects.append({"do": "damage", "who": controlled, "n": n, **src})
                continue
            kind, key, group = ref(part)
            who = _who(kind, key)
            if group is not None:
                who = "target" if not groups else f"target:{len(groups)}"
                groups.append(group)
            effects.append({"do": "damage", "who": who, "n": n, **src})
        for joined in effects[:-1]:  # one sentence: one simultaneous damage event (app/rules/effects.damage)
            joined["with_next"] = True
        _check_per_player(effects, groups)  # -- damage sized by a count (wave 4E) --
        return effects, _out(groups)
    found = _bite_many(text)  # -- as long as (wave 9B) --
    if found is not None:
        return found
    found = _bite(text)  # -- temporary grants & riders (agent G) --  "target creature you control deals damage equal to its power to …"
    if found is not None:
        if rider is not None:
            raise _Fail
        return found
    if rider is not None and not text.startswith(("put ", "remove ")) and not re.search(r"\bgets? [+\-−]", text):
        raise _Fail
    # -- objects --------------------------------------------------------------------------------
    found = _target_forms(text)  # -- target forms (agent T) --
    if found is not None:
        return found
    # -- counters (wave 7C) -- "Exile ~ with three time counters on it." (the printed spell half of a suspend card, 702.62b)
    m = re.fullmatch(rf"exile ~ with (?P<n>{AMT}) time counters on it", text)
    if m and rider is None:
        n = _amount(m["n"])
        if isinstance(n, int):
            return [{"do": "spell_self_move", "to": "exile", "counters": {"time": n}}], None
    # -- end counters (wave 7C) --
    m = re.fullmatch(r"(?P<o>.+?) phases? out", text)  # -- phasing (wave 13D) -- 702.26b: "Target creature phases out."
    if m and not re.search(r"\b(?:until|unless|if|when|whenever|at|and|then|can't|for as long as)\b", m["o"]):
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "phase_out", "who": _who(kind, key)}], _one(group)
    if (found := exile_choice(text)) is not None:
        return found
    m = re.fullmatch(r"(?P<v>destroy|exile|tap|untap|airbend) (?P<o>.+)", text)  # (-- trigger other (wave 25B) -- airbend 701.65: app/rules/airbend.py)
    if m and not (m["v"] == "airbend" and re.search(r"\bspells?\b", m["o"])):
        # -- trigger damage (wave 39B) -- "untap it and all Samurai you control" (Godo): no target in either part, so one instruction for each, in the
        # order given (608.2c); "it" is bound like any pronoun
        if (found_both := _tap_it_and_all(m["v"], m["o"])) is not None:
            return found_both
        if m["v"] == "destroy" and (tc := re.fullmatch(r"(?:all|each) creatures with (?P<w>power|toughness) (?P<d>greater|less) than (?P<t>target|that) creature's (?P<r>power|toughness)", m["o"])):
            # -- most-played cards II (wave 45A) -- "Destroy all creatures with power greater than target creature's power." (Fell the Mighty): the target is named inside the
            # selector; "that creature's" (Mandate of Abaddon) is the one an earlier sentence chose (scripts._event_refs_ok refuses it when no target was chosen)
            sel = selectors.parse(f"creatures with {tc['w']} {tc['d']} than target creature's {tc['r']}")
            if sel is None:
                raise _Fail
            return [{"do": "destroy", "who": sel.key()}], _one(target_group("target creature")) if tc["t"] == "target" else None
        whos, groups = _objects(m["o"])
        if len(whos) > 1:  # "destroy target artifact and target enchantment": one group each (115.3)
            # -- activated other (wave 34B) -- "Exile ~ and target creature without flying that's attacking you." (Hunting Kavu), "Exile Mangara and target
            # permanent": the source is no target (115.1), so it has no group of its own; one instruction names both (608.2c: carried out in the order given)
            if len(groups) != len(whos) and not (whos[0] == "self" and len(groups) == len(whos) - 1 and all(w.startswith("target") for w in whos[1:])):
                raise _Fail
            return [{"do": m["v"], "who": w} for w in whos], _out(groups)
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        if kind == "each" and m["v"] == "destroy":
            return [{"do": "destroy", "who": key}], None
        return [{"do": m["v"], "who": _who(kind, key)}], _one(group)
    # -- static wordings (wave 6E) -- "It must be blocked this turn if able." (Enlarge): a requirement (509.1c)
    m = re.fullmatch(r"(?P<o>.+?) must be blocked (?:each combat )?this turn if able", text)  # (-- block effects (wave 30P) -- Anzrag: "each combat this turn" is this turn's every combat)
    if m and not _PUMP.fullmatch(text):
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "restrict", "who": _who(kind, key), "rules": ["must_be_blocked"]}], _one(group)
    # -- lure (wave 12B) -- "All creatures able to block target creature this turn do so." (509.1c: rule "lure" on it)
    m = re.fullmatch(r"all creatures able to block (?P<o>target creature|it|this creature|~)(?: this turn)? do so", text)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "restrict", "who": _who(kind, key), "rules": ["lure"]}], _one(group)
    # -- evasion (wave 30P) -- "… can't be blocked this combat" (Ma Chao, Yuan Shao's Infantry): the requirement or restriction ends with the combat
    # (a turn may have several, 500.8); "~ and up to one other target creature can't be blocked this turn" (Martha Jones, Lockjaw): one effect each
    m = re.fullmatch(r"(?P<o>.+?) can't (?P<r>attack or block|block|attack|be blocked) this (?P<d>turn|combat)", text)
    if m and not _PUMP.fullmatch(text) and (m["d"] == "turn" or m["r"] in ("block", "be blocked")):  # (agent G: "… gets +2/+2 until end of turn and can't be blocked …" is a pump's rider)
        for_combat = {"duration": "end_of_combat"} if m["d"] == "combat" else {}
        whos, groups = _objects(m["o"])
        if len(whos) > 1:
            if not all(w == "self" or w.startswith("target") for w in whos):
                raise _Fail
            return [{"do": "restrict", "who": w, "rules": RESTRICTIONS[m["r"]], **for_combat} for w in whos], _out(groups)
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "restrict", "who": _who(kind, key), "rules": RESTRICTIONS[m["r"]], **for_combat}], _one(group)
    # -- prohibitions (wave 22B) -- 602.5: "Its activated abilities can't be activated this turn." (Koma, Deadlock Trap): the rule "cant_activate"
    # (mana abilities too, as for detain), on the object the sentence is about, until end of turn
    m = re.fullmatch(r"(?P<o>it|that creature|that permanent)'s activated abilities can't be activated this turn|"
                     r"(?P<o2>its|their) activated abilities can't be activated this turn", text)
    if m:
        kind, key, group = ref("it" if m["o2"] else m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "restrict", "who": _who(kind, key), "rules": ["cant_activate"]}], _one(group)
    # -- no combat damage (wave 19E) -- "If you do, this creature assigns no combat damage this turn." (510.1a: it assigns 0; read by
    # combat._assigns; a rule-modifying effect, not prevention: lifelink, deathtouch and damage replacements see no damage at all)
    m = re.fullmatch(r"(?P<o>~|it|this creature|that creature|target creature|enchanted creature|equipped creature) assigns no combat damage this turn", text)  # (wave 53C: Laccolith Rig)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "restrict", "who": _who(kind, key), "rules": ["assign_none"]}], _one(group)
    # -- multiple blocks (wave 13B) -- "Target creature can block any number of creatures this turn." (509.1a: block_extra)
    m = re.fullmatch(r"(?P<o>.+?) (?P<r>can block (?:an additional creature|an additional \w+ creatures|up to \w+ additional creatures"
                     r"|any number of creatures)) this turn", text)
    if m and not _PUMP.fullmatch(text):
        from app.rules.statics import _rule

        kind, key, group = ref(m["o"])
        rules = _rule(m["r"])
        if kind == "players" or not rules:
            raise _Fail
        return [{"do": "restrict", "who": _who(kind, key), "rules": rules}], _one(group)
    # -- token & pump wordings (wave 6C) -- "This creature can attack this turn as though it didn't have defender." (702.3b:
    # the defender's restriction doesn't apply to it this turn; read by combat.attack_problem)
    m = re.fullmatch(r"(?P<o>.+?) can attack this turn as though (?:it|they) didn't have defender", text)
    if m and not _PUMP.fullmatch(text):
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "restrict", "who": _who(kind, key), "rules": ["attack_despite_defender"]}], _one(group)
    # -- activated other (wave 21E) -- 510.1a: "assigns combat damage equal to its toughness rather than its power this turn"
    m = re.fullmatch(r"(?P<o>.+?) assigns combat damage equal to its toughness rather than its power this turn", text)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "restrict", "who": _who(kind, key), "rules": ["assign_toughness"]}], _one(group)
    # -- recursion & tutors (wave 4M) -- "Return all artifact and enchantment cards from your graveyard to the battlefield"
    # (Brilliant Restoration): every card that is any of the types named (the "and" lists the kinds, as "or" would)
    text = re.sub(r"^return all ((?:[a-z]+, )*[a-z]+),? and ([a-z]+) cards (?=(?:with [^,]+ )?from your graveyard to )",
                  lambda m: "return all " + " or ".join([*m[1].split(", "), m[2]]) + " cards ", text)
    # -- graveyard history (wave 36A) -- the destination first, because the cards are described at length: "Return to your hand all creature
    # cards in your graveyard that were put there from anywhere this turn." (Garna), "return to the battlefield target creature card in your
    # graveyard that …" (Moira) say what "Return all … to your hand" / "return target … to the battlefield" do
    text = re.sub(r"^(?P<may>you may )?return to (?P<d>your hand|the battlefield) (?P<o>(?:all|target|up to \w+ target|another target|each) "
                  r"(?!.* (?:under|tapped|attacking|face down|with(?! (?:equal or )?lesser\b)|attached)\b).+)$", lambda m: f"{m['may'] or ''}return {m['o']} to {m['d']}", text)
    found = reanimation_forms(text)  # -- reanimation (wave 3R) --
    if found is not None:
        return found
    found = control_forms(text)  # -- control (wave 3K) --
    if found is not None:
        return found
    found = keyword_forms(text)  # -- keyword actions & face-down (wave 3F) --
    if found is not None:
        return found
    if text in ("return ~ to its owner's hand", "return it to its owner's hand"):
        return [{"do": "bounce", "who": "self" if text.startswith("return ~") else "it"}], None
    # -- activated sweep (wave 17B) -- "Put your commander into your hand from the command zone." (Command Beacon, Netherborn Altar): one
    # of your commanders there (a partner pair: you choose, 608.2d); "Put all commanders you own from the command zone and from your
    # graveyard into your hand." (Campfire). Its owner may put it into the command zone instead (903.9b: engine.ask_903_9b_first)
    if text == "put your commander into your hand from the command zone":
        key = selectors.Selector(commander=True, owner="you", zones=("command",), card=True).key()
        return [{"do": "return_choice", "to": "hand", "sel": key, "n": 1, "label": "your commander"}], None
    if text == "put all commanders you own from the command zone and from your graveyard into your hand":
        key = selectors.Selector(commander=True, owner="you", zones=("command", "graveyard"), card=True).key()
        return [{"do": "return_card", "who": key, "to": "hand", "under": "owner"}], None
    m = re.fullmatch(r"put (?P<o>it|them|that card|those cards) onto the battlefield(?P<rest>(?: tapped)?(?: under your control)?)", text)
    if m:  # -- triggers (wave 19B) -- "put that card onto the battlefield": a card in a graveyard (the trigger's), as "return it" reads it
        found = _parse(f"return {m['o']} to the battlefield{m['rest']}")
        return [{**e, "put": True} for e in found[0]], found[1]  # (scripts refuses it unless "it" is the trigger event's card)
    m = re.fullmatch(r"return (?P<o>.+?) to (?P<d>its owner's hand|their owners' hands|their owner's hand|their hand|your hand|"
                     r"the battlefield(?P<t> tapped(?P<atk> and attacking)?)?(?: under (?P<u>your|its owner's|their owners') control)?"
                     r"(?P<t2> tapped(?P<atk2> and attacking)?)?"  # (-- trigger other (wave 41C) -- 508.4: "… under your control tapped and attacking", The Neutrinos)
                     r"(?: with (?:(?:an?|one) |(?P<cn>two|three|four|five) )(?P<ck>[+-]\d+/[+-]\d+|[a-z]+) counters? on it)?)", text)  # (wave 19D: N counters)
    if m:
        # -- activated sweep (wave 17B) -- "Return target commander you own from the battlefield to your hand." (Sanctum of Eternity)
        kind, key, group = ref(re.sub(r" from the battlefield$", "", m["o"]) if m["d"] == "your hand" else m["o"])
        if kind in ("players", "self"):
            raise _Fail
        sel = selectors.from_key(key) if key.startswith(selectors.PREFIX) else None
        # a pronoun names cards an earlier instruction put in a graveyard or exile (400.7j:
        # "Exile target creature. Return it to the battlefield …" finds it there)
        from_zone = (sel is not None and sel.card) or kind in ("it", "them")
        who = _who(kind, key)
        target = _one(group)
        if m["d"].startswith("the battlefield"):
            if not from_zone:
                raise _Fail  # (blink wordings are templated elsewhere)
            if m["ck"] and m["ck"] in values.UNMODELED_COUNTERS:
                raise _Fail
            # (-- quoted grants, wave 2D -- "… with a +1/+1 counter on it": it enters with it, 122.6)
            if (m["atk"] or m["atk2"]) and (kind not in ("it", "them") or m["u"] not in (None, "your")):
                raise _Fail  # -- trigger other (wave 41C) -- 508.4: only what an earlier instruction moved, under your control (506.3b: not read under its owner's)
            return [{"do": "return_card", "who": who, "to": "battlefield", "tapped": bool(m["t"] or m["t2"]),
                     "under": "owner" if m["u"] and m["u"] != "your" else "you",  # (110.2a: unless it says otherwise)
                     **({"attacking": True} if m["atk"] or m["atk2"] else {}),
                     **({"counter": m["ck"]} if m["ck"] else {}), **({"counter_n": values.NUMBERS[m["cn"]]} if m["cn"] else {})}], target
        if from_zone and kind not in ("it", "them"):
            return [{"do": "return_card", "who": who, "to": "hand", "under": "you" if m["d"] == "your hand" else "owner"}], target
        if m["d"] == "your hand" and kind not in ("it", "them") and (sel is None or sel.owner != "you"):
            raise _Fail  # (wave 13E: 400.3 a card goes to its owner's hand, "your" or not: "you own" makes the two the same)
        return [{"do": "bounce", "who": who}], target
    m = re.fullmatch(rf"distribute (?P<n>{AMT}) (?P<k>[+-]\d+/[+-]\d+|[a-z]+) counters among (?P<o>.+)", text)
    if m and rider is None:  # 601.2d: counters divided among the targets as the ability is put on the stack
        if m["k"] in values.UNMODELED_COUNTERS:
            raise _Fail
        return [{"do": "add_counters", "who": "target", "kind": m["k"], "n": {"divided": 0}}], \
            _divided(m["o"], "counters", _amount(m["n"]))
    # -- counters (wave 5H) -- "When ~ dies, put its counters on target creature you control", "Whenever a creature you
    # control leaves the battlefield, if it had counters on it, put those counters on ~": the same number of each kind
    # the object had as it last existed (122.8) — a placeholder "it" bound by scripts.resolve_it only to an object that
    # left (otherwise it would be a move, 122.5: refused)
    # "put a +1/+1 counter on each creature you control and a loyalty counter on each planeswalker you control"
    # (Brokers Ascendancy): one instruction, all at once (122.6)
    m = re.fullmatch(rf"put (?P<n>{AMT}) (?P<k>[+-]\d+/[+-]\d+|[a-z]+) counters? on (?P<o>each [^,]+?) and "
                     rf"(?P<n2>{AMT}) (?P<k2>[+-]\d+/[+-]\d+|[a-z]+) counters? on (?P<o2>each .+)", text)
    if m and rider is None and "target" not in text:
        if m["k"] in values.UNMODELED_COUNTERS or m["k2"] in values.UNMODELED_COUNTERS:
            raise _Fail
        k1, key1, _g1 = ref(m["o"])
        k2, key2, _g2 = ref(m["o2"])
        if "players" in (k1, k2):
            raise _Fail
        return [{"do": "add_counters", "who": _who(k1, key1), "kind": m["k"], "n": _amount(m["n"]),
                 "also": [{"kind": m["k2"], "n": _amount(m["n2"]), "who": _who(k2, key2)}]}], None
    # -- suspend granted (wave 24C) -- "It gains suspend." (app/rules/suspend_grants.py)
    if text in ("it gains suspend", "that card gains suspend") and rider is None:
        return [{"do": "suspend_mark", "who": "it"}], None
    if rider is None and (m := re.fullmatch(rf"suspend (?P<w>that card|it) with (?P<n>{AMT}) time counters", text)) is not None:
        return [{"do": "suspend_found", "n": _amount(m["n"]), **({"who": "it"} if m["w"] == "it" else {})}], None  # (app/rules/suspend_grants.py: the card an exile-until found / the exiled card)
    # -- cast riders (wave 38C) -- 702.170c: "It becomes plotted." (the card an instruction exiled: app/rules/resolve_exile.py)
    if text in ("it becomes plotted", "that card becomes plotted") and rider is None:
        return [{"do": "plotted", "who": "it"}], None
    from app.rules import counter_choice_effects

    if rider is None and (counter_options := counter_choice_effects.parse_sentence(text)) is not None:
        return counter_options
    if rider is None and (counter_copy := re.fullmatch(r"put a copy of ~'s counters on (?P<who>.+)", text)) is not None:
        counter_kind, counter_key, counter_group = ('each', 'event', None) if counter_copy['who'] == 'the creature that entered' else ref(counter_copy['who'])
        if counter_kind == 'players':
            raise _Fail
        return [{'do': 'lki_counters', 'from': 'self', 'who': _who(counter_kind, counter_key)}], _one(counter_group)
    if rider is None and (vanishing_gain := re.fullmatch(r"(?P<who>it|~|that creature) gains? vanishing", text)) is not None:
        vanish_kind, vanish_key, vanish_group = ref(vanishing_gain['who'])
        return [{'do':'grant', 'who':_who(vanish_kind, vanish_key), 'keywords':[], 'abilities':['Vanishing'], 'duration':'permanent'}], _one(vanish_group)
    # -- counter kinds (wave 24C) -- app/rules/counter_kinds.py
    found = _counter_kinds(text, rider)
    if found is not None:
        return found
    # -- moving counters (wave 12A) -- "move all counters from ~ onto target creature" (The Ozolith), graft's "move a +1/+1
    # counter from ~ onto that creature" (702.58a), "move a counter from target permanent you control onto a second target
    # permanent" (Nesting Grounds), "move any number of +1/+1 counters from ~ onto another target creature" (122.5:
    # app/rules/counter_moves.py); "a second target" is another word "target" (115.3)
    distribution = re.fullmatch(r"move any number of (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters from ~ onto other creatures", text)
    if distribution is not None and rider is None and distribution["kind"] not in values.UNMODELED_COUNTERS:
        sel = selectors.parse("creatures")
        assert sel is not None
        return [{"do": "distribute_moved_counters", "kind": distribution["kind"], "sel": sel.key()}], None
    m = re.fullmatch(r"move (?P<n>a|one|all|any number of) (?:(?P<k>\+1/\+1|-1/-1|[a-z]+) )?counters? from (?P<s>.+?) onto (?P<o>.+)", text)
    if m and rider is None and m["k"] not in values.UNMODELED_COUNTERS:
        s_kind, s_key, s_group = ref(m["s"])
        if m["k"] is None and m["n"] == "any number of" and s_kind != "target":  # (wave 24C: of mixed kinds, from one chosen object only)
            raise _Fail
        d_kind, d_key, d_group = ref(re.sub(r"^an? second target ", "target ", m["o"]))
        if s_kind not in ("self", "target", "each") or d_kind not in ("self", "it", "target") or (s_kind, d_kind) == ("self", "self") \
                or (s_kind == "each" and m["n"] != "all"):  # (a number from several: which ones? the player's choice, not read)
            raise _Fail
        if any(g is not None and not on_battlefield_only(g["what"]) for g in (s_group, d_group)) \
                or (s_kind == "each" and not on_battlefield_only(s_key)):
            raise _Fail
        move: dict[str, Any] = {"do": "move_counters", "n": {"a": 1, "one": 1, "all": "all", "any number of": "any"}[m["n"]],
                                "who": "target:1" if s_group is not None and d_group is not None else _who(d_kind, d_key)}
        if s_kind != "self":
            move["from"] = "target" if s_group is not None else _who(s_kind, s_key)
        if m["k"]:
            move["kind"] = m["k"]
        return [move], _out([g for g in (s_group, d_group) if g is not None])
    m = re.fullmatch(r"put (?P<whose>its|those|~'s|this creature's) counters on (?P<o>.+)", text)
    if m and rider is None:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "lki_counters", "from": "it" if m["whose"] in ("its", "those") else "self_named",
                 "who": _who(kind, key)}], _one(group)
    # -- Station (wave 46D) -- "put your choice of a +1/+1 counter or two charge counters on up to one other target artifact" (Inspirit, Flagship
    # Vessel): the kind is chosen as the instruction is carried out (608.2d), after the target is (counter_pick.py)
    m = re.fullmatch(r"put your choice of (?P<k>.+) on (?P<o>(?:up to \w+ )?(?:other )?target .+)", text)
    if m and rider is None:
        from app.rules import counter_pick

        kind, key, group = ref(m["o"])
        picks = counter_pick.parse(m["k"], _who(kind, key)) if kind != "players" else None
        if picks is None:
            raise _Fail
        return picks, _one(group)
    # -- counters (wave 5H) -- "put a +1/+1 counter, a reach counter, and a deathtouch counter on target creature",
    # "put two +1/+1 counters and a flying counter on …": counters of several kinds put at once (one event, 122.6)
    m = re.fullmatch(rf"put (?P<list>(?:(?:{AMT}) (?:[+-]\d+/[+-]\d+|[a-z]+(?: [a-z]+)?) counters?,? )+and "
                     rf"(?:{AMT}) (?:[+-]\d+/[+-]\d+|[a-z]+(?: [a-z]+)?) counters?) on (?P<o>.+)", text)
    if m and rider is None:
        specs = [re.fullmatch(rf"(?P<n>{AMT}) (?P<k>[+-]\d+/[+-]\d+|[a-z]+(?: [a-z]+)?) counters?", p.strip())
                 for p in re.split(r",? and |, ", m["list"])]
        if any(p is None or p["k"] in values.UNMODELED_COUNTERS
               or (" " in p["k"] and p["k"] not in ("first strike", "double strike")) for p in specs):
            raise _Fail
        kinds = [(p["k"], _amount(p["n"])) for p in specs if p is not None]
        if len({k for k, _ in kinds}) != len(kinds):
            raise _Fail
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "add_counters", "who": _who(kind, key), "kind": kinds[0][0], "n": kinds[0][1],
                 "also": [{"kind": k, "n": n} for k, n in kinds[1:]]}], _one(group)
    # -- counters sweep (wave 19D) -- "Put a +1/+1 counter on target creature, two +1/+1 counters on another target creature, and three
    # +1/+1 counters on a third target creature." (Incremental Growth), "… on target creature you control and three … on target
    # creature an opponent controls" (Evolutionary Escalation): each part is its own instruction on its own target (115.3), all in one
    # resolution
    if rider is None and text.startswith("put ") and " counter" in text:
        pieces = re.split(rf",? and (?=(?:{AMT}) (?:[+-]\d+/[+-]\d+|[a-z]+) counters? on )|, (?=(?:{AMT}) (?:[+-]\d+/[+-]\d+|[a-z]+) counters? on )",
                          text[len("put "):])
        specs = [re.fullmatch(rf"(?P<n>{AMT}) (?P<k>[+-]\d+/[+-]\d+|[a-z]+) counters? on (?P<o>(?:a third |another |a second )?target .+)", p)
                 for p in pieces]
        if len(pieces) > 1 and all(specs) and not any(s["k"] in values.UNMODELED_COUNTERS for s in specs if s):
            effects_out: list[dict[str, Any]] = []
            groups_out: list[dict[str, Any]] = []
            for s in specs:
                assert s is not None
                _kind, _key, group = ref(re.sub(r"^(?:a third|a second) ", "another ", s["o"]))
                if group is None:
                    raise _Fail
                effects_out.append({"do": "add_counters", "who": "target" if not groups_out else f"target:{len(groups_out)}",
                                    "kind": s["k"], "n": _amount(s["n"])})
                groups_out.append(group)
            return effects_out, _out(groups_out)
    # -- end counters (wave 5H) --
    # -- counters (wave 33C) -- "put another +1/+1 counter on ~" / "put an additional +1/+1 counter on it" (Yorvo, Cursed Wombat): one more counter
    # put by this instruction, which is "put a counter" (122.6: through the counter choke point, so replacement effects apply to it as to any put)
    text = re.sub(r"^put (?:another|an additional) (?=(?:[+-]\d+/[+-]\d+|[a-z]+) counter on )", "put a ", text)
    m = re.fullmatch(rf"put (?P<n>{AMT}) (?P<k>[+-]\d+/[+-]\d+|(?:first|double) strike|[a-z]+) counters? on (?P<o>.+)", text)  # (wave 26D: first / double strike)
    if m:
        if m["k"] in values.UNMODELED_COUNTERS:
            raise _Fail
        whos, groups = _objects(m["o"])  # -- target forms (agent T) --  "on up to one target land and up to one target creature"
        if len(whos) > 1:
            if len(groups) != len(whos):
                raise _Fail  # (each part of "… and …" is a target of its own: 115.3)
            return [{"do": "add_counters", "who": w, "kind": m["k"], "n": _apply(_amount(m["n"]), rider)} for w in whos], \
                _out(groups)
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "add_counters", "who": _who(kind, key), "kind": m["k"], "n": _apply(_amount(m["n"]), rider)}], \
            _one(group)
    # -- attached events (wave 25D) -- "remove all counters from it" (122.8: every kind it has, each as many as there are): Honest Work,
    # Vampire Hexmage, Purging Stormbrood
    m = re.fullmatch(r"remove all counters from (?P<o>.+)", text)
    if m and rider is None:
        kind, key, group = ref(m["o"])
        if kind not in ("target", "self", "host", "it"):
            raise _Fail
        return [{"do": "remove_counters", "who": _who(kind, key), "kind": "*", "n": 10**6}], _one(group)
    # -- counter removal (wave 30L) -- "Remove up to three counters from target permanent." (Glissa Sunslayer, Heartless Act, Render
    # Inert, Mabel), "Remove a counter from target permanent." (Thrull Parasite, Medicine Runner, Ferropede), "Remove X counters from …,
    # where X is …" (Thornmantle Striker), "Remove up to four charge counters from …" (Gremlin Mine): no kind named, or "up to": the
    # controller chooses the kinds and numbers (608.2d, 609.3: counter_kinds.remove_any). A player's counters aren't read here.
    m = re.fullmatch(rf"remove (?:(?P<up>up to) )?(?P<n>{AMT}) (?:(?P<k>[+-]\d+/[+-]\d+|[a-z]+) )?counters? from (?P<o>.+)", text)
    if m and (m["up"] or not m["k"]):
        kind, key, group = ref(m["o"])
        if kind not in ("target", "self") or re.search(r"\b(?:players?|opponents?)\b", m["o"]) or (rider is not None and rider[0] != "x"):
            raise _Fail
        return [{"do": "remove_any_counters", "who": _who(kind, key), "n": _apply(_amount(m["n"]), rider), "upto": bool(m["up"]),
                 **({"kind": m["k"]} if m["k"] else {})}], _one(group)
    m = re.fullmatch(rf"remove (?P<n>{AMT}|all) (?P<k>[+-]\d+/[+-]\d+|[a-z]+) counters? from (?P<o>.+)", text)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players" or (m["n"] == "all" and rider is not None):
            raise _Fail
        # (wave 17D: "remove all -1/-1 counters from it" - as many as there are, 122.8)
        n = 10**6 if m["n"] == "all" else _apply(_amount(m["n"]), rider)
        return [{"do": "remove_counters", "who": _who(kind, key), "kind": m["k"], "n": n}], _one(group)
    # -- counters (wave 5H) -- "double the number of +1/+1 counters on each creature you control" (Kalonian Hydra),
    # "double the number of each kind of counter on target permanent" (Vorel): 701.10e, as many more as it has
    m = re.fullmatch(r"double the number of (?:(?P<k>[+-]\d+/[+-]\d+|[a-z]+) counters|(?P<each>each kind of counter)) on (?P<o>.+)",
                     text)
    if m and rider is None:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail  # (a player's counters: not read here)
        return [{"do": "double_counters", "who": _who(kind, key), "kind": m["k"] or "*"}], _one(group)
    # -- end counters (wave 5H) --
    # -- temporary grants & riders (agent G) --  "+X/+0", "+1/+1 … for each …", "-X/-X … where X is …",
    # "gets +2/+2 and gains flying and first strike", "… and can't be blocked this turn", "loses flying"
    # -- X sized by a count (wave 4K) -- "creatures you control gain trample and get +X/+X until end of turn" (Craterhoof
    # Behemoth): the grant, then the pump, as printed; X (or "where X is …") read once as the pump begins (608.2h, 611.2c)
    m = _GAIN_PUMP.fullmatch(text)
    if m:
        swapped = _PUMP.fullmatch(f"{m['o']} {m['g']} {m['p']}/{m['t']} and {m['v']} {m['kw']} until end of turn")
        if swapped is None:
            raise _Fail
        effects, target = _pump(swapped, rider)
        return [*effects[1:], effects[0]], target
    # -- trigger other (wave 39A) -- "attacking red creatures get +2/+0 and attacking white creatures get +0/+2 until end of turn." (Agrus Kos, Wojek Veteran): two
    # groups, each its own pump with its own modifier (611.2c: each set of creatures is fixed as this resolves; a creature that is both gets both)
    m = _PUMP_TWO.fullmatch(text)
    if m and (rider is None or rider[0] == "x"):
        half_a = _PUMP.fullmatch(f"{m['a']} gets {m['pa']} until end of turn")
        half_b = _PUMP.fullmatch(f"{m['b']} gets {m['pb']} until end of turn")
        if half_a is None or half_b is None:
            raise _Fail
        (ka, _, ga), (kb, _, gb) = ref(half_a["o"]), ref(half_b["o"])
        if (ka, kb) == ("target", "target") and ga is not None and gb is not None:  # -- activated sweep (wave 48A) -- "target creature gets +0/+2 and another target creature gets -2/-0" (Rookie Mistake): two targets, each its own pump (115.3); "+X/+0 and -0/-X, where X is …" (Monoist Circuit-Feeder): the one X for both
            return [*_pump(half_a, rider)[0], *({**e, "who": _shift(e["who"], 1)} for e in _pump(half_b, rider)[0])], _out([ga, gb])
        if (ka, kb) != ("each", "each") or rider is not None:
            raise _Fail
        return [*_pump(half_a, None)[0], *_pump(half_b, None)[0]], None
    permanent_pump = _PUMP.fullmatch(text + " until end of turn")
    if permanent_pump and permanent_pump["kw"]:
        effects, target = _pump(permanent_pump, rider)
        return [{**effect, "duration": "permanent"} for effect in effects], target
    m = _PUMP.fullmatch(text)
    if m:
        return _pump(m, rider)
    m = _DOUBLE.fullmatch(text)  # -- sized amounts (wave 3D) -- "Double target creature's power until end of turn": +X/+0, X its power now
    if m and rider is None:
        kind, key, group = ref(m["o"])
        if kind not in ("target", "self", "host"):
            raise _Fail
        who = _who(kind, key)
        of = "target" if kind == "target" else who
        return [{"do": "pump", "who": who, "p": {"power": of}, "t": {"toughness": of} if m["both"] else 0}], _one(group)
    m = _LOSE_GAIN.fullmatch(text)  # -- quoted grants (wave 2D) -- "This creature loses defender and gains ⟦0⟧"
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        e = _grant_effect(_who(kind, key), m["kw"])
        if "quotes" not in e and not m["eot"]:
            raise _Fail  # (keywords only: not read here, unless it states its duration)
        e = {**e, "remove": _keyword_list(m["rm"])}
        return [e if m["eot"] else {**e, "duration": "permanent"}], _one(group)
    m = _GAIN_LOSE.fullmatch(text)  # -- activated sweep (wave 17B) -- "gains flying and loses trample until end of turn" (Canopy Dragon): 613.1f, one effect
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        e = _grant_effect(_who(kind, key), m["kw"])
        if "quotes" in e or set(e["keywords"]) & set(_keyword_list(m["rm"])):
            raise _Fail
        return [{**e, "remove": _keyword_list(m["rm"])}], _one(group)
    # -- protection grants (wave 5E) -- "… gains protection from red / the color of your choice until end of turn"
    from app.rules import protection_grants

    if (protected := protection_grants.clause(text)) is not None:
        return protected
    m = _LOSE_PW.fullmatch(text)
    if m and re.search(r"\b(?:protection|ward)\b", m["kw"]):  # (any other list of keywords to lose: the grant below)
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "grant", "who": _who(kind, key), "keywords": [], "remove": _keyword_list(m["kw"])}], _one(group)
    m = _GRANT.fullmatch(text)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        e = _grant_effect(_who(kind, key), m["kw"])
        if m["v"].startswith("lose"):
            if "quotes" in e:
                raise _Fail  # ("loses ⟦…⟧": nothing to take away by quoting it)
            e = {**e, "keywords": [], "remove": e["keywords"]}
        return [e], _one(group)
    m = _GRANT_GAME.fullmatch(text)  # -- quoted grants (wave 2D) -- no duration stated: the game (611.2a)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        e = _grant_effect(_who(kind, key), m["kw"])
        if "quotes" not in e:
            raise _Fail  # (a bare "gains flying" with no duration: not a clause this grammar reads)
        return [{**e, "duration": "permanent"}], _one(group)
    raise _Fail


def _signed(p: str) -> int:
    return -int(p[1:]) if p[0] in "-−" else int(p.lstrip("+"))


# -- target forms (agent T) ---------------------------------------------------------------------------
# Sentences whose whole point is their targets (CR 115, 601.2c): "Choose up to one target creature."
# (a later sentence acts on it: "That creature can't block this turn"), "[~ / it / target creature
# you control] fights [another] target creature" (701.14: two words "target", so two groups, and
# "another" means an object distinct from the first, 115.3), and "counter [target spell /
# activated or triggered ability]" (115.1c-d; a mana ability never uses the stack, 605.3a). A
# sentence is only read when the engine has the primitive that carries it out: the ones whose
# primitive another module hasn't added yet are refused (app/rules/coverage.py REFUSED).
_CHOOSE = re.compile(r"choose (?P<o>(?:each of )?(?:up to \w+ |any number of |one or two |\w+ )?(?:(?:an)?other )?targets?\b.*)")
_FIGHTS = re.compile(r"(?P<a>.+?) fights (?P<b>.+)")
_COUNTER = re.compile(r"counter (?P<o>.+)")


def has_primitive(name: str) -> bool:
    """Does the effects module carry out this primitive? (Never claim a wording the engine can't run.)"""
    from app.rules import effects  # (effects imports this module's users; a lazy import)

    return name in effects.PRIMITIVES


def _target_forms(text: str) -> tuple[Effects, Any] | None:
    m = _CHOOSE.fullmatch(text)
    if m:
        if not has_primitive("choose_targets"):
            raise _Fail  # (refused until the primitive exists: coverage.REFUSED "choose_targets")
        whos, groups = _objects(m["o"])
        if len(whos) != len(groups):
            raise _Fail  # ("choose a creature": a choice, not a target — the player-choices grammar)
        return [{"do": "choose_targets", "who": w} for w in whos], _out(groups)
    if text == "the two chosen creatures fight each other":  # -- counters (wave 26D) -- app/rules/fight_pair.py: the two groups before it
        return [{"do": "fight", "who": "pair:0", "with": "pair:1"}], None
    m = _FIGHTS.fullmatch(text)
    if m:
        if not has_primitive("fight"):
            raise _Fail  # (refused until the fight primitive exists: coverage.REFUSED "fight")
        a_kind, a_key, a_group = ref(m["a"])
        b_kind, b_key, b_group = ref(m["b"])
        if a_kind not in ("self", "it", "host", "target") or b_kind != "target":
            raise _Fail  # (a creature fights "each creature …": one at a time, in what order? not read)
        groups = [g for g in (a_group, b_group) if g is not None]
        for g in groups:
            if not g["what"].startswith(selectors.PREFIX) or selectors.from_key(g["what"]).player is not None:
                raise _Fail  # (only creatures fight, 701.14a: "any target" can't be one)
        who = "target" if a_group is not None else _who(a_kind, a_key)
        partner = "target" if a_group is None else "target:1"
        return [{"do": "fight", "who": who, "with": partner}], _out(groups)
    m = _COUNTER.fullmatch(text)
    if m:
        kind, key, group = ref(m["o"])
        if kind != "target" or not key.startswith(selectors.PREFIX) or selectors.from_key(key).zones != ("stack",):
            raise _Fail  # (only an object on the stack can be countered, 701.6a)
        return [{"do": "counter", "who": "target"}], _one(group)
    return None


# -- temporary grants & riders (agent G) ---------------------------------------------------------------
# Pumps and keyword grants "until end of turn" with what rides on them, researched against CR
# 2026-09-25: the amount may be X (107.3: chosen on activation, or defined by "where X is …",
# 107.3c) or "for each …" — a value read ONCE, as the effect begins (611.2d, 608.2h: "Creatures
# you control get +1/+1 until end of turn for each creature you control" is locked when it
# resolves, unlike a static's "for each", 611.3a); several keywords ("gains flying and first
# strike"); a rules rider in the same sentence ("… until end of turn and can't be blocked this
# turn", two effects: 611.2c's parts); "loses flying until end of turn" (layer 6 removal,
# 613.1f); a bite ("target creature you control deals damage equal to its power to target creature
# you don't control": the first creature is the damage source, so ITS lifelink and deathtouch
# count, 120.3f, 702.2b; "src" names it). Refused, never guessed: a granted quoted ability with a
# duration (the resolved-effect layer model carries keywords only), "gains flashback until end of
# turn" (a casting permission from the graveyard), "where X is" a quantity the value grammar
# doesn't read, "its power" for a pronoun subject the pump can't bind itself.
# -- token & pump wordings (wave 6C) -- the evasion and damage keywords the engine reads from a creature's keywords
# wherever they come from (combat.py: 702.14c landwalk, 702.28b shadow, 702.31b horsemanship, 702.36b fear, 702.13b
# intimidate, 702.118b skulk; 702.80 wither, 702.90 infect): a resolved grant carries them like any other (613.1f)
GRANT_KEYWORDS = KEYWORDS + "|" + "|".join(("fear", "shadow", "horsemanship", "intimidate", "skulk", "wither", "infect",
                                             "plainswalk", "islandwalk", "swampwalk", "mountainwalk", "forestwalk",
                                             "desertwalk"))
_GRANT_ITEM = rf"(?:{GRANT_KEYWORDS}|⟦\d+⟧)"  # (a keyword, or -- wave 2D -- a quoted ability set aside as ⟦n⟧)
_KW_LIST = rf"{_GRANT_ITEM}(?:(?:, and |, | and ){_GRANT_ITEM})*"
_KW_ONLY = rf"(?:{GRANT_KEYWORDS})(?:(?:, and |, | and )(?:{GRANT_KEYWORDS}))*"  # (wave 6C)
# -- untap choice (wave 7F) -- "gets +2/+2 and has trample" (Everglove Courier): "has" reads like "gains"
_PUMP = re.compile(rf"(?P<o>.+?)(?: each)? gets? (?:an additional )?(?P<p>[+\-−](?:\d+|[xX]))/(?P<t>[+\-−](?:\d+|[xX]))"
                   rf"(?: and (?:gains?|has|have) (?P<kw>{_KW_LIST})| and loses? (?P<lose>{_KW_ONLY}))? until end of turn"
                   r"(?: and can't (?P<r>attack or block|block|attack|be blocked) this turn"
                   r"| and (?P<d>can attack this turn as though it didn't have defender)"  # (d: wave 6C)
                   r"| and (?P<mb>must be blocked this turn if able)"  # (mb: wave 6E, 509.1c)
                   r"| and can (?P<bx>block (?:an additional creature|an additional \w+ creatures|up to \w+ additional creatures"
                   r"|any number of creatures)) this turn)?")  # (bx: wave 13B, 509.1a)
_PUMP_TWO = re.compile(r"(?P<a>.+?) gets? (?P<pa>[+\-−](?:\d+|[xX])/[+\-−](?:\d+|[xX])) and (?P<b>(?:(?!\b(?:and|gets?)\b).)+?) gets? (?P<pb>[+\-−](?:\d+|[xX])/[+\-−](?:\d+|[xX])) until end of turn")  # (wave 39A; 48A: X)
_GRANT = re.compile(rf"(?P<o>.+?)(?: each)? (?P<v>gains?|has|have|loses?) (?P<kw>{_KW_LIST}) until end of turn")
# -- activated other (wave 42C) -- "Permanents your opponents control lose hexproof, indestructible, protection, shroud, and ward until end of turn." (Shay Cormac): losing
# protection (702.16, every instance) or ward (702.21) takes no quality or cost, so (unlike gaining them) it is a keyword in its own right
_LOSE_PW = re.compile(rf"(?P<o>.+?)(?: each)? loses? (?P<kw>(?:{GRANT_KEYWORDS}|protection|ward)(?:(?:, and |, | and )(?:{GRANT_KEYWORDS}|protection|ward))*) until end of turn")
_GAIN_PUMP = re.compile(rf"(?P<o>.+?)(?: each)? (?P<v>gains?) (?P<kw>{_KW_LIST}) and (?P<g>gets?) "  # (X sized: wave 4K)
                        rf"(?P<p>[+\-−](?:\d+|[xX]))/(?P<t>[+\-−](?:\d+|[xX])) until end of turn")
_GRANT_GAME = re.compile(rf"(?P<o>.+?)(?: each)? (?:gains?|has|have) (?P<kw>{_KW_LIST})")  # (quoted abilities only: see _parse)
_LOSE_GAIN = re.compile(rf"(?P<o>.+?) loses? (?P<rm>{_KW_ONLY}) and gains? (?P<kw>{_KW_LIST})(?P<eot> until end of turn)?")
_GAIN_LOSE = re.compile(rf"(?P<o>.+?) gains? (?P<kw>{_KW_ONLY}) and loses? (?P<rm>{_KW_ONLY}) until end of turn")
_DOUBLE = re.compile(r"double (?P<o>target creature|~|this creature|enchanted creature|equipped creature)'s power(?P<both> and toughness)? until end of turn")  # (wave 3D; 40B: host)
_BITE = re.compile(r"(?P<s>.+?) deals damage equal to (?P<stat>its power|its toughness|twice its power|that creature's power) to (?P<o>.+)")
_ITS = {"target": "target", "self": "self", "host": "host"}  # what "its" names for a pump's subject


def _keyword_list(text: str) -> list[str]:
    return re.split(r", and | and |, ", text)


# -- quoted grants (wave 2D: app/rules/granted.py) ----------------------------------------------------
# "Until end of turn, target creature gets +2/+0 and gains "When this creature dies, return it to the
# battlefield tapped under its owner's control."" (Supernatural Stamina), "Until end of turn, creatures
# you control gain "{T}: This creature deals 1 damage to any target."" (Lightning Volley), "Return
# target creature card … to the battlefield. It gains "If this creature would die, exile it
# instead."" (Can't Stay Away: no duration, so the game, 611.2a). A sentence with quoted abilities is
# read with each quote set aside as ⟦n⟧ — so nothing inside it is taken for the sentence's own
# words (its "until end of turn", its "for each …") — and each quote checked on its own
# (granted.quote); the grants then carry their texts. A leading "Until end of turn," reads as the
# trailing wording the grammar above knows (611.2a: the same duration).
_EOT_LEAD = re.compile(r"^until end of turn, (?P<rest>.+)$")
_RESTRICT_TAIL = re.compile(r"^.+? can't (?:attack or block|block|attack|be blocked)$")


def _grant_effect(who: str, items: str) -> dict[str, Any]:
    """"flying, first strike, and ⟦0⟧" → one grant: the keywords, and the quoted abilities (their numbers)."""
    from app.rules import granted

    words, quotes = granted.items(items)
    e: dict[str, Any] = {"do": "grant", "who": who, "keywords": words}
    if quotes:
        e["quotes"] = quotes
    return e


def bare_pronoun_grant(text: str) -> Effects | None:
    """-- recursion & tutors (wave 4M) -- a whole sentence "It gains haste." / "That creature gains menace, deathtouch,
    and haste." after an instruction that put the object onto the battlefield (Puppeteer Clique, Sneak Attack): no
    duration is stated, so the grant lasts as long as that object exists (611.2a, 400.7). Read for a whole sentence
    only (scripts._parse_effects): inside "Until end of turn, … and it gains first strike" the lead's duration rules."""
    m = re.fullmatch(rf"(?P<o>it|that creature|that token|they|those creatures|those tokens|that artifact) gains? (?P<kw>{_KW_ONLY})", text)  # (that artifact: wave 6A)
    if m is None:
        return None
    try:
        kind, _key, _group = ref("it" if m["o"] == "that artifact" else m["o"])  # (wave 6A: Arms Race)
        e = _grant_effect(_who(kind, _key), m["kw"])
    except _Fail:
        return None
    if kind not in ("it", "them") or "quotes" in e or not e["keywords"]:
        return None
    return [{**e, "duration": "permanent"}]


def _end_of_turn_first(rest: str) -> tuple[Effects, Any]:
    """"Until end of turn, <clause>": the clause with the duration after it, if that is a continuous
    effect (only a pump, a grant or a restriction has one: delayed.wrap_duration's rule)."""
    # -- X sized by a count (wave 4K) -- "Until end of turn, creatures you control gain trample and get +X/+X, where X is …":
    # the duration goes before the rider (which defines X for the whole sentence, 107.3c)
    head, sep, tail = rest.partition(", where X is ")
    if sep and not _RESTRICT_TAIL.fullmatch(head):
        effects, target = _parse(f"{head} until end of turn{sep}{tail}")
    else:
        effects, target = _parse(rest + (" this turn" if _RESTRICT_TAIL.fullmatch(rest) else " until end of turn"))
    if not effects or any(e["do"] not in ("pump", "grant", "restrict", "gain_control") for e in effects):
        raise _Fail
    return effects, target


def _quoted(text: str) -> tuple[Effects, Any]:
    """A sentence with quoted abilities (see above): only a grant may carry them, and every quote
    must be carried out by the engine (granted.quote) and used."""
    from app.rules import granted

    parts = granted.protect(text)
    if parts is None or not parts[1]:
        raise _Fail
    safe, quotes = parts
    checked = [granted.quote(q) for q in quotes]  # (an ability the engine carries out as granted …)
    ruled = [granted.rules_of(q) if c is None else None for q, c in zip(quotes, checked, strict=True)]  # (… or a rule)
    if any(c is None and r is None for c, r in zip(checked, ruled, strict=True)):
        raise _Fail
    effects, target = _parse(safe)
    used: list[int] = []
    out: Effects = []
    for e in effects:
        e = dict(e)
        numbers = e.pop("quotes", None)
        if not numbers:
            out.append(e)
            continue
        used += numbers
        rules = [rule for i in numbers for rule in (ruled[i] or ())]
        abilities = [c for i in numbers if (c := checked[i]) is not None]
        if abilities:
            e["abilities"] = abilities
        if abilities or e["keywords"] or e.get("remove"):
            out.append(e)
        if rules:  # "gains "This creature can't be blocked."": a restriction on the same objects (granted.rules_of)
            out.append({"do": "restrict", "who": e["who"], "rules": list(dict.fromkeys(rules)), "locked": True,
                        **({"duration": e["duration"]} if "duration" in e else {})})
    if sorted(used) != list(range(len(quotes))) or not _permanents(out, target):
        raise _Fail
    return out, target


def _permanents(effects: Effects, target: Any) -> bool:
    """Does every grant of quoted abilities name permanents? A card in a graveyard or exile, or a
    spell, doesn't gain an ability an effect grants (611.2e: only a permanent on the battlefield
    does): those stay manual. A pronoun is read when it resolves (effects.grant skips what isn't there)."""
    from app.rules.scripts import SELECTORS  # (scripts imports this module)

    keys = [e["who"] for e in effects if e["do"] in ("grant", "restrict") and isinstance(e.get("who"), str)]
    groups = [g["what"] if isinstance(g, dict) else g for g in (target if isinstance(target, list) else [target]) if g]
    not_permanents = {"any", "player", "opponent", "spell", "creature_spell", "noncreature_spell", "instant_or_sorcery_spell"}
    legacy = {v for v in SELECTORS.values() if v not in not_permanents}  # ("target creature", "target land", …)
    for key in (*keys, *groups):
        if not isinstance(key, str):
            return False
        if key.startswith(selectors.PREFIX):
            sel = selectors.from_key(key)
            if sel.zones != ("battlefield",) or sel.player is not None:
                return False
        elif key in not_permanents or key.startswith(("graveyard:", "stack", "player")) or (
                key not in legacy and not key.startswith(("target", "it", "them", "self", "host", "ref:", "event", "object:"))
                and key not in ("creatures_you_control", "each_creature")):
            return False
    return True


class _Ante(dict[str, Any]):
    """A value whose "it" is an object an earlier instruction named, not the subject of the sentence it is written in."""


def _bind_its(v: Any, its: str | None) -> Any:
    """A rider's placeholder "it" ("where X is its power", "for each counter on it") as the pump's
    own subject; refused when the subject is a pronoun the grammar can't bind here."""
    if isinstance(v, list):
        return [_bind_its(x, its) for x in v]
    if not isinstance(v, dict) or isinstance(v, _Ante):
        return v
    out = {}
    for k, x in v.items():
        if k in ("power", "toughness", "mana_value", "on", "colors") and x == "it":
            if its is None:
                raise _Fail
            x = its
        else:
            x = _bind_its(x, its)
        out[k] = x
    return out


def _mod(word: str, rider: Any, its: str | None) -> Any:
    """One half of "+N/+N": an int, or a value expression ("+X", "-X", "+2 for each …": ``{"neg":
    …}`` for a negative one, evaluated by values.evaluate_signed as the pump begins)."""
    neg = word[0] in "-−"
    body = word[1:]
    base: Any = {"x": 1} if body.lower() == "x" else int(body)
    if rider is not None:
        kind, v = rider
        v = _bind_its(v, its)
        if kind == "x":
            if base == {"x": 1}:
                base = v
        elif base == {"x": 1}:
            raise _Fail  # ("+X/+X for each …": no such wording is read)
        elif base:
            base = v if base == 1 else {"times": [base, v]}
    if isinstance(base, int):
        return -base if neg else base
    return {"neg": base} if neg else base


def _pump(m: re.Match[str], rider: Any) -> tuple[Effects, Any]:
    its: str | None
    combined = re.fullmatch(r"(?:~|this creature) and (?P<group>.+ you control)", m['o'])
    if combined:
        kind, key, group = ref(combined['group'])
        sel = selectors.from_key(key) if key.startswith(selectors.PREFIX) else None
        if kind != 'each' or group is not None or sel is None or sel.player is not None or sel.card \
                or sel.zones != ('battlefield',) or sel.controller != 'you' or '+' in key:
            raise _Fail
        who, its = f'union:self+{key}', None
    else:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        who = _who(kind, key)
        its = _ITS.get(kind)
    p, t = _mod(m["p"], rider, its), _mod(m["t"], rider, its)
    if rider is not None and rider[0] == "x" and "x" not in (m["p"] + m["t"]).lower():
        raise _Fail  # "where X is …" with no X in the sentence
    out: Effects = [{"do": "pump", "who": who, "p": p, "t": t}]
    if m["kw"]:
        out.append(_grant_effect(who, m["kw"]))
    if m["lose"]:  # -- activated sweep (wave 17B) -- "gets -2/+2 and loses flying until end of turn" (Leering Gargoyle): 613.1f
        out.append({"do": "grant", "who": who, "keywords": [], "remove": _keyword_list(m["lose"])})
    if m["r"]:
        out.append({"do": "restrict", "who": who, "rules": RESTRICTIONS[m["r"]]})
    if m["d"]:  # -- token & pump wordings (wave 6C) -- 702.3b
        out.append({"do": "restrict", "who": who, "rules": ["attack_despite_defender"]})
    if m["bx"]:  # -- multiple blocks (wave 13B) -- 509.1a
        from app.rules.statics import _rule

        rules = _rule("can " + m["bx"])
        if not rules:
            raise _Fail
        out.append({"do": "restrict", "who": who, "rules": rules})
    if m["mb"]:  # -- static wordings (wave 6E) -- a blocking requirement for this turn (509.1c: combat.block_requirements)
        out.append({"do": "restrict", "who": who, "rules": ["must_be_blocked"]})
    return out, _one(group)


def _shift(who: str, by: int) -> str:
    """A target reference of a later part of the sentence, after ``by`` earlier groups."""
    if who == "target":
        return f"target:{by}"
    if who.startswith("target:"):
        return f"target:{int(who[7:]) + by}"
    return who


_BITES = re.compile(r"(?P<s>.+?) each deal damage equal to their power to (?P<o>.+)")


def _bite_many(text: str) -> tuple[Effects, Any] | None:
    """-- as long as (wave 9B) -- "Up to two target creatures you control each deal damage equal to their power to another target
    creature" (Band Together), "They each deal damage equal to their power to target creature an opponent controls" (Coordinated
    Clobbering): every creature of the group is a damage source (120.3: its own lifelink and deathtouch count), each dealing its own
    power, all at once (608.2h). ``src_many``: ``src`` names a target group (or "them": resolve_it binds it to the group)."""
    m = _BITES.fullmatch(text)
    if m is None:
        return None
    groups: list[dict[str, Any]] = []
    src = "them"
    if m["s"] != "they":
        # "Target creature you control and up to one other target legendary creature you control each deal …" (Friendly Rivalry):
        # two groups, both sources
        subjects = re.split(r" and (?=up to \w+ other target )", m["s"])
        if len(subjects) > 2:
            raise _Fail
        for subject in subjects:
            kind, key, group = ref(subject)
            if kind != "target" or group is None or selectors.from_key(key).player is not None:
                raise _Fail
            groups.append(group)
        src = "target"
    whos, parts = _bite_recipients(m["o"])
    effects: Effects = [{"do": "damage", "who": _shift(w, len(groups)), "n": {"power": "each"}, "src": src, "src_many": True,
                         **({"src2": "target:1"} if len(groups) == 2 else {})} for w in whos]
    for joined in effects[:-1]:
        joined["with_next"] = True
    return effects, _out(groups + parts)


def _bite(text: str) -> tuple[Effects, Any] | None:
    """"[Target creature you control / enchanted creature] deals damage equal to its power to
    [target creature you don't control / each creature …]": damage whose source is the named
    creature (120.3, 608.2h: as it is, or as it last existed). "~" and "it" as the subject are the
    older damage grammar's."""
    m = _BITE.fullmatch(text)
    if m is None or m["s"] in ("~", "it"):
        return None
    kind, key, group = ref(m["s"])
    stat = "toughness" if "toughness" in m["stat"] else "power"
    if kind == "each" and m["stat"] in ("its power", "its toughness", "twice its power"):
        # -- sized amounts (wave 3D) -- "each creature you control deals damage equal to its power to …": every one is a source
        if selectors.from_key(key).player is not None:
            raise _Fail
        whos, parts = _objects(m["o"])
        n_each: Any = {stat: "each"} if not m["stat"].startswith("twice ") else {"times": [2, {stat: "each"}]}
        return [{"do": "damage", "who": w, "n": n_each, "src": "each:" + key} for w in whos], _out(parts)
    if kind not in ("target", "host"):
        raise _Fail  # (a pronoun subject: which creature deals it isn't read here)
    src = "target" if group is not None else "host"
    groups = [group] if group is not None else []
    if src == "target" and (m["o"] == "its controller" or (m["o"] == "that player" and m["s"].endswith(" an opponent controls"))):
        # -- damage sized by a count (wave 42D) -- "target creature an opponent controls deals damage equal to its power to that player" (Dong Zhou): the player who
        # controls the creature dealing it (the opponent the target phrase names), as it last existed if it left (608.2h, 108.4a): not the trigger event's player
        whos, parts = ["target_player_or_controller"], []
    else:
        whos, parts = _bite_recipients(m["o"])  # (wave 4E: "… to each other creature and each opponent")
    if src != "target" and any(g.get("another") == "any" for g in parts):
        raise _Fail  # -- damage sized by a count (wave 34D) -- "enchanted creature deals … to any other target": other than the creature, not than the Aura
    n: Any = {stat: src} if not m["stat"].startswith("twice ") else {"times": [2, {stat: src}]}  # (sized amounts, wave 3D)
    effects: Effects = [{"do": "damage", "who": _shift(w, len(groups)), "n": n, "src": src} for w in whos]
    for joined in effects[:-1]:  # -- damage sized by a count (wave 4E) -- one sentence: one damage event (120.3, 608.2)
        joined["with_next"] = True
    return effects, _out(groups + parts)


# -- damage sized by a count (wave 4E): app/rules/sized_damage.py ------------------------------------

def _bite_recipients(o: str) -> tuple[list[str], list[dict[str, Any]]]:
    """A bite's recipients: "target creature you don't control", "each other creature and each opponent"
    (several "each" parts; at most one of them a target group)."""
    parts = re.split(r" and (?=each )", o)
    if len(parts) == 1:
        return _objects(o)
    whos: list[str] = []
    groups: list[dict[str, Any]] = []
    for part in parts:
        w, g = _objects(part)
        if g:
            raise _Fail  # (a target among "each" recipients: not read)
        whos += w
    return whos, groups


_THAT_PLAYER_CONTROLS = re.compile(r"^each (?P<sel>.+?) that player (?P<or>or that planeswalker's controller )?controls$")


def _that_player_controls(part: str) -> str | None:
    """"each creature that player controls" (Balefire Dragon): the permanents of the player "that player"
    names (resolved by scripts.resolve_it like any "that player": the trigger event's player, or a target
    player) → "controlled:that_player|<selector>" (app/rules/effects._cards)."""
    m = _THAT_PLAYER_CONTROLS.fullmatch(part)
    if m is None:
        return None
    sel = selectors.parse(m["sel"])
    if sel is None or sel.player is not None or sel.controller is not None:
        raise _Fail
    if m["or"]:  # -- damage wordings (wave 6B) -- "… that player or that planeswalker's controller controls"
        return f"controlled:target_player_or_controller|{sel.key()}"
    return f"controlled:that_player|{sel.key()}"


_PLAYER_RECIPIENTS = ("each_player", "each_opponent", "that_player", "event_player", "you")


def _check_per_player(effects: Effects, groups: list[dict[str, Any]]) -> None:
    """An amount read per recipient player is dealt to players only ("… to each player equal to the
    number of lands that player controls"); any other recipient leaves the sentence unread."""
    if not any(sized_damage.has_per_player(e.get("n")) for e in effects):
        return
    for e in effects:
        who = str(e.get("who"))
        if who in _PLAYER_RECIPIENTS:
            continue
        if who == "target" or who.startswith("target:"):
            g = 0 if who == "target" else int(who[7:])
            if g < len(groups) and groups[g].get("what") in ("player", "opponent"):
                continue
        raise _Fail


_EACH_TO_CONTROLLER = re.compile(rf"(?P<s>each .+?) deals (?P<n>{AMT}) damage to its controller")


def _sized_damage_forms(text: str, rider: Any) -> tuple[Effects, Any] | None:
    """"Target creature deals damage to itself equal to its power" / "Each creature deals damage to
    itself equal to its power" (the creature is the source: 120.3; its power as it is or as it last
    existed: 608.2h)."""
    each_ctrl = _EACH_TO_CONTROLLER.fullmatch(text)  # -- modal spells (wave 24D) -- "Each creature deals 1 damage to its controller."
    if each_ctrl is not None and rider is None:
        kind, key, _ = ref(each_ctrl["s"])
        if kind != "each" or selectors.from_key(key).player is not None:
            raise _Fail
        return [{"do": "damage", "who": "itself", "n": _amount(each_ctrl["n"]), "src": "each:" + key, "to": "controller"}], None
    fixed_each = re.fullmatch(r"(?P<s>each .+?) deals (?P<n>\d+) damage to (?P<o>.+)", text)
    if fixed_each is not None and rider is None:
        kind, key, _ = ref(fixed_each["s"])
        source = selectors.from_key(key) if kind == "each" else None
        if source is None or source.player is not None or source.zones != ("battlefield",) or source.card:
            raise _Fail
        whos, groups = _bite_recipients(fixed_each["o"])
        return [{"do": "damage", "who": who, "n": int(fixed_each["n"]), "src": "each:" + key}
                for who in whos], _out(groups)
    m = sized_damage.SELF_DAMAGE.fullmatch(text)
    if m is None or (m["c"] and not m["s"].startswith("target ")):  # (wave 49B: a fixed amount only for a target; "this creature deals 1 damage to itself" is read elsewhere)
        return None
    if rider is not None:
        raise _Fail
    stat = "toughness" if "toughness" in (m["a"] or m["b"] or "") else "power"
    kind, key, group = ref(m["s"])
    if kind == "each":
        if selectors.from_key(key).player is not None:
            raise _Fail
        return [{"do": "damage", "who": "itself", "n": int(m["c"]) if m["c"] else {stat: "each"}, "src": "each:" + key}], None
    if kind != "target" or group is None or group.get("max", 1) != 1:
        raise _Fail
    return [{"do": "damage", "who": "target", "n": int(m["c"]) if m["c"] else {stat: "target"}, "src": "target"}], _one(group)  # (wave 49B: a fixed amount, "deals 6 damage to itself")
# -- end damage sized by a count (wave 4E) --


# Compound sentences whose subject is one player, read as two instructions ("Target player draws
# two cards and loses 2 life": one word "target", the same player for both, 115.3): the halves for
# scripts._clause, which reads each with the subject repeated.
_V3 = (r"draws|loses|gains|discards|mills|sacrifices|creates|puts|exiles|returns|reveals|shuffles|scries|surveils|"
       r"gets|searches")
COMPOUND = (rf"(?P<s>target player|target opponent|each player|each opponent|each of your opponents|that player) "
            rf"(?P<l>(?:{_V3}) [^\"]+?) and (?P<r>(?:{_V3}) .+)")  # (wave 26A: no "and" inside a quoted ability: an emblem's text)
# -- most-played cards II (wave 45A) -- "Any number of target opponents each sacrifice a creature … and lose 3 life." (Will of the Abzan): the group of players is the subject of both
# halves (a bare "lose" would be read as the controller's own); scripts._compound_multi
_VB = r"draw|lose|gain|discard|mill|sacrifice|create|put|exile|return|reveal|shuffle|scry|surveil|get"
COMPOUND_MULTI = (rf"(?P<s>{_MULTI_PLAYERS}) (?P<l>(?:{_VB}) [^\"]+?) and (?P<r>(?:{_VB}) .+)")


# -- delayed triggers & durations (agent J) --------------------------------------------------------
# Sentence forms app/rules/delayed.py needs that the grammar above doesn't read on its own. Each is
# registered as a template by the appended block of app/rules/scripts.py, so the pronoun resolver
# and the target-group bookkeeping treat the deferred effects like any others.
_PRONOUN_SACRIFICE = {"them": "them", "those tokens": "them", "those creatures": "them", "the tokens": "them",
                      "those permanents": "them", "that creature": "it", "that token": "it", "the token": "it",
                      "that permanent": "it", "that card": "it"}
_PRONOUN_SACRIFICE.update({"the creature": "it", "that artifact": "it"})  # -- permanent effects (wave 6A) -- Sneak Attack, Arms Race
_OWNER_RETURN = re.compile(r"^return (?P<o>.+?) to the battlefield(?P<t> tapped)?(?P<fd> face down)? under (?P<u>their owner's|its owner's|your) control"
                           r"(?: as (?P<spec>.+))?$")


def parse_sacrifice_pronoun(phrase: str) -> tuple[Effects, Any] | None:
    """"Sacrifice that creature / those tokens / the token": the objects an earlier instruction
    named (a pronoun for scripts.resolve_it)."""
    who = _PRONOUN_SACRIFICE.get(phrase.strip())
    return ([{"do": "sacrifice", "who": who}], None) if who else None


def parse_return_owner(text: str) -> tuple[Effects, Any] | None:
    """"Return those cards to the battlefield under their owner's control" (the singular "owner's"
    of current Oracle wording): the cards an earlier instruction moved (400.7j), each to its
    owner's side."""
    m = _OWNER_RETURN.fullmatch(text.strip())
    if not m:
        return None
    try:
        kind, key, group = ref(m["o"])
    except _Fail:
        return None
    if kind not in ("it", "them"):
        return parse_sentence(text)  # ("return all creature cards from your graveyard …": the grammar above)
    if (m["u"] == "your" or m["spec"]) and not m["fd"] and not (m["u"] == "your" and not m["spec"] and "|" in key):
        return None  # (-- hidden exile (wave 18A) -- "under your control" / "as a …" are read only for the face-down return;
        # wave 22D: and for "each card put into a graveyard this way", which names its objects)
    spec = chars.parse_spec(m["spec"]) if m["spec"] else None
    if m["spec"] and spec is None:
        return None
    return [{"do": "return_card", "who": _who(kind, key), "to": "battlefield", "tapped": bool(m["t"]),
             "under": "you" if m["u"] == "your" else "owner", **({"face_down": True} if m["fd"] else {}),
             **({"spec": spec} if spec else {})}], _one(group)


def exile_own(n: str, sel_text: str, until: bool) -> tuple[Effects, Any]:
    """-- resolution memory (wave 22D) -- "Exile another creature you control until ~ leaves the battlefield." (Yannik), "… any number of
    non-Angel creatures you control …" (Glorious Protector): chosen as this resolves (608.2d); until: 610.3, returned when ~ leaves."""
    noun = ("another " if n == "another" else "") + sel_text
    sel = selectors.parse(noun)
    if sel is None or sel.player is not None or sel.controller != "you" or sel.zones != ("battlefield",):
        raise _Fail
    if n == "any number of" and not until:
        raise _Fail  # ("exile any number of …" with no duration: not read)
    many = n == "any number of"
    return [{"do": "sacrifice_choice", "who": "you", "sel": sel.key(), "n": 10**6 if many else 1 if n == "another" else _amount(n),
             "exile": "until" if until else True, **({"upto": True} if many else {})}], None


_EXILE_OWN = re.compile(r"(?P<n>another|any number of) (?P<sel>(?!target )[A-Za-z -]+? you control)")


def parse_exile_until(phrase: str) -> tuple[Effects, Any] | None:
    """"Exile <objects> until ~ leaves the battlefield" (610.3) for any target phrase the selector
    grammar reads ("target artifact or creature an opponent controls", "up to one target nonland
    permanent …"). Not a pronoun: "exile that card until …" may name a card in a hand, and 610.3
    returns it to its previous zone, while the engine's linked return puts it onto the
    battlefield (610.3c) — that wording stays manual."""
    if (own := _EXILE_OWN.fullmatch(phrase.strip())) is not None:
        try:
            return exile_own(own["n"], own["sel"], True)  # (-- wave 22D -- chosen as it resolves, not targeted)
        except _Fail:
            return None
    try:
        kind, key, group = ref(phrase.strip())
    except _Fail:
        return None
    if kind == "it" and phrase.strip() in ("that card", "it"):
        # -- resolution memory (wave 22D) -- "You choose a nonland card from it. Exile that card until ~ leaves the battlefield." (Kitesail
        # Freebooter): the card chosen from a hand returns to that hand (610.3). scripts.resolve_it accepts it only after such a choice
        return [{"do": "exile_until", "who": "it", "hand_origin": True}], None
    if kind in ("players", "self", "host", "it", "them") or not on_battlefield_only(key):
        return None  # (a card exiled from a graveyard returns there, 610.3: not the linked return)
    return [{"do": "exile_until", "who": _who(kind, key)}], _one(group)


def on_battlefield_only(key: str | None) -> bool:
    """Does the selector name only objects on the battlefield (the only ones "until ~ leaves the
    battlefield" returns to the battlefield, 610.3c)? ``key``: a selector key, or a named target
    kind ("creature", "nonland_permanent_opp", "creature_spell", …)."""
    if not key:
        return False
    if key.startswith(selectors.PREFIX):
        return set(selectors.from_key(key).zones) == {"battlefield"}
    return not key.endswith("spell") and key not in ("any", "player", "opponent")


# -- player choices (agent I) ---------------------------------------------------------------------
# Sentences whose choice belongs to a named player, read by the templates registered at the end of
# app/rules/scripts.py (they run before the generic grammar): edicts — "[each opponent / target
# player / that player] sacrifices N [selector] of their choice" (701.21a: the sacrificing player
# chooses; several players in APNAP order, 101.4, each knowing the earlier choices, 101.4b, then
# all at once); "[target opponent] chooses N [selector] they control"; a revealed hand — "target
# player reveals their hand" (701.20a), "you [may] choose [up to] N [card selector] from it", "that
# player discards that card"; and a named choice — "choose a color / creature type / basic land
# type / opponent / player" (105.1, 205.3m, 205.3i). "As ~ enters, choose …" (614.1c, 614.12a) is
# read by ``enters_choice`` for the engine's entering code; it is not a resolution effect.
_CHOOSERS = ("target player", "target opponent", "each opponent", "each of your opponents", "each player", "each other player",
             "that player", "its controller", "that creature's controller", "that permanent's controller", "defending player")
CHOOSER = "|".join(re.escape(c) for c in sorted(_CHOOSERS, key=len, reverse=True))
# (patterns are format()-ed by scripts.effect: no literal braces)
EDICT = rf"(?P<s>{CHOOSER}) sacrifices (?P<n>{AMT}) (?P<sel>(?:(?!, then ).)+?) of their choice(?P<tail> that dealt combat damage to you this turn)?(?: for each (?P<each>.+))?"  # (each: wave 19D, Smokestack; tail: wave 39A)
EDICT_OTHERS = rf"each other player sacrifices (?P<n>{AMT}) (?P<sel>.+?)(?: of their choice)?"
# -- trigger other (wave 39A) -- "Each player sacrifices half the non-God creatures they control of their choice, rounded down." (Zodiark), "Target
# opponent sacrifices half the nonland permanents they control of their choice, rounded down." (Lord Xander): half of what that player controls (107.1a:
# rounded as written), counted for each player on their own; the choices are made in APNAP order (101.4) and everything goes at once
EDICT_HALF = rf"(?P<s>{CHOOSER}) sacrifices half the (?P<sel>.+?) they control(?: of their choice)?, rounded (?P<r>up|down)"
# -- modal spells (wave 24D) -- "Target opponent exiles a creature they control." (Doomfall, Debt to the Kami): the edict's choice (101.4,
# 701.21a-style: the player chooses among what they control), exiled instead of sacrificed
EDICT_EXILE = (rf"(?P<s>{CHOOSER}) exiles (?P<n>{AMT}) (?P<sel>.+?) they control"
               r"(?P<great> with the greatest (?:power|toughness|mana value) among .+? they control)?")  # (wave 26A: Blot Out)
PLAYER_CHOOSES = (rf"(?P<s>{CHOOSER}) chooses (?:(?P<upto>up to )?(?P<n>{AMT})) (?P<sel>.+?) they control"
                  r"(?:, then (?:(?P<sac>sacrifices the rest)|(?P<des>the rest are destroyed)))?")  # (wave 11D: "… then sacrifices the rest")
# -- per-player choices (wave 31B) -- "Starting with you, each player chooses a creature." (The Horus Heresy), "Starting with the next opponent in turn order,
# each player chooses a creature you don't control." (Sadistic Shell Game), "… chooses up to one permanent with mana value 3 or greater from among
# permanents your opponents control." (The Legend of Yangchen), "… each player may choose an artifact or enchantment you don't control." (Druid of
# Purification): a choice among the permanents anyone controls that the ability's controller's words allow, made in turn order from the named player
# (101.4: "starting with" a player is that player first, then turn order), then what the next sentence does to all that were chosen
CHOOSE_ANY = (rf"(?:starting with (?P<start>you|the next opponent in turn order), )?each player (?:(?P<may>may) choose|chooses) (?P<upto>up to )?"
              rf"(?P<n>{AMT}) (?P<sel>(?!.*\bthey control)[^,]+?)(?: from among (?P<among>permanents your opponents control))?")
REVEAL_HAND = rf"(?P<s>{CHOOSER}) reveals their hand"
REVEAL_SOME = rf"(?P<s>target player|target opponent) reveals (?:(?P<n>{AMT})|a number of) cards from their hand(?: equal to (?P<eq>.+))?"  # -- hand disruption (wave 52C) -- Blackmail, Noggin Whack, Mire's Toll
CHOOSE_FROM_HAND = (rf"you (?P<may>may )?choose (?:(?P<upto>up to )?(?P<n>{AMT})|(?P<any>any number of)) (?P<sel>.+?) "
                    r"from (?:it|among them|that hand)(?P<tail> with mana value \d+ or (?:less|greater))?")
# -- hand disruption (wave 11D) -- "You choose a nonland card from it or a card from their graveyard." (Agonizing Remorse), "You
# choose a nonland card from that player's graveyard or hand." (Memory Leak): the revealed hand and that player's graveyard
CHOOSE_FROM_HAND_GY = (r"you choose (?:a|an) (?P<sel>.+?) from (?:it or (?:a|an) (?P<sel2>.+?) from their graveyard"
                       r"|that player's graveyard or hand)")
# "Look at target player's hand." (Gitaxian Probe, Peek): a private look (701.20e: only the looking player sees it)
LOOK_HAND = rf"look at (?P<s>{CHOOSER})'s hand(?: and (?P<ch>choose .+))?"  # (Painful Memories, Extortion: "… and choose a card from it")
# "Target player reveals their hand and discards all nonland cards." (Amnesia, Trapfinder's Trick)
DISCARD_ALL_REVEALED = (rf"(?P<s>{CHOOSER}) reveals their hand and discards all (?:(?P<sel>.+?) )?cards?"
                        r"(?P<tail> with (?:(?:the chosen|that) name|that spell's mana value|mana value (?:equal to the chosen number|\d+))| of the chosen (?:color|type))?")  # (wave 22B: Cabal Therapy, "all cards with that name"; wave 36A: Infernal Kirin)
DISCARD_NAMED = r"(?:that player|the player|they|its owner) discards? (?P<o>that card|those cards|it|them)"  # (-- player-relative selectors (wave 53A) -- "The player discards that card.": Doomsday Specter)
CHOICE_KINDS = ("color", "creature type", "basic land type", "opponent", "player")
CHOOSE_VALUE = rf"choose (?:(?:a|an) )?(?P<what>color|creature type|basic land type|opponent|another player|one of your opponents|player with the most life or tied for most life|player|odd or even|{_NAME_WHAT}|{_chosen.TYPE_CHOICE}|{_chosen.NUMBER_CHOICE})"  # (wave 53C: The Black Gate; wave 53B: chosen type and number)  # (wave 50J: odd or even, Thanos)
CARD_TYPE_FIVE = "artifact, creature, enchantment, instant, or sorcery"  # -- commanders (wave 47A) -- Cloud Key: the five card types it offers
TYPE_LIST = r"[A-Z][a-z]+(?:, [A-Z][a-z]+)+, or [A-Z][a-z]+"  # -- chosen type (wave 51C) -- "choose Elemental, Elf, Faerie, Giant, Goblin, Kithkin, Merfolk, or Treefolk" (Eclipsed Realms, Dawn-Blessed Pennant)
_BASIC_PAIR = "(?:Plains|Island|Swamp|Mountain|Forest) or (?:Plains|Island|Swamp|Mountain|Forest)"  # -- chosen filters (wave 53B) -- "choose Island or Swamp" (Roots of Life): a basic land type, only those two
ENTERS_CHOICE = re.compile(rf"^As ~ enters, choose (?:(?:a|an) )?(?P<what>color|creature type|basic land type|land type|opponent|player|odd or even|card type(?: other than creature or land)?|{CARD_TYPE_FIVE}|number between 1 and 10|two abilities from among first strike, vigilance, and lifelink|{TYPE_LIST}|{_chosen.TYPE_CHOICE}|{_chosen.NUMBER_CHOICE}|color and a creature type|color and an opponent|two basic land types|two colors|{_BASIC_PAIR}|{_chosen.PAIRS})\.$")  # (wave 47A: card type, Umori and Stenn; Cloud Key; wave 51C: a short list of creature types)


# -- choose own (wave 32A) -- "Then you may choose a token you control." (Brudiclad), "Choose a Giant creature you control. It deals damage equal to its
# power to target creature." (Crush Underfoot): a choice made on resolution (608.2d: not a target, so nothing is chosen on cast and hexproof
# doesn't matter) among the permanents the controller controls; what is chosen is "it" / "that token" for the next sentences
CHOOSE_OWN = r"(?:you (?P<may>may )?)?choose (?:an?|one) (?P<sel>.+?) you control"


def choose_own(m: re.Match[str]) -> tuple[Effects, Any]:
    return [{"do": "player_chooses", "who": "you", "sel": _permanent_sel(m["sel"]), "n": 1, "label": m["sel"],
             **({"upto": True, "optional": True} if m["may"] else {})}], None


def _chooser(s: str) -> tuple[str, Any]:
    """A choosing player's phrase → ("who", the target group it adds)."""
    if s in ("target player", "target opponent"):
        return "target", {"what": _LEGACY_TARGETS[s], "min": 1, "max": 1}
    if s == "each other player":
        return "each_opponent", None  # every other player is an opponent in a free-for-all (102.2, 806.2)
    # (-- defending player (wave 6D) -- "defending player": the attack trigger event's, 508.5: app/rules/defending.py)
    return PLAYER_GROUPS[s], None


def _permanent_sel(phrase: str) -> str:
    """"creature", "creature or planeswalker", "nontoken artifact", "permanent" — a permanent
    selector (no player, not a card in another zone, no controller: the chooser's own)."""
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or sel.controller is not None or any(e.startswith("ext:") for e in sel.extras):
        raise _Fail  # (wave 49C: an extreme is among the chooser's own permanents here, not the whole table's: _GREATEST_OWN reads that)
    return sel.key()


_GREATEST_OWN = re.compile(r"(?P<s>.+?) with the (?P<ext>greatest|least) (?P<stat>power|toughness|mana value) among (?P<among>.+?) (?:that player|they) controls?")  # (ext: wave 39A)


def _greatest_own(noun: str) -> selectors.Selector | None:
    """-- static_other sweep (wave 26A) -- "a creature or planeswalker with the greatest mana value among creatures and planeswalkers they
    control" (Break Under Pressure, Blot Out; Crackling Doom's power): among the objects the choosing player controls of the named kinds,
    one holding the greatest value (ties all qualify). The kinds are card types only (a qualifier would need its own judgement)."""
    m = _GREATEST_OWN.fullmatch(noun)
    if m is None:
        return None
    sel, among = selectors.parse(m["s"]), selectors.parse(m["among"])
    if sel is None or among is None or among.player is not None or among.card or among.controller is not None or sel.controller is not None:
        raise _Fail
    if replace(among, types=(), not_types=()) != selectors.Selector():
        raise _Fail
    kinds = "|".join(among.types) + ("!" + "|".join(among.not_types) if among.not_types else "")
    return replace(sel, extras=(*sel.extras, f"{m['ext']}_own:{m['stat'].replace(' ', '_')}:{kinds}"))


def edict(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"] if "s" in m.groupdict() else "each other player")
    if m.groupdict().get("great"):  # -- static_other sweep (wave 26A) -- "… they control with the greatest mana value among … they control"
        greatest = _greatest_own(m["sel"] + m["great"].replace(" they control", "", 1) + " they control")
        if greatest is None:
            raise _Fail
        key = greatest.key()
    else:
        key = _permanent_sel(m["sel"] + (m.groupdict().get("tail") or ""))
    n = _amount(m["n"])
    if m.groupdict().get("each"):  # -- counters sweep (wave 19D) -- "… of their choice for each soot counter on this artifact": a count read as it resolves
        v = this_way.parse(m["each"]) if m["each"].endswith(" this way") else values.parse_count(m["each"], it="self")  # (wave 21C: Malfegor)
        if v is None:
            raise _Fail
        n = v if n == 1 else {"times": [n, v]}
    return [{"do": "edict", "who": who, "sel": key, "n": n, "label": m["sel"], **({"action": "exile"} if "exiles" in m.re.pattern else {})}], _one(group)


def edict_half(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"])  # (-- trigger other (wave 39A) -- ``half_own``: effects._choose_next counts it for each player)
    return [{"do": "edict", "who": who, "sel": _permanent_sel(m["sel"]), "n": {"half_own": m["r"]}, "label": m["sel"]}], _one(group)


def player_chooses(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"])
    if " with the " in m["sel"] and " among " in m["sel"]:  # -- group choices (wave 53D) -- "chooses a creature with the greatest mana value among creatures they control" (Summon: Valefor)
        greatest = _greatest_own(m["sel"] + " they control")
        if greatest is None:
            raise _Fail
        key = greatest.key()
    else:
        key = _permanent_sel(m["sel"])
    out: dict[str, Any] = {"do": "player_chooses", "who": who, "sel": key, "n": _amount(m["n"]), "label": m["sel"]}
    if m["upto"]:
        out["upto"] = True
    if m["sac"] or m["des"]:  # -- choose the rest (wave 11D) -- the choice is simultaneous (101.4); what wasn't chosen is sacrificed / destroyed
        out["rest"] = "sacrifice" if m["sac"] else "destroy"
    return [out], _one(group)


def choose_any(m: re.Match[str]) -> tuple[Effects, Any]:
    sel = selectors.parse(m["sel"] + (" your opponents control" if m["among"] else ""))
    if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or (m["among"] and sel.controller != "opponent"):
        raise _Fail
    out: dict[str, Any] = {"do": "player_chooses", "who": "each_player", "sel": sel.key(), "n": _amount(m["n"]), "label": m["sel"], "any": True}
    if m["upto"] or m["may"]:
        out["upto"] = True
    if m["start"]:
        out["start"] = "next" if m["start"].startswith("the next") else "you"
    return [out], None


# -- per-player choices (wave 30K) -- one choice for each kind of permanent, the rest sacrificed: "Each player chooses an artifact, a
# creature, an enchantment, and a planeswalker from among the nonland permanents they control, then sacrifices the rest." (Cataclysmic
# Gearhulk, Ajani), "… chooses from among the permanents they control an artifact, a creature, an enchantment, and a land, then sacrifices
# the rest." (Cataclysm), "… chooses a permanent they control of each permanent type and sacrifices the rest." (Liliana, Dreadhorde General),
# "… chooses from the lands they control a land of each basic land type, then sacrifices the rest." (Global Ruin) and, the ability's controller
# choosing for every player, "For each player, you choose from among the permanents that player controls an artifact, a creature, an
# enchantment, and a planeswalker. Then each player sacrifices all other nonland permanents they control." (Tragic Arrogance).
# CR 2026-09-25: 101.4 — each player makes all their choices (one per kind, in the order written, 101.4c) in APNAP order, each knowing the
# earlier ones (101.4b); 608.2d; then everything not chosen is sacrificed at once (701.21a). The kinds are separate choices: one permanent
# can be chosen for several (the rulings of Cataclysm, Cataclysmic Gearhulk, Tragic Arrogance, Liliana and Global Ruin) and a kind a player
# controls nothing of is skipped. The six permanent types are 110.4, the five basic land types 205.3i.
_KIND_LIST = r"an? [a-z]+(?:,? (?:and )?an? [a-z]+)*"
CHOOSE_KINDS = (rf"(?P<s>{CHOOSER}) chooses (?:(?P<kinds>{_KIND_LIST}) from among the (?P<scope>nonland permanents|permanents) they control"
                 rf"|from among the (?P<scope2>permanents) they control (?P<kinds2>{_KIND_LIST})), then sacrifices the rest"
                 r"(?:, you choosing them for each player when (?P<spent>(?:\{{[WUBRG]\}})+) was spent to cast this spell)?")  # (Mythos of Snapdax)
CHOOSE_FOR_EACH = (rf"for each player, you choose from among the permanents that player controls (?P<kinds>{_KIND_LIST}), "
                   r"then each player sacrifices all other (?P<scope>nonland permanents) they control")
# "Each player chooses any number of creatures they control with total power 4 or less, then sacrifices all other creatures they control."
# (Slaughter the Strong, Destined Confrontation): the answer is checked against the total (effects.check_total_power); a power below 0 subtracts
CHOOSE_POWER_CAP = (rf"(?P<s>{CHOOSER}) chooses any number of creatures they control with total power (?P<cap>\d+) or less, "
                    r"then sacrifices all other creatures they control")
CHOOSE_EACH_TYPE = rf"(?P<s>{CHOOSER}) chooses a permanent they control of each permanent type and sacrifices the rest"
CHOOSE_EACH_LAND = rf"(?P<s>{CHOOSER}) chooses from the lands they control a land of each basic land type, then sacrifices the rest"


def _kinds_effect(s: str | None, names: list[str], scope_phrase: str, spent: str | None = None, rest: str | None = "sacrifice") -> tuple[Effects, Any]:
    """A choice per kind among ``scope_phrase`` ("permanents" …), made by the player whose permanents they are (``s``) or, with no ``s``, by
    the ability's controller for each player; what the kinds left out is sacrificed."""
    from app.rules import conditions

    who, group = _chooser(s) if s else ("each_player", None)
    scope = selectors.parse(scope_phrase)
    if scope is None or replace(scope, types=(), not_types=()) != selectors.Selector() or len(scope.types) > 1:
        raise _Fail
    keys = []
    for name in names:
        kind = selectors.parse(name)
        if (kind is None or replace(kind, types=(), subtypes=()) != selectors.Selector() or bool(kind.types) == bool(kind.subtypes)
                or set(kind.types) & set(scope.not_types) or not set(kind.types) <= {"Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"}):
            raise _Fail  # (110.4: only a permanent type is a kind of permanent)
        keys.append(replace(kind, types=kind.types or scope.types, not_types=scope.not_types).key())
    if len(set(keys)) != len(keys):
        raise _Fail
    return [{"do": "player_chooses", "who": who, "sel": scope.key(), "sels": keys, "labels": names, "n": 1, "label": "permanent",
             **({"rest": rest} if rest else {}), **({} if s else {"by": "you"}),  # (wave 53D: rest None, Planar Overlay: the chosen are returned)
             # "If {B}{R} was spent to cast this spell, you choose the permanents for each player instead." (Mythos of Snapdax)
             **({"by_if": conditions.parse(f"{spent} was spent to cast this spell", objects=True)} if spent else {})}], _one(group)


def choose_kinds(m: re.Match[str]) -> tuple[Effects, Any]:
    g = m.groupdict()
    names = [re.sub(r"^an? ", "", x) for x in re.split(r", and |, | and ", g.get("kinds") or g.get("kinds2") or "")]
    return _kinds_effect(g.get("s"), names, g.get("scope") or g.get("scope2") or "permanents", g.get("spent"))


def choose_power_cap(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"])
    return [{"do": "player_chooses", "who": who, "sel": _permanent_sel("creature"), "n": 1, "label": "creatures", "rest": "sacrifice",
             "power_cap": int(m["cap"])}], _one(group)


def choose_each_type(m: re.Match[str]) -> tuple[Effects, Any]:
    return _kinds_effect(m["s"], ["artifact", "battle", "creature", "enchantment", "land", "planeswalker"], "permanents")  # (110.4)


def choose_each_land(m: re.Match[str]) -> tuple[Effects, Any]:
    return _kinds_effect(m["s"], ["Plains", "Island", "Swamp", "Mountain", "Forest"], "lands")  # (205.3i)


def reveal_hand(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"])
    if who in ("each_player", "each_opponent"):
        raise _Fail  # ("each opponent reveals their hand. You choose a card from it": from whose? not read)
    return [{"do": "reveal_hand", "who": who}], _one(group)


def reveal_some(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"])
    if (m["n"] is None) == (m["eq"] is None):
        raise _Fail
    n: Any = _amount(m["n"]) if m["n"] else values.parse_count(m["eq"])
    if n is None or (m["n"] is not None and not isinstance(n, int)):
        raise _Fail
    return [{"do": "reveal_some", "who": who, "n": n}], _one(group)


def choose_from_hand_gy(m: re.Match[str]) -> tuple[Effects, Any]:
    sel, sel2 = selectors.parse(m["sel"]), selectors.parse(m["sel2"] or m["sel"])
    if sel is None or sel2 is None or sel.player is not None or sel2.player is not None or not sel.card or not sel2.card \
            or sel.zones or sel2.zones:
        raise _Fail
    return [{"do": "choose_from_hand", "who": "you", "sel": sel.key(), "n": 1, "label": m["sel"], "optional": False,
             "gy_sel": selectors.replace(sel2, zones=("graveyard",)).key()}], None


def look_hand(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"])
    if who in ("each_player", "each_opponent"):
        raise _Fail  # (a private look at several hands: not read)
    chosen: Effects = []
    if m["ch"]:
        pick = re.fullmatch(CHOOSE_FROM_HAND, "you " + m["ch"])
        if pick is None:
            raise _Fail
        chosen = choose_from_hand(pick)[0]
    return [{"do": "reveal_hand", "who": who, "private": True}, *chosen], _one(group)


EXILE_FROM_HAND = rf"(?P<s>{CHOOSER}) exiles (?P<n>{AMT}) cards? from their (?P<z>hand|graveyard)(?P<fd> face down)?"  # (Aim for the Head, Witness the End; wave 15D: Relic of Progenitus)


def exile_from_hand(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"])
    n = _amount(m["n"])
    if not isinstance(n, int):
        raise _Fail
    return [{"do": "discard", "who": who, "n": n, "to": "exile", **({"face_down": True, "blind": True} if m["fd"] else {}), **({"zone": "graveyard"} if m["z"] == "graveyard" else {})}], _one(group)


def discard_all_revealed(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"])
    if not m["sel"] and not m["tail"]:
        raise _Fail
    sel = selectors.parse((m["sel"] + " " if m["sel"] else "") + "cards" + (m["tail"] or ""))
    if who in ("each_player", "each_opponent") or sel is None or sel.player is not None or not sel.card or sel.zones:
        raise _Fail
    return [{"do": "reveal_hand", "who": who}, {"do": "discard_named", "who": "revealed", "sel": sel.key()}], _one(group)


def choose_from_hand(m: re.Match[str]) -> tuple[Effects, Any]:
    sel = selectors.parse(m["sel"] + (m["tail"] or ""))
    if sel is None or sel.player is not None or not sel.card or sel.zones:
        raise _Fail  # (a card in the hand: "a nonland card", "an instant or sorcery card" — nothing else)
    n = 99 if m["any"] else _amount(m["n"])
    if not isinstance(n, int) and n != {"x": 1}:  # (wave 34C: "choose X cards from it" — the X announced, 107.3a; Mind Warp, Abandon Hope)
        raise _Fail
    return [{"do": "choose_from_hand", "who": "you", "sel": sel.key(), "n": n, "label": m["sel"],
             "optional": bool(m["may"] or m["upto"] or m["any"])}], None


def discard_named(m: re.Match[str]) -> tuple[Effects, Any]:
    return [{"do": "discard_named", "who": "it" if m["o"] in ("that card", "it") else "them"}], None


def choose_value(m: re.Match[str]) -> tuple[Effects, Any]:
    # CR 102.2, 806.1: in the supported free-for-all game, every other player is an opponent.
    what = "opponent" if m["what"] in ("another player", "one of your opponents") else m["what"]
    return [_chosen.type_choice(what) or _chosen.number_choice(what) or {"do": "choose_value", "who": "you", "what": what}], None  # (-- chosen filters (wave 53B) -- a card type, a number)


# -- card names (wave 49C) -- "Target player chooses a card name, then reveals the top card of their library." (Petra Sphinx, Vexing Arcanix): the target player names it as this resolves
CHOOSE_NAME_TARGET = rf"(?P<s>target player|target opponent) chooses (?:a|an) (?P<what>{_NAME_WHAT})"


def choose_name_target(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"])
    return [{"do": "choose_value", "who": who, "what": m["what"]}], _one(group)


def enters_choice(text: str) -> dict[str, Any] | None:
    """"As ~ enters, choose a color / a creature type / an opponent …" (614.1c: a replacement effect
    of the permanent; 614.12a: the choice is made before it enters; 603.6d: not a trigger). The
    definition for the engine's entering code (app/rules/engine.py, attachments.enter): the
    ``choose_value`` effect with ``remember`` writes the answer on the object as its public
    ``choices`` entry. Not registered as a template until the engine asks for it as the permanent
    enters — the choice must not be modeled as an enters trigger."""
    m = ENTERS_CHOICE.match(text)
    if m is None:
        return None
    if re.fullmatch(_BASIC_PAIR, m["what"]):  # (wave 53B: the answer is a basic land type; the two words are its options)
        return {"kind": "replacement", "replacement": "enters_choice",
                "effects": [{"do": "choose_value", "who": "you", "what": "basic land type", "options": m["what"].split(" or "), "remember": True}]}
    if re.fullmatch(_chosen.PAIRS, m["what"]):  # -- chosen filters (wave 53B) -- "choose white Citizen, blue Camarid, …": one answer, a color and its creature type (replacements.after_entry writes both records)
        from app.rules.creature_types import CREATURE_TYPES

        pairs = re.findall(r"(white|blue|black|red|green) ([A-Z][a-z]+)", m["what"])
        if not all(k in CREATURE_TYPES for _, k in pairs):
            return None
        return {"kind": "replacement", "replacement": "enters_choice",
                "effects": [{"do": "choose_value", "who": "you", "what": _chosen.PAIR_WHAT, "options": [f"{c.capitalize()} {k}" for c, k in pairs], "remember": True}]}
    if m["what"] == "two colors":
        return {"kind": "replacement", "replacement": "enters_choice",
                "effects": [{"do": "choose_value", "who": "you", "what": "color", "remember": True},
                            {"do": "choose_value", "who": "you", "what": "second color", "remember": True}]}
    if m["what"] == "two basic land types":  # -- chosen filters (wave 53B) -- Illusionary Terrain: the first, then the second (each its own public record, 614.12a)
        return {"kind": "replacement", "replacement": "enters_choice",
                "effects": [{"do": "choose_value", "who": "you", "what": "basic land type", "remember": True}, {"do": "choose_value", "who": "you", "what": "second basic land type", "remember": True}]}
    if m["what"] == "color and an opponent":
        return {"kind": "replacement", "replacement": "enters_choice",
                "effects": [{"do": "choose_value", "who": "you", "what": "color", "remember": True},
                            {"do": "choose_value", "who": "you", "what": "opponent", "remember": True}]}
    if m["what"] == "color and a creature type":  # -- chosen filters (wave 53B) -- two answers, each its own public record ("Chosen color", "Chosen creature type"), 614.12a
        return {"kind": "replacement", "replacement": "enters_choice",
                "effects": [{"do": "choose_value", "who": "you", "what": "color", "remember": True}, {"do": "choose_value", "who": "you", "what": "creature type", "remember": True}]}
    if m["what"] not in ("card type", "card type other than creature or land", CARD_TYPE_FIVE, "number between 1 and 10") \
            and (picked := _chosen.type_choice(m["what"]) or _chosen.number_choice(m["what"])) is not None:  # -- chosen filters (wave 53B) -- "choose a permanent type", "choose artifact, enchantment, instant, sorcery, or planeswalker", "choose a number"
        return {"kind": "replacement", "replacement": "enters_choice", "effects": [{**picked, "remember": True}]}
    if m["what"][:1].isupper():  # (wave 51C: the creature types it lists, each a real one; the choice is still "a creature type" for "the chosen type", offered from the list)
        from app.rules.creature_types import CREATURE_TYPES

        listed = re.split(r", or |, ", m["what"])
        if not all(t in CREATURE_TYPES for t in listed):
            return None
        return {"kind": "replacement", "replacement": "enters_choice",
                "effects": [{"do": "choose_value", "who": "you", "what": "creature type", "options": listed, "remember": True}]}
    return {"kind": "replacement", "replacement": "enters_choice",
            "effects": [{"do": "choose_value", "who": "you", "what": m["what"], "remember": True}]}


# -- animation (agent A2) --------------------------------------------------------------------------
# "~ becomes a 2/2 creature with all creature types until end of turn" (Mutavault), "until end of
# turn, this land becomes a 4/4 white and blue Elemental creature with flying and vigilance"
# (Celestial Colonnade), "target land becomes a 3/3 creature that's still a land" (Lifespark
# Spellbomb), "target permanent becomes an artifact in addition to its other types until end of
# turn" (Liquimetal Coating), "each noncreature artifact you control becomes a 4/4 artifact
# creature until end of turn" (Cyberdrive Awakener), "target noncreature artifact becomes an
# artifact creature with power and toughness each equal to its mana value until end of turn"
# (Karn's Touch), "target creature loses all abilities and becomes a blue Frog with base power and
# toughness 1/1" (Turn to Frog), "it becomes an artifact creature and gains haste" (Chandra, Spark
# Hunter), "target land you control becomes an X/X Elemental creature until end of turn, where X
# is the number of Allies you control" (Vastwood Animist). The separate sentence "It's still a
# land." is ``parse_still``. Read against CR 205.1a/205.1b (types set or retained), 105.3
# (colors), 613.1d-f / 613.4b (the layers each part applies in), 611.2a (no duration: the game).
# Not read (manual): "becomes a copy …" (a copy effect, layer 1), "becomes an Aura … Attach it"
# (Licids), "if ~ is an enchantment, it becomes …" (conditions), "with ward {2}" / protection
# (keywords the engine doesn't grant), a creature type not in the CR list.
_COLOR_LETTERS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_COLOR_LIST = r"(?:white|blue|black|red|green)(?:(?:,? and |, )(?:white|blue|black|red|green))*"
_BECOME = re.compile(
    r"^(?:(?P<lead>until end of turn, )|(?P<nlead>until your next turn, ))?(?:have )?(?P<o>.+?) "
    r"(?P<lose>loses all abilities and )?becomes? "
    r"(?:a|an) (?P<desc>.+?)"
    r"(?P<addition> in addition to its other (?P<addcolors>colors and )?(?:creature )?types)?"
    r"(?P<still> that(?:'s| are) still (?:an? )?(?:land|artifact|enchantment|planeswalker|creature)s?)?"  # (wave 19A: "that are still lands")
    r"(?: and gains? (?:(?P<gain>[a-z ,]+?)|(?P<gainq>\"[^\"]*\"(?:,? and \"[^\"]*\")*)))?"
    r"(?:(?P<trail> until end of turn)|(?P<ntrail> until your next turn))?"
    r"(?P<cbb> and can't be blocked this turn)?$")  # (cbb: wave 7E, Dimir Keyrune)
_DESC = re.compile(  # (each part optional, space-separated: "legendary 8/12 green Spirit artifact creature with …")
    r"^(?P<leg>legendary)?(?: ?(?P<p>X|\d+)/(?P<t>X|\d+))?(?: ?(?P<colors>colorless|" + _COLOR_LIST + r"))?"
    r"(?: ?(?P<subs>[A-Z][\w’'-]+(?: [A-Z][\w’'-]+)*))?(?: ?(?P<kinds>(?:artifact |enchantment )?(?:creature|artifact|enchantment)))?"
    r"(?: with (?P<with>.+))?$")
_QUOTED = re.compile(r'"([^"]+)"')
STILL_A = r"(?:it's still an?|they're still) (?P<t>land|artifact|enchantment|planeswalker|creature)s?"  # (wave 19A: "They're still lands.")
_STAT_WORDS = {"power": "power", "toughness": "toughness", "mana value": "mana_value"}


def _animation_keywords(text: str) -> list[str]:
    """"flying", "trample and haste", "vigilance, indestructible, and haste" → the keywords."""
    parts = [p.strip() for p in re.split(r",? and |, ", text) if p.strip()]
    from app.rules.statics import (
        GRANTABLE_KEYWORDS,  # -- animation keywords (wave 7E) -- infect, wither, landwalk … too
    )

    for p in parts:
        if (p not in selectors.KEYWORDS and p not in GRANTABLE_KEYWORDS) or p == "protection":
            raise _Fail
    return parts


def _with_list(text: str, out: dict[str, Any]) -> None:
    """The "with …" part: keywords, "all creature types", quoted abilities, "base power and
    toughness N/N", "power and toughness each equal to <value>"."""
    abilities = _QUOTED.findall(text)
    rest = _QUOTED.sub("", text)
    rest = re.sub(r"(?:,? and|,)$", "", rest.strip())  # (wave 49C: "with flying and \"…\"" leaves "flying and")
    m = re.search(r"(?:^|,? and |, )(?:base power and toughness (?P<p>\d+)/(?P<t>\d+)|"
                  r"power and toughness each equal to (?P<eq>.+))$", rest)
    if m:
        if out.get("p") is not None:
            raise _Fail
        if m["eq"]:
            out["p"] = out["t"] = _stat(m["eq"])
        else:
            out["p"], out["t"] = int(m["p"]), int(m["t"])
        rest = rest[: m.start()]
    # -- become (wave 19E) -- "with base power and toughness 8/8, flying, and first strike" (Figure of Destiny): the setting first
    m = re.match(r"base power and toughness (?P<p>\d+)/(?P<t>\d+)(?:,? and |, )(?P<rest>.+)$", rest) if m is None else None
    if m:
        if out.get("p") is not None:
            raise _Fail
        out["p"], out["t"] = int(m["p"]), int(m["t"])
        rest = m["rest"]
    if re.search(r"(?:^|,? and |, )all creature types$", rest):
        out["all_creature_types"] = True
        rest = re.sub(r"(?:,? and |, )?all creature types$", "", rest)
    rest = re.sub(r"(?:,? and |, )\s*$", "", rest.strip())
    # -- become (wave 30O) -- "becomes a blue Dragon with base power and toughness 4/4, loses all abilities, and gains flying" (Dragonshift):
    # the loss rides in the same layer-6 effect as the keywords (the effect's own grants apply after it, 613.7: Kenrith's Transformation)
    if (lose := re.search(r"(?:^|,? and |, )loses all abilities(?:,? and |, |,?$)", rest)) is not None and "lose_abilities" not in out:
        out["lose_abilities"] = True
        rest = (rest[: lose.start()] + (", " if rest[lose.end():] else "") + rest[lose.end():]).strip(", ")
    # -- animation keywords (wave 7E) -- "with ward {3}": a parameterised keyword is granted as its keyword line
    # (statics.keyword_line; the engine checks it as a quoted grant, scripts._become)
    for w in re.findall(r"(?:^|,? and |, )(ward \{[^}]+\})", rest):
        abilities.append(w[0].upper() + w[1:] + ".")
        rest = rest.replace(w, "", 1)
        rest = re.sub(r"^(?:,? and |, )|(?:,? and |, )$", "", rest.strip())
    # -- layers (wave 49C) -- "becomes a 3/4 Gargoyle creature with flying and protection from red" (Opal Guardian): protection from a colour is a keyword
    # ability line, granted like ward above
    for w in re.findall(r"(?:^|,? and |, )(protection from (?:white|blue|black|red|green))(?=$|,? and |, )", rest):
        abilities.append(w[0].upper() + w[1:] + ".")
        rest = rest.replace(w, "", 1)
        rest = re.sub(r"^(?:,? and|,)\s*|\s*(?:,? and|,)$", "", rest.strip()).strip()
    if rest == "protection from each of that spell's colors":
        abilities.append("Protection from each of that spell's colors")
        rest = ""
    if rest == "protection from each of your opponents":
        abilities.append("Protection from each of your opponents")
        rest = ""
    if rest:
        out["keywords"] = _animation_keywords(rest)
    if abilities:
        out["abilities"] = abilities


def parse_loses_all(text: str) -> tuple[Effects, Any] | None:
    """"All creatures lose all abilities until end of turn" / "Until end of turn, target creature loses all abilities" (613.1f)."""
    m = re.fullmatch(r"(?:(?P<lead>until end of turn), )?(?P<o>.+?) loses? all abilities(?P<trail> until end of turn)?", text.strip())
    if m is None or (m["lead"] and m["trail"]):
        return None  # (two durations: not Oracle wording)
    try:
        kind, key, group = ref(m["o"])
    except _Fail:
        return None
    if kind in ("players", "them") or (kind == "it" and m["o"].lower() != "it"):  # (wave 35D: a bare "it" is the target of the sentence before; "that creature" is read by the event grammar)
        return None
    timed = bool(m["lead"] or m["trail"])
    if not timed and kind not in ("target", "it"):
        return None  # -- counters (wave 41A) -- 611.2a: no duration, the game — read for a chosen target, or the object the sentence before moved ("It loses all abilities.", Hellcat),
        # only (its set is fixed as the effect begins, 611.2c); a group's isn't read
    return [{"do": "become", "who": _who(kind, key), "types": [], "lose_abilities": True, "duration": "end_of_turn" if timed else "permanent"}], _one(group)


def parse_become(text: str) -> tuple[Effects, Any] | None:
    """One "… becomes a …" sentence → ([become effect, (grant)], target) or None."""
    try:
        return _become(text.strip())
    except _Fail:
        return None


# -- land types set (wave 12D) -- "Target land becomes an Island until end of turn." (Tidal Warrior), "… becomes the basic land
# type of your choice …" (Reef Shaman), "… becomes a Plains or an Island …" (Tundra Kavu), "… becomes an Island in addition to
# its other types" (Sealock Monster). 305.7: setting a land's subtype to basic land types takes away its old land types and
# the abilities of its rules text and gives the new types' mana abilities (a layer 4 effect, 613.1d); "in addition" keeps
# them (205.1b). Only a target land is read (a group's choice, "Choose a basic land type. Each land … that type", is not).
_BASICS = "Plains|Island|Swamp|Mountain|Forest"
_BECOME_LAND = re.compile(
    rf"^(?:(?P<lead>until end of turn, ))?(?P<o>target .+?|it|that land) becomes? (?:(?:an? )?(?P<a>{_BASICS})(?: or an? (?P<b>{_BASICS}))?|"
    rf"(?P<pick>the basic land type of your choice))(?P<add> in addition to its other types)?(?P<trail> until end of turn)?$")


# -- activated wordings (wave 15D) -- "This creature becomes the creature type of your choice until end of turn." (Mistform
# Dreamer), "Target creature becomes the color of your choice until end of turn.": a public choice made as it resolves (608.2),
# then the same layer 4 / 5 effect as "becomes a Frog" / "becomes red" (205.1a: the chosen type replaces its creature types)
_BECOME_PICK = re.compile(r"^(?:until end of turn, )?(?P<o>.+?) becomes? the (?P<what>creature type|color or colors|color)(?: other than (?P<ex>[A-Z][a-z]+))? of your choice"
                          r"(?P<eot> until end of turn)?$")  # (-- activated other (wave 21E) -- no duration: for the rest of the game, 611.2a; Alchor's Tomb)


def _become_land(m: re.Match[str]) -> tuple[Effects, Any]:
    kind, key, group = ref(m["o"])
    # (-- durations (wave 30M) -- a pronoun too: "Put a flood counter on target land. That land becomes an Island in addition to its other types
    # for as long as it has a flood counter on it." — the land an earlier instruction named, resolved by scripts.resolve_it)
    if (kind != "it" and (kind != "target" or group is None or '"types":["Land"]' not in key)) or (m["lead"] and m["trail"]):
        raise _Fail
    e: dict[str, Any] = {"do": "become", "who": "target" if kind == "target" else "it", "types": [],
                         "duration": "end_of_turn" if m["lead"] or m["trail"] else "permanent"}
    if m["pick"] or m["b"]:
        e["land_pick"] = list(_BASICS.split("|")) if m["pick"] else [m["a"], m["b"]]
    else:
        e["land_types"] = [m["a"]]
    if m["add"]:
        e["retain"] = True  # 205.1b
    return [e], _one(group)


def _become_forms(text: str) -> str:
    """-- layers (wave 22A) -- other wordings of the effects below, rewritten to the one this grammar reads (the same layers, 613.1d-f):
    "Artifacts you control become artifact creatures with base power and toughness 5/5 until end of turn." (Tezzeret the Seeker),
    "… has base power and toughness 5/5 and becomes a Dinosaur in addition to its other creature types." (Allosaurus Shepherd),
    "… becomes a creature in addition to its other types and has base power and base toughness each equal to its mana value." (Zur),
    "… loses all abilities, becomes a Coward in addition to its other types, and has base power and toughness 1/1." (Curious Colossus)"""
    text = re.sub(r"^(?P<pre>.+? becomes?) (?P<k>(?:artifact |enchantment )?)creatures with (?=base power and toughness \d+/\d+)",
                  r"\g<pre> a \g<k>creature with ", text)
    text = re.sub(r"^(?P<lead>until end of turn, )?(?P<o>.+?) has base power and toughness (?P<p>\d+|X)/(?P<t>\d+|X) and becomes an? "
                  r"(?P<s>[A-Z][a-z]+) in addition to its other (?:creature )?types$", r"\g<lead>\g<o> becomes a \g<p>/\g<t> \g<s> in addition to its "
                  r"other creature types", text)
    text = re.sub(r"^(?P<o>.+?) becomes? a creature in addition to its other types and has base power and base toughness each equal to "
                  r"its mana value$", r"\g<o> becomes a creature with power and toughness each equal to its mana value in addition to its other "
                  r"types", text)
    return re.sub(r"^(?P<o>.+?) loses all abilities, becomes an? (?P<s>[A-Z][a-z]+) in addition to its other types, and has base power and "
                  r"toughness (?P<p>\d+)/(?P<t>\d+)$", r"\g<o> loses all abilities and becomes a \g<p>/\g<t> \g<s> in addition to its other types",
                  text)


# -- layers (wave 30O) -- "This creature's base power and toughness become 4/2 until end of turn." (Mirkwood Meditator), "You may have the base
# power and toughness of target Human you control become equal to this creature's power and toughness until end of turn." (Exuberant Wolfbear),
# "Its base power and toughness become equal to Galion's power and toughness until end of turn.": the same layer 7b setting (613.4b, 208.4a) as
# "<object> has base power and toughness …", which ``BASE_PT`` / ``BASE_EQ`` read. Outside quotes only (a granted ability keeps its words).
_BASE_OF = re.compile(r"(?:\bhave )?\bthe base power( and toughness)? of (?P<o>[^.,\"]+?) becomes? (?=\S)")
_BASE_OWN = re.compile(r"(?<![\w'])(?:have )?(?:(?P<o>~|that creature|that permanent)'s|(?P<it>[Ii]ts)) base (?P<w>power|toughness)( and toughness)? becomes? (?=\S)")  # (-- block events (wave 53C) -- also one stat alone: Sentinel's "base toughness")


def base_become(text: str) -> str:
    """The wordings above as "<object> has base power [and toughness] <value>" (unchanged when it isn't one of them)."""
    def of(m: re.Match[str]) -> str:
        return f"{m['o']} has base power{m[1] or ''} "

    def own(m: re.Match[str]) -> str:
        return f"{m['o'] or ('It' if m['it'] == 'Its' else 'it')} has base {m['w']}{m[4] or ''} "

    parts = text.split('"')
    return '"'.join(_BASE_OWN.sub(own, _BASE_OF.sub(of, p)) if i % 2 == 0 else p for i, p in enumerate(parts))


def _become(text: str) -> tuple[Effects, Any]:
    from app.rules.creature_types import CREATURE_TYPES

    text, rider = _with_rider(_become_forms(text))
    # -- static_other sweep (wave 19A) -- "All lands you control become 2/2 Elemental creatures with reach …" (Sylvan Awakening): a group
    # becomes the plural of the singular wording read below
    # -- trigger other (wave 41C) -- also without a P/T and with a card type before "creatures": "Vehicles you control become artifact creatures until end of
    # turn" (The Thanos-Copter), "Treasures you control become 3/3 Construct Assassin artifact creatures in addition to their other types until end of turn"
    # (Vihaan, Goldwaker): the singular wording, "their other" → "its other" (205.1b)
    plural = re.sub(r"^(?P<pre>.+? becomes?) (?P<d>(?=\d|[A-Z]|artifact |enchantment )(?:\d+/\d+ )?(?:[A-Z][\w'-]+ )*(?:(?:artifact|enchantment) )?)creatures\b",
                    r"\g<pre> a \g<d>creature", text)
    if plural != text:
        text = plural.replace(" in addition to their other", " in addition to its other")
    if rider is None and (land := _BECOME_LAND.fullmatch(text)) is not None:
        return _become_land(land)
    if rider is None and (pick := _BECOME_PICK.fullmatch(text)) is not None:  # -- activated wordings (wave 15D) --
        kind, key, group = ref(pick["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "become", "who": _who(kind, key), "types": [], "pick": pick["what"], "duration": "end_of_turn" if pick["eot"] else "permanent",
                 **({"not": pick["ex"]} if pick["ex"] else {})}], _one(group)
    m = _BECOME.fullmatch(text)
    if m is None and rider is None and (c := _BECOME_COLOR.fullmatch(text)) is not None:
        return _become_color(c)  # -- static wordings (wave 6E) --
    if m is None:
        raise _Fail
    d = _DESC.fullmatch(m["desc"])
    if d is None:
        raise _Fail
    tg: list[dict[str, Any]] = []
    if (controlled := target_controls(m["o"], tg)) is not None:  # -- activated other (wave 44D) -- "All lands target player controls become 3/3 creatures" (Jolrael)
        who, group = controlled, tg[0]
    else:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        who = _who(kind, key)
    kinds = (d["kinds"] or "").split()
    types = [k.capitalize() for k in kinds]
    subs = (d["subs"] or "").split()
    if any(s not in CREATURE_TYPES for s in subs) or ("Creature" not in types and (subs or d["p"])
                                                       and types):
        raise _Fail  # (not a creature type; a P/T or creature type for something that isn't a creature)
    if not types and not subs:
        raise _Fail
    e: dict[str, Any] = {"do": "become", "who": who, "types": types}
    if m["addition"] or m["still"] or types == ["Artifact", "Creature"]:
        e["retain"] = True  # 205.1b
    if subs:
        # 205.1b: "in addition to its other types" / "that's still a …" retain every prior subtype
        # (the creature types named are added); "[creature type] artifact creature" or a plain
        # "becomes a … creature" replaces its creature types (205.1a/205.1b last sentence)
        e["add_creature_types" if (m["addition"] or m["still"]) else "creature_types"] = subs
    if d["leg"]:
        e["legendary"] = True
    if d["colors"]:
        colors = [] if d["colors"].strip() == "colorless" else \
            [_COLOR_LETTERS[c] for c in re.split(r",? and |, ", d["colors"].strip())]
        if m["addcolors"]:
            e["add_colors"] = colors
        else:
            e["colors"] = colors
    if d["p"]:
        e["p"] = _apply(_amount(d["p"]), rider) if d["p"] == "X" else int(d["p"])
        e["t"] = _apply(_amount(d["t"]), rider) if d["t"] == "X" else int(d["t"])
    elif rider is not None:
        raise _Fail
    if d["with"]:
        _with_list(d["with"], e)
    if m["lose"]:
        e["lose_abilities"] = True
    if m["lead"] or m["trail"]:
        e["duration"] = "end_of_turn"
    elif m["nlead"] or m["ntrail"]:
        e["duration"] = "next_turn"  # 611.2a; ends as its controller's next turn begins (500.4, app/rules/delayed.py)
    else:
        e["duration"] = "permanent"  # 611.2a
    out: Effects = [e]
    if m["gain"]:
        if e["duration"] == "permanent":  # -- become (wave 19E) -- "… becomes a 3/2 Human Faerie Rogue and gains double strike." (Kellan): the same effect
            e["keywords"] = [*e.get("keywords", []), *_animation_keywords(m["gain"])]
        elif e["duration"] != "end_of_turn":
            raise _Fail
        else:
            out.append({"do": "grant", "who": who, "keywords": _animation_keywords(m["gain"])})
    if m["cbb"]:  # -- animation keywords (wave 7E) -- "… artifact creature until end of turn and can't be blocked this turn"
        if not m["trail"] and not m["lead"]:
            raise _Fail
        out.append({"do": "restrict", "who": who, "rules": ["cant_be_blocked"]})
    if m["gainq"]:  # -- quoted grants (wave 2D) -- "… becomes a Bear creature in addition to its other types and gains "…""
        e["abilities"] = [*e.get("abilities", []), *_QUOTED.findall(m["gainq"])]  # (the same layer-6 effect, 613.6)
    return out, _one(group)


# -- static wordings (wave 6E) -- "Target creature becomes red and gains haste until end of turn." (Crimson Wisps): a
# color-changing effect (layer 5, 613.1e) whose colors replace the object's (105.3), locked in to the objects (611.2c)
# -- activated other (wave 21E) -- "Target creature gains flying and becomes blue until end of turn." (Disciple of Kangee), "Target
# permanent becomes blue in addition to its other colors until end of turn." (Indigo Faerie: the color is added, 105.3, 613.1e)
_BECOME_COLOR = re.compile(r"^(?:(?P<lead>until end of turn, ))?(?P<o>.+?)(?: gains? (?P<pre>[a-z ]+?) and)? becomes? (?P<colors>colorless|all colors|"
                           + _COLOR_LIST + r")(?P<add> in addition to its other colors)?"
                           r"(?: and gets (?P<pp>[+−-]\d+)/(?P<tt>[+−-]\d+))?"  # (wave 26A: Viridescent Wisps)
                           r"(?: and gains? (?P<gain>[a-z ]+?))?(?P<trail> until end of turn)?$")


def _become_color(m: re.Match[str]) -> tuple[Effects, Any]:
    kind, key, group = ref(m["o"])
    # -- color lace (wave 46B) -- no duration: for the rest of the game (611.2a; Thoughtlace); a rider ("and gains …") would need its own duration
    perm = not (m["lead"] or m["trail"])
    if kind == "players" or (perm and (m["pp"] or m["gain"] or m["pre"])):
        raise _Fail
    who = _who(kind, key)
    colors = [] if m["colors"] == "colorless" else list(_COLOR_LETTERS.values()) if m["colors"] == "all colors" \
        else [_COLOR_LETTERS[c] for c in re.split(r",? and |, ", m["colors"])]
    if m["add"] and not colors:
        raise _Fail
    out: Effects = [{"do": "become", "who": who, "types": [], **({"add_colors": colors} if m["add"] else {"colors": colors}),
                     "duration": "permanent" if perm else "end_of_turn"}]
    if m["pp"]:
        out.append({"do": "pump", "who": who, "p": _signed(m["pp"]), "t": _signed(m["tt"])})
    if m["gain"] or m["pre"]:
        from app.rules.statics import GRANTABLE_KEYWORDS  # (the keywords a grant carries out, 613.1f)

        if m["gain"] and m["pre"]:
            raise _Fail
        kws = [p.strip() for p in re.split(r",? and |, ", m["gain"] or m["pre"]) if p.strip()]
        if not kws or any(k not in GRANTABLE_KEYWORDS for k in kws):
            raise _Fail
        out.append({"do": "grant", "who": who, "keywords": kws})
    return out, _one(group)


BASE_PT = (r"(?:(?P<lead>until end of turn|until your next turn), )?(?P<o>.+?)(?: (?P<lose>loses? all abilities and))? (?:has|have) base "
           r"(?:power and toughness (?P<p>\d+|X)/(?P<t>\d+|X)(?P<more>(?:,? and |, )gains? [a-z0-9 ,]+?)?(?:, where X is (?P<xdef>[^\"]+?))?"  # (X: wave 4K)
           # -- activated sweep (wave 17B) -- "has base power 4 and gains trample" (Turtle-Duck): one of the two, layer 7b (613.4b)
           rf"|(?P<one>power|toughness) (?P<n>\d+)(?: and gains? (?P<gk>{_KW_ONLY}))?)"
           r"(?: (?P<trail>until end of turn|until your next turn))?")


def parse_base_pt(m: re.Match[str]) -> tuple[Effects, Any]:
    """"Target creature has base power and toughness 3/3 until end of turn" (Restless Vinestalk):
    layer 7b only (613.4b); nothing else about it changes. With no duration it lasts the game (611.2a)."""
    if m["lead"] and m["trail"]:
        raise _Fail
    kind, key, group = ref(m["o"])
    if kind == "players":
        raise _Fail
    when = m["lead"] or m["trail"] or ""
    duration = {"until end of turn": "end_of_turn", "until your next turn": "next_turn"}.get(when, "permanent")
    # -- X sized by a count (wave 4K) -- "have base power and toughness X/X [and gain all creature types][, where X is …]"
    # (Mirror Entity, Jolrael): X read once as the effect begins (608.2h), for the objects then (611.2c); 613.4b
    x: Any = {"x": 1}
    if m["xdef"]:
        import json

        x = x_definition(m["xdef"])
        if x is None or "X" not in (m["p"], m["t"]) or '"it"' in json.dumps(x):
            raise _Fail
    if m["one"]:
        if duration != "end_of_turn" or m["lose"]:
            raise _Fail
        who = _who(kind, key)
        one: Effects = [{"do": "become", "who": who, "types": [], "duration": duration,
                         ("p" if m["one"] == "power" else "t"): int(m["n"])}]
        if m["gk"]:
            one.append({"do": "grant", "who": who, "keywords": _keyword_list(m["gk"])})
        return one, _one(group)
    if (m["more"] or m["xdef"]) and duration == "permanent":
        raise _Fail
    out: dict[str, Any] = {"do": "become", "who": _who(kind, key), "types": [],
                           "p": x if m["p"] == "X" else int(m["p"]), "t": x if m["t"] == "X" else int(m["t"]), "duration": duration}
    more: Effects = []
    for part in re.split(r"(?:,? and |, )(?=gains? )", re.sub(r"^(?:,? and |, )", "", m["more"] or "")) if m["more"] else ():
        # -- layers (wave 30O) -- "has base power and toughness 4/4, gains all creature types, and gains flying" (Wings of Velis Vel), "…
        # 10/10 and gains trample" (Oko): the grants of the same sentence, each its own layer-6 effect on the objects locked in now (611.2c, 613.6)
        what = re.sub(r"^gains? ", "", part)
        if what == "all creature types":
            out["all_creature_types"] = True
        elif duration == "end_of_turn":
            more.append({"do": "grant", "who": out["who"], "keywords": _animation_keywords(what)})
        else:
            raise _Fail
    if m["lose"]:  # -- static_other sweep (wave 19A) -- "loses all abilities and has base power and toughness 0/1" (Ovinize): layers 6 and 7b
        out["lose_abilities"] = True
    return [out, *more], _one(group)


# -- layers (wave 30O) -- "has base power and toughness equal to that creature's power and toughness" / "base power equal to the number of Towns you
# control": a base power and/or toughness set to a value (613.4b), read once as the effect begins (611.2d, 608.2h: a specific object's
# characteristic is used as it is then, or as it last existed). "that creature's" names another object (``ante``, bound like a pump's "it":
# scripts.resolve_it); "its" would be the object being set, which nothing reads here.
BASE_EQ = (r"(?:(?P<lead>until end of turn|until your next turn), )?(?P<o>.+?) (?:has|have) base (?P<what>power and toughness|power|toughness) (?:equal to |(?=\d+ plus ))"
           r"(?P<v>.+?)(?: (?P<trail>until end of turn|until your next turn))?")


def parse_base_eq(m: re.Match[str]) -> tuple[Effects, Any]:
    import json

    if m["lead"] and m["trail"] or re.search(r"\bits\b", m["v"]):
        raise _Fail
    kind, key, group = ref(m["o"])
    if kind == "players":
        raise _Fail
    when = m["lead"] or m["trail"] or ""
    duration = {"until end of turn": "end_of_turn", "until your next turn": "next_turn"}.get(when, "permanent")
    both = re.fullmatch(r"(?P<s>.+?)'s power and toughness", m["v"]) if m["what"] == "power and toughness" else None
    if both is not None:
        p, t = _stat(f"{both['s']}'s power"), _stat(f"{both['s']}'s toughness")
    else:
        p = t = _stat(m["v"])
    e: dict[str, Any] = {"do": "become", "who": _who(kind, key), "types": [], "duration": duration}
    if m["what"] != "toughness":
        e["p"] = p
    if m["what"] != "power":
        e["t"] = t
    if '"it"' in json.dumps([p, t]):
        e["ante"] = True  # (scripts.resolve_it binds "that creature's power" to the object an earlier instruction or the trigger named)
    return [e], _value_target([p, t], _one(group))  # ("… equal to target creature's power": the sentence's one target, 115.1)


def parse_still(m: re.Match[str]) -> tuple[Effects, Any]:
    """"It's still a land.": the sentence before it retains the object's types (205.1b)."""
    return [{"do": "still_a", "type": m["t"].capitalize()}], None


# -- reanimation (wave 3R) -----------------------------------------------------------------------------
# "Put target creature card from a graveyard onto the battlefield under your control", "return this card
# from your graveyard to your hand", "return a creature card from your graveyard to the battlefield"
# (chosen on resolution, 608.2d), "return up to two creature cards …", "… at random …". A card enters
# under the control of the player the effect names, by default the one instructed (110.2a); a card
# returns to its OWNER's hand (400.3).
_RA_UNDER = r"(?: under (?P<u>your|its owner's|their owner's|their owners') control)?"
# -- refused zones/sized (wave 3R4) -- "… with a finality counter on it": it enters with it (122.6, 122.1h)
_RA_WITH = (r"(?: with (?:(?:an?|one) (?P<add1>additional )?(?P<ck>[+-]\d+/[+-]\d+|[a-z]+) counter|"
            # -- recursion & tutors (wave 4M) -- "… with two additional +1/+1 counters on it" (Rakdos Joins Up): they
            # enter with them (122.6; "additional": besides any it would enter with, 614.1c)
            r"(?P<cn>two|three|four|five) (?P<add2>additional )?(?P<ck2>\+1/\+1|-1/-1) counters) on (?:it|him|her|~))?")  # (wave 30L: a named card's "on him" / "on her" (scripts._self_pronouns writes "~"): Winter Soldier, Gallia)
# "… attached to this creature / that creature" (303.4f, 303.4i, 301.5e): app/rules/effects._return_cards
# -- attached events (wave 25D) -- also "attached to enchanted creature" (Mantle of the Ancients) and "attached to target creature [you control]"
# (Gryff's Boon: a target of the ability, chosen with it, 115.1)
_RA_HOST = (r"(?: attached to (?P<host>this creature|~|that creature|enchanted creature|a creature you control|target creature(?: you control)?(?: with power \d+ or less)?"
             r"|target opponent|target creature or planeswalker an opponent controls))?")  # (-- block events (wave 53C) -- a Curse / Aura the other face of a double-faced card, 712.14a)
# -- enter attacking (wave 30P) -- "… tapped and attacking [that player]" before "under your control" or after it
# ("put target creature card from that player's graveyard onto the battlefield under your control tapped and attacking that player")
_RA_TAPPED = rf"(?P<t> tapped(?P<atk> and attacking{token_grammar.AT})?)?"
_RA_TAPPED2 = rf"(?P<t2> tapped(?P<atk2> and attacking{token_grammar.at_re('2')})?)?"
_RA_RETURN = re.compile(rf"return (?P<o>.+?) to (?:(?P<h>your hand|its owner's hand|their owner's hand|their owners' hands|their hand)|"
                        rf"the battlefield{_RA_TAPPED}(?P<xf> transformed)?(?P<fd> face down)?{_RA_UNDER}{_RA_TAPPED2}{_RA_WITH}{_RA_HOST})")  # (face down: wave 18A, 708.4; transformed: wave 37B, 712.14a)
_RA_PUT = re.compile(rf"put (?P<o>.+?) onto the battlefield{_RA_TAPPED}{_RA_UNDER}{_RA_TAPPED2}{_RA_WITH}{_RA_HOST}")
_RA_ZONE = r"(?:your graveyard|your hand (?:or|and/or) graveyard|a graveyard|an opponent's graveyard|that player's graveyard|their graveyard)"  # (-- reanimation (wave 37B) -- Danitha: "from your hand or graveyard"; -- player-relative selectors (wave 53A) -- "that player's / their graveyard": the player named before)
_RA_CHOICE = re.compile(rf"(?:(?:an?|one) |up to (?P<upto>{AMT}) |(?P<any>any number of )|(?P<n>{AMT}) )(?P<what>(?:[^,]|,(?= [^,]+, or | or ))+?)(?P<rand> at random)?"  # (wave 50I: "an artifact, instant, or sorcery card")
                        rf" from (?P<z>{_RA_ZONE})")
_RA_SELF = re.compile(r"(?:this card|~) from your graveyard")
_RA_SELF_EXILE = re.compile(r"(?:this card|~) from your graveyard or from exile")  # -- activated other (wave 42C) -- 113.6m: Mister Immortal works from either zone
# -- activated from hand / command zone (wave 27D) -- "Put this card from your hand onto the battlefield." (Talon Gates of Madara, Urban
# Retreat), "Put ~ onto the battlefield from the command zone." (Derevi): the source itself, only while it is still that object there
_RA_SELF_ZONE = re.compile(r"put (?:(?P<h>this card|~) from your hand onto the battlefield|~ onto the battlefield from the command zone)")
_RA_LIB = re.compile(r"put (?P<o>.+? from your graveyard) on top of your library")  # (wave 3R4)
_RA_LIB_NTH = re.compile(r"put (?:this card|~) from your graveyard into your library (?P<n>second|third) from the top")
# -- reanimation (wave 37B) -- "the top creature card of your graveyard" (Shallow Grave, Corpse Dance, Mistmoon Griffin): nothing is chosen, the topmost
# creature card in the graveyard order (404.1: the graveyard is kept in order, face up); "this card and target land card from your graveyard"
# (Sandman, Slimefoot and Squee): the source and a target of the ability, entering together (one instruction, 608.2c)
_RA_TOP = re.compile(r"the top (?P<what>[^,]+? card) of your graveyard")
_RA_SELF_AND = re.compile(r"(?:this card|~) and (?P<rest>.+? from your graveyard)")
_RA_TARGET_RANDOM = re.compile(r"put an? (?P<what>[\w -]+? card) at random from target (?P<t>opponent|player)'s graveyard onto the battlefield under your control")  # (wave 42C)
_PERMANENT_TYPES = frozenset({"Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle"})


def _hand_or_graveyard(sel: Any) -> bool:
    """-- reanimation (wave 37B) -- a selector over "your hand or graveyard" for a permanent card (an instant or sorcery card can't enter the battlefield)."""
    return (sel is not None and sel.card and sel.zones == ("hand", "graveyard") and sel.zone_owner == "you" and not sel.player
            and bool(sel.types or sel.subtypes) and set(sel.types) <= _PERMANENT_TYPES)


def _graveyard_cards(key: str) -> bool:
    sel = selectors.from_key(key) if key.startswith(selectors.PREFIX) else None
    return sel is not None and sel.card and sel.zones == ("graveyard",) and not sel.player


def gy_to_library(text: str) -> tuple[Effects, Any] | None:
    """-- refused zones/sized (wave 3R4) -- "[You may] put a land card from your graveyard on top of your library" (one
    card, chosen on resolution: 608.2d) and "put this card from your graveyard on top of your library" (113.6m: works
    from the graveyard). None for anything else ("put target … on top": the older grammar)."""
    text = text[len("then "):] if text.startswith("then you may ") else text  # ("Then you may …": "then" only orders)
    may = text.startswith("you may ")
    nth = _RA_LIB_NTH.fullmatch(text)  # -- activated sweep (wave 26C) -- "put this card from your graveyard into your library third from the top" (Bookwurm)
    if nth is not None and not may:
        return [{"do": "to_library", "who": "self_gy", "place": {"second": 2, "third": 3}[nth["n"]]}], None
    lib = _RA_LIB.fullmatch(text[len("you may "):] if may else text)
    if lib is None:
        return None
    if _RA_SELF.fullmatch(lib["o"]):
        return ([{"do": "to_library", "who": "self_gy", "place": "top"}], None) if not may else None
    c = _RA_CHOICE.fullmatch(lib["o"])
    if c is None or c["upto"] or c["n"] or c["any"] or c["rand"] or c["z"] != "your graveyard":
        return None  # (several cards: their order isn't read here)
    words = re.sub(r"\bcards\b", "card", c["what"])
    sel = selectors.parse(f"{words} from {c['z']}")
    if sel is None or not _graveyard_cards(sel.key()):
        return None
    return [{"do": "return_choice", "to": "library_top", "sel": sel.key(), "n": 1, "upto": may, "random": False,
             "label": words, **({"optional": True} if may else {})}], None


def _reanimation_compound(obj: str, effect: dict[str, Any]) -> tuple[Effects, Any] | None:
    """-- reanimation (wave 10A) -- see reanimation_forms: "X card and Y card from your graveyard" → one instruction per kind
    (``effect`` is the shared destination: to hand / battlefield). None for anything not exactly that shape."""
    zone = " from your graveyard"
    if not obj.endswith(zone):
        return None
    body = obj[: -len(zone)]
    if re.search(r"\btargets?\b", body):
        parts = re.split(_AND_TARGET, body)
        if len(parts) < 2:
            return None
        whos: list[str] = []
        groups: list[dict[str, Any]] = []
        for part in parts:
            try:
                kind, key, group = ref(part + zone)
            except _Fail:
                return None
            if kind != "target" or group is None or not _graveyard_cards(key) or group.get("another"):
                return None
            whos.append("target" if not groups else f"target:{len(groups)}")
            groups.append(group)
        return [{**effect, "who": w} for w in whos], _out(groups)
    parts = re.split(r" and (?=(?:an?|up to \w+) )", body)
    if len(parts) < 2:
        return None
    out: list[dict[str, Any]] = []
    for part in parts:
        c = _RA_CHOICE.fullmatch(part + zone)
        if c is None or c["n"] or c["any"] or c["rand"] or c["z"] != "your graveyard" or (c["upto"] and c["upto"] != "one"):
            return None
        words = re.sub(r"\bcards\b", "card", c["what"])
        sel = selectors.parse(f"{words} from {c['z']}")
        if sel is None or not _graveyard_cards(sel.key()) or "card" not in words.split():
            return None
        out.append({**effect, "do": "return_choice", "sel": sel.key(), "n": 1, "upto": bool(c["upto"]), "random": False,
                    "label": words})
    return out, None


def exile_choice(text: str) -> tuple[Effects, Any] | None:
    """-- if you do (wave 25C) -- "Exile an instant or sorcery card [at random] from your graveyard": one card, chosen on resolution (608.2d)
    or at random, nothing targeted; recorded for "it" / "that card" after (effects.return_choice, to "exile")."""
    late = text.endswith(" at random")  # ("… from your graveyard at random")
    public_pick = re.fullmatch(r"choose an? exiled (?P<what>card(?: .+)?)", text)
    if public_pick is not None:
        sel = selectors.parse(public_pick["what"] + " in exile")
        if sel is None or not sel.card or sel.player is not None or sel.zones != ("exile",):
            return None
        return [{"do": "return_choice", "to": "choose", "sel": sel.key(), "n": 1, "upto": False,
                 "random": False, "label": "exiled " + public_pick["what"]}], None
    pick = re.fullmatch(r"choose (?:an?|one) (?P<what>[^,]+? card) in your graveyard", text)  # "Choose an instant or sorcery card in your graveyard."
    if pick is not None:  # (nothing moves: the card is chosen on resolution, 608.2d, and "it" after names it, effects._return_cards "choose")
        sel = selectors.parse(f"{pick['what']} from your graveyard")
        if sel is None or not _graveyard_cards(sel.key()) or "card" not in pick["what"].split():
            return None
        return [{"do": "return_choice", "to": "choose", "sel": sel.key(), "n": 1, "upto": False, "random": False, "label": pick["what"]}], None
    c = _RA_CHOICE.fullmatch(text[len("exile "):len(text) - len(" at random") * late]) if text.startswith("exile ") else None
    if c is None or c["z"] != "your graveyard" or c["upto"] or c["n"] or c["any"]:
        return None
    words = re.sub(r"\bcards\b", "card", c["what"])
    sel = selectors.parse(f"{words} from {c['z']}")
    if sel is None or not _graveyard_cards(sel.key()) or "card" not in words.split():
        return None
    return [{"do": "return_choice", "to": "exile", "sel": sel.key(), "n": 1, "upto": False, "random": bool(c["rand"] or late), "label": words}], None


def reanimation_forms(text: str) -> tuple[Effects, Any] | None:
    """The graveyard-return wordings above; None when the sentence is not one of them (the older
    grammar then reads it, or it stays manual)."""
    text = text[len("then "):] if text.startswith("then you may ") else text  # (wave 3R4: "Then you may return …")
    if (tr := _RA_TARGET_RANDOM.fullmatch(text)) is not None:  # -- activated other (wave 42C) -- Tariel: a random card of the target player's graveyard
        sel = selectors.parse(f"{tr['what']} from a graveyard")
        if sel is None or not _graveyard_cards(sel.key()):
            return None
        return [{"do": "return_choice", "who": f"graveyard_of:target|{sel.key()}", "n": 1, "upto": False, "random": True, "label": tr["what"],
                 "to": "battlefield", "tapped": False, "under": "you"}], SELECTORS_TARGET[f"target {tr['t']}"]
    if (z := _RA_SELF_ZONE.fullmatch(text)) is not None:  # -- activated from hand / command zone (wave 27D) -- 113.6m
        return [{"do": "return_card", "to": "battlefield", "tapped": False, "under": "you",
                 "who": "self_hand" if z["h"] else "self_command"}], None
    # -- recursion & tutors (wave 4M) -- "Then you return up to two creature cards …" (Unseal the Necropolis), "Then you put
    # a creature card from a graveyard onto the battlefield under your control" (Extract from Darkness): the subject
    # is the one instructed anyway (110.2a)
    text = re.sub(r"^you (return|put) (?=(?:an?|one|up to \w+|\w+) [^,]*?cards? from )", r"\1 ", text)
    may = text.startswith("you may ")  # (mid-ability: "Mill three cards, then you may return a creature card …")
    if may:
        text = text[len("you may "):]
    put = _RA_PUT.fullmatch(text)
    m = put or _RA_RETURN.fullmatch(text)
    if m is None:
        return None
    hand = not put and bool(m["h"])
    effect: dict[str, Any] = {"do": "return_card", "to": "hand" if hand else "battlefield"}
    host_group: dict[str, Any] | None = None
    if not hand:  # (110.2a: the one instructed controls it unless the text says "its owner's")
        atk = m["atk"] or m["atk2"]
        effect.update(tapped=bool(m["t"] or m["t2"]), under="owner" if m["u"] and m["u"] != "your" else "you")
        if m.groupdict().get("xf"):  # -- reanimation (wave 37B) -- 712.14a: "Return this card from your graveyard to the battlefield transformed" (Garland): it enters with its back face up
            effect["transformed"] = True
        if m.groupdict().get("fd"):  # -- hidden exile (wave 18A) -- "return it to the battlefield face down" (708.4: a 2/2 face-down creature)
            effect["face_down"] = True
        if m["ck"]:  # -- refused zones/sized (wave 3R4) --
            if m["ck"] in values.UNMODELED_COUNTERS:
                return None
            effect["counter"] = m["ck"]
        if m["ck2"]:  # -- recursion & tutors (wave 4M) --
            effect.update(counter=m["ck2"], counter_n=values.NUMBERS[m["cn"]])
        if atk:  # -- refused zones/sized (wave 3R4) -- 508.4 (effects._return_cards → refused_zones.enter_attacking)
            if m["u"] and m["u"] != "your":
                return None  # (under its owner's control: 506.3b, not read)
            effect["attacking"] = True
            if (at := token_grammar.at_spec(m) or token_grammar.at_spec(m, "2")) is not None:  # -- enter attacking (wave 30P) -- "… attacking that player"
                effect["at"] = at
        if m["host"] == "a creature you control":
            host_selector = selectors.parse("creatures you control")
            assert host_selector is not None
            effect["host_choice"] = host_selector.key()
        elif m["host"]:  # -- refused zones/sized (wave 3R4) -- "that creature": a trigger's object only (scripts._attached_host)
            effect["host"] = {"that creature": "that_creature", "enchanted creature": "host"}.get(m["host"], "self")
            if m["host"].startswith("target "):  # -- attached events (wave 25D) -- a target group of its own, after the card's (fixed below)
                host_group = target_group(m["host"])
                if host_group is None or m["u"] not in (None, "your"):
                    return None
                effect["host"] = "target"
    obj = m["o"]
    if not may and not hand and (one := this_way.choice_who(obj)) is not None:
        # -- resolution memory (wave 22D) -- "return a creature card put into a graveyard this way": one of them, chosen (608.2d)
        return [{**effect, "do": "return_choice", "who": one, "n": 1, "upto": False, "random": False, "label": "card"}], None
    if _RA_TOP.fullmatch(obj) is not None:  # -- review 35 -- 404.3: cards put into a graveyard at the same time are arranged by their owner; the
        # engine doesn't ask that, so which creature card is on top after a combat or a wrath isn't known: Shallow Grave, Corpse Dance and Mistmoon
        # Griffin stay manual (wave 37B read it as the last matching card of the order: effects.return_choice "top", kept for saved stacks).
        # -- graveyard order (wave 40C) -- the engine now asks the owner (app/rules/graveyard_order.py), but only when a reader is on the table
        # or they opted in: a Shallow Grave in a hand with the preference off still meets an order its owner never arranged, so not in every game
        return None
    if may and not _RA_CHOICE.fullmatch(obj):
        return None  # (only a choice models its own "may": choosing none)
    if (both := _RA_SELF_AND.fullmatch(obj)) is not None and not may and host_group is None:
        # -- reanimation (wave 37B) -- "Return this card and target land card from your graveyard to the battlefield tapped" (Sandman), "… this card and up to
        # one other target creature card …" (Slimefoot and Squee): the source, and the ability's target; both move in one instruction (608.2c), so both enter
        # at once (603.6a). Works from the graveyard only (113.6m: casting._GRAVEYARD_SELF)
        try:
            kind, key, group = ref(both["rest"])
        except _Fail:
            return None
        if kind != "target" or group is None or not _graveyard_cards(key):
            return None
        return [{**effect, "who": _who(kind, key), "also": "self_gy"}], _one(group)
    if _RA_SELF_EXILE.fullmatch(obj) and not may:  # -- activated other (wave 42C) -- the source, from the graveyard or from exile (effects._cards "self_gy_exile")
        return [{**effect, "who": "self_gy_exile"}], _one(host_group)
    if _RA_SELF.fullmatch(obj) or obj == "this card":  # works from the graveyard (113.6m): coverage keeps it to activated abilities
        # (wave 19C: "return this card to your hand" — a card that isn't on the battlefield: the one in the graveyard, nothing if it left)
        return [{**effect, "who": "self_gy"}], _one(host_group)  # (wave 25D: a host target, "attached to target creature")
    # -- reanimation (wave 10A) -- one instruction, several cards of different kinds: "Return up to one target instant card
    # and up to one target sorcery card from your graveyard to your hand." (one target group each, 115.1, 601.2c; the zone
    # is stated once) and "return a creature card and a land card from your graveyard to your hand." (nothing targeted: each
    # card is chosen on resolution, 608.2d). Only your own graveyard, and no "may" (a choice models its own).
    if not may and not _RA_SELF.search(obj) and not obj.startswith("all ") and host_group is None:
        compound = _reanimation_compound(obj, effect)
        if compound is not None:
            return compound
    c = _RA_CHOICE.fullmatch(obj)
    if c is not None and c["what"].startswith("target "):
        c = None  # (wave 25D: "up to two target Aura or Equipment cards …": targets, read below with the host's group)
    if c is not None:
        what, different = c["what"], None
        dm = _DIFFERENT.fullmatch(what)  # -- refused zones/sized (wave 3R4) -- "… cards with different names"
        if dm is not None:
            what, different = dm["a"] + (dm["b"] or ""), "name" if dm["k"] == "names" else "mana_value"
        tm = re.fullmatch(r"(.+?) with total mana value (\d+) or less", what)  # -- total mana value (wave 51A) -- "any number of artifact creature cards with total mana value 6 or less" (Technomancer)
        if tm is not None:
            if not (c["any"] or c["upto"]):
                return None
            what = tm[1]
        words = re.sub(r"\bcards\b", "card", what)
        phrase = f"{words} from {c['z'].replace('their graveyard', 'that player' + chr(39) + 's graveyard')}"
        sel = selectors.parse(phrase) or selectors.parse_either(phrase)  # (their = that player's, scripts.resolve_it tags the player)
        if sel is None:
            return None
        if c["z"] in ("your hand or graveyard", "your hand and/or graveyard"):  # -- reanimation (wave 37B) -- the hidden hand is asked about whether or not a card is there (effects.return_choice)
            if hand or c["rand"] or not _hand_or_graveyard(sel):
                return None
        elif not _graveyard_cards(sel.key()):
            return None
        n = 999 if c["any"] else _amount(c["upto"] or c["n"]) if (c["upto"] or c["n"]) else 1  # ("any number of": wave 3R4)
        if not (isinstance(n, int) or n == {"x": 1}) or (c["rand"] and (not isinstance(n, int) or c["upto"] or c["any"] or sel.zone_owner != "you")):
            return None
        return [{**effect, "do": "return_choice", "sel": sel.key(), "n": n, "upto": bool(c["upto"] or c["any"] or may),
                 "random": bool(c["rand"]), "label": words, **({"optional": True} if may else {}),
                 **({"different": different} if different else {}), **({"total_mv": int(tm[2])} if tm is not None else {})}], _one(host_group)
    if not put and not (not hand and (m["atk"] or m["atk2"] or m["host"] or m["ck2"] or m["add1"])):  # (ck2/add1: wave 4M)  # (wave 3R4: "… tapped and attacking", "… attached to" read here)
        return None  # ("return target …" / "return all …": the grammar below)
    try:
        kind, key, group = ref(obj)
    except _Fail:
        return None
    if kind == "it" and host_group is not None and not may and not hand:  # -- block events (wave 53C) -- "When this creature dies, return it to the battlefield transformed
        # under your control attached to target opponent": the pronoun is the antecedent's (scripts.resolve_it), the host is the one target
        return [{**effect, "who": "it", "host": "target"}], _one(host_group)
    if kind == "them" and "|" in key and not may:  # -- resolution memory (wave 22D) -- "each creature card put into a graveyard this way"
        return [{**effect, "who": _who(kind, key)}], None
    if kind not in ("target", "each") or not _graveyard_cards(key):
        return None
    if host_group is not None:  # -- attached events (wave 25D) -- "Return target Aura card … attached to target creature": two groups, the card then its host
        if kind != "target" or group is None:
            return None
        return [{**effect, "who": "target:0", "host": "target:1"}], _out([group, host_group])
    return [{**effect, "who": _who(kind, key)}], _one(group)


# -- control (wave 3K) ---------------------------------------------------------------------------------
# "Gain control of target creature [until end of turn]", "Untap target creature and gain control of it
# until end of turn" (Threaten), "Untap all creatures and gain control of them until end of turn",
# "Target opponent gains control of target permanent you control", "Exchange control of two target
# creatures / of ~ and target creature an opponent controls". Effects: ``gain_control`` (who, to, duration)
# and ``exchange_control`` (701.12; who, with). Other durations ("for as long as …") wrap these (delayed.py);
# "until the end of your next turn" is wrapped like "until your next turn" (wave 32C, delayed.DURATIONS); the rest are not read (the sentence stays manual).
_CT_END = r"(?P<d> until end of turn)?"
_CT_PRONOUN = r"(?:it|them|that creature|those creatures|that permanent|those permanents)"
_CT_GAIN = re.compile(rf"(?:you )?gain control of (?P<o>.+?){_CT_END}")
_CT_UNTAP = re.compile(rf"untap (?P<o>.+?) and gain control of {_CT_PRONOUN}{_CT_END}")
_CT_GIVE = re.compile(rf"(?P<p>target opponent|target player|an opponent|that player|that (?:permanent|creature|artifact)'s controller) gains control of (?P<o>.+?){_CT_END}")
_CT_OWN = re.compile(r"each player gains control of all (?P<o>(?:nontoken )?(?:creatures|permanents)) they own")  # (wave 12D)
_CT_EXCHANGE = re.compile(r"exchange control of (?P<o>.+)")
# -- control change (wave 20E) -- "Gain control of all creatures target opponent controls." (Ashiok, Tezzeret): the permanents that player
# controls as it resolves (608.2c; the group form of "tap all creatures target player controls", scripts._tap_their_all)
_CT_THEIRS = re.compile(rf"(?:you )?gain control of all (?P<o>[a-z]+(?: and [a-z]+)?|nonland permanents) "
                        rf"(?P<p>target player|target opponent) controls{_CT_END}")


def _control_object(phrase: str) -> tuple[str, str, dict[str, Any] | None] | None:
    """The permanents a control effect names: a target, "each" (all of them) or a pronoun for earlier ones."""
    try:
        kind, key, group = ref(phrase)
    except _Fail:
        return None
    if kind in ("it", "them", "self", "host"):  # ("self": wave 12D, "Target opponent gains control of this creature"; host: wave 40B, 303.4b — "gain control of enchanted land")
        return kind, key, group
    if kind not in ("target", "each") or not on_battlefield_only(key):
        return None
    return kind, key, group


def control_forms(text: str) -> tuple[Effects, Any] | None:
    """The control-changing wordings above; None when the sentence is not one of them."""
    if re.fullmatch(r"that player untaps (?:~|this creature) and gains control of (?:it|~)", text):
        # -- commanders (wave 47A) -- Karona, False God: "At the beginning of each player's upkeep, that player untaps Karona and gains control of it": the player the trigger is
        # about (the one whose upkeep it is) gets control (613.1b, permanent), after the untap
        return [{"do": "untap", "who": "self"}, {"do": "gain_control", "who": "self", "to": "event_player"}], None
    m = _CT_UNTAP.fullmatch(text)
    if m:
        found = _control_object(m["o"])
        if found is None or found[0] in ("it", "them"):
            return None
        kind, key, group = found
        who = _who(kind, key)
        return [{"do": "gain_control", "who": who, "untap": True, **({"duration": "end_of_turn"} if m["d"] else {})}], _one(group)
    m = _CT_THEIRS.fullmatch(text)
    if m and (sel := selectors.parse(m["o"])) is not None and (pgroup := target_group(m["p"])) is not None:
        return [{"do": "gain_control", "who": f"controlled:target|{sel.key()}", **({"duration": "end_of_turn"} if m["d"] else {})}], _one(pgroup)
    m = _CT_GAIN.fullmatch(text)
    if m:
        found = _control_object(m["o"])
        if found is None:
            return None
        kind, key, group = found
        return [{"do": "gain_control", "who": _who(kind, key), **({"duration": "end_of_turn"} if m["d"] else {})}], _one(group)
    m = _CT_GIVE.fullmatch(text)
    if m:
        found = _control_object(m["o"])
        if found is None:
            return None
        kind, key, group = found
        dur = {"duration": "end_of_turn"} if m["d"] else {}
        # -- other players' choices (wave 12D) -- "An opponent gains control of it / this creature / that permanent": not a
        # target, so the effect's controller chooses which opponent on resolution (608.2d; effects.gain_control)
        if m["p"] == "an opponent":
            return [{"do": "gain_control", "who": _who(kind, key), "to": "choose_opponent", **dur}], _one(group)
        if m["p"] == "that player":  # CR 608.2c: the previously identified player, not a new choice
            return [{"do": "gain_control", "who": _who(kind, key), "to": "that_player", **dur}], _one(group)
        # -- activated other (wave 42C) -- "Destroy target artifact or creature. That permanent's controller gains control of ~." (Starke of Rath): the controller of the
        # permanent the instruction before was about (as it last existed if it is gone: 608.2h), not a target; what changes hands is the source itself
        if m["p"].startswith("that "):
            return ([{"do": "gain_control", "who": "self", "to": "it.controller", **dur}], None) if kind == "self" else None
        pgroup = target_group(m["p"])
        if pgroup is None:
            return None
        if kind != "target":  # "Target opponent gains control of this creature / of all other permanents you control"
            return [{"do": "gain_control", "who": _who(kind, key), "to": "target", **dur}], pgroup
        if group is not None and set(group) == {"what", "min", "max", "another"}:  # -- if you do (wave 51D) -- "Target opponent gains control of another target permanent you control." (Stiltzkin): the first target is a player, so "another" is than the source (as reconfigure's, 702.151a), which the selector already says (``other``)
            group = {k: v for k, v in group.items() if k != "another"}
        if group is None or not simple(group):
            return None
        return [{"do": "gain_control", "who": "target:1", "to": "target:0", **dur}], [pgroup, group]
    m = _CT_OWN.fullmatch(text)  # -- other players' choices (wave 12D) -- "Each player gains control of all creatures they own."
    if m:
        found = _control_object("all " + m["o"])
        if found is None or found[0] != "each":
            return None
        return [{"do": "gain_control", "who": found[1], "to": "owner"}], None
    m = _CT_EXCHANGE.fullmatch(text)
    if m:
        return _exchange(m["o"])
    return None


def _exchange(phrase: str) -> tuple[Effects, Any] | None:
    from app.rules import permanent_exchanges

    if (relative := permanent_exchanges.parse(phrase)) is not None:
        return relative
    both = _control_object(phrase)
    if both is not None:  # "two target creatures": one group of exactly two (701.12a: both or nothing)
        group = both[2]
        if both[0] != "target" or group is None or (group["min"], group["max"]) != (2, 2):  # (wave 51A: "two other target creatures", other than the source, is read as for any group)
            return None
        return [{"do": "exchange_control", "who": "target"}], group
    left, sep, right = phrase.partition(" and target ")
    if not sep:
        return None
    a, b = _control_object(left), _control_object("target " + right)
    if b is None or b[0] != "target" or b[2] is None or not simple(b[2]):
        return None
    if left in ("~", "this creature", "this permanent"):
        return [{"do": "exchange_control", "who": "self", "with": "target"}], b[2]
    if a is None or a[0] != "target" or a[2] is None or not simple(a[2]):
        return None
    return [{"do": "exchange_control", "who": "target", "with": "target:1"}], [a[2], b[2]]
# -- counters & designations (wave 3E) --------------------------------------------------------------
# Counters a player gets (122.1, 122.6): "each opponent gets a poison counter", "you get an experience
# counter", "target player gets four rad counters", "you get {E}{E}" / "six {E}" / "that many {E}" / "an
# amount of {E} equal to …" (107.14: {E} is one energy counter). Only the kinds whose rules the engine
# models: poison (704.5c), energy (107.14), experience (122.1), rad (728: app/rules/designations.py).
PLAYER_COUNTER_KINDS = ("poison", "energy", "experience", "rad")
_GETS = _SUBJ + r"gets? "
_PC_KIND = r"(?P<kind>poison|experience|rad|energy)"
_PC_FORMS = (
    re.compile(_GETS + rf"(?P<n>{AMT}) {_PC_KIND} counters?"),
    re.compile(_GETS + r"(?P<e>(?:\{E\})+)"),
    re.compile(_GETS + rf"(?P<n>{AMT}) \{{E\}}"),
    re.compile(_GETS + r"(?:an amount of \{E\}|a number of " + _PC_KIND + r" counters) equal to (?P<stat>.+)"),
)


def player_counters(text: str, rider: Any) -> tuple[Effects, Any] | None:
    """"<player(s)> get(s) N <kind> counter(s)" → ``player_counter`` (through the counter choke
    point, app/rules/replace.put_counters: Vorinclex / Winding Constrictor), or None when the
    sentence isn't one. "They get …" is "that player gets …" (the pronoun binder decides who that is:
    the trigger event's player, or nobody — then it's refused)."""
    text = re.sub(r"^they get ", "that player gets ", text)
    for i, rx in enumerate(_PC_FORMS):
        m = rx.fullmatch(text)
        if m is None:
            continue
        who, target = _subject(m)
        kind = m.groupdict().get("kind") or "energy"
        n: Any
        if i == 1:  # "{E}{E}" (a count of symbols; "for each …" multiplies it)
            if rider is not None and rider[0] != "each":
                raise _Fail
            n = _apply(m["e"].count("{E}"), rider)
        elif i == 3:  # "an amount of {E} equal to its mana value"
            if rider is not None:
                raise _Fail
            n = _stat(m["stat"])
        else:
            n = _apply(_amount(m["n"]), rider)
        return [{"do": "player_counter", "who": who, "counter": kind, "n": n}], _value_target(n, target)
    return None


# Designations (app/rules/designations.py): "target player becomes the monarch" (725), "you take the
# initiative" (726), "venture into the dungeon" / "venture into Undercity" (701.49, 701.49d), "the Ring
# tempts you" (701.54).
_MONARCH = re.compile(_SUBJ + r"becomes? the monarch")
_INITIATIVE = re.compile(_SUBJ + r"takes? the initiative")
_VENTURE = re.compile(r"(?:you )?venture into (?P<into>the dungeon|Undercity)")
_RING = re.compile(r"the Ring tempts you")
_EMBLEM = re.compile(_SUBJ + r'gets? an emblem with "(?P<t>[^"]+)"(?P<more>(?: and "[^"]+")*)')  # (nested quotes: not read; wave 26A: several abilities)


def _emblem(text: str) -> tuple[Effects, Any] | None:
    """114.1: "You get an emblem with "…"" — only when every quoted ability is one the engine runs from the command zone;
    a quote it can't read is no template match (the card stays manual)."""
    m = _EMBLEM.fullmatch(text)
    if m is None:
        return None
    from app.rules.designations import emblem_text_ok

    # (wave 26A: "an emblem with "You have no maximum hand size" and "Whenever …."": one ability per quote, one line each; 114.2)
    abilities = [m["t"], *re.findall(r'"([^"]+)"', m["more"])]
    # Nested Oracle ability quotations use single quotes inside the emblem's
    # outer double quotes. Restore only a has/have ability quotation; apostrophes
    # in names and possessives remain literal text.
    abilities = [re.sub(r"\b(has|have) ((?:[a-z]+(?:, [a-z]+)*,? and )?)'([^']+)'", r'\1 \2"\3"', a) for a in abilities]  # (-- xdamage (wave 100E) --
    # "have haste and '{T}: …'" (Arlinn, Embraced by the Moon): keywords first, then the quoted ability)
    text = "\n".join(a if a.endswith((".", "!", "?")) else a + "." for a in abilities)
    if not emblem_text_ok(text):
        raise _Fail
    who, target = _subject(m)
    return [{"do": "emblem", "who": who, "text": text}], target


def designation_instruction(text: str) -> tuple[Effects, Any] | None:
    for rx, do in ((_MONARCH, "monarch"), (_INITIATIVE, "initiative")):
        m = rx.fullmatch(text)
        if m:
            who, target = _subject(m)
            return [{"do": do, "who": who}], target
    m = _VENTURE.fullmatch(text)
    if m:
        return [{"do": "venture", "who": "you", "into": "undercity" if m["into"] == "Undercity" else "dungeon"}], None
    if _RING.fullmatch(text):
        return [{"do": "ring_tempts", "who": "you"}], None
    m = re.fullmatch(r"it becomes (?P<v>day|night)", text)  # 731.1
    if m:
        return [{"do": "day_night", "value": m["v"]}], None
    if re.fullmatch(r"(?:you may )?pay any amount of \{E\}", text):  # 107.14: an amount chosen as it resolves
        return [{"do": "pay_energy_any", "as": ENERGY_PAID}], None
    return None


ENERGY_PAID = "energy_paid"  # the binding of "the amount of {E} paid this way" / "that much" after it


# -- keyword actions & face-down (wave 3F) ------------------------------------------------------------
# "Goad target creature [an opponent controls]", "goad up to two target creatures", "goad it / them / that
# creature", "goad all creatures you don't control" (701.15a), and "goad each creature target player /
# that player controls" (``controlled``: "who" names the player). Effect ``goad`` (app/rules/keyword_actions.py).
_GOAD = re.compile(r"goad (?P<o>.+)")
_GOAD_PLAYER = re.compile(r"goad (?:each|all) creatures? (?P<p>target player|target opponent|that player) controls?")


# "Manifest the top card of your library", "its controller manifests the top card of their library",
# "manifest the top two cards of your library", "cloak the top card of your library", "manifest dread",
# "manifest dread twice / X times" (701.40a, 701.58a, 701.62a): effect ``manifest`` ("who": the player
# who manifests, "kind", "n", "dread"; app/rules/facedown.py).
_MANIFEST = re.compile(r"(?:(?P<p>its controller|that player|target player|target opponent|each player|each opponent) )?"
                       r"(?P<v>manifests?|cloaks?) the top (?:(?P<n>two|three|four|five|x|\d+) cards|card) of "
                       r"(?P<lib>your|their) library")
_DREAD = re.compile(r"(?:(?P<p>its controller|that player) )?manifests? dread(?: (?P<n>twice|x times|\w+ times))?")  # (wave 17C: "Its controller manifests dread.")


def _manifest_forms(text: str) -> tuple[Effects, Any] | None:
    if not has_primitive("manifest"):
        return None
    m = _DREAD.fullmatch(text)
    if m:
        n: Any = 1 if not m["n"] else 2 if m["n"] == "twice" else _amount(m["n"][:-6])
        if (m["p"] is None) != m.group(0).startswith("manifest dread"):
            return None
        return [{"do": "manifest", "dread": True, "kind": "manifest", "who": {None: "you", "its controller": "it.controller",
                                                                              "that player": "that_player"}[m["p"]], "n": n}], None
    if (hand := re.fullmatch(r"(?P<v>manifest|cloak) a card from your hand", text)) is not None:  # -- hidden exile (wave 18A) --
        return [{"do": "manifest", "kind": hand["v"], "who": "you", "n": 1, "from": "hand"}], None  # (Scroll of Fate, Vannifar)
    other = re.fullmatch(r"(?:you )?(?P<v>manifest|cloak) the top card of (?P<lib>that player's|target opponent's|target player's|defending player's) library", text)
    if other is not None:  # -- player-relative selectors (wave 53A) -- 701.40a: the top card of another player's library goes onto the battlefield face down under your control
        who_ = {"that player's": "that_player", "target opponent's": "target", "target player's": "target", "defending player's": "defending_player"}[other["lib"]]
        group = target_group(other["lib"][:-2]) if who_ == "target" else None
        return [{"do": "manifest", "kind": other["v"], "who": "you", "n": 1, "library": who_}], _one(group)
    m = _MANIFEST.fullmatch(text)
    if m is None:
        return None
    p = m["p"] or ""
    if (p == "") != (m["v"] in ("manifest", "cloak")) or (p == "") != (m["lib"] == "your"):
        return None  # ("you manifests", "manifest the top card of their library": not read)
    n = 1 if m["n"] is None else _amount(m["n"])
    who = {"": "you", "its controller": "it.controller", "that player": "that_player", "each player": "each_player",
           "each opponent": "each_opponent", "target player": "target", "target opponent": "target"}[p]
    group = target_group(p) if p.startswith("target ") else None
    kind = "cloak" if m["v"].startswith("cloak") else "manifest"
    return [{"do": "manifest", "kind": kind, "who": who, "n": n}], _one(group)


def keyword_forms(text: str) -> tuple[Effects, Any] | None:
    """The keyword-action wordings above; None when the sentence is not one of them."""
    if text.startswith(("manifest", "cloak", "you manifest", "you cloak", "its controller ", "that player ", "target player ", "target opponent ",
                        "each player ", "each opponent ")):
        found = _manifest_forms(text)
        if found is not None:
            return found
    if text == "look at all face-down creatures that player controls" and has_primitive("look_face_down"):  # -- hidden exile (wave 18A) -- Spy Network
        return [{"do": "look_face_down", "who": _that_player_controls("each face-down creature that player controls")}], None
    m = re.fullmatch(r"look at (?P<o>target face-down .+)", text)  # -- hidden exile (wave 18A) -- 708.5 / 701.20e
    if m and has_primitive("look_face_down"):
        try:
            kind, key, group = ref(m["o"])
        except _Fail:
            return None
        return ([{"do": "look_face_down", "who": "target"}], _one(group)) if kind == "target" and on_battlefield_only(key) else None
    m = re.fullmatch(r"turn (?P<o>.+?) face (?P<d>up|down)(?: as (?P<spec>.+))?", text)  # -- hidden exile (wave 18A) -- 701.40g / 708.2a / 708.8
    if m and has_primitive("turn_face_up"):
        up = m["d"] == "up"
        choose = re.fullmatch(r"an? (face-down (?:creature|permanent|artifact|enchantment|land)) you control", m["o"]) if up else None
        if choose:
            sel = selectors.parse(f"{choose[1]} you control")
            return ([{"do": "turn_face_up", "choose": sel.key()}], None) if sel is not None else None
        try:
            kind, key, group = ref("this permanent" if re.fullmatch(r"this (?:enchantment|artifact|land)", m["o"]) else m["o"])
        except _Fail:
            return None
        if kind not in ("target", "self", "it", "them", "host") or (kind == "target" and not on_battlefield_only(key)):
            return None
        spec = chars.parse_spec(m["spec"]) if m["spec"] else None
        if m["spec"] and (up or spec is None):
            return None
        return [{"do": "turn_face_up" if up else "turn_face_down", "who": _who(kind, key), **({"spec": spec} if spec else {})}], _one(group)
    m = re.fullmatch(r"(?:you )?incubate (?P<n>\d+|[xX])(?P<twice> twice)?", text)
    if m and has_primitive("incubate"):  # 701.53a; -- keyword actions (wave 48A) -- "Incubate X twice" (Glistening Dawn): two separate Incubator tokens, one instruction after the other
        return [*([{"do": "repeat", "n": 2, "span": 1}] if m["twice"] else []), {"do": "incubate", "n": _amount(m["n"])}], None
    m = re.fullmatch(r"(?:you )?empower Jace (?P<n>\d+|[xX])", text)
    if m and has_primitive("empower_jace"):  # -- keyword actions (wave 48A) -- 701.71a
        return [{"do": "empower_jace", "n": _amount(m["n"])}], None
    # -- transform (wave 11A) -- 701.27a: "transform ~" / "transform this creature"; the source only (an ability putting
    # "it" or another object through is not read), once per object since the ability was put on the stack (701.27f)
    if re.fullmatch(r"transform (?:this token|~|this (?:creature|artifact|land|enchantment|permanent|saga|vehicle))", text) \
            and has_primitive("transform"):
        return [{"do": "transform", "who": "self"}], None  # (701.27c: anything that isn't double-faced doesn't turn over)
    if (m := re.fullmatch(r"transform all (?P<o>Incubator tokens you control)", text)) and has_primitive("transform"):
        # -- commanders (wave 50C) -- 701.27a: "transform all Incubator tokens you control" (Glissa, Elesh Norn): every double-faced token the selector finds as this resolves,
        # each one object that turns over (701.27f: not one that transformed since the ability went on the stack). (Other mass wordings - "Transform all Humans you
        # control" - stay refused: tests/test_rules_wave11a_transform.py.)
        sel = selectors.parse(m["o"])
        return ([{"do": "transform", "who": sel.key()}], None) if sel is not None else None
    m = re.fullmatch(r"transform (?P<o>(?:up to one )?target .+)", text)
    if m and has_primitive("transform"):  # -- transform (wave 48A) -- "transform up to one target Werewolf you control" (Waxing Moon), "transform target Incubator token you control": a chosen permanent on the battlefield (701.27a)
        try:
            kind, key, group = ref(m["o"])
        except _Fail:
            return None
        return ([{"do": "transform", "who": "target"}], _one(group)) if kind == "target" and on_battlefield_only(key) else None
    if text in ("transform it", "transform him", "transform her") and has_primitive("transform"):  # -- transform (wave 20F) --
        return [{"do": "transform", "who": "it"}], None  # (the pronoun's antecedent is bound by scripts.resolve_it: the source in its own trigger)
    # -- flip (wave 24C) -- 710: "flip ~" / "flip this creature" / "flip it" (the source only: a flip card's own ability)
    if re.fullmatch(r"flip (?:~|it|this (?:creature|permanent))", text) and has_primitive("flip"):
        return [{"do": "flip", "who": "self"}], None
    m = re.fullmatch(r"return (?:it|him|her) to the battlefield(?P<t> tapped)?(?: and)? transformed under "
                     r"(?P<u>your|(?:its|his|her) owner's) control", text)
    if m:
        found = parse_sentence(f"return it to the battlefield{m['t'] or ''} under {'your' if m['u'] == 'your' else 'its owner' + chr(39) + 's'} control")
        if found is not None and len(found[0]) == 1 and found[0][0].get("do") == "return_card":
            return [{**found[0][0], "transformed": True}], found[1]
    m = re.fullmatch(r"(?:you )?earthbend (?P<n>\d+|[xX]|one|two|three|four|five|six|seven|eight)", text)
    if m and has_primitive("earthbend"):  # 701.66a: "Target land you control …" is part of the action
        land = selectors.parse("land you control")
        if land is None:
            return None
        return [{"do": "earthbend", "who": "target", "n": _amount(m["n"])}], land.key()
    if text.startswith("detain ") and has_primitive("detain"):  # -- detain (wave 12A) -- 701.35a: permanents, not players
        try:
            kind, key, group = ref(text[len("detain "):])
        except _Fail:
            return None
        if kind not in ("target", "each", "it", "them", "host") or (kind in ("target", "each") and not on_battlefield_only(key)):
            return None
        return [{"do": "detain", "who": _who(kind, key)}], _one(group)
    if text.startswith("suspect ") and has_primitive("suspect"):  # -- suspect (wave 12A) -- 701.60a: a creature
        try:
            kind, key, group = ref(text[len("suspect "):])
        except _Fail:
            return None
        if kind not in ("target", "it", "host", "self") or (kind == "target" and not on_battlefield_only(key)):
            return None
        return [{"do": "suspect", "who": _who(kind, key)}], _one(group)
    if not text.startswith("goad ") or not has_primitive("goad"):
        return None
    m = _GOAD_PLAYER.fullmatch(text)
    if m:
        if m["p"] == "that player":
            return [{"do": "goad", "who": "that_player", "controlled": True}], None
        group = target_group(m["p"])
        return ([{"do": "goad", "who": "target", "controlled": True}], _one(group)) if group is not None else None
    m = _GOAD.fullmatch(text)
    if m is None:
        return None
    try:
        kind, key, group = ref(m["o"])
    except _Fail:
        return None
    if kind not in ("target", "each", "it", "them", "host"):
        return None  # (a player, or "goad ~": not a printed wording)
    if kind in ("target", "each") and not on_battlefield_only(key):
        return None
    return [{"do": "goad", "who": _who(kind, key)}], _one(group)
