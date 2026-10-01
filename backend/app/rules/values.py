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
    "flying", "first strike", "double strike", "deathtouch", "decayed", "exalted", "haste", "hexproof",
    "indestructible", "lifelink", "menace", "reach", "shadow", "trample", "vigilance",
    "shield", "finality", "rad", "hone", "lore"})  # (stun: 122.1d, wave 3F — keyword_actions.untap_stunned)

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
_HALF = re.compile(r"^half (?P<v>.+?), rounded (?P<round>up|down)$")
_PLUS = re.compile(r"^(?P<v>.+?) plus (?P<n>\d+|one|two|three|four|five)$")
_TYPE_WORDS = "|".join(selectors.CARD_TYPES)


def parse_count(phrase: str, *, it: str | None = None) -> Value | None:
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
    if what in ("cards in target player's hand", "cards in target opponent's hand"):
        return {"hand": "target"}
    if what in ("opponents you have", "opponent you have", "your opponents", "opponent", "opponents"):
        return {"opponents": 1}
    if what in ("time it was kicked", "time this spell was kicked", "time ~ was kicked"):
        return {"kicked": 1}
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
    return None


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
    if "x" in v:
        return max(0, int(ctx.get("x") or 0))
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
    if "count" in v:
        sel = selectors.from_key(v["count"])
        if sel.player is not None:
            return sum(1 for p in plan.live() if selectors.matches_player(plan, sel, p, you))
        return len(selectors.candidates(plan, sel, you, _other_than(ctx)))
    if "spells_cast" in v:  # -- sized amounts (wave 3D) -- "the number of spells you've cast this turn"
        return plan.rules.spells_this_turn(you, plan.state.turn.number)
    if "event_amount" in v:  # "that much" / "that many": the trigger event's amount (608.2k)
        from app.rules import context  # (context → triggers → … → values)

        return context.amount(ctx, context.EVENT)
    if "ref_amount" in v:  # "that much" of an earlier effect of this resolution (app/rules/context.py)
        from app.rules import context

        return context.amount(ctx, v["ref_amount"])
    if "event_count" in v:  # how many objects the "one or more" batch had
        return max(0, int((ctx.get("event") or {}).get("count") or 0))
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
        return max(0, int(plan.state.players[you].resources.get(v["player_counters"], 0)))
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
            _, ch = got
            return max(0, _stat_of(ch, stat) or 0)
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
        elif kind == "powers":  # "creatures with different powers" (conditions.py): how many distinct values
            power = _stat_of(ch, "power")
            if power is not None:
                found.add(str(power))
        else:
            from app.rules.creature_types import CREATURE_TYPES

            found |= ch.subtypes & CREATURE_TYPES
    return len(found)


def _devotion(plan: Plan, you: str, colors: list[str]) -> int:
    """700.5: the number of mana symbols of those colors among the mana costs of permanents you
    control (a hybrid symbol of two of them counts once; a Phyrexian or twobrid symbol is a symbol
    of its color, 107.4e-f)."""
    wanted = set(colors)
    total = 0
    for card in plan.state.cards.values():
        if not card.zone.endswith(":battlefield") or card.controller != you or not plan.in_game(card):
            continue
        for sym in _MANA_SYMBOL.findall(plan.ch(card).mana_cost):
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
