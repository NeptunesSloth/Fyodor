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
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "twenty": 20}
AMOUNT = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|x|X|that much|that many)"

# Counters that carry rules the engine doesn't model yet (122.1b keyword counters, 122.1c shield,
# 122.1d stun, 122.1h finality, 122.1i rad, 122.1j hone, 714 lore): an effect putting one of these
# stays manual rather than placing an inert marker.
UNMODELED_COUNTERS = frozenset({
    "decayed", "exalted",  # (-- counters (wave 5H) -- the other keyword counters give their keyword in layer 6:
    # app/rules/layers.keyword_counters, 122.1b, 613.1f, 613.7c)
    "shield", "rad", "hone", "lore"})  # (stun: 122.1d, wave 3F — keyword_actions.untap_stunned; finality: 122.1h, wave 3R4 — replacements.replace_move)

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
    if w in ("that much", "that many"):
        return {"event_amount": 1}  # the trigger event's amount (TriggerEvent.amount)
    return None


# -- dynamic values (agent F): "the number of …" and friends --------------------------------------
_COUNT = re.compile(r"^the (?:total )?number of (?P<what>.+?)$")
_STATS = {"power": "power", "toughness": "toughness", "mana value": "mana_value"}
_COUNTERS_ON = re.compile(r"^(?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters? on (?P<on>.+)$")
_ON = {"~": "self", "it": "it", "this creature": "self", "this permanent": "self", "this artifact": "self",
       "this enchantment": "self", "this land": "self", "this equipment": "self", "this aura": "self",
       "that creature": "it", "that permanent": "it"}
_DISTINCT = {"card types": "types", "different card types": "types", "card type": "types",
             "colors": "colors", "different colors": "colors", "color": "colors",
             "basic land types": "basic_land_types", "basic land type": "basic_land_types",
             "creature types": "creature_types", "different creature types": "creature_types",
             "creature type": "creature_types"}
_AMONG = re.compile(r"^(?P<kind>" + "|".join(sorted(map(re.escape, _DISTINCT), key=len, reverse=True)) + r") among (?P<sel>.+)$")
_DEVOTION = re.compile(r"^your devotion to (?P<c1>white|blue|black|red|green)(?: and (?P<c2>white|blue|black|red|green))?$")
_AGGREGATE = re.compile(r"^the (?:(?P<max>greatest|highest)|(?P<sum>total)) (?P<stat>power|toughness|mana value) "
                        r"(?:among|of) (?P<sel>.+)$")
_PLAYER_COUNTERS = re.compile(r"^(?P<kind>[a-z]+) counters? you have$")
# -- counters & designations (wave 3E) -- "poison counters your opponents have" (all of them together),
# "{E} you have" / "the amount of {E} you have" (107.14: each {E} is an energy counter)
_PLAYER_COUNTERS_3E = re.compile(r"^(?:the amount of )?(?:(?P<kind>poison|experience|rad|energy) counters?|(?P<e>\{E\})) "
                                 r"(?P<who>you have|your opponents have)$")
_HALF = re.compile(r"^half (?P<v>.+?), rounded (?P<round>up|down)$")
_PLUS = re.compile(r"^(?P<v>.+?) plus (?P<n>\d+|one|two|three|four|five)$")
_TYPE_WORDS = "|".join(selectors.CARD_TYPES)


# -- ability words (wave 4F) -- converge: "the number of colors of mana spent to cast this spell", "for each color of
# mana spent to cast it": the colors (105.1) among the mana actually spent on its total cost (601.2h), from the
# spell's payment record (the same record for the permanent it became; a copy wasn't cast: none, 707.10)
_COLORS_SPENT = re.compile(r"colors? of mana spent to cast (?:this spell|it|~|this creature|this permanent)")


def parse_count(phrase: str, *, it: str | None = None) -> Value | None:
    """See ``_parse_count``. -- damage wordings (wave 6B) -- a count of what "that player" controls is a different
    number for each player it could name (the target player's, the recipient's: app/rules/sized_damage.py): never read
    through the selectors' trigger-bound "that player" (selectors.THAT_PLAYER)."""
    v = _parse_count(phrase, it=it)
    return None if v is not None and f'"controller":"{selectors.THAT_PLAYER}"' in str(v) else v


