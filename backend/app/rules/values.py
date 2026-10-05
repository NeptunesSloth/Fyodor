"""Quantities in effects ("draw two cards", "X damage", "a +1/+1 counter for each creature you
control"): explicit, deterministic expressions evaluated at resolution (608.2h: values are
determined as the effect is carried out).

A value is an int (a literal) or a dict:

* ``{"x": 1}`` — the X the spell or ability was cast / activated with (107.3);
* ``{"count": "<selector key>"}`` — the number of objects (or players) matching a selector;
* ``{"hand": "you" | "target"}`` — the number of cards in a player's hand;
* ``{"opponents": 1}`` — the number of opponents still in the game;
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

if TYPE_CHECKING:
    from app.rules.plan import Plan

Value = int | dict[str, Any]
NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "twenty": 20}
AMOUNT = r"(?:twice [xX]|(?:two|three|four) times [xX]|\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|x|X|that much|that many)"

# Counters that carry rules the engine doesn't model yet (122.1b keyword counters, 122.1c shield,
# 122.1d stun, 122.1h finality, 122.1i rad, 122.1j hone, 714 lore): an effect putting one of these
# stays manual rather than placing an inert marker.
UNMODELED_COUNTERS = frozenset({
    "decayed", "exalted",  # (-- counters (wave 5H) -- the other keyword counters give their keyword in layer 6:
    # app/rules/layers.keyword_counters, 122.1b, 613.1f, 613.7c)
    "rad", "hone"})  # (shield: 122.1c, wave 7C — shield_counters.py; lore: 714, sagas.py handles any lore counter put)  # (stun: 122.1d, wave 3F — keyword_actions.untap_stunned; finality: 122.1h, wave 3R4 — replacements.replace_move)

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
    if (m := re.fullmatch(r"(?:twice|(two|three|four) times) x", w)) is not None:  # (wave 16D) "twice X", "three times X"
        return {"times": [NUMBERS[m[1]] if m[1] else 2, {"x": 1}]}
    if w in ("that much", "that many"):
        return {"event_amount": 1}  # the trigger event's amount (TriggerEvent.amount)
    return None


# -- dynamic values (agent F): "the number of …" and friends --------------------------------------
_COUNT = re.compile(r"^the (?:total )?number of (?P<what>.+?)$")
_STATS = {"power": "power", "toughness": "toughness", "mana value": "mana_value", "power and/or toughness": "power_or_toughness"}
_COUNTERS_ON = re.compile(r"^(?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters? on (?P<on>.+)$")
_ON = {"~": "self", "it": "it", "this creature": "self", "this permanent": "self", "this artifact": "self",
       "this enchantment": "self", "this land": "self", "this equipment": "self", "this aura": "self",
       "that creature": "it", "that permanent": "it"}
_DISTINCT = {"card types": "types", "different card types": "types", "card type": "types",
             "colors": "colors", "different colors": "colors", "color": "colors",
             "basic land types": "basic_land_types", "basic land type": "basic_land_types",
             "creature types": "creature_types", "different creature types": "creature_types",
             "creature type": "creature_types",
             "different power": "powers", "different powers": "powers",  # (wave 17B: Selvala, Eager Trailblazer)
             "mana values": "mana_values", "different mana values": "mana_values", "mana value": "mana_values",
             "different mana value": "mana_values", "planeswalker types": "planeswalker_types"}  # (wave 21F: Eris, Roar of the Storm)  # (wave 20B)
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
_PLUS = re.compile(r"^(?P<v>.+?) plus (?P<n>\d+|one|two|three|four|five)$")
_TYPE_WORDS = "|".join(selectors.CARD_TYPES)


# -- ability words (wave 4F) -- converge: "the number of colors of mana spent to cast this spell", "for each color of
# mana spent to cast it": the colors (105.1) among the mana actually spent on its total cost (601.2h), from the
# spell's payment record (the same record for the permanent it became; a copy wasn't cast: none, 707.10)
_COLORS_SPENT = re.compile(r"colors? of mana spent to cast (?:this spell|it|~|this creature|this permanent)")


# -- X actions (wave 9A) -- 700.14-style "mana spent": the total amount of mana paid for the spell (601.2h), from its payment
# record; "that spell" is the cast event's spell, "her" / "this spell" / "~" the source (the permanent remembers its spell's
# record). A bare "it" is not read: it could be either.
# -- mana provenance (wave 18B) -- 107.4h/106.3: "the amount of {S} spent to cast this spell", "{S} spent to cast it", "mana from a Treasure
# spent to cast it / this spell" (PaymentRecord.mana_tags; the source's own record, like converge)
_FROM_TAGS = {"treasure": "Treasure", "artifact": "Artifact", "desert": "Desert", "cave": "Cave", "creature": "Creature"}
_MANA_FROM = re.compile(r"(?:the amount of )?(?:\{S\}|mana from (?:an? )?(?P<what>[Tt]reasure|[Aa]rtifact|[Dd]esert|[Cc]ave|[Cc]reature)(?: source)?)(?: that was)? spent to cast "
                        r"(?:this spell|it|~|this creature|this permanent)")
_MANA_SPENT = re.compile(r"(?:the )?amount of mana spent to cast (?P<o>that spell|this spell|her|him|~|this creature)")


_THAT_PLAYER = re.compile(r"\b(?:that player's|their|that player controls|they control|that player owns|they own)\b")
_THAT_PLAYER_TO_YOU = {"that player's": "your", "their": "your", "that player controls": "you control", "they control": "you control",
                       "that player owns": "you own", "they own": "you own"}


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
    if p.endswith(" beyond the first"):  # -- keywords (wave 15E) -- rampage 702.23a: "for each creature blocking it beyond the first"
        inner = _parse_count(p[: -len(" beyond the first")], it=it)
        return None if inner is None else {"minus": [inner, 1]}
    # -- cost self reduction (wave 16F) -- "for each 1 life you gained this turn" (a count of life)
    p = re.sub(r"^1 (life you (?:gained|lost) this turn)$", r"\1", p)
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
    m = re.match(r"^twice (?P<v>.+)$", what)
    if m:
        inner = parse_count(m["v"], it=it)
        return {"times": [2, inner]} if inner is not None else None
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
    if what in ("opponents you have", "opponent you have", "your opponents", "opponent", "opponents"):
        return {"opponents": 1}
    if what in ("cards exiled with ~", "cards exiled with it", "card exiled with ~", "card exiled with it"):
        return {"exiled_with": 1}  # -- resolution memory (wave 22D) -- 607.2a: the cards the linked ability exiled and that are still there
    if what == "opponent you attacked with a creature this combat":  # -- casting extras (wave 18E) -- melee 702.121a
        return {"attacked_opponents": 1}
    if re.fullmatch(r"times? (?:it|he|she|~|this (?:spell|creature|permanent|enchantment|artifact|land|planeswalker)) (?:was|were) kicked", what):
        return {"kicked": 1}  # (wave 23C: plural and "he"/"she"/"this permanent": 702.33d, a permanent remembers how its spell was kicked)
    if what in ("times this creature has mutated", "times ~ has mutated", "times this permanent has mutated", "time this creature has mutated"):  # -- merged permanents (wave 18D)
        return {"mutated": 1}  # (702.140: how many spells merged with it)
    if what in ("creature it devoured", "creature ~ devoured"):  # -- keyword mechanics (wave 9D) -- 702.82b
        return {"devoured": 1}
    if _COLORS_SPENT.fullmatch(what):  # -- ability words (wave 4F) -- converge
        return {"colors_spent": 1}
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
    m = re.fullmatch(r"(?P<c>white|blue|black|red|green) mana symbols? (?:in|among) the mana costs? of permanents you control", what)
    if m:  # -- value grammar (wave 23C) -- 700.5: that IS devotion (chroma)
        return {"devotion": [_COLOR_WORDS[m["c"]]]}
    m = _DEVOTION.match(what)
    if m:
        return {"devotion": [_COLOR_WORDS[c] for c in (m["c1"], m["c2"]) if c]}
    m = _PLAYER_COUNTERS.match(what)
    if m:
        return {"player_counters": m["kind"]}
    if _EXCESS_DEALT.fullmatch(what):  # -- as long as (wave 9B) -- 120.10: scripts bind it to the damage just before (this_way.excess_dealt)
        return {"ref_amount": "excess_dealt"}
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
    m = _AMONG.match(what)
    if m:
        key = _selector_key(m["sel"])
        return {"distinct": _DISTINCT[m["kind"]], "among": key} if key else None
    if what == "the greatest mana value among your commanders":  # -- value grammar (wave 23C) -- 903.3: a commander is one wherever it is (Cactus Preserve)
        return {"max": "mana_value", "of": selectors.Selector(commander=True, owner="you", zones=selectors.ZONES).key()}
    if what == "the greatest mana value of a commander you own on the battlefield or in the command zone":  # -- amounts (wave 12C) --
        return {"max": "mana_value", "of": selectors.Selector(commander=True, owner="you", zones=("battlefield", "command")).key()}  # 903.3
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
_TURN_DREW = re.compile(r"^(?:the number of )?cards? you(?:'ve| have) drawn this turn$")
_TURN_DIED = re.compile(r"^(?:the number of )?(?P<sel>creatures?|nontoken creatures?|[A-Z][a-z-]+) that died(?P<mine> under your control)? this turn$")
_OPPONENTS_WHO = re.compile(r"^(?:the number of )?opponents? who (?:(?P<drew>drew (?P<n>\w+) or more cards)|"
                            r"(?P<lost>lost life)|(?P<hurt>was dealt damage)|(?P<lands>had (?P<m>\w+) or more lands enter the battlefield under their control)) "
                            r"this turn$")


_OPPONENTS_HAND = re.compile(r"^(?:the number of )?opponents? who (?:has|have) (?P<n>\w+) or (?P<cmp>more|fewer) cards in hand$")  # (-- triggers (wave 21B) --)
# ("who has more cards in hand than you" stays manual: tests/test_rules_wave8b_triggers.py)


def _turn_amount(what: str) -> Value | None:
    if m := _OPPONENTS_HAND.match(what):  # each opponent whose hand size now says so (the count of a hand is public)
        n = int(m["n"]) if m["n"].isdigit() else NUMBERS.get(m["n"])
        return {"opponents_hand": m["cmp"], "n": n} if n is not None else None
    m = _TURN_LIFE.match(what)
    if m:
        return {"turn_history": "gained" if m["k"] == "gained" else "lost"}
    if (m := _TURN_SPELL.match(what)):
        return {"spells_cast": "you" if m["who"] == "you" else "event_player"}
    if re.fullmatch(r"cards? you(?:'ve)? discarded this turn", what):  # -- value grammar (wave 23C) -- a cycled card is discarded too (702.29a)
        return {"turn_history": "discarded"}
    m = re.fullmatch(r"creature (?:(?P<any>that attacked)|(?P<mine>you attacked with)) this turn", what)
    if m:  # -- cost self reduction (wave 16F) -- the creatures declared as attackers (508.1, wave 4D log), whether or not still here
        return {"turn_history": "attackers", **({"who": "you"} if m["mine"] else {})}
    if _TURN_DREW.match(what):
        return {"turn_history": "drew"}
    m = _TURN_DIED.match(what)
    if m:  # 700.4; as they last existed on the battlefield (608.2i)
        # -- trigger tail (wave 15B) -- "for each Zubera that died this turn": a creature type counts creatures (700.4)
        sel = selectors.parse(m["sel"] + (" creature" if m["sel"][0].isupper() else ""))
        if sel is None:
            return None
        # -- X actions (wave 9A) -- "that died under your control this turn": the ones you controlled as they died (700.4)
        return {"turn_history": "died", "sel": sel.key(), **({"who": "you"} if m["mine"] else {})}
    # -- X sized by a count (wave 19F) -- this turn's log: tokens you created, permanents you sacrificed, what your opponents lost
    if re.fullmatch(r"tokens? you(?:'ve)? created this turn", what):
        return {"turn_history": "tokens"}
    if m := re.fullmatch(r"permanents? (you(?:'ve)? )?sacrificed this turn", what):  # (wave 21F: The Balrog, "each permanent sacrificed": anyone's)
        return {"turn_history": "sacrificed", **({} if m[1] else {"who": "any"})}
    if re.fullmatch(r"cards? you(?:'ve)? cycled or discarded this turn", what):  # (wave 21F: Hollow One; a cycled card is discarded, 702.29a)
        return {"turn_history": "discarded"}
    if re.fullmatch(r"(?:the )?(?:total )?(?:amount of )?life (?:lost by your opponents|your opponents have lost) this turn", what):
        return {"turn_history": "opp_lost"}
    if re.fullmatch(r"(?:the )?(?:total )?damage dealt to your opponents this turn", what):
        return {"turn_history": "opp_damage"}
    m = _OPPONENTS_WHO.match(what)
    if m:  # each opponent whose history this turn says so (one per opponent)
        word = m["n"] or m["m"]
        n = 1 if word is None else int(word) if word.isdigit() else NUMBERS.get(word)
        if n is None:
            return None
        return {"turn_history": "opponents_who", "what": "drew" if m["drew"] else "lost" if m["lost"] else "damaged" if m["hurt"] else "lands", "n": n}
    from app.rules import (
        player_filter,  # -- per-player filters (wave 23A) -- "for each opponent who controls fewer creatures than you"
    )

    return player_filter.count(what)
# -- end this-turn history (wave 4D) --


def _normalise(what: str) -> str:
    """Noun phrases the selector grammar spells differently: "cards in all graveyards" (400.1:
    every player's), "instant and sorcery cards" (cards of either type: a list, not "artifact
    creature"'s both-types reading)."""
    out = re.sub(r"\b(?:from|in) all graveyards$", "in graveyards", re.sub(r" on the battlefield(?=$| named ~| with )", "", what))  # (sized amounts, wave 3D)
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
    you = ctx["controller"]
    if "players_where" in v:  # -- per-player filters (wave 23A) -- the players a predicate holds for (app/rules/player_filter.py)
        from app.rules import player_filter

        return player_filter.amount(plan, ctx, v)
    if "ref_count" in v:  # -- "this way" outcomes (wave 4A) -- what an earlier instruction actually did
        from app.rules import this_way

        return this_way.count(plan, ctx, v)
    if "per_player" in v:  # -- damage sized by a count (wave 4E) -- read for the recipient player (app/rules/sized_damage.py)
        from app.rules import sized_damage

        return sized_damage.evaluate(plan, ctx, v)
    if "x" in v:
        return max(0, int(ctx.get("x") or 0))
    if "die" in v:  # -- rolling dice (wave 12A) -- this resolution's own roll (app/rules/dice.py)
        from app.rules import dice

        return dice.evaluate(ctx, v["die"])
    if "paid_x" in v:  # -- sized payments (wave 5G) -- the X an optional payment of this resolution paid
        from app.rules import paid_x

        return paid_x.amount(ctx, v["paid_x"])
    if "times" in v:
        a, b = v["times"]
        return evaluate(plan, ctx, a) * evaluate(plan, ctx, b)
    if "plus" in v:
        return sum(evaluate(plan, ctx, x) for x in v["plus"])
    if "half" in v:
        n = evaluate(plan, ctx, v["half"])
        return (n + 1) // 2 if v.get("round") == "up" else n // 2
    if "neg" in v:
        return 0  # a negative result of an effect is zero (107.1b); the sign is evaluate_signed's
    if "kicked" in v:
        return kicked_count(plan, ctx)
    if "mutated" in v:  # -- merged permanents (wave 18D) --
        from app.rules import merged

        return merged.times_mutated_in(plan, ctx)
    if "devoured" in v:  # -- keyword mechanics (wave 9D) -- 702.82b: sacrificed as a result of its devour as it entered
        return plan.rules.devoured.get(ctx.get("source_object") or "", 0)
    if "colors_spent" in v:  # -- ability words (wave 4F) -- converge (a spell cast by hand: no mana known, 0)
        record = plan.rules.payments.get(ctx.get("source_object") or "")
        if record is None:
            return 0
        if not record.mana_known:  # -- review (wave 4R) -- cast by hand: say the 0 isn't the colors spent
            name = plan.state.cards[record.card].name if record.card in plan.state.cards else ''
            plan.note(f"{name or 'It'} was cast by hand: the colors of mana spent to cast it aren't known (read as 0) — "
                      "adjust by hand", [record.card] if record.card in plan.state.cards else ())
            return 0
        return sum(1 for c in "WUBRG" if record.mana_spent.get(c, 0) > 0)
    if "mana_from" in v:  # -- mana provenance (wave 18B) -- {S} (107.4h) or mana from a Treasure ... spent to cast the source
        record = plan.rules.payments.get(ctx.get("source_object") or "")
        if record is None or not record.mana_known:
            plan.note("What paid for the spell isn't known (read as 0) — adjust by hand",
                      [record.card] if record is not None and record.card in plan.state.cards else ())
            return 0
        return sum(1 for t in record.mana_tags if v["mana_from"] in t)
    if "mana_spent" in v:  # -- X actions (wave 9A) -- a spell cast by hand: no mana known, 0 (and said so)
        return _mana_spent(plan, ctx, v["mana_spent"])
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
        return len(selectors.candidates(plan, sel, you, _other_than(ctx)))
    if "spells_cast" in v:  # -- sized amounts (wave 3D) -- "the number of spells you've cast this turn"
        from app.rules import context

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
    if "event_count" in v:  # how many objects the "one or more" batch had
        return max(0, int((ctx.get("event") or {}).get("count") or 0))
    if "minus" in v:  # -- refused zones/sized (wave 3R4) -- 107.1b: a negative result is 0
        return max(0, evaluate(plan, ctx, v["minus"][0]) - evaluate(plan, ctx, v["minus"][1]))
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
    if "hand" in v and v["hand"] == "all":  # (wave 19F) every player's hand, a public count
        return sum(len(plan.state.zones.get(f"{p}:hand", [])) for p in plan.live())
    if "hand" in v:
        players = [you] if v["hand"] == "you" else _target_players(plan, ctx)
        return sum(len(plan.state.zones.get(f"{p}:hand", [])) for p in players)
    if "library" in v:  # -- static grants (wave 15A) -- "half their library": the cards in the library of the player it names
        from app.rules import context

        players = [you] if v["library"] == "you" else context.players(plan, ctx, context.EVENT) if v["library"] == "event" \
            else _target_players(plan, ctx)
        return sum(len(plan.state.zones.get(f"{p}:library", [])) for p in players if p in plan.live())
    if "opponents" in v:
        return sum(1 for p in plan.live() if p != you)
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
    if "player_counters" in v:
        if v.get("of") == "opponents":  # (wave 3E) "poison counters your opponents have": all of them together
            return sum(max(0, int(plan.state.players[p].resources.get(v["player_counters"], 0))) for p in plan.live() if p != you)
        return max(0, int(plan.state.players[you].resources.get(v["player_counters"], 0)))
    if "party" in v:  # -- refused modal/conditional (wave 3R1) --
        return party_size(plan, you)
    if "opponents_hand" in v:  # -- triggers (wave 21B) -- the opponents still in the game (800.4a), by hand size as it resolves
        size = {p: len(plan.state.zones.get(f"{p}:hand", [])) for p in plan.live() if p != you}
        return sum(1 for k in size.values() if (k >= v["n"] if v["opponents_hand"] == "more" else k <= v["n"]))
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
    if "devotion" in v:
        return _devotion(plan, you, v["devotion"])
    if "sum" in v or "max" in v:
        stat = v.get("sum") or v["max"]
        found = [_stat_of(plan.ch(plan.state.cards[c]), stat)
                 for key in (v["of"], *([v["also"]] if "also" in v else []))  # (wave 19F: "among A and B")
                 for c in selectors.candidates(plan, selectors.from_key(key), you, _other_than(ctx))]
        nums = [n for n in found if n is not None]
        return max(0, sum(nums) if "sum" in v else max(nums or [0]))
    for stat in ("power", "toughness", "mana_value", "colors"):
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
        return sum(1 for c in plan.state.cards.values() if c.attached_to == host and c.zone.endswith(":battlefield")
                   and plan.in_game(c) and kinds & plan.ch(c).subtypes)
    if "for_player" in v:  # -- value grammar (wave 23C) -- "the number of cards in that player's graveyard": the count as that one player's ("you" of the phrase)
        from app.rules import context

        if v["for_player"] not in ("target", "event"):
            raise ValueError(f"unbound player in {v!r}")  # (scripts binds "that_player" / "target_player" / "target_opponent" or refuses the line)
        players = _target_players(plan, ctx) if v["for_player"] == "target" else context.players(plan, ctx, context.EVENT)
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
    if isinstance(v, dict) and "neg" in v:
        return -evaluate(plan, ctx, v["neg"])
    return evaluate(plan, ctx, v)


def _stat_of(ch: Any, stat: str) -> int | None:
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


def _target_players(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    from app.rules.effects import target_refs  # (effects imports this module)

    return [t["id"] for t in target_refs(ctx, "target") if t["id"] in plan.state.players and t["id"] in plan.live()]


def _distinct(plan: Plan, ctx: dict[str, Any], kind: str, key: str) -> int:
    """How many different card types / colors / basic land types / creature types the objects a
    selector names have between them."""
    found: set[str] = set()
    for cid in selectors.candidates(plan, selectors.from_key(key), ctx["controller"], _other_than(ctx)):
        ch = plan.ch(plan.state.cards[cid])
        if kind == "types":
            found |= {"Kindred" if t == "Tribal" else t for t in ch.types if t in CARD_TYPES}
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
    mine = plan.ch(card)
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
        for sym in _MANA_SYMBOL.findall(copiable(plan.state, card, plan.info).mana_cost):
            if set(sym.split("/")) & wanted:
                total += 1
    return total


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
