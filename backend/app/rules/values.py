"""Quantities in effects ("draw two cards", "X damage", "a +1/+1 counter for each creature you
control"): explicit, deterministic expressions evaluated at resolution (608.2h: values are
determined as the effect is carried out).

A value is an int (a literal) or a dict:

* ``{"x": 1}`` — the X the spell or ability was cast / activated with (107.3);
* ``{"count": "<selector key>"}`` — the number of objects (or players) matching a selector;
* ``{"hand": "you" | "target" | "opponent_max"}`` — the number of cards in a player's hand (opponent_max, wave 42A: the largest hand among your opponents);
* ``{"opponents": 1}`` — the number of opponents still in the game; ``{"players_lost": 1}`` — the players who have lost the game, ``{"lowest_life": 1}`` — the lowest life total among the players, ``{"below_start": 1}`` — how far your life total is below the starting one, ``{"greater": [a, b]}`` — the larger of two values (wave 51G);
* ``{"power": "self" | "target" | "it" | "event" | "ref:<b>"}`` / ``{"toughness": …}`` /
  ``{"mana_value": …}`` — of an object (as it is, or as it last existed: 608.2h);
* ``{"counters": kind | None, "on": "self" | "target" | …}`` — counters of a kind (None: of all
  kinds) on an object;
* ``{"player_counters": kind}`` — counters a player has ("experience counters you have", 122.1e);
* ``{"life": "you" | "target" | "opponent_max"}`` — a life total ("your life total", "the highest
  life total among your opponents");
* ``{"distinct": "types" | "colors" | "basic_land_types" | "creature_types" | "powers", "among":
  "<selector key>"}`` — how many different card types (205.2a) / colors (105.1) / basic land types
  (205.3i) / creature types / power values are represented among the objects a selector names ("the
  number of card types among cards in all graveyards", domain; "creatures with different powers");
* ``{"devotion": ["B"]}`` / ``["W", "U"]`` — devotion to a color or two colors (700.5);
* ``{"sum" | "max": "power" | "toughness" | "mana_value", "of": "<selector key>"}`` — "the total
  power of creatures you control", "the greatest mana value among …";
* ``{"times": [a, b]}`` — a product (e.g. "two for each …", "twice …");
* ``{"plus": [a, b]}`` — a sum ("that number plus 1");
* ``{"half": v, "round": "up" | "down"}`` — half, rounded as the text says (107.1: integers only);
* ``{"neg": v}`` — a negative amount (only through :func:`evaluate_signed`: "-1/-1 for each …");
* ``{"event_amount": 1}`` — "that much" / "that many": the trigger event's amount, read from the
  context the ability carries from when it triggered (app.game.rules_state.TriggerEvent).
* ``{"spells_cast": "you"}`` — the spells you've cast this turn (wave 3D);
* ``{"colors_spent": 1}`` — converge: the colors of mana spent to cast the spell (wave 4F);
* ``{"kicked": 1}`` — the number of times the spell (or the permanent it became) was kicked
  (702.33d; "for each time it was kicked").

Parsing lives in :func:`parse_amount` (words) and :func:`parse_count` ("the number of …"; any
of the quantity phrases above). Everything is data: nothing from a card is ever executed.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import selectors
from app.rules.characteristics import PERMANENT_TYPES

if TYPE_CHECKING:
    from app.rules.plan import Plan

Value = int | dict[str, Any]
NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "twenty": 20,
           "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
           "thirty": 30, "forty": 40, "fifty": 50}  # (static_other, wave 36B: "if you control thirty or more artifacts" (Knuckles the Echidna), "mills fourteen cards")
AMOUNT = r"(?:twice [xX]|half [xX] rounded (?:up|down)|(?:two|three|four|five|six|seven|eight|nine|ten) times [xX]|[xX] (?:plus|minus) (?:\d+|one|two|three|four|five)|twice that (?:much|many)|\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|x|X|that much|that many|the chosen number)"  # (wave 36B: the number words up to nineteen; wave 34C: "five times X", "X plus 3", "X minus one")

# Counters that carry rules the engine doesn't model yet (122.1b keyword counters, 122.1c shield,
# 122.1d stun, 122.1h finality, 122.1i rad, 714 lore): an effect putting one of these
# stays manual rather than placing an inert marker.
UNMODELED_COUNTERS = frozenset({
    "rad"})  # (hone: wave 24C, 122.1j — layers._derive)  # (shield: 122.1c, wave 7C — shield_counters.py; lore: 714, sagas.py handles any lore counter put)  # (stun: 122.1d, wave 3F — keyword_actions.untap_stunned; finality: 122.1h, wave 3R4 — replacements.replace_move)

BASIC_LAND_TYPES = ("Plains", "Island", "Swamp", "Mountain", "Forest")  # 205.3i
# 205.2a: the card types (as the type line writes them; "Tribal" is the old name of kindred)
CARD_TYPES = frozenset({"Artifact", "Battle", "Conspiracy", "Creature", "Dungeon", "Enchantment", "Instant", "Kindred",
                        "Land", "Phenomenon", "Plane", "Planeswalker", "Scheme", "Sorcery", "Vanguard"})
_COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_MANA_SYMBOL = re.compile(r"\{([^}]+)\}")


def parse_amount(word: str) -> Value | None:
    w = word.strip().lower()
    if w.isdigit():
        return int(w)
    if w in NUMBERS:
        return NUMBERS[w]
    if w == "x":
        return {"x": 1}
    if (m := re.fullmatch(r"(?:twice|(two|three|four|five|six|seven|eight|nine|ten) times) x", w)) is not None:  # (wave 16D) "twice X", "three times X"
        return {"times": [NUMBERS[m[1]] if m[1] else 2, {"x": 1}]}
    if (m := re.fullmatch(r"half x rounded (up|down)", w)) is not None:  # -- X arithmetic (wave 34C) -- 107.1a: rounded as the text says (half_x)
        return {"half": {"x": 1}, "round": m[1]}
    if (m := re.fullmatch(r"x (plus|minus) (\d+|one|two|three|four|five)", w)) is not None:  # -- X arithmetic (wave 34C) -- "X plus 3", "X minus one" (107.1b: never below 0)
        return {m[1]: [{"x": 1}, int(m[2]) if m[2].isdigit() else NUMBERS[m[2]]]}
    if w in ("that much", "that many"):
        return {"event_amount": 1}  # the trigger event's amount (TriggerEvent.amount)
    if w == "the chosen number":  # -- chosen filters (wave 53B) -- "Choose a number. … that many creatures": chosen.bind_effects writes the answer in
        return {"chosen_n": 1}
    if w in ("twice that much", "twice that many"):  # -- reflexive this way (wave 30G) -- "deals twice that much damage"
        return {"times": [2, {"event_amount": 1}]}
    return None


_HALF_X_NOUN = re.compile(r"\bhalf X ([a-z]+(?: counters)?),? rounded (up|down)(?:,(?= ))?")
_ROUND_EACH = re.compile(r"^(?P<pre>.*?)\s*\bRound (?P<dir>up|down) each time\.", re.S)


def half_x(text: str) -> str:
    """-- X arithmetic (wave 34C) -- 107.1a: "half X" is rounded the way the text says, wherever it says so ("draw half X cards, rounded down",
    "half X damage, rounded up, to you", "…half X life and draw half X cards. Round down each time."): the rounding moves next to the
    quantity ("half X rounded down cards"), where the amount grammar reads it (``AMOUNT``)."""
    if (each := _ROUND_EACH.match(text)) is not None:
        text = re.sub(r"\bhalf X\b(?! rounded)", f"half X rounded {each['dir']}", each["pre"]) + text[each.end():]
    return _HALF_X_NOUN.sub(lambda m: f"half X rounded {m[2]} {m[1]}", text)


# -- dynamic values (agent F): "the number of …" and friends --------------------------------------
_COUNT = re.compile(r"^the (?:total )?number of (?P<what>.+?)$")
_STATS = {"power": "power", "toughness": "toughness", "mana value": "mana_value", "power and/or toughness": "power_or_toughness"}
_COUNTERS_ON = re.compile(r"^(?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters? on (?P<on>.+)$")
_ON = {"~": "self", "it": "it", "this creature": "self", "this permanent": "self", "this artifact": "self",
       "this enchantment": "self", "this land": "self", "this equipment": "self", "this aura": "self",
       "that creature": "it", "that permanent": "it"}
_DISTINCT = {"card types": "types", "different card types": "types", "card type": "types",
             "permanent types": "permanent_types", "permanent type": "permanent_types",
             "colors": "colors", "different colors": "colors", "color": "colors",
             "basic land types": "basic_land_types", "basic land type": "basic_land_types",
             "creature types": "creature_types", "different creature types": "creature_types",
             "creature type": "creature_types",
             "different power": "powers", "different powers": "powers",  # (wave 17B: Selvala, Eager Trailblazer)
             "mana values": "mana_values", "different mana values": "mana_values", "mana value": "mana_values",
             "different mana value": "mana_values", "planeswalker types": "planeswalker_types",
             "different mana cost": "mana_costs", "different mana costs": "mana_costs", "mana costs": "mana_costs"}  # (-- counters (wave 52D) -- Embodiment of Agonies, 202.1)  # (wave 21F: Eris, Roar of the Storm)  # (wave 20B)
_AMONG = re.compile(r"^(?P<kind>" + "|".join(sorted(map(re.escape, _DISTINCT), key=len, reverse=True)) + r") among (?P<sel>.+)$")
_DEVOTION = re.compile(r"^your devotion to (?P<c1>white|blue|black|red|green)(?: and (?P<c2>white|blue|black|red|green))?$")
_AGGREGATE = re.compile(r"^the (?:(?P<max>greatest|highest)|(?P<sum>total)) (?P<stat>power and/or toughness|power|toughness|mana value) "
                        r"(?:among|of) (?P<sel>.+)$")
_PLAYER_COUNTERS = re.compile(r"^(?P<kind>[a-z]+) counters? you have$")
# -- counters & designations (wave 3E) -- "poison counters your opponents have" (all of them together),
# "{E} you have" / "the amount of {E} you have" (107.14: each {E} is an energy counter)
_PLAYER_COUNTERS_3E = re.compile(r"^(?:the amount of )?(?:(?P<kind>poison|experience|rad|energy) counters?|(?P<e>\{E\})) "
                                 r"(?P<who>you have|your opponents have)$")
# -- as long as (wave 9B) -- "the amount of excess damage dealt to that creature this way" (Goblin Negotiation), "the excess damage
# dealt this way", "that excess damage" (after "If excess damage was dealt this way, …, where X is that excess damage")
_EXCESS_DEALT = re.compile(r"(?:the amount of |the )?excess damage dealt (?:to (?:that|a) (?:creature|permanent) )?this way|that excess damage")
_COUNTERS_AMONG = re.compile(r"^(?:(?P<kinds>different kinds of counters)|(?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters?) (?:on|among) (?P<sel>.+)$")
_DAMAGE_EVENT = re.compile(r"^the amount of (?:combat )?damage (?:(?:it|he|she|they|~|this creature|that creature|those creatures) dealt"
                           r"(?: to (?:that player|that opponent|them))?|dealt)$")
_HALF = re.compile(r"^half (?P<v>.+?), rounded (?P<round>up|down)$")
_EVENT_GROUP = re.compile(r"^(?:(?P<max>the (?:greatest|highest) (?P<s1>power|toughness|mana value) among (?:them|those creatures))"
                          r"|their total (?P<s2>power|toughness|mana value)|(?:the )?total (?P<s3>power|toughness|mana value) of (?:them|those creatures))$")
_PLUS = re.compile(r"^(?P<v>.+?) plus (?P<n>\d+|one|two|three|four|five)$")
_TYPE_WORDS = "|".join(selectors.CARD_TYPES)


# -- ability words (wave 4F) -- converge: "the number of colors of mana spent to cast this spell", "for each color of
# mana spent to cast it": the colors (105.1) among the mana actually spent on its total cost (601.2h), from the
# spell's payment record (the same record for the permanent it became; a copy wasn't cast: none, 707.10)
_COLORS_SPENT = re.compile(r"colors? of mana spent to cast (?:this spell|that spell|it|~|this creature|this permanent)")


# -- X actions (wave 9A) -- 700.14-style "mana spent": the total amount of mana paid for the spell (601.2h), from its payment
# record; "that spell" is the cast event's spell, "her" / "this spell" / "~" the source (the permanent remembers its spell's
# record). A bare "it" is not read: it could be either.
# -- mana provenance (wave 18B) -- 107.4h/106.3: "the amount of {S} spent to cast this spell", "{S} spent to cast it", "mana from a Treasure
# spent to cast it / this spell" (PaymentRecord.mana_tags; the source's own record, like converge)
_FROM_TAGS = {"treasure": "Treasure", "artifact": "Artifact", "desert": "Desert", "cave": "Cave", "creature": "Creature"}
_MANA_FROM = re.compile(r"(?:the amount of )?(?:\{S\}|mana from (?:an? )?(?P<what>[Tt]reasure|[Aa]rtifact|[Dd]esert|[Cc]ave|[Cc]reature)(?: source)?)(?: that was)? spent to cast "
                        r"(?:this spell|it|~|this creature|this permanent)")
_MANA_SPENT = re.compile(r"(?:the )?amount of mana spent to cast (?P<o>that spell|this spell|her|him|~|this creature)")


_THAT_PLAYER = re.compile(r"\b(?:that player's|their|that player controls|they control|that player owns|they own|they have|that player has|that opponent controls)\b")
_THAT_PLAYER_TO_YOU = {"that player's": "your", "their": "your", "that player controls": "you control", "they control": "you control",
                       "that player owns": "you own", "they own": "you own", "they have": "you have", "that player has": "you have", "that opponent controls": "you control"}  # (wave 30N: "poison counters they have")


def player_relative(phrase: str) -> Value | None:
    """-- value grammar (wave 23C) -- "the number of artifacts that player controls" / "cards in their graveyard" / "creatures they control of the
    chosen type" as a "where X is" definition: the phrase read for ONE player (the target or the trigger's: scripts._where_x binds it), as
    ``{"for_player": "that_player", "of": <the count for "you">}``. A count of a hand or a library has no such reading here (a quantity per
    recipient is sized_damage's)."""
    if not _THAT_PLAYER.search(phrase):
        return None
    inner = _parse_count(_THAT_PLAYER.sub(lambda m: _THAT_PLAYER_TO_YOU[m[0]], phrase), it=None)
    if inner is None or any(k in str(inner) for k in ("hand", "library", '"controller":"chosen"', '"zone_owner":"chosen"', "exiled_with", "'on'")):
        return None
    return {"for_player": "that_player", "of": inner}


_TARGET_RELATIVE = re.compile(r"^(?P<what>.+?) (?:(?P<ctl>target (?:player|opponent) controls)|in target (?P<own>player|opponent)'s (?P<zone>graveyard|hand))$")


def target_relative(phrase: str) -> Value | None:
    """-- value grammar (wave 23C) -- "tapped creature target opponent controls" / "card in target opponent's hand" / "creature card in target player's
    graveyard": the count for the one player a target names ("you" of the phrase is that player), as ``{"for_player": "target_opponent" |
    "target_player", "of": …}``; scripts._value_targets declares the target when the sentence names none (115.1) and binds it."""
    m = _TARGET_RELATIVE.match(phrase)
    if m is None:
        return None
    who = "opponent" if "opponent" in phrase.rpartition(" target ")[2][:9] or m["own"] == "opponent" else "player"
    inner = _parse_count(f"{m['what']} you control" if m["ctl"] else f"{m['what']} in your {m['zone']}", it=None)
    if inner is None or any(k in str(inner) for k in ('"controller":"that_player"', '"zone_owner":"that_player"', "chosen", "'on'")):
        return None
    return {"for_player": f"target_{who}", "of": inner}


def parse_count(phrase: str, *, it: str | None = None) -> Value | None:
    """See ``_parse_count``. -- damage wordings (wave 6B) -- a count of what "that player" controls is a different
    number for each player it could name (the target player's, the recipient's: app/rules/sized_damage.py): never read
    through the selectors' trigger-bound "that player" (selectors.THAT_PLAYER)."""
    v = _parse_count(phrase, it=it)
    if v is not None and it != "self" and any(k in str(v) for k in ('"controller":"chosen"', '"zone_owner":"chosen"', "'hand': 'chosen'")):
        return None  # (wave 16F: "the chosen player" of the very object that counts)
    return None if v is not None and f'"controller":"{selectors.THAT_PLAYER}"' in str(v) else v


def _parse_count(phrase: str, *, it: str | None = None) -> Value | None:
    """A quantity phrase → value: "the number of creatures you control" / "cards in your hand" /
    "opponents you have" / "+1/+1 counters on ~" / "card types among cards in all graveyards" /
    "your devotion to green" / "your life total" / "twice …" / "half …, rounded up" / "X".

    ``it`` is what a bare "it" means for the caller ("counters on it": the static's own source
    is "self"); None refuses it (a pronoun the caller can't bind is never guessed)."""
    p = phrase.strip()
    if p.lower() in ("counter among players and permanents", "counters among players and permanents", "the number of counters among players and permanents"):
        return {"all_counters_among_players_and_permanents": True}
    from app.rules import linked_aggregates

    if (linked := linked_aggregates.parse_value(p)) is not None:
        return linked
    from app.rules import cast_mana_totals, player_max_counts

    if (cast_total := cast_mana_totals.parse(p)) is not None:
        return cast_total

    maximum = player_max_counts.parse(p)
    if maximum is not None:
        return maximum
    if p.endswith(" beyond the first"):  # -- keywords (wave 15E) -- rampage 702.23a: "for each creature blocking it beyond the first"
        inner = _parse_count(p[: -len(" beyond the first")], it=it)
        return None if inner is None else {"minus": [inner, 1]}
    # -- cost self reduction (wave 16F) -- "for each 1 life you gained this turn" (a count of life)
    p = re.sub(r"^1 (life you (?:gained|lost) this turn)$", r"\1", p)
    p = re.sub(r"^the amount of (unspent (?:\w+ )?mana you have)$", r"the number of \1", p)  # -- activated other (wave 48C) -- Glissa Sunseeker: 106.4, the same count
    if p == "the amount of life you gained":  # -- event batches (wave 34C) -- "Whenever you gain life, …": the event's amount (scripts._event_refs_ok: only a life-gain trigger has one)
        return {"event_amount": 1}
    p = re.sub(r"\b(counters?) (?:it|he|she|they) had on (it|them)$", r"\1 on \2", p)  # -- event batches (wave 34C) -- "the number of counters it had on it" (Felisa): as it last existed (608.2h)
    g = re.fullmatch(r"(?P<a>\d+|the .+?) or (?P<b>the .+?), whichever is greater", p)  # -- most-played cards IV (wave 51G) -- "the number of Zombies you control or the number of Zombie cards in your graveyard, whichever is greater" (Prophet of the Scarab): the larger count
    if g:
        a, b = (int(g["a"]) if g["a"].isdigit() else _parse_count(g["a"], it=it)), _parse_count(g["b"], it=it)
        return None if a is None or b is None else {"greater": [a, b]}
    m = _COUNT.match(p)
    what = m["what"] if m else p
    if what.lower() == "x":
        return {"x": 1}
    if (ahead := re.fullmatch(r"(?:the )?(?:number of )?(?:players?|opponents?) who (?P<verb>controls?|has|have) (?:at least (?P<k>two|three|four) )?(?P<cmp>more|fewer|less) "
                              r"(?P<w>lands|creatures|artifacts|enchantments) than you", p)) is not None \
            and ((ahead["w"] in ("life", "cards in hand", "cards in their hand")) == (ahead["verb"] in ("has", "have"))):
        # -- tutor (wave 20D) -- Oreskos Explorer, Surveyor's Scope (a count of players, 107.1); -- value grammar (wave 23C) -- "opponent who has less
        # life than you" / "who controls fewer creatures than you": each other player's own value against yours
        inner = {"life": "you"} if ahead["w"] == "life" else {"hand": "you"} if ahead["w"].startswith("cards") \
            else _parse_count(f"the number of {ahead['w']} you control", it=it)
        if inner is None:
            return None
        return {"ahead": inner, "margin": NUMBERS[ahead["k"]] if ahead["k"] else 1, **({} if ahead["cmp"] == "more" else {"below": True})}
    from app.rules import (
        dice,  # -- rolling dice (wave 12A) -- "the result", "that result", "the other result" (706.4)
    )

    if (rolled := dice.amount(p)) is not None:
        return rolled
    # -- refused zones/sized (wave 3R4) -- "the number of cards in their hand minus 4", "3 minus the number of …",
    # "… minus the number of cards in your hand": never below 0 (107.1b)
    minus = re.match(r"^(?P<a>.+?) minus (?P<b>\d+|one|two|three|four|five|the number of .+|the amount of mana spent to cast that spell)$", what)
    if minus:
        a_text = minus["a"] if m is None else f"the number of {minus['a']}"
        a = {"mana_value": "event"} if a_text == "that spell's mana value" else int(a_text) if a_text.isdigit() else NUMBERS.get(a_text) or parse_count(a_text, it=it)  # (wave 21B)
        b = int(minus["b"]) if minus["b"].isdigit() else NUMBERS.get(minus["b"]) or parse_count(minus["b"], it=it)
        return {"minus": [a, b]} if a is not None and b is not None else None
    if what in ("cards in their hand", "cards in that player's hand", "card in their hand", "card in that player's hand"):
        return {"hand": "that_player"}  # (scripts._that_players_hand binds it: the target player, or the trigger's)
    if what in ("cards in their library", "cards in that player's library"):  # -- most-played cards II (wave 45A) -- Peer into the Abyss: the same binding, a library's public count
        return {"library": "that_player"}
    m = re.match(r"^twice (?P<v>.+)$", what)
    if m:
        inner = parse_count(m["v"], it=it)
        return {"times": [2, inner]} if inner is not None else None
    m = _EVENT_GROUP.match(what)  # -- event batches (wave 34C) -- scripts._event_refs_ok: only a trigger whose event holds the batch
    if m:
        stat = (m["s1"] or m["s2"] or m["s3"]).replace(" ", "_")
        return {"max" if m["max"] else "sum": stat, "of": "event"}
    m = _HALF.match(what)
    if m:
        inner = parse_count(m["v"], it=it)
        return {"half": inner, "round": m["round"]} if inner is not None else None
    m = _PLUS.match(what)
    if m:
        inner = parse_count(m["v"], it=it)
        return {"plus": [inner, int(m["n"]) if m["n"].isdigit() else NUMBERS[m["n"]]]} if inner is not None else None
    sized = _sized(what, it)  # -- sized amounts (wave 3D) --
    if sized is not None:
        return sized
    if what == "1 damage prevented this way":  # -- prevention riders (wave 17A) -- "for each 1 damage prevented this way"
        return {"ref_amount": "prevented"}
    if what in ("cards looked at while scrying this way", "card looked at while scrying this way"):
        return {"event_amount": 1}  # -- scry counts (wave 19C) -- 701.22d: the scry trigger's event (designations.facts)
    if what in ("cards in your hand", "card in your hand"):
        return {"hand": "you"}
    if what in ("cards in the chosen player's hand", "card in the chosen player's hand"):  # -- chosen type (wave 16F) --
        return {"hand": "chosen"}
    if what in ("creatures in your party", "creature in your party"):  # -- refused modal/conditional (wave 3R1) --
        return {"party": "you"}  # 700.8
    if what in ("time you've cast a commander from the command zone this game", "times you've cast a commander from the command zone this game",
                "time you've cast your commander from the command zone this game", "times you've cast your commander from the command zone this game"):
        return {"commander_casts": 1}  # -- triggers (wave 19B) -- 903.8: every cast of one of your commanders from the command zone
    if what in ("cards in target player's hand", "cards in target opponent's hand"):
        return {"hand": "target"}
    if what in ("cards in all players' hands", "card in all players' hands"):  # -- X sized by a count (wave 19F) --
        return {"hand": "all"}
    if what in ("cards in the hand of the opponent with the most cards in hand", "cards in the hand of the opponent with the most cards in their hand"):
        return {"hand": "opponent_max"}  # -- static_other (wave 42A) -- Adamaro: the largest hand among your opponents (a count of cards, public: 402.3)
    if what in ("opponents you have", "opponent you have", "your opponents", "opponent", "opponents"):
        return {"opponents": 1}
    if what in ("card type among those cards", "card types among those cards"):
        return {"types_among": "event"}  # -- trigger other (wave 52B) -- 205.2a, 603.2c: the card types among the cards a "one or more cards are put into your graveyard" batch counted (Polluted Cistern)
    if what in ("opponent dealt damage", "opponents dealt damage", "opponent dealt damage this way", "opponents dealt damage this way"):
        return {"event_players": 1}  # -- trigger other (wave 52B) -- 603.2c: the opponents a "one or more … deal damage to your opponents" batch dealt damage (Malcolm, Hordewing Skaab)
    if what in ("player who has lost the game", "players who have lost the game"):  # -- most-played cards IV (wave 51G) -- Rampant Frogantua: the seats no longer in the game (800.4)
        return {"players_lost": 1}
    if what in ("cards exiled with ~", "cards exiled with it", "card exiled with ~", "card exiled with it"):
        return {"exiled_with": 1}  # -- resolution memory (wave 22D) -- 607.2a: the cards the linked ability exiled and that are still there
    if what == "opponent you attacked with a creature this combat":  # -- casting extras (wave 18E) -- melee 702.121a
        return {"attacked_opponents": 1}
    if what in ("players being attacked", "player being attacked"):  # -- if you do (wave 40A) -- "draw a card for each player being attacked" (Amber Gristle O'Maul), "create a
        return {"players_attacked": 1}  # Food token for each player being attacked" (Apothecary White): the players some creature is attacking now (506.2, 506.6; not a player whose planeswalker or battle is attacked — Commander Liara Portyr's ruling of 2022-06-10, Suppressor Skyguard's of 2024-02-02)
    if re.fullmatch(r"times? (?:it|he|she|~|this (?:spell|creature|permanent|enchantment|artifact|land|planeswalker)) (?:was|were) kicked", what):
        return {"kicked": 1}  # (wave 23C: plural and "he"/"she"/"this permanent": 702.33d, a permanent remembers how its spell was kicked)
    if what in ("times that spell was kicked", "time that spell was kicked"):  # -- cast keywords (wave 43D) -- Rumbling Aftershocks: the cast trigger's spell (its record, 702.33d)
        return {"kicked": 1, "of": "cast_spell"}
    if what in ("times this creature has mutated", "times ~ has mutated", "times this permanent has mutated", "time this creature has mutated"):  # -- merged permanents (wave 18D)
        return {"mutated": 1}  # (702.140: how many spells merged with it)
    if what in ("creature it devoured", "creature ~ devoured"):  # -- keyword mechanics (wave 9D) -- 702.82b
        return {"devoured": 1}
    if (paid_group := re.fullmatch(r"(?P<symbols>(?:\{[WUBRG]\}){2,}) spent to cast (?:this spell|it|~|this creature|this permanent)", what)) is not None:
        symbols = re.findall(r"\{([WUBRG])\}", paid_group['symbols'])
        if len(set(symbols)) == 1:
            return {'mana_pairs': {'color': symbols[0], 'size': len(symbols)}}
    if _COLORS_SPENT.fullmatch(what):  # -- ability words (wave 4F) -- converge
        return {"colors_spent": "event" if what.endswith("that spell") else 1}
    m = _MANA_FROM.fullmatch(what)  # -- mana provenance (wave 18B) -- "the amount of {S} spent to cast this spell"
    if m:
        return {"mana_from": "Snow" if m["what"] is None else _FROM_TAGS[m["what"].lower()]}
    m = _MANA_SPENT.fullmatch(what)  # -- X actions (wave 9A) -- "the amount of mana spent to cast that spell / her"
    if m:
        return {"mana_spent": "event" if m["o"] == "that spell" else "self"}
    if what == "your life total":
        return {"life": "you"}
    if what == "your speed":  # -- speed (wave 24B) -- 702.179f: no speed reads as 0 (values.evaluate: the player counter)
        return {"player_counters": "speed"}
    m = re.fullmatch(r"unspent (?:(white|blue|black|red|green) )?mana you have", what)  # -- static_other sweep (wave 21A) -- Omnath, Locus of Mana
    if m:
        return {"unspent": {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}.get(m[1] or "", "")}
    if what in ("target player's life total", "target opponent's life total"):
        return {"life": "target"}
    if what in ("the highest life total among your opponents", "the greatest life total among your opponents"):
        return {"life": "opponent_max"}
    m = re.fullmatch(r"(?:the number of )?(?P<c>white|blue|black|red|green) mana symbols? in that spell's mana cost", what)
    if m:  # -- trigger other (wave 44B) -- Namor the Sub-Mariner: the symbols of that color in the mana cost of the spell a cast trigger is about (202.1, 107.4e hybrid counts for each color)
        return {"cast_symbols": _COLOR_WORDS[m["c"]]}
    m = re.fullmatch(r"(?P<c>white|blue|black|red|green) mana symbols? (?:in|among) the mana costs? of permanents you control", what)
    if m:  # -- value grammar (wave 23C) -- 700.5: that IS devotion (chroma)
        return {"devotion": [_COLOR_WORDS[m["c"]]]}
    m = _DEVOTION.match(what)
    if m:
        return {"devotion": [_COLOR_WORDS[c] for c in (m["c1"], m["c2"]) if c]}
    m = _PLAYER_COUNTERS.match(what)
    if m:
        return {"player_counters": m["kind"]}
    if what == "differently named dungeon you've completed":  # -- dungeons (wave 45B) -- 309.7: Ellywick Tumblestrum's emblem, one per name
        return {"dungeons_completed": 1}
    if _EXCESS_DEALT.fullmatch(what):  # -- as long as (wave 9B) -- 120.10: scripts bind it to the damage just before (this_way.excess_dealt)
        return {"ref_amount": "excess_dealt"}
    if (gv := re.fullmatch(r"graveyards? with (?P<n>\w+) or more cards? in (?:it|them)", what)) is not None and gv["n"] in NUMBERS:
        return {"graveyards_with": NUMBERS[gv["n"]]}  # -- trigger other (wave 44D) -- "a card for each graveyard with seven or more cards in it" (The Master of Lake-town): every player's, 404.1
    if re.fullmatch(r"cards in all graveyards with the same name as (?:that|the) spell", what):  # -- value grammar (wave 23C) -- Cabal Shrine: 201.2
        return {"same_name": "event", "zone": "graveyard"}  # (the spell a cast trigger is about; scripts._event_refs_ok)
    if _DAMAGE_EVENT.fullmatch(what):  # -- value grammar (wave 23C) -- "the amount of damage it dealt to that player": the damage trigger's amount
        return {"event_amount": 1, "of": "damage"}  # (scripts._event_refs_ok: only a damage event's trigger reads it; 603.2c: a batch's total)
    if what in ("the damage prevented this way", "damage prevented this way"):  # -- prevention riders (wave 17A) -- 615.5
        return {"ref_amount": "prevented"}  # (source_shields.rider: bound by the prevention effect when it prevented damage)
    if what == "the damage dealt this way":  # -- if you do (wave 5G) -- what the damage just before dealt (this_way)
        return {"ref_amount": "damage_dealt"}
    if what == "the life lost this way":  # -- refused zones/sized (wave 3R4) -- what the lose_life just before lost
        return {"ref_amount": "life_lost"}  # (scripts._life_lost binds it to that instruction, else the line is manual)
    if what in ("{E} paid this way", "the amount of {E} paid this way", "{E} you paid this way"):  # (wave 3E)
        return {"ref_amount": "energy_paid"}  # (language.ENERGY_PAID: bound by the pay_energy_any effect)
    m = _PLAYER_COUNTERS_3E.match(what)  # -- counters & designations (wave 3E) --
    if m:
        kind = "energy" if m["e"] else m["kind"]
        return {"player_counters": kind, "of": "opponents"} if m["who"] == "your opponents have" else {"player_counters": kind}
    m = _ATTACHED_TO.fullmatch(what)  # -- token & pump wordings (wave 6C) --
    if m:
        on = "self" if m["on"] == "~" else it
        if on != "self":
            return None
        return {"attached": sorted(set(re.findall(r"Aura|Equipment", m["kinds"]))), "on": on}
    m = _COUNTERS_AMONG.match(what)  # -- value grammar (wave 23C) -- "the number of counters on permanents you control", "time counters among permanents you control"
    if m and m["sel"].lower() not in _ON and "‹granter" not in m["sel"]:  # (review 23C: one granting object is no group — a token an effect
        key = _selector_key(m["sel"])  # created never has its ‹granter› bound (Gutter Grime's Ooze would read 0)
        if key is None or selectors.from_key(key).player is not None or selectors.from_key(key).card or selectors.from_key(key).zones != ("battlefield",):
            return None
        if m["kinds"]:  # 122.1: how many different kinds of counters there are among them
            return {"counter_kinds": 1, "of": key}
        return {"counters_among": m["kind"], "of": key}
    m = _COUNTERS_ON.match(what)
    if m:
        on = _ON.get(m["on"].lower())
        if on == "it":
            on = it
        if on is None or (m["kind"] and m["kind"] in UNMODELED_COUNTERS):
            return None
        return {"counters": m["kind"], "on": on}
    if (m := re.fullmatch(r"abilities from among (?P<ks>.+?) found among (?P<sel>.+)", what)) is not None:  # -- keyword soups (wave 50J) -- Odric, Blood-Cursed
        from app.rules import keyword_soup

        ks, key = keyword_soup.words(m["ks"]), _selector_key(m["sel"])
        return {"abilities_among": ks, "among": key} if ks and key else None
    m = _AMONG.match(what)
    if m and m["sel"] in ("spells you've cast this turn", "spells you have cast this turn") and _DISTINCT[m["kind"]] == "types":
        return {"cast_types": "you"}  # -- trigger other (wave 44B) -- April O'Neil: the card types of this turn's cast spells, as they were cast (601.2i, history.CastNote)
    if m:
        key = _selector_key(m["sel"])
        return {"distinct": _DISTINCT[m["kind"]], "among": key} if key else None
    if what == "the greatest mana value among your commanders":  # -- value grammar (wave 23C) -- 903.3: a commander is one wherever it is (Cactus Preserve)
        return {"max": "mana_value", "of": selectors.Selector(commander=True, owner="you", zones=selectors.ZONES).key()}
    if what == "the greatest mana value of a commander you own on the battlefield or in the command zone":  # -- amounts (wave 12C) --
        return {"max": "mana_value", "of": selectors.Selector(commander=True, owner="you", zones=("battlefield", "command")).key()}  # 903.3
    m = re.fullmatch(r"the (?:greatest|highest) mana value among (?P<sel>.+? spells?) you(?:'ve| have) cast this turn", what)
    if m:  # -- this-turn state (wave 33D) -- Rootha: the spells cast this turn, as they were cast (601.2i), an {X} spell with its X (202.3e)
        from app.rules import conditions  # (conditions imports this module)

        kind = re.sub(r"^(instant|sorcery) and (instant|sorcery) ", r"\1 or \2 ", m["sel"])
        key = conditions._history_sel(kind, "stack")
        return None if key is None else {"spells_cast": "you", "sel": key, "greatest": True}
    m = _AGGREGATE.match(what)
    if m:
        # -- X sized by a count (wave 19F) -- "the greatest power among creatures you control and creature cards in your graveyard":
        # the greatest of two groups (not a sum: "total" would count each)
        parts = m["sel"].split(" and ") if m["max"] and " and " in m["sel"] and _selector_key(m["sel"]) is None else [m["sel"]]
        keys = [_selector_key(x) for x in parts]
        if len(parts) > 2 or None in keys or any(selectors.from_key(k).player is not None for k in keys if k):
            return None
        return {"max" if m["max"] else "sum": _STATS[m["stat"]], "of": keys[0], **({"also": keys[1]} if len(keys) == 2 else {})}
    m = re.fullmatch(r"the greatest number of (?P<sel>creatures you control) that have a creature type in common", p)  # -- value grammar (wave 23C) -- 205.3m
    if m and (key := _selector_key(m["sel"])) is not None and not selectors.from_key(key).player:
        return {"shared_type": 1, "of": key}
    m = re.fullmatch(r"differently named (?P<sel>.+)", what)  # -- amounts (wave 12C) -- 201.2: how many different names
    if m:
        key = _selector_key(m["sel"])
        return {"distinct": "names", "among": key} if key else None
    if what.startswith(("the ", "a ", "an ")):
        return None
    # -- static grants (wave 15A) -- "for each land you control and each land card in your graveyard" (Multani): the sum of the
    # two counts (an object that is both counts once for each, as "for each" reads)
    m = re.fullmatch(r"(?P<a>.+?) and each (?P<b>.+)", what)
    if m:
        a, b = parse_count(m["a"], it=it), parse_count(m["b"], it=it)
        if isinstance(a, dict) and isinstance(b, dict) and set(a) == set(b) == {"count"}:
            return {"plus": [a, b]}
        return None
    sel = selectors.parse(_normalise(what))
    if sel is None:
        return None
    return {"count": sel.key()}


# -- token & pump wordings (wave 6C) -- "+2/+2 for each Aura attached to it", "… for each Aura and Equipment attached to
# ~": the Auras / Equipment attached to the source now (301.5, 303.4; read whenever its characteristics are, 611.3a)
_ATTACHED_TO = re.compile(r"(?P<kinds>Aura|Equipment|Aura (?:and|or|and/or) Equipment) attached to (?P<on>it|~)")


# -- sized amounts (wave 3D) -- ------------------------------------------------------------------
_N_PLUS = re.compile(r"^(?P<n>\d+|one|two|three|four|five) plus (?P<v>.+)$")
_SPELLS_CAST = re.compile(r"^(?:the number of )?spells (?P<who>you|they)(?:'ve| have) cast this turn$")


def _sized(what: str, it: str | None) -> Value | None:
    """"2 plus the number of Lessons in your graveyard" (a sum), "the number of spells you've cast
    this turn" (the turn's spell count, 601.2i). ``{"spells_cast": "you"}`` reads it as the effect
    is carried out (608.2h)."""
    if re.fullmatch(r"(?:the number of )?spells? you(?:'ve| have) cast (?:this turn from anywhere other than your hand|from anywhere other than your hand this turn)", what):
        from app.rules import conditions

        key = conditions._history_sel("spell", "stack")
        assert key is not None
        return {"spells_cast": "you", "sel": key, "from": "not_hand"}
    m = _N_PLUS.match(what)
    if m:
        inner = parse_count(m["v"], it=it)
        return {"plus": [inner, int(m["n"]) if m["n"].isdigit() else NUMBERS[m["n"]]]} if inner is not None else None
    m = re.match(r"^(?P<a>.+?) plus (?P<b>the number of .+)$", what)
    if m:  # "the number of creatures you control plus the number of Foods you control" (a sum of two counts)
        a, b = parse_count(m["a"], it=it), parse_count(m["b"], it=it)
        return {"plus": [a, b]} if a is not None and b is not None else None
    # -- cost self reduction (wave 21F) -- Thrasta: "for each other spell cast this turn" (every player's, 601.2i: this one isn't counted yet)
    if re.fullmatch(r"other spells? cast this turn", what):
        return {"spells_cast": "all"}
    # Huskburster Swarm: "creature card you own in exile and in your graveyard" (the two zones' counts together)
    m = re.fullmatch(r"(?P<sel>.+?) you own in exile and in your graveyard", what)
    if m and (a := parse_count(f"{m['sel']} you own in exile", it=it)) is not None \
            and (b := parse_count(f"{m['sel']} you own in your graveyard", it=it)) is not None:
        return {"plus": [a, b]}
    if (m := _SPELLS_CAST.match(what)):  # (wave 17D: "they" the trigger's player, Rug of Smothering)
        return {"spells_cast": "you" if m["who"] == "you" else "event_player"}
    return _turn_amount(what)


# -- this-turn history (wave 4D) -- amounts of this turn's history (app/rules/history.py: TurnLog), read as the effect
# is carried out (608.2h): "the amount of life you gained this turn", "spell you've cast this turn" ("for each …"),
# "cards you've drawn this turn", "creatures that died this turn", "opponent who drew two or more cards this turn".
_TURN_LIFE = re.compile(r"^(?:the )?(?:amount of )?life you(?:'ve| have)? (?P<k>gained|lost) this turn$")
_TURN_SPELL = re.compile(r"^spell (?P<who>you|they)(?:'ve| have) cast this turn$")
# -- this-turn state (wave 42B) -- 119.3, 608.2h: "the amount of life you gained this turn or the amount of life you lost this turn, whichever is greater"
# (Willowdusk, Essence Seer): the larger of the two totals the turn's log keeps (neither is the net change: 119.3)
_TURN_LIFE_GREATER = re.compile(r"^(?:the )?amount of life you(?:'ve| have)? (?:gained|lost) this turn or the amount of life you(?:'ve| have)? "
                                r"(?:lost|gained) this turn, whichever is greater$")
_TURN_CAST = re.compile(r"^(?:the number of )?(?P<other>other )?(?:(?P<sel>[a-z]+(?: (?:and|or) [a-z]+)?) )?spells?"
                        r"(?: (?P<who>you|they)(?:'ve| have))? cast(?P<before> before it)? this turn(?P<first> other than the first)?$")
_TURN_DREW = re.compile(r"^(?:the number of )?cards? you(?:'ve| have) drawn this turn$")
_TURN_OPP_DREW = re.compile(r"^(?:the number of )?cards? your opponents(?:'ve| have) drawn this turn$")  # -- commanders (wave 47A) -- Heliod, the Radiant Dawn
# -- this-turn history (wave 30R) -- also "creature you controlled that died", "creature put into your graveyard from the battlefield" (dies, 700.4,
# into its owner's graveyard, 400.3) and "permanent that left the battlefield under your control" (to any zone): history.amount "died"
_TURN_DIED = re.compile(r"^(?:the number of )?(?P<sel>creatures?|nontoken creatures?|permanents?|[A-Z][a-z-]+)(?P<ctl> you controlled)?"
                        r"(?: that (?P<verb>died|left the battlefield)|(?: that (?:was|were))? (?P<gy>put into your graveyard from the battlefield))"
                        r"(?P<mine> under your control)? this turn$")
_TURN_EXILED = re.compile(r"^(?:the number of )?(?P<sel>creatures?|nontoken creatures?) that (?:was|were) exiled under your opponents' control this turn$")  # (wave 41B)
_OPPONENTS_WHO = re.compile(r"^(?:the number of )?(?:your )?opponents? (?:who|that) (?:(?P<drew>drew (?P<n>\w+) or more cards)|"  # (wave 41B: "your opponents")
                            r"(?P<lost>lost life)|(?P<hurt>(?:was|were) dealt (?P<combat>combat )?damage(?: by ~ or an? (?P<by>[A-Z][a-z]+))?)|(?P<lands>had (?P<m>\w+) or more lands enter the battlefield under their control)) "
                            r"this turn$")


_OPPONENTS_HAND = re.compile(r"^(?:the number of )?opponents? who (?:has|have) (?P<n>\w+) or (?P<cmp>more|fewer) cards in hand$")  # (-- triggers (wave 21B) --)
# ("who has more cards in hand than you" stays manual: tests/test_rules_wave8b_triggers.py)


# -- tokens (wave 38B) -- "the number of nontoken creatures you had enter the battlefield under your control this turn" (Gyome, Master Chef), "for each land you
# had enter the battlefield under your control this turn" (Emergent Sequence): a look back (608.2i) at what entered under your control this turn, whether or not it
# is still there (the ruling for Gyome counts those that died, stopped being creatures or changed hands), read as each was when it entered (history.entered)
_TURN_ENTERED = re.compile(r"^(?:the number of )?(?P<sel>(?:nontoken )?(?:creature|land|permanent|artifact)s?) you had enter the battlefield under your control this turn$")


def _turn_amount(what: str) -> Value | None:
    if what == 'the total amount of noncombat damage dealt to your opponents this turn':
        return {'turn_history': 'opponent_noncombat_damage'}
    if what in ("{E} you've paid or lost this turn", "the amount of {E} you've paid or lost this turn"):
        return {"turn_history": "energy_lost"}
    if m := _OPPONENTS_HAND.match(what):  # each opponent whose hand size now says so (the count of a hand is public)
        n = int(m["n"]) if m["n"].isdigit() else NUMBERS.get(m["n"])
        return {"opponents_hand": m["cmp"], "n": n} if n is not None else None
    if m := _TURN_ENTERED.match(what):
        sel = selectors.parse(m["sel"])
        return {"turn_history": "entered", "sel": sel.key()} if sel is not None else None
    if re.fullmatch(r"(?:the )?(?:number of )?cards put into your graveyard from anywhere this turn", what):
        return {"turn_history": "graveyard_entries"}
    if re.fullmatch(r"(?:the )?(?:number of )?times you descended this turn", what):  # -- commander sweep (wave 49B) -- 700.11: the permanent cards put into your graveyard from anywhere (The Mycotyrant)
        return {"turn_history": "descended"}
    m = _TURN_LIFE.match(what)
    if m:
        return {"turn_history": "gained" if m["k"] == "gained" else "lost"}
    if _TURN_LIFE_GREATER.match(what):
        return {"turn_history": "life_greater"}  # (-- this-turn state (wave 42B) --)
    if (m := _TURN_SPELL.match(what)):
        return {"spells_cast": "you" if m["who"] == "you" else "event_player"}
    if (m := _TURN_CAST.match(what)):  # -- this-turn history (wave 30R) -- "instant and sorcery spells you've cast", "other spells", "spells cast"
        from app.rules import conditions  # (conditions imports this module)

        kind = re.sub(r"^(instant|sorcery) and (instant|sorcery)$", r"\1 or \2", m["sel"] or "")
        key = conditions._history_sel(f"{kind} spell" if kind else "spell", "stack")
        if key is not None:  # (a kind the recorded notes can't answer — keywords, a creature type with a capital … — isn't read)
            found: Value = {"spells_cast": {"you": "you", "they": "event_player", None: "all"}[m["who"]], "sel": key,
                            **({"other": True} if m["other"] else {}), **({"before": True} if m["before"] else {})}
            return {"minus": [found, 1]} if m["first"] else found  # ("other than the first": one fewer, 601.2i)
    if re.fullmatch(r"cards? you(?:'ve)? discarded this turn", what):  # -- value grammar (wave 23C) -- a cycled card is discarded too (702.29a)
        return {"turn_history": "discarded"}
    m = re.fullmatch(r"creature (?:(?P<any>that attacked)|(?P<mine>you attacked with)) this turn", what)
    if m:  # -- cost self reduction (wave 16F) -- the creatures declared as attackers (508.1, wave 4D log), whether or not still here
        return {"turn_history": "attackers", **({"who": "you"} if m["mine"] else {})}
    if _TURN_DREW.match(what):
        return {"turn_history": "drew"}
    if _TURN_OPP_DREW.match(what):  # the cards your opponents (still in the game, 800.4a) drew this turn, all of them together (121.1)
        return {"turn_history": "opp_drew"}
    m = _TURN_EXILED.match(what)
    if m:  # -- this-turn history (wave 41B) -- "the number of creatures that were exiled under your opponents' control this turn" (Vren): each left the battlefield
        # for exile, controlled by an opponent as it left (608.2i: as it last existed there)
        sel = selectors.parse(m["sel"])
        return None if sel is None else {"turn_history": "died", "sel": sel.key(), "to": "exile", "who": "opponent"}
    m = _TURN_DIED.match(what)
    if m:  # 700.4; as they last existed on the battlefield (608.2i)
        # -- trigger tail (wave 15B) -- "for each Zubera that died this turn": a creature type counts creatures (700.4)
        sel = selectors.parse(m["sel"] + (" creature" if m["sel"][0].isupper() else ""))
        if sel is None or (m["mine"] and m["ctl"]) or (m["verb"] == "left the battlefield" and not (m["mine"] or m["ctl"])):
            return None  # (leaving is read only for what was yours: no card counts anyone's)
        # -- X actions (wave 9A) -- "that died under your control this turn": the ones you controlled as they died (700.4)
        return {"turn_history": "died", "sel": sel.key(), **({"who": "you"} if m["mine"] or m["ctl"] else {}),
                **({"owner": "you"} if m["gy"] else {}), **({"left": True} if m["verb"] == "left the battlefield" else {})}
    # -- X sized by a count (wave 19F) -- this turn's log: tokens you created, permanents you sacrificed, what your opponents lost
    if re.fullmatch(r"tokens? you(?:'ve)? created this turn", what):
        return {"turn_history": "tokens"}
    if m := re.fullmatch(r"permanents? (you(?:'ve)? )?sacrificed this turn", what):  # (wave 21F: The Balrog, "each permanent sacrificed": anyone's)
        return {"turn_history": "sacrificed", **({} if m[1] else {"who": "any"})}
    if re.fullmatch(r"card types? among permanents you(?:'ve)? sacrificed this turn", what):
        return {"turn_history": "sacrificed_card_types82"}
    if re.fullmatch(r"other artifacts? or creatures? you(?:'ve)? sacrificed this turn", what):  # -- cost reductions paid with objects (wave 47C) -- Dargo, the Shipwrecker: the ones
        return {"turn_history": "sacrificed", "sel": selectors.Selector(types=("Artifact", "Creature")).key()}  # sacrificed before; this cast's own are sacrificed later (601.2h)
    if re.fullmatch(r"cards? you(?:'ve)? cycled or discarded this turn", what):  # (wave 21F: Hollow One; a cycled card is discarded, 702.29a)
        return {"turn_history": "discarded"}
    if re.fullmatch(r"(?:the )?(?:total )?(?:amount of )?(?:1 )?life (?:lost by your opponents|your opponents (?:have )?lost) this turn", what):  # (wave 30J: "for each 1 life", Neheb; "the total amount of life your opponents lost", Florian)
        return {"turn_history": "opp_lost"}
    if re.fullmatch(r"(?:the )?(?:total )?damage dealt to your opponents this turn", what):
        return {"turn_history": "opp_damage"}
    if re.fullmatch(r"(?:the )?total (?:amount of )?life lost by all players this turn", what):  # -- activated other (wave 52D) -- Tainted Sigil: every player's loss together (119.3)
        return {"turn_history": "all_lost"}
    if re.fullmatch(r"(?:the )?(?:total )?(?:amount of )?(?:1 )?damage dealt to you this turn", what):  # -- this-turn history (wave 50E) -- 120.3: "gain life equal to the damage dealt to you this turn" (Simulacrum), "for each 1 damage dealt to you this turn" (Discordant Spirit)
        return {"turn_history": "damage_to_you"}
    if re.fullmatch(r"opponents? you(?:'ve| have)? attacked(?: this turn)?", what):  # -- this-turn state (wave 33D) -- Rose: 508.6, players you declared attackers against
        return {"turn_history": "opponents_attacked"}
    m = _OPPONENTS_WHO.match(what)
    if m:  # each opponent whose history this turn says so (one per opponent)
        word = m["n"] or m["m"]
        n = 1 if word is None else int(word) if word.isdigit() else NUMBERS.get(word)
        if n is None:
            return None
        from app.rules.creature_types import CREATURE_TYPES

        if m["by"] and m["by"] not in CREATURE_TYPES:
            return None
        return {"turn_history": "opponents_who", "what": "drew" if m["drew"] else "lost" if m["lost"] else "damaged" if m["hurt"] else "lands", "n": n,
                **({"combat": True} if m["combat"] else {}),  # (-- triggers (wave 30J) -- Tymna the Weaver: "opponents that were dealt combat damage", 510.2)
                **({"by": m["by"]} if m["by"] else {})}  # (-- this-turn history (wave 41B) -- "dealt combat damage by ~ or a Dragon this turn" (Estinien Varlineau): the source was ~ or had that type, as it dealt it)
    from app.rules import (
        player_filter,  # -- per-player filters (wave 23A) -- "for each opponent who controls fewer creatures than you"
    )

    return player_filter.count(what)
# -- end this-turn history (wave 4D) --


def _normalise(what: str) -> str:
    """Noun phrases the selector grammar spells differently: "cards in all graveyards" (400.1:
    every player's), "instant and sorcery cards" (cards of either type: a list, not "artifact
    creature"'s both-types reading)."""
    out = re.sub(r"\b(?:from|in) all graveyards$", "in graveyards", re.sub(r" on the battlefield(?=$| named | with )", "", what))  # Literal names remain literal (201.5).
    return re.sub(rf"\b(?P<a>{_TYPE_WORDS}) and (?P<b>{_TYPE_WORDS}) (?P<n>cards?|spells?)\b", r"\g<a> or \g<b> \g<n>", out)


def _selector_key(phrase: str) -> str | None:
    sel = selectors.parse(_normalise(phrase))
    return sel.key() if sel is not None else None


class NoChosenPlayer(Exception):
    """-- chosen type (wave 16F) -- a count about "the chosen player" read before the source has chosen one (a creature with
    "As ~ enters, choose an opponent" is on the battlefield before the choice is made): the value is not known yet."""


def evaluate(plan: Plan, ctx: dict[str, Any], v: Value) -> int:
    """The number a value stands for right now (never negative: 107.1b)."""
    if isinstance(v, int):
        return max(0, v)
    if isinstance(v, dict) and "perm100d" in v:  # -- static permanents (wave 100D) -- (a CDA setting P/T may set it below 0: 107.1b)
        from app.rules import static_perm100d

        return static_perm100d.amount(plan, ctx, v)
    if 'quotient' in v or 'mana_symbols' in v:
        from app.rules import static_count_values94

        return static_count_values94.amount(plan, ctx, v)
    if isinstance(v, dict) and 'event_x' in v:
        return max(0, int((ctx.get('event') or {}).get('x') or 0))
    if isinstance(v, dict) and 'activation_life' in v:
        return max(0, int(((ctx.get('event') or {}).get('activation_cost') or {}).get('life') or 0))
    if "linked_pool" in v:
        from app.rules import linked_aggregates

        return max(0, int(linked_aggregates.aggregate(plan, ctx, v['linked_pool'])))
    you = ctx["controller"]
    if "sum_for_players" in v:
        from app.rules import target_player_counts

        return target_player_counts.evaluate(plan, ctx, v)
    if "cast_mana_total" in v:
        from app.rules import cast_mana_totals

        return cast_mana_totals.evaluate(plan, ctx, v)
    if "max_player_count" in v:
        from app.rules import player_max_counts

        return player_max_counts.evaluate(plan, ctx, v)
    if "players_where" in v:  # -- per-player filters (wave 23A) -- the players a predicate holds for (app/rules/player_filter.py)
        from app.rules import player_filter

        return player_filter.amount(plan, ctx, v)
    if "live_ref_count" in v:  # Exact current incarnations, never objects that left and returned (400.7).
        from app.rules import context

        return sum(1 for cid in context.objects(plan, ctx, v["live_ref_count"])
                   if not v.get("zone") or plan.state.cards[cid].zone.endswith(":" + v["zone"]))
    if "ref_count" in v:  # -- "this way" outcomes (wave 4A) -- what an earlier instruction actually did
        from app.rules import this_way

        return this_way.count(plan, ctx, v)
    if "revealed_mv" in v:  # -- trigger other (wave 52B) -- the mana value of the card(s) a trade revealed (app/rules/top_trade.py)
        from app.rules import top_trade

        return top_trade.revealed_mv(plan, ctx, v)
    if "per_player" in v:  # -- damage sized by a count (wave 4E) -- read for the recipient player (app/rules/sized_damage.py)
        from app.rules import sized_damage

        return sized_damage.evaluate(plan, ctx, v)
    if "x" in v:
        return max(0, int(ctx.get("x") or 0))
    if "last_chosen_number95" in v:
        from app.rules import chosen_forms95

        return chosen_forms95.number(plan, ctx)
    if "chosen_n" in v:  # (wave 53B: never left unbound by a definition chosen.chosen_value_ok accepts)
        return 0
    if "coin_flips" in v:  # -- chosen filters (wave 53B) -- the flips this resolution made, won or lost (app/rules/coin_flips.py)
        from app.rules import coin_flips

        return coin_flips.count(ctx, v["coin_flips"])
    if "die" in v:  # -- rolling dice (wave 12A) -- this resolution's own roll (app/rules/dice.py)
        from app.rules import dice

        return dice.evaluate(ctx, v["die"])
    if "dice" in v:  # -- dice (wave 24B) -- the even / odd / different results of this resolution's roll
        from app.rules import dice

        return dice.count_of(ctx, v["dice"])
    if "paid_x" in v:  # -- sized payments (wave 5G) -- the X an optional payment of this resolution paid
        from app.rules import paid_x

        return paid_x.amount(ctx, v["paid_x"])
    if "times" in v:
        a, b = v["times"]
        return evaluate(plan, ctx, a) * evaluate(plan, ctx, b)
    if "plus" in v:  # (review 30b: 107.1b, a calculation uses a negative power as it is, only its result is at least 0: Phthisis's 2021 ruling)
        return max(0, sum(_signed_stat(plan, ctx, x) for x in v["plus"]))
    if "half" in v:
        n = evaluate(plan, ctx, v["half"])
        return (n + 1) // 2 if v.get("round") == "up" else n // 2
    if "neg" in v:
        return 0  # a negative result of an effect is zero (107.1b); the sign is evaluate_signed's
    if "kicked" in v:
        if v.get("of") == "cast_spell":  # -- cast keywords (wave 43D) -- "the number of times that spell was kicked" (702.33d): the spell a cast trigger is about
            from app.rules import context

            refs = context._object_refs(ctx, context.EVENT)
            record = plan.rules.payments.get(refs[0].object_id) if refs else None
            return record.kicked if record is not None else 0
        return kicked_count(plan, ctx)
    if "mutated" in v:  # -- merged permanents (wave 18D) --
        from app.rules import merged

        return merged.times_mutated_in(plan, ctx)
    if "devoured" in v:  # -- keyword mechanics (wave 9D) -- 702.82b: sacrificed as a result of its devour as it entered
        return plan.rules.devoured.get(ctx.get("source_object") or "", 0)
    if "convoked" in v:  # -- counters (wave 26D) -- "for each creature that convoked it" (702.51a: its payment record's contributions)
        record = plan.rules.payments.get(ctx.get("source_object") or "")
        return len({c.object_id for c in record.contributions if c.kind == "convoke"}) if record is not None else 0
    if "colors_spent" in v:  # -- ability words (wave 4F) -- converge (a spell cast by hand: no mana known, 0)
        if v['colors_spent'] == 'event':
            if isinstance((ctx.get("event") or {}).get("mana_spent"),dict):
                return sum(n>0 for c,n in ctx["event"]["mana_spent"].items() if c in "WUBRG")
            from app.rules import context

            refs = context._object_refs(ctx, context.EVENT)
            payment_oid = refs[0].object_id if len(refs) == 1 else ''
        else:
            payment_oid = ctx.get('source_object') or ''
        record = plan.rules.payments.get(payment_oid)
        if record is None:
            return 0
        if not record.mana_known:  # -- review (wave 4R) -- cast by hand: say the 0 isn't the colors spent
            name = plan.state.cards[record.card].name if record.card in plan.state.cards else ''
            plan.note(f"{name or 'It'} was cast by hand: the colors of mana spent to cast it aren't known (read as 0) — "
                      "adjust by hand", [record.card] if record.card in plan.state.cards else ())
            return 0
        return sum(1 for c in "WUBRG" if record.mana_spent.get(c, 0) > 0)
    if 'mana_pairs' in v:
        record = plan.rules.payments.get(ctx.get('source_object') or '')
        if record is None or not record.mana_known:
            return 0
        group = v['mana_pairs']
        return record.mana_spent.get(group['color'], 0) // group['size']
    if "mana_from" in v:  # -- mana provenance (wave 18B) -- {S} (107.4h) or mana from a Treasure ... spent to cast the source
        record = plan.rules.payments.get(ctx.get("source_object") or "")
        if record is None or not record.mana_known:
            plan.note("What paid for the spell isn't known (read as 0) — adjust by hand",
                      [record.card] if record is not None and record.card in plan.state.cards else ())
            return 0
        return sum(1 for t in record.mana_tags if v["mana_from"] in t)
    if "spell_payment" in v:
        from app.rules import spell_payment_facts

        return spell_payment_facts.amount(plan,ctx,v["spell_payment"]) or 0
    if "mana_spent" in v:  # -- X actions (wave 9A) -- a spell cast by hand: no mana known, 0 (and said so)
        return _mana_spent(plan, ctx, v["mana_spent"])
    if "graveyards_with" in v:  # -- trigger other (wave 44D) -- the graveyards of the players still in the game
        live = plan.live()
        return sum(1 for key, ids in plan.state.zones.items() if key.endswith(":graveyard") and key.split(":")[0] in live and len(ids) >= v["graveyards_with"])
    if "named_self_in_graveyards" in v:  # -- mana riders (wave 5A) -- cards with the source's name in every graveyard
        from app.rules import characteristics as chars

        src = plan.state.cards.get(ctx.get("source_card") or "")
        name = chars.of(src, plan.info).name if src is not None else ""
        live = plan.live()
        return sum(1 for key, ids in plan.state.zones.items() if key.endswith(":graveyard") and key.split(":")[0] in live
                   for cid in ids if name and chars.of(plan.state.cards[cid], plan.info).name == name)
    if "ahead" in v:  # -- tutor (wave 20D) -- "the number of players who control [at least two] more lands than you": the same count read for each other player
        mine = evaluate(plan, ctx, v["ahead"])
        return sum(1 for p in plan.live() if p != you and (evaluate(plan, {**ctx, "controller": p}, v["ahead"]) + v["margin"] <= mine if v.get("below")
                                                           else evaluate(plan, {**ctx, "controller": p}, v["ahead"]) >= mine + v["margin"]))
    if "count" in v:
        sel = selectors.from_key(v["count"])
        if ctx.get("unknown_choice_raises") and "chosen" in (sel.controller, sel.zone_owner):
            from app.rules import chosen

            if chosen.player_of(plan, ctx.get("source_card") or "") is None:
                raise NoChosenPlayer
        if sel.player is not None:
            return sum(1 for p in plan.live() if selectors.matches_player(plan, sel, p, you))
        away = ctx.get("not_yet_entered") or ()  # -- review (wave 26D) -- an "enters with" count, read before they enter (replacements._counter_amount)
        if "blocking_event" in sel.extras:  # -- trigger other (wave 39A) -- "for each creature blocking it": the creature the "becomes blocked" event is about, as this resolves
            from app.rules import context

            event_creatures = context.objects(plan, ctx, context.EVENT)
            sel = selectors.replace(sel, extras=tuple("blocking_source" if x == "blocking_event" else x for x in sel.extras))
            return sum(1 for c in selectors.candidates(plan, sel, you, event_creatures[0] if event_creatures else "") if c not in away)
        if "other_event" in sel.extras:  # -- trigger other (wave 52B) -- "five other Mountains" of "Whenever a Mountain you control enters, if …" (Valakut): other than the object that entered
            from app.rules import context

            event_objects = context._object_refs(ctx, context.EVENT)
            sel = selectors.replace(sel, other=True, extras=tuple(x for x in sel.extras if x != "other_event"))
            return sum(1 for c in selectors.candidates(plan, sel, you, event_objects[0].card if event_objects else None) if c not in away)
        if "shares_type_event" in sel.extras:  # -- most-played cards (wave 43B) -- "for each other attacking creature that shares a creature type with it" (Shared Animosity): "it"
            from app.rules import (
                context,  # is the creature the trigger is about, as this resolves; the others than IT are counted
            )

            event_creatures = context.objects(plan, ctx, context.EVENT)
            return sum(1 for c in selectors.candidates(plan, sel, you, event_creatures[0] if event_creatures else "") if c not in away)
        # (wave 32A: "for each land with the same name as the exiled card" (Strata Scythe) compares with the ability's own source, not with the
        # object a static's "other" is about — the equipped creature)
        where = ctx.get("source_card") if not sel.other and any(x.startswith(("samename_src", "nosamename_src", "samename_exiled_with")) for x in sel.extras) \
            else _other_than(ctx)
        return sum(1 for c in selectors.candidates(plan, sel, you, where) if c not in away)
    if "cast_symbols" in v:  # -- trigger other (wave 44B) -- the spell the trigger is about, on the stack (a cast trigger resolves with it still there or as it was)
        from app.rules import context

        refs = context._object_refs(ctx, context.EVENT)
        card = plan.state.cards.get(refs[0].card) if refs else None
        cost = plan.ch(card).mana_cost if card is not None else ""
        return sum(1 for sym in re.findall(r"\{([^}]+)\}", cost or "") if v["cast_symbols"] in sym.split("/"))
    if "cast_types" in v:  # -- trigger other (wave 44B) -- 205.2a: the different card types among the spells you cast this turn (a spell of two types counts both)
        from app.rules import history

        return len({"Kindred" if t == "Tribal" else t for n in history.log_for(plan).casts if n.player == ctx["controller"] for t in n.types if t in CARD_TYPES})
    if 'crafted_colors' in v:
        from app.rules import mana_crafted_profiles

        if (ctx.get('source_object') or '') not in plan.rules.crafted_materials:
            raise NoChosenPlayer  # Legacy craft history is unknown, not an invented zero-color receipt.
        return len(mana_crafted_profiles.colors(plan, ctx))
    if "spells_cast" in v:  # -- sized amounts (wave 3D) -- "the number of spells you've cast this turn"
        from app.rules import context

        if "sel" in v:  # -- this-turn history (wave 30R) -- of a kind ("instant and sorcery"), "other" than this one (history.cast_amount)
            from app.rules import history

            return history.cast_amount(plan, ctx, v)
        return sum(plan.rules.spells_this_turn(p, plan.state.turn.number) for p in (
            [you] if v["spells_cast"] == "you" else plan.state.seat_order if v["spells_cast"] == "all"
            else context.players(plan, ctx, context.EVENT)))
    if "turn_history" in v:  # -- this-turn history (wave 4D) --
        from app.rules import history

        return history.amount(plan, ctx, v)
    if "event_amount" in v:  # "that much" / "that many": the trigger event's amount (608.2k)
        from app.rules import context  # (context → triggers → … → values)

        return context.amount(ctx, context.EVENT)
    if "ref_amount" in v:  # "that much" of an earlier effect of this resolution (app/rules/context.py)
        from app.rules import context

        return context.amount(ctx, v["ref_amount"])
    if "types_among" in v:  # -- trigger other (wave 52B) -- the different card types of the batch's cards, as they are now (a card's types in the graveyard are its printed ones)
        from app.rules import context

        return len({"Kindred" if t == "Tribal" else t for _, ch in context.infos(plan, ctx, context.EVENT) for t in ch.types if t in CARD_TYPES})
    if "event_players" in v:  # -- trigger other (wave 52B) -- how many different players the "one or more" batch was about (triggers._event: the recipients of the batch)
        return len({p for p in (ctx.get("event") or {}).get("players") or [] if p in plan.live()})
    if "event_count" in v:  # how many objects the "one or more" batch had
        return max(0, int((ctx.get("event") or {}).get("count") or 0))
    if "greater" in v:  # (wave 51G)
        return max(evaluate(plan, ctx, x) for x in v["greater"])
    if "diff" in v:  # -- most-played cards II (wave 45A) -- "the difference between A and B": how far apart, never negative
        return abs(evaluate(plan, ctx, v["diff"][0]) - evaluate(plan, ctx, v["diff"][1]))
    if "minus" in v:  # -- refused zones/sized (wave 3R4) -- 107.1b: a negative result is 0
        return max(0, evaluate(plan, ctx, v["minus"][0]) - evaluate(plan, ctx, v["minus"][1]))
    if "defending_player_graveyard_count" in v:
        from app.rules import defending

        sel = selectors.from_key(v["defending_player_graveyard_count"])
        return sum(len(selectors.candidates(plan, selectors.replace(sel, zone_owner=f"player:{p}"), you, ctx.get("source_card"))) for p in defending.players(plan, ctx))
    if "greatest_damage100e" in v or "total_power100e" in v or "effigy_damage100e" in v:  # -- xdamage (wave 100E) -- Impact Resonance, Angrath,
        from app.rules import xdamage100e  # Blazing Effigy (app/rules/xdamage100e.py)

        return (xdamage100e.greatest_damage if "greatest_damage100e" in v else xdamage100e.total_power if "total_power100e" in v
                else xdamage100e.effigy_damage)(plan, ctx, v)
    if "hand" in v and str(v["hand"]).startswith("player:"):  # -- xdamage (wave 100E) -- one named player's hand (a villainous choice's "their hand", each_may._for)
        return len(plan.state.zones.get(f"{v['hand'][7:]}:hand", [])) if v["hand"][7:] in plan.live() else 0
    if "controller_hand100e" in v:  # -- xdamage (wave 100E) -- "the number of cards in that creature's controller's hand" (Flunk): its controller as it is, or as it last existed (608.2h)
        got = _object(plan, ctx, v["controller_hand100e"])
        return len(plan.state.zones.get(f"{got[0].controller}:hand", [])) if got is not None and got[0].controller in plan.live() else 0
    if "hand" in v and v["hand"] == "defending_player":
        from app.rules import defending

        return sum(len(plan.state.zones.get(f"{p}:hand", [])) for p in defending.players(plan, ctx))
    if "hand" in v and v["hand"] == "event":  # -- refused zones/sized (wave 3R4) -- the trigger's player ("that player")
        from app.rules import context

        return sum(len(plan.state.zones.get(f"{p}:hand", [])) for p in context.players(plan, ctx, context.EVENT)
                   if p in plan.live())
    if "hand" in v and v["hand"] == "chosen":  # the player the source chose as it entered (the count of a hand is public)
        from app.rules import chosen

        who = chosen.player_of(plan, ctx.get("source_card") or "")
        if who is None and ctx.get("unknown_choice_raises"):
            raise NoChosenPlayer
        return len(plan.state.zones.get(f"{who}:hand", [])) if who in plan.live() else 0
    if "hand" in v and str(v["hand"]).startswith("ref:"):  # -- trigger other (wave 52B) -- "that player" an earlier "choose an opponent" bound (a hand's size is public, 402.3)
        from app.rules import context

        return sum(len(plan.state.zones.get(f"{p}:hand", [])) for p in context.players(plan, ctx, v["hand"][4:]))
    if "hand" in v and v["hand"] == "all":  # (wave 19F) every player's hand, a public count
        return sum(len(plan.state.zones.get(f"{p}:hand", [])) for p in plan.live())
    if "hand" in v and v["hand"] == "opponent_max":  # (wave 42A) the opponent with the most cards in hand: that many (0 with no opponent)
        return max([len(plan.state.zones.get(f"{p}:hand", [])) for p in plan.live() if p != you] or [0])
    if "hand" in v:
        players = [you] if v["hand"] == "you" else _target_players(plan, ctx, v["hand"] if str(v["hand"]).startswith("target:") else "target")
        return sum(len(plan.state.zones.get(f"{p}:hand", [])) for p in players)
    if "library" in v:  # -- static grants (wave 15A) -- "half their library": the cards in the library of the player it names
        from app.rules import context

        players = [you] if v["library"] == "you" else context.players(plan, ctx, context.EVENT) if v["library"] == "event" \
            else _target_players(plan, ctx)
        return sum(len(plan.state.zones.get(f"{p}:library", [])) for p in players if p in plan.live())
    if "opponents" in v:
        return sum(1 for p in plan.live() if p != you)
    if "lowest_life" in v:  # -- most-played cards IV (wave 51G) -- the lowest life total among the players still in the game (Repay in Kind)
        return min(plan.state.players[p].life for p in plan.live())
    if "below_start" in v:  # -- most-played cards IV (wave 51G) -- "the difference" between the starting life total and a lower life total (119.1, 903.7), Shadow of Mortality
        return max(0, plan.state.settings.starting_life - plan.state.players[you].life)
    if "players_lost" in v:  # (wave 51G)
        return len(plan.state.seat_order) - len(plan.live())
    if "players_attacked" in v:  # -- if you do (wave 40A) -- 506.2, 506.6: a player is "being attacked" when a creature attacks that player (the ruling of Commander Liara Portyr, 2022-06-10: a planeswalker attacked alone does not count its controller)
        return len({c.attacking.id for c in plan.state.cards.values()
                    if c.attacking is not None and c.attacking.kind == "player" and c.zone.endswith(":battlefield") and c.attacking.id in plan.live()
                    and (v.get('by') != 'you' or (c.controller == you and c.attacking.id != you))})
    if "attacked_opponents" in v:  # -- casting extras (wave 18E) -- the players its controller attacked in the latest declaration
        return sum(1 for p in plan.rules.attacked_players.get(you, []) if p in plan.live() and p != you)
    if "life" in v:
        if v["life"] == "you":
            return max(0, plan.state.players[you].life)
        if v["life"] == "opponent_max":
            return max([plan.state.players[p].life for p in plan.live() if p != you] or [0])
        if v["life"] == "player_min":  # -- static wordings (wave 6E) -- "a player has 13 or less life": the lowest life total
            return min([plan.state.players[p].life for p in plan.live()] or [0])
        return max([plan.state.players[p].life for p in _target_players(plan, ctx)] or [0])
    if "unspent" in v:  # (106.4: the plain pool and the units both hold mana; "" = any color)
        me = plan.state.players[you]
        return sum(n for c, n in me.mana.items() if v["unspent"] in ("", c)) + sum(1 for u in me.mana_units if v["unspent"] in ("", u.sym))
    if "dungeons_completed" in v:  # -- dungeons (wave 45B) -- the different names among the dungeons you completed (309.7)
        return len(set(plan.rules.completed_dungeons.get(you, ())))
    if "players_with_counters" in v:
        spec=v["players_with_counters"]
        return sum(int(plan.state.players[p].resources.get(spec["kind"],0))>=spec["at_least"]
                   for p in plan.live() if spec["who"]!="opponents" or p!=you)
    if "all_counters_among_players_and_permanents" in v:
        player_total = sum(
            max(0, n)
            for pid in plan.live()
            for kind, n in plan.state.players[pid].resources.items()
            if kind != "speed"
        )
        permanents = selectors.Selector(types=tuple(PERMANENT_TYPES))
        return player_total + sum(
            max(0, n)
            for cid in selectors.candidates(plan, permanents, you)
            for n in plan.state.cards[cid].counters.values()
        )
    if "player_counters" in v:
        if v.get("of") in ("opponents", "all"):  # (wave 3E) "poison counters your opponents have": all of them together; -- zones (wave 100G) -- "all": among players (Vault 12)
            return sum(max(0, int(plan.state.players[p].resources.get(v["player_counters"], 0))) for p in plan.live() if p != you or v["of"] == "all")
        return max(0, int(plan.state.players[you].resources.get(v["player_counters"], 0)))
    if "party" in v:  # -- refused modal/conditional (wave 3R1) --
        return party_size(plan, you)
    if "opponents_hand" in v:  # -- triggers (wave 21B) -- the opponents still in the game (800.4a), by hand size as it resolves
        size = {p: len(plan.state.zones.get(f"{p}:hand", [])) for p in plan.live() if p != you}
        return sum(1 for k in size.values() if (k >= v["n"] if v["opponents_hand"] == "more" else k <= v["n"]))
    if "turns_taken" in v:  # -- most-played cards (wave 43B) -- "your first, second, or third turn of the game" (Starting Town): the turns you have begun, this one included
        tt = plan.rules.turns_taken
        return tt.get(you, 0) if tt else int(plan.state.turn.active_player == you)  # (before the first turn ends nothing is counted: it is the first player's first)
    if "commander_casts_of" in v:
        got = _object(plan, ctx, v["commander_casts_of"])
        if got is None or not got[0].commander_key:
            return 0
        card = got[0]
        return plan.state.players[card.owner].commander_casts.get(card.commander_key, 0)
    if "commander_casts" in v:  # -- triggers (wave 19B) --
        return sum(plan.state.players[you].commander_casts.values())
    if "exiled_with" in v:  # -- resolution memory (wave 22D) -- Unlicensed Hearse: "the number of cards exiled with it"
        from app.rules import exiled_with

        return len(exiled_with.cards(plan, ctx))
    if "same_name" in v:  # -- value grammar (wave 23C) -- 201.2: objects share a name when they have one in common (a split card has both)
        got = _object(plan, ctx, v["same_name"])
        if got is None:
            return 0
        names = set((got[1].name or "").split(" // "))
        return sum(1 for c in plan.state.cards.values() if c.zone.endswith(f":{v['zone']}") and names & set((plan.ch(c).name or "").split(" // ")))
    if "shared_type" in v:  # -- value grammar (wave 23C) -- the most of them that share one creature type (a changeling has every one: 702.73a)
        from collections import Counter

        from app.rules.creature_types import CREATURE_TYPES

        tally = Counter(t for c in selectors.candidates(plan, selectors.from_key(v["of"]), you, _other_than(ctx))
                        for t in plan.ch(plan.state.cards[c]).subtypes & CREATURE_TYPES)
        return max(tally.values(), default=0)
    if "distinct" in v:
        return _distinct(plan, ctx, v["distinct"], v["among"])
    if "abilities_among" in v:  # -- keyword soups (wave 50J) --
        from app.rules import keyword_soup

        return keyword_soup.count(plan, ctx, v["among"], v["abilities_among"])
    if "devotion" in v:
        return _devotion(plan, you, v["devotion"])
    if ("sum" in v or "max" in v) and str(v.get("of") or "").startswith("ref:"):
        from app.rules import context

        stat = v.get("sum") or v["max"]
        nums = [ref_stat for _, ch in context.infos(plan, ctx, v["of"][4:]) if (ref_stat := _stat_of(ch, stat)) is not None]
        return max(0, sum(nums) if "sum" in v else max(nums or [0]))
    if ("sum" in v or "max" in v) and v.get("of") == "event":  # -- event batches (wave 34C) -- "their total power" / "the greatest power among them": the
        from app.rules import (
            context,  # objects a "one or more" trigger's event holds (603.2c), as they were (608.2h)
        )

        stat = v.get("sum") or v["max"]
        nums = [stat_n for _, ch in context.infos(plan, ctx, context.EVENT) if (stat_n := _stat_of(ch, stat)) is not None]
        return max(0, sum(nums) if "sum" in v else max(nums or [0]))
    if "sum" in v or "max" in v:
        stat = v.get("sum") or v["max"]
        found = [_stat_of(plan.ch(plan.state.cards[c]), stat)
                 for key in (v["of"], *([v["also"]] if "also" in v else []))  # (wave 19F: "among A and B")
                 for c in selectors.candidates(plan, selectors.from_key(key), you, _other_than(ctx))]
        nums = [n for n in found if n is not None]
        return max(0, sum(nums) if "sum" in v else max(nums or [0]))
    for stat in ("power", "toughness", "base_power", "mana_value", "colors"):
        if stat in v:
            got = _object(plan, ctx, v[stat])
            if got is None:
                return 0
            obj, ch = got
            if stat == "colors":  # -- value grammar (wave 23C) -- 105.1: how many of the five colors it is
                return len(ch.colors)
            if stat == "mana_value":  # -- stack interaction (wave 5B) -- X on the stack counts (202.3e)
                from app.rules.stack_interaction import mana_value

                return max(0, mana_value(obj, ch))
            return max(0, _stat_of(ch, stat) or 0)
    if "relative" in v:  # -- token & pump wordings (wave 6C) -- statics._relative_count: about the object modified
        return _relative(plan, ctx, v)
    if "attached" in v:  # -- token & pump wordings (wave 6C) --
        got = _object(plan, ctx, v.get("on", "self"))
        if got is None or not getattr(got[0], "zone", "").endswith(":battlefield"):
            return 0
        host = got[0].id
        kinds = set(v["attached"])
        # -- attached events (wave 30S) -- 608.2h: this object left the battlefield before it resolved (Valduk's ruling 2022-12-08): the
        # Auras and Equipment last attached to it, wherever they are now
        snap = plan.rules.lki.get(ctx.get("source_object") or "") if v.get("on", "self") == "self" and plan.state.cards.get(host) is not got[0] else None
        if snap is not None:  # (-- review 30c -- a token Aura that ceased to exist, 704.5d, as it last existed too)
            from app.rules.triggers import _snapshot_card

            gone = {s.card: s for s in plan.rules.lki.values() if s.card in snap.attached and s.card not in plan.state.cards}
            return sum(1 for c in snap.attached if (c in plan.state.cards or c in gone) and kinds & (
                plan.ch(plan.state.cards[c]) if c in plan.state.cards else _snapshot_card(plan, gone[c])[1]).subtypes)
        return sum(1 for c in plan.state.cards.values() if c.attached_to == host and c.zone.endswith(":battlefield")
                   and plan.in_game(c) and kinds & plan.ch(c).subtypes)
    if "for_player" in v:  # -- value grammar (wave 23C) -- "the number of cards in that player's graveyard": the count as that one player's ("you" of the phrase)
        from app.rules import context

        if v["for_player"] == "host_controller":  # -- attached (wave 100F) -- "each tapped creature its controller controls" (Observed Stasis): the enchanted creature's
            got = _object(plan, ctx, "host")  # controller, as it is now (608.2h)
            return evaluate(plan, {**ctx, "controller": got[0].controller}, v["of"]) if got is not None else 0
        if v["for_player"] not in ("target", "event") and not re.fullmatch(r"target:\d+", v["for_player"]):
            raise ValueError(f"unbound player in {v!r}")  # (scripts binds "that_player" / "target_player" / "target_opponent" or refuses the line)
        players = _target_players(plan, ctx, v["for_player"]) if v["for_player"] != "event" else context.players(plan, ctx, context.EVENT)
        return evaluate(plan, {**ctx, "controller": players[0]}, v["of"]) if len(players) == 1 else 0
    if "counters_among" in v or "counter_kinds" in v:  # -- value grammar (wave 23C) -- counters on a group of permanents (122.1)
        held = [plan.state.cards[c].counters for c in selectors.candidates(plan, selectors.from_key(v["of"]), you, _other_than(ctx))]
        if "counter_kinds" in v:
            return len({k for cs in held for k, n in cs.items() if n > 0})
        return sum(cs.get(v["counters_among"], 0) if v["counters_among"] else sum(cs.values()) for cs in held)
    if "counters" in v:
        got = _object(plan, ctx, v.get("on", "self"))
        if got is None:
            return 0
        counters = got[0].counters
        return counters.get(v["counters"], 0) if v["counters"] else sum(counters.values())
    raise ValueError(f"unknown value {v!r}")


def evaluate_signed(plan: Plan, ctx: dict[str, Any], v: Value) -> int:
    """A modification's amount, with its sign ("-1/-1 for each …": ``{"neg": …}``; 613.4c)."""
    if isinstance(v, dict) and (v.get('linked_pool') or {}).get('projection') == 'power':
        from app.rules import linked_aggregates

        return int(linked_aggregates.aggregate(plan, ctx, v['linked_pool']))
    if isinstance(v, dict) and "neg" in v:
        return -evaluate(plan, ctx, v["neg"])
    return evaluate(plan, ctx, v)


def _signed_stat(plan: Plan, ctx: dict[str, Any], v: Value) -> int:
    """A power or toughness as it is, below 0 too (107.1b); any other value as ``evaluate`` reads it."""
    stat = next((s for s in ("power", "toughness") if isinstance(v, dict) and s in v and set(v) <= {s, "target_sel"}), None)
    if stat is None or not isinstance(v, dict):
        return evaluate(plan, ctx, v)
    got = _object(plan, ctx, v[stat])
    return 0 if got is None else _stat_of(got[1], stat) or 0


def _stat_of(ch: Any, stat: str) -> int | None:
    if stat == "base_power":
        return ch.base_pt[0] if ch.base_pt is not None else _stat_of(ch, "power")
    if stat == "mana_value":
        return int(ch.mana_value)
    if stat == "power_or_toughness":  # -- value grammar (wave 23C) -- "the greatest power and/or toughness among …": each object's larger number
        both = [n for n in (_stat_of(ch, "power"), _stat_of(ch, "toughness")) if n is not None]
        return max(both) if both else None
    if ch.pt is not None:
        return int(ch.pt[0 if stat == "power" else 1])
    raw = ch.power if stat == "power" else ch.toughness
    return int(raw) if raw is not None and raw.lstrip("-").isdigit() else None


def _other_than(ctx: dict[str, Any]) -> str | None:
    """What "other" / "another" in a counted selector leaves out: the source, unless the context
    says which object the count is about (``other_than``: a static's affected object — "Enchanted
    creature gets +1/+1 for each other creature you control" counts the others than IT)."""
    return ctx.get("other_than") or ctx.get("source_card")


def _target_players(plan: Plan, ctx: dict[str, Any], which: str = "target") -> list[str]:
    from app.rules.effects import target_refs  # (effects imports this module)

    return [t["id"] for t in target_refs(ctx, which) if t["id"] in plan.state.players and t["id"] in plan.live()]


def _distinct(plan: Plan, ctx: dict[str, Any], kind: str, key: str) -> int:
    """How many different card types / colors / basic land types / creature types the objects a
    selector names have between them."""
    found: set[str] = set()
    for cid in selectors.candidates(plan, selectors.from_key(key), ctx["controller"], _other_than(ctx)):
        ch = plan.ch(plan.state.cards[cid])
        if kind == "types":
            found |= {"Kindred" if t == "Tribal" else t for t in ch.types if t in CARD_TYPES}
        elif kind == "permanent_types":
            found |= ch.types & PERMANENT_TYPES
        elif kind == "colors":
            found |= set(ch.colors)
        elif kind == "basic_land_types":
            found |= ch.subtypes & set(BASIC_LAND_TYPES)
        elif kind == "names":  # -- token & pump wordings (wave 6C) -- "lands with different names" (201.2, 708.2a)
            if ch.name and not ch.face_down:
                found.add(ch.name)
        elif kind == "planeswalker_types":  # -- value grammar (wave 23C) -- 205.3j: the planeswalker subtypes of the planeswalkers
            if "Planeswalker" in ch.types:
                found |= ch.subtypes & selectors.PLANESWALKER_TYPES
        elif kind == "mana_costs":  # -- counters (wave 52D) -- 202.1b: no mana cost is no cost to pay, not a cost of its own (a nonland card with none, a suspend-only card: not counted)
            if ch.mana_cost:  # (-- review 52 -- 709.4b: a split card's cost is its halves combined, "{1}{R} // {1}{U}" is "{2}{U}{R}"; the symbols, not their order)
                syms = re.findall(r"\{([^}]+)\}", ch.mana_cost)
                found.add(f"{sum(int(x) for x in syms if x.isdigit())}|{sorted(x for x in syms if not x.isdigit())}")
        elif kind == "mana_values":  # -- as long as (wave 20B) -- "five or more mana values among cards in your graveyard" (202.3)
            found.add(str(int(ch.mana_value)))
        elif kind == "powers":  # "creatures with different powers" (conditions.py): how many distinct values
            power = _stat_of(ch, "power")
            if power is not None:
                found.add(str(power))
        else:
            from app.rules.creature_types import CREATURE_TYPES

            found |= ch.subtypes & CREATURE_TYPES
    return len(found)


def _relative(plan: Plan, ctx: dict[str, Any], v: Any) -> int:
    """-- token & pump wordings (wave 6C) -- the others (``among``, never the object itself) that share a creature type
    (205.3m) / have the same name (201.2) as the object a static modifies (layers: ``other_than``). A face-down
    permanent has no name (708.2a): it shares one with nothing."""
    from app.rules.creature_types import CREATURE_TYPES

    card = plan.state.cards.get(ctx.get("other_than") or "")
    if card is None:
        return 0
    if v["relative"] == "attached":  # -- attached events (wave 8D) -- the Auras / Equipment attached to the modified object
        kinds = set(v["kinds"])
        return sum(1 for c in plan.state.cards.values() if c.attached_to == card.id and c.zone.endswith(":battlefield")
                   and plan.in_game(c) and kinds & plan.ch(c).subtypes)
    if v["relative"] == "controller":  # -- attached events (wave 25D) -- "for each card in its controller's hand": the count as the modified object's controller's ("you")
        return evaluate(plan, {**ctx, "controller": card.controller}, v["of"])
    if v["relative"] == "counters":  # -- counters (wave 26D) -- "for each +1/+1 counter on it" (122.1): counters on the object modified
        return sum(n for k, n in card.counters.items() if v["kind"] in ("any", k))
    if v["relative"] == "attacks":  # -- commander sweep (wave 49B) -- "for each time it has attacked this turn" (Moraug): this turn's record of the object
        from app.rules import history

        return history.log_for(plan).attack_counts.get(plan.oid(card), 0)
    if v["relative"] in ("mana_symbols", "creature_types_count"):
        from app.rules import static_count_values94

        return static_count_values94.recipient(plan, card, v)
    mine = plan.ch(card)
    if v["relative"] == "bushido":  # -- counters (wave 44C) -- 702.45a: "for each point of bushido it has": the sum of its bushido abilities' numbers (each instance counts)
        return sum(int(n) for a in mine.abilities if "bushido" in a.keywords for n in re.findall(r"(?i)bushido (\d+)", a.text))
    if v["relative"] == "mana_value":  # -- attached events (wave 20A) -- 202.3: the object modified (a creature's X is 0 on the battlefield)
        from app.rules.stack_interaction import mana_value

        return max(0, mana_value(card, mine))
    if v["relative"] == "colors":
        return len(mine.colors)
    if v["relative"] == "creature_type":
        want = mine.subtypes & CREATURE_TYPES
        if not want:
            return 0
        ok = lambda ch: bool(ch.subtypes & want)  # noqa: E731
    else:
        if not mine.name or mine.face_down:
            return 0
        ok = lambda ch: ch.name == mine.name and not ch.face_down  # noqa: E731
    found = selectors.candidates(plan, selectors.from_key(v["among"]), ctx["controller"], card.id)
    return sum(1 for cid in found if cid != card.id and ok(plan.ch(plan.state.cards[cid])))


def _devotion(plan: Plan, you: str, colors: list[str]) -> int:
    """700.5: the number of mana symbols of those colors among the mana costs of permanents you
    control (a hybrid symbol of two of them counts once; a Phyrexian or twobrid symbol is a symbol
    of its color, 107.4e-f)."""
    # -- conditional statics (wave 4B) -- 700.5a: after copy (and control) effects only — mana costs as layer 1
    # leaves them, so a god's own "isn't a creature" never recurses here
    from app.rules.layers import copiable

    wanted = set(colors)
    total = 0
    for card in plan.state.cards.values():
        if not card.zone.endswith(":battlefield") or card.controller != you or not plan.in_game(card):
            continue
        copy_ch=copiable(plan.state,card,plan.info)
        total += sum(a.text=='Your devotion to each color and each combination of colors is increased by one.' for a in copy_ch.abilities)
        for sym in _MANA_SYMBOL.findall(copy_ch.mana_cost):
            if set(sym.split("/")) & wanted:
                total += 1
    return total


def kicked_holds(plan: Plan, ctx: dict[str, Any], need: Any, card_id: str | None = None) -> bool:
    """-- keywords (wave 50H) -- 702.33f: "if it was kicked", "kicked twice", "kicked with its {R} kicker" (``need``: True, ``{"times": 2}`` or ``{"with": "{R}"}``)."""
    n = kicked_count(plan, ctx)
    if not isinstance(need, dict):
        return n > 0
    if "times" in need:
        return n == need["times"]
    from app.rules.costs import kicker_cost

    entry = plan.rules.stack.get(ctx.get("stack_id") or "")
    record = plan.rules.payments.get(ctx.get("source_object") or "")
    mask = entry.kicked_mask if entry is not None and entry.kind == "spell" else record.kicked_mask if record is not None else 0
    card = plan.state.cards.get(card_id or ctx.get("source_card") or "")
    kick = kicker_cost(plan.ch(card).abilities) if card is not None else None
    bit = 0 if kick is None or not kick.second else 1 if kick.cost.upper() == need["with"].upper() else 2 if kick.second.upper() == need["with"].upper() else 0
    return bool(mask & bit)


def kicked_count(plan: Plan, ctx: dict[str, Any]) -> int:
    """702.33d: how many times the spell resolving (or copied, 707.10) was kicked; for an ability
    of a permanent, how many times the spell it was cast as was (its payment record)."""
    entry = plan.rules.stack.get(ctx.get("stack_id") or "")
    if entry is not None and entry.kind == "spell":
        return entry.kicked
    record = plan.rules.payments.get(ctx.get("source_object") or "")
    return record.kicked if record is not None else 0


def _object(plan: Plan, ctx: dict[str, Any], who: str) -> tuple[Any, Any] | None:
    """The object a value reads ("its power", "the target's toughness") and its characteristics:
    as it is now while it's still that object, else as it last existed (608.2h, 400.7). An
    object id with no current object and no last known information reads as nothing."""
    refs: list[tuple[str, str | None]] = []
    if who == "self":
        refs = [(ctx.get("source_card") or "", ctx.get("source_object"))]
    elif who == "target" or who.startswith("target:"):
        from app.rules.effects import target_refs  # (effects imports this module)

        refs = [(t["id"], t.get("object_id")) for t in target_refs(ctx, who)]
    if who == "host":  # -- attached events (wave 8D) -- "equipped creature", "enchanted creature": what the source is attached to
        from app.rules.effects import _cards  # (effects imports this module)

        refs = [(c, plan.oid(c)) for c in _cards(plan, ctx, "host")]
    if who.startswith("granter:"):  # -- xdamage (wave 100E) -- the granting object (layers.py binds its object id), as it is or as it last existed
        refs = [(next((c.id for c in plan.state.cards.values() if plan.oid(c) == who[8:]), ""), who[8:])]
    if who == "each":  # -- sized amounts (wave 3D) -- "each creature you control deals damage equal to its power": the one being read
        card = plan.state.cards.get(ctx.get("each_source") or "")
        return (card, plan.ch(card)) if card is not None else None
    if who == "cost:discarded":  # -- as long as (wave 9B) -- "the discarded card's mana value": the one card a cost discarded
        sid = ctx.get("stack_id")
        record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
        ids = record.discarded if record is not None else []
        card = plan.state.cards.get(ids[0]) if len(ids) == 1 else None
        return (card, plan.ch(card)) if card is not None else None
    if who == "cost:exiled":  # -- value grammar (wave 23C) -- "the exiled card's mana value": the one card a cost exiled (in exile now: printed values)
        sid = ctx.get("stack_id")
        record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
        ids = record.exiled if record is not None else []
        card = plan.state.cards.get(ids[0]) if len(ids) == 1 else None
        return (card, plan.ch(card)) if card is not None else None
    if who == "cost:tapped":  # -- activated sweep (wave 26C) -- "the power of the creature tapped this way": the one creature a cost tapped
        sid = ctx.get("stack_id")  # (review 26C: as it is while it's that object, else as it last existed, 608.2h / 400.7)
        record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
        ids = record.tapped_for_cost if record is not None else []
        oids = record.tapped_objects if record is not None else []
        if len(ids) != 1 or len(oids) != 1:
            return None
        refs = [(ids[0], oids[0])]
    if who == "cost:revealed":  # -- static_other sweep (wave 17C) -- "the revealed card's mana value": the one card a spell's cost revealed
        sid = ctx.get("stack_id") or ctx.get("source_card")
        record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
        ids = record.revealed if record is not None else []
        card = plan.state.cards.get(ids[0]) if len(ids) == 1 else None
        return (card, plan.ch(card)) if card is not None else None
    if who == "cost:sacrificed":  # -- sized amounts (wave 3D) -- "the sacrificed creature's power": what a cost sacrificed, as it last existed
        from app.rules.triggers import _snapshot_card

        sid = ctx.get("stack_id")
        record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
        oids = record.sacrificed_objects if record is not None else []
        snap = plan.rules.lki.get(oids[0]) if len(oids) == 1 else None
        return _snapshot_card(plan, snap) if snap is not None else None
    if who == "event" or who.startswith("ref:"):  # the trigger event's object, or an earlier effect's
        from app.rules import context  # (as it is, or as it last existed: 603.10a, 608.2h)

        return context.info(plan, ctx, context.EVENT if who == "event" else who[4:])
    for card_id, oid in refs:
        card = plan.state.cards.get(card_id)
        if card is not None and (oid is None or plan.oid(card) == oid):
            return card, plan.ch(card)
        snap = plan.rules.lki.get(oid or "")
        if snap is not None:
            from app.rules.triggers import _snapshot_card  # (triggers imports this module's users)

            return _snapshot_card(plan, snap)
        if who == "self" and card is not None and card.zone.endswith(":exile"):
            # -- scavenge (wave 12B) -- 702.97a: "the power of the card you exiled" as a cost from the graveyard. No last-known
            # snapshot is kept of a graveyard card, and in the graveyard and in exile it has its printed characteristics
            return card, plan.ch(card)
    return None


def _mana_spent(plan: Plan, ctx: dict[str, Any], which: str) -> int:
    from app.rules import context

    if which == "event" and isinstance((ctx.get("event") or {}).get("mana_spent"),dict):
        return sum(ctx["event"]["mana_spent"].values())
    if which == "event":  # (the spell as cast: its record is kept under the object that was on the stack)
        refs = context._object_refs(ctx, context.EVENT)
        oid = refs[0].object_id if len(refs) == 1 else ""
    else:
        oid = ctx.get("source_object") or ""
    record = plan.rules.payments.get(oid)
    if record is None or not record.mana_known:
        plan.note("The mana spent to cast the spell isn't known (read as 0) — adjust by hand",
                  [record.card] if record is not None and record.card in plan.state.cards else ())
        return 0
    return sum(record.mana_spent.values())


# -- refused modal/conditional (wave 3R1) --
PARTY_TYPES = ("Cleric", "Rogue", "Warrior", "Wizard")


def party_size(plan: Plan, you: str) -> int:
    """700.8: up to one each of a Cleric, a Rogue, a Warrior and a Wizard creature ``you`` control; 700.8a: counted
    by the game, 0 to 4; 700.8b: a creature of several of those types fills only one place, counted the way that
    gives the highest number (a maximum matching of creatures to the four places)."""
    roles: list[set[str]] = []
    for card in plan.state.cards.values():
        if card.zone == f"{you}:battlefield" and card.controller == you and plan.in_game(card):
            ch = plan.ch(card)
            if "Creature" in ch.types and (fits := set(PARTY_TYPES) & set(ch.subtypes)):
                roles.append(fits)
    taken: dict[str, int] = {}

    def place(i: int, seen: set[str]) -> bool:  # an augmenting path (Kuhn's algorithm)
        for role in sorted(roles[i]):
            if role in seen:
                continue
            seen.add(role)
            if role not in taken or place(taken[role], seen):
                taken[role] = i
                return True
        return False

    return sum(1 for i in range(len(roles)) if place(i, set()))
# -- end refused modal/conditional (wave 3R1) --