def _parse_count(phrase: str, *, it: str | None = None) -> Value | None:
    """A quantity phrase → value: "the number of creatures you control" / "cards in your hand" /
    "opponents you have" / "+1/+1 counters on ~" / "card types among cards in all graveyards" /
    "your devotion to green" / "your life total" / "twice …" / "half …, rounded up" / "X".

    ``it`` is what a bare "it" means for the caller ("counters on it": the static's own source
    is "self"); None refuses it (a pronoun the caller can't bind is never guessed)."""
    p = phrase.strip()
    m = _COUNT.match(p)
    what = m["what"] if m else p
    if what.lower() == "x":
        return {"x": 1}
    # -- refused zones/sized (wave 3R4) -- "the number of cards in their hand minus 4", "3 minus the number of …",
    # "… minus the number of cards in your hand": never below 0 (107.1b)
    minus = re.match(r"^(?P<a>.+?) minus (?P<b>\d+|one|two|three|four|five|the number of .+)$", what)
    if minus:
        a_text = minus["a"] if m is None else f"the number of {minus['a']}"
        a = int(a_text) if a_text.isdigit() else NUMBERS.get(a_text) or parse_count(a_text, it=it)
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
    if what in ("cards in your hand", "card in your hand"):
        return {"hand": "you"}
    if what in ("creatures in your party", "creature in your party"):  # -- refused modal/conditional (wave 3R1) --
        return {"party": "you"}  # 700.8
    if what in ("cards in target player's hand", "cards in target opponent's hand"):
        return {"hand": "target"}
    if what in ("opponents you have", "opponent you have", "your opponents", "opponent", "opponents"):
        return {"opponents": 1}
    if what in ("time it was kicked", "time this spell was kicked", "time ~ was kicked"):
        return {"kicked": 1}
    if _COLORS_SPENT.fullmatch(what):  # -- ability words (wave 4F) -- converge
        return {"colors_spent": 1}
    if what == "your life total":
        return {"life": "you"}
    if what in ("target player's life total", "target opponent's life total"):
        return {"life": "target"}
    if what in ("the highest life total among your opponents", "the greatest life total among your opponents"):
        return {"life": "opponent_max"}
    m = _DEVOTION.match(what)
    if m:
        return {"devotion": [_COLOR_WORDS[c] for c in (m["c1"], m["c2"]) if c]}
    m = _PLAYER_COUNTERS.match(what)
    if m:
        return {"player_counters": m["kind"]}
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
    m = _AGGREGATE.match(what)
    if m:
        key = _selector_key(m["sel"])
        if key is None or selectors.from_key(key).player is not None:
            return None
        return {"max" if m["max"] else "sum": _STATS[m["stat"]], "of": key}
    if what.startswith(("the ", "a ", "an ")):
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
_SPELLS_CAST = re.compile(r"^(?:the number of )?spells you(?:'ve| have) cast this turn$")


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
    if _SPELLS_CAST.match(what):
        return {"spells_cast": "you"}
    return _turn_amount(what)


# -- this-turn history (wave 4D) -- amounts of this turn's history (app/rules/history.py: TurnLog), read as the effect
# is carried out (608.2h): "the amount of life you gained this turn", "spell you've cast this turn" ("for each …"),
# "cards you've drawn this turn", "creatures that died this turn", "opponent who drew two or more cards this turn".
_TURN_LIFE = re.compile(r"^(?:the )?(?:amount of )?life you(?:'ve| have)? (?P<k>gained|lost) this turn$")
_TURN_SPELL = re.compile(r"^spell you(?:'ve| have) cast this turn$")
_TURN_DREW = re.compile(r"^(?:the number of )?cards? you(?:'ve| have) drawn this turn$")
_TURN_DIED = re.compile(r"^(?:the number of )?(?P<sel>creatures?|nontoken creatures?) that died this turn$")
_OPPONENTS_WHO = re.compile(r"^(?:the number of )?opponents? who (?:(?P<drew>drew (?P<n>\w+) or more cards)|"
                            r"(?P<lost>lost life)|(?P<lands>had (?P<m>\w+) or more lands enter the battlefield under their control)) "
                            r"this turn$")


def _turn_amount(what: str) -> Value | None:
    m = _TURN_LIFE.match(what)
    if m:
        return {"turn_history": "gained" if m["k"] == "gained" else "lost"}
    if _TURN_SPELL.match(what):
        return {"spells_cast": "you"}
    if _TURN_DREW.match(what):
        return {"turn_history": "drew"}
    m = _TURN_DIED.match(what)
    if m:  # 700.4; as they last existed on the battlefield (608.2i)
        sel = selectors.parse(m["sel"])
        return {"turn_history": "died", "sel": sel.key()} if sel is not None else None
    m = _OPPONENTS_WHO.match(what)
    if m:  # each opponent whose history this turn says so (one per opponent)
        word = m["n"] or m["m"]
        n = 1 if word is None else int(word) if word.isdigit() else NUMBERS.get(word)
        if n is None:
            return None
        return {"turn_history": "opponents_who", "what": "drew" if m["drew"] else "lost" if m["lost"] else "lands", "n": n}
    return None
# -- end this-turn history (wave 4D) --


def _normalise(what: str) -> str:
    """Noun phrases the selector grammar spells differently: "cards in all graveyards" (400.1:
    every player's), "instant and sorcery cards" (cards of either type: a list, not "artifact
    creature"'s both-types reading)."""
    out = re.sub(r"\b(?:from|in) all graveyards$", "in graveyards", re.sub(r" on the battlefield$", "", what))  # (sized amounts, wave 3D)
    return re.sub(rf"\b(?P<a>{_TYPE_WORDS}) and (?P<b>{_TYPE_WORDS}) (?P<n>cards?|spells?)\b", r"\g<a> or \g<b> \g<n>", out)


def _selector_key(phrase: str) -> str | None:
    sel = selectors.parse(_normalise(phrase))
    return sel.key() if sel is not None else None


def evaluate(plan: Plan, ctx: dict[str, Any], v: Value) -> int:
    """The number a value stands for right now (never negative: 107.1b)."""
    if isinstance(v, int):
        return max(0, v)
    you = ctx["controller"]
    if "ref_count" in v:  # -- "this way" outcomes (wave 4A) -- what an earlier instruction actually did
        from app.rules import this_way

        return this_way.count(plan, ctx, v)
    if "per_player" in v:  # -- damage sized by a count (wave 4E) -- read for the recipient player (app/rules/sized_damage.py)
        from app.rules import sized_damage

        return sized_damage.evaluate(plan, ctx, v)
    if "x" in v:
        return max(0, int(ctx.get("x") or 0))
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
    if "named_self_in_graveyards" in v:  # -- mana riders (wave 5A) -- cards with the source's name in every graveyard
        from app.rules import characteristics as chars

        src = plan.state.cards.get(ctx.get("source_card") or "")
        name = chars.of(src, plan.info).name if src is not None else ""
        live = plan.live()
        return sum(1 for key, ids in plan.state.zones.items() if key.endswith(":graveyard") and key.split(":")[0] in live
                   for cid in ids if name and chars.of(plan.state.cards[cid], plan.info).name == name)
    if "count" in v:
        sel = selectors.from_key(v["count"])
        if sel.player is not None:
            return sum(1 for p in plan.live() if selectors.matches_player(plan, sel, p, you))
        return len(selectors.candidates(plan, sel, you, _other_than(ctx)))
    if "spells_cast" in v:  # -- sized amounts (wave 3D) -- "the number of spells you've cast this turn"
        return plan.rules.spells_this_turn(you, plan.state.turn.number)
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
    if "hand" in v:
        players = [you] if v["hand"] == "you" else _target_players(plan, ctx)
        return sum(len(plan.state.zones.get(f"{p}:hand", [])) for p in players)
    if "opponents" in v:
        return sum(1 for p in plan.live() if p != you)
    if "life" in v:
        if v["life"] == "you":
            return max(0, plan.state.players[you].life)
        if v["life"] == "opponent_max":
            return max([plan.state.players[p].life for p in plan.live() if p != you] or [0])
        return max([plan.state.players[p].life for p in _target_players(plan, ctx)] or [0])
    if "player_counters" in v:
        if v.get("of") == "opponents":  # (wave 3E) "poison counters your opponents have": all of them together
            return sum(max(0, int(plan.state.players[p].resources.get(v["player_counters"], 0))) for p in plan.live() if p != you)
        return max(0, int(plan.state.players[you].resources.get(v["player_counters"], 0)))
    if "party" in v:  # -- refused modal/conditional (wave 3R1) --
        return party_size(plan, you)
    if "distinct" in v:
        return _distinct(plan, ctx, v["distinct"], v["among"])
    if "devotion" in v:
        return _devotion(plan, you, v["devotion"])
    if "sum" in v or "max" in v:
        stat = v.get("sum") or v["max"]
        found = [_stat_of(plan.ch(plan.state.cards[c]), stat)
                 for c in selectors.candidates(plan, selectors.from_key(v["of"]), you, _other_than(ctx))]
        nums = [n for n in found if n is not None]
        return max(0, sum(nums) if "sum" in v else max(nums or [0]))
    for stat in ("power", "toughness", "mana_value"):
        if stat in v:
            got = _object(plan, ctx, v[stat])
            if got is None:
                return 0
            obj, ch = got
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
    mine = plan.ch(card)
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
    if who == "each":  # -- sized amounts (wave 3D) -- "each creature you control deals damage equal to its power": the one being read
        card = plan.state.cards.get(ctx.get("each_source") or "")
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
    return None


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
