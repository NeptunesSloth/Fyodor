"""-- mana riders (wave 5A) -- more of the wordings of activated mana abilities, researched against CR 2026-09-25.

* 605.1a: an activated ability is a mana ability if it has no target, could add mana, isn't a loyalty ability and its
  cost and effect don't move a card to or from a library ("{T}, Mill a card: Add {C}." — Millikin — is therefore NOT
  one: it isn't read here, app/rules/oracle.py classifies it as an ordinary activated ability).
* 605.2: it stays a mana ability even when the game state lets it add no mana ("{T}: Add {G} for each Elf on the
  battlefield" with no Elves). The engine offers such an ability only while it would add mana.
* 605.3b: it resolves immediately after it is activated, so every amount ("for each …", "where X is …") and every
  set of colors ("any color among …") is read as it is activated — no one can respond in between (Priest of Titania
  ruling 2024-06-07). Other effects of the ability ("You gain 2 life.", "Each opponent gains 1 life.") happen as
  part of that same resolution, right after the mana is added (The Great Henge, Pristine Talisman, Grove of the
  Burnwillows); a life gain goes through the life-gain choke point (119.10, app/rules/replace.py).
* 105.1 / 105.2c: the colors are white, blue, black, red and green; colorless is not a color. "One mana of any color
  among legendary creatures and planeswalkers you control" (Mox Amber; ruling 2018-04-27: legendary creatures and
  legendary planeswalkers) adds one mana of a color one of them has — none when they are all colorless. "For each
  color among permanents you control, add one mana of that color" (Bloom Tender; rulings 2025-11-17) adds one mana
  of each such color, at most {W}{U}{B}{R}{G}, never {C}.

Representation (all data, nothing from a card is executed; app/rules/mana.py ``ManaAbility``):

* ``count = "value:<json>"`` — an app/rules/values.py value (a restricted set: counts of objects, this turn's
  draws, devotion, the greatest stat among objects …; never X, targets or a trigger's event), each option repeated
  that many times;
* options ``("@among", <selector key>, …)`` — one option per color among the objects the selectors name;
  ``("@each_color", <selector key>)`` — one option holding one mana of each color among them;
* riders ``("gain", n)`` — its controller gains n life; ``("opp_gain", n)`` — each opponent gains n life.

Resolved by :func:`resolve` (from app/rules/casting.py ``_resolve_options``) and :func:`after` (from
``after_mana_ability``). Unknown wordings still return None (the ability stays manual).
"""

from __future__ import annotations

import json
import re
from itertools import combinations, combinations_with_replacement
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules import mana as M
    from app.rules.characteristics import CardInfo
    from app.rules.plan import Plan

COLORS = ("W", "U", "B", "R", "G")
_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_SYMS = r"(?:\{[WUBRGC]\})+"

_FOR_EACH = re.compile(rf"^Add (?P<syms>{_SYMS}) for each (?P<what>.+)$")
_X_ONE_COLOR = re.compile(r"^Add X mana of any one color, where X is (?P<what>.+)$")
# -- activated sweep (wave 17B) -- "Add X mana in any combination of colors, where X is the number of creatures you control with
# defender." (Axebane Guardian), "… of {U} and/or {R}, where X is Vivi Ornitier's power": X as the ability is activated (605.3b), each mix
# one option (106.1)
_X_COMBO = re.compile(r"^Add X mana in any combination of (?:(?P<colors>colors)|\{(?P<a>[WUBRG])\} and/or \{(?P<b>[WUBRG])\}), "
                      r"where X is (?P<what>.+)$")
# -- X sized by a count (wave 41B) -- "{T}: Add X {G} or X {W}, where X is the number of other creatures you control." (Brigid, Clachan's Heart): one
# of the two colors, X times (106.1, 605.3b: counted as the ability resolves, at once)
_X_TWO_COLORS = re.compile(r"^Add X \{(?P<a>[WUBRG])\} or X \{(?P<b>[WUBRG])\}, where X is (?P<what>.+)$")
_AMOUNT_EQUAL = re.compile(r"^Add an amount of \{(?P<sym>[WUBRGC])\} equal to (?P<what>.+)$")
_AMONG = re.compile(r"^Add one mana of any color among (?P<what>.+)$")
# (app/rules/oracle.py classifies this line as a mana ability; :func:`normalise` gives it the "Add" form)
EACH_COLOR_LINE = re.compile(r"^(?P<cost>[^:]+): For each color among permanents you control, add one mana of that color\.$")
_EACH_COLOR = "Add one mana of each color among permanents you control"
_COMBO = re.compile(r"^Add (?P<n>two|three) mana in any combination of \{(?P<a>[WUBRG])\}, \{(?P<b>[WUBRG])\}, "
                    r"and/or \{(?P<c>[WUBRG])\}$")
_DIFFERENT = re.compile(r"^Add (?P<n>two|three) mana of different colors$")
_GAIN = re.compile(r"^You gain (?P<n>\d+|one|two|three|four|five) life$")
_RAD = re.compile(r"^You get (?P<n>one|two|three|four|five) rad counters?$")  # (wave 110D: Harold and Bob's Forest)
_OPP_GAIN = re.compile(r"^Each opponent gains (?P<n>\d+|one|two|three|four|five) life$")
# -- activated other (wave 34B) -- 605.3b: "If you control another Mutant, you gain 1 life." (Black Tom Cassidy), "If you control a Nissa planeswalker, you
# gain 2 life." (Avid Reclaimer): the condition is read as the mana is added (the ability resolves at once; 608.2c), as the activating player
_GAIN_IF = re.compile(r"^If (?P<c>you control [^,]+), you gain (?P<n>\d+|one|two|three|four|five) life$")
# "Put a nest counter on this creature." (Twitching Doll, Strixhaven Stadium, the depletion lands); "If there are no
# mining counters on this land, sacrifice it." (Gemstone Mine, Peat Bog — after the cost removed one, 602.2b / 605.3b)
_PUT_COUNTER = re.compile(r"^Put an? (?P<k>[a-z]+) counter on (?:this (?:artifact|creature|land|permanent|enchantment)|~)$")
_SAC_IF_NONE = re.compile(r"^If there are no (?P<k>[a-z]+) counters on (?:this (?:artifact|creature|land|permanent)|~), "
                          r"sacrifice it$")

# value kinds a mana ability may be sized by (read for its controller, with the source as "this"/"other")
_SAFE_KEYS = {"count", "distinct", "among", "devotion", "sum", "max", "of", "opponents", "spells_cast", "party",
              "player_counters", "shared_type", "counters_among", "counter_kinds"}  # (wave 23C: value grammar)


def _n(word: str) -> int:
    return int(word) if word.isdigit() else _NUM[word]


# -- activated sweep (wave 17B) -- "Choose a color of a permanent you control. Add one mana of that color." (Meteor Crater), "…of a card in
# your graveyard…" (Corrupted Grafstone): the color is chosen among those the objects have (105.2: never colorless), as "any color among"
_CHOOSE_AMONG = re.compile(r"^(?P<cost>[^:]+): Choose a color of (?:a permanent you control|a card in your graveyard)\. "
                           r"Add one mana of that color\.$")


def normalise(text: str) -> str:
    """Bloom Tender's "For each color among permanents you control, add one mana of that color." in the Add form."""
    from app.rules.activated_copy_effects import NEXT_X

    if NEXT_X + '.' in text:
        text = text.replace(NEXT_X + '.', NEXT_X.split('. You may')[0] + '.')
    if m := _CHOOSE_AMONG.match(text):
        what = "permanents you control" if "permanent" in text else "cards in your graveyard"
        return f"{m['cost']}: Add one mana of any color among {what}."
    m = EACH_COLOR_LINE.match(text)
    return f"{m['cost']}: {_EACH_COLOR}." if m else text


def _safe(v: Any) -> bool:
    """Is this value one a mana ability can be sized by (no X, target, trigger event or earlier instruction)?"""
    if isinstance(v, int):
        return True
    if not isinstance(v, dict):
        return False
    if "turn_history" in v:
        return v["turn_history"] in ("drew", "gained", "lost", "died",
                                     "opponents_attacked")  # -- mana amounts (wave 111D) -- 508.6: the opponents you declared attackers against this turn

    if "times" in v or "plus" in v or "minus" in v:
        return all(_safe(x) for x in (v.get("times") or v.get("plus") or v.get("minus") or []))
    if "half" in v:
        return _safe(v["half"])
    if "hand" in v:
        return v["hand"] == "you"
    if "life" in v:
        return v["life"] in ("you", "opponent_max")
    if "counters" in v:
        return v.get("on") == "self"
    if any(k in v for k in ("power", "toughness", "mana_value")):
        return all(v.get(k, "self") == "self" for k in ("power", "toughness", "mana_value"))
    if "player_counters" in v:
        return True
    return set(v) <= _SAFE_KEYS


def _value(what: str) -> str | None:
    from app.rules import values

    # -- counters (wave 41A) -- the source's own name ("{T}: Add {U} for each counter on Nardole."): a mana ability is read before its card's name is written ~
    what = re.sub(r"(\bcounters?) on (?!this |~|it\b)[A-Z][\w',-]*(?: [\w',-]+)*$", r"\1 on ~", what)
    v = values.parse_count(what, it=None)
    if v is None or not _safe(v):
        return None
    return "value:" + json.dumps(v, sort_keys=True)


def _selectors(what: str) -> list[str] | None:
    """The selectors "any color among <what>" names ("legendary creatures and planeswalkers you control": legendary
    creatures and legendary planeswalkers, Mox Amber ruling 2018-04-27)."""
    from app.rules import selectors

    m = re.fullmatch(r"(?P<adj>legendary) (?P<a>[a-z]+) and (?P<b>[a-z]+) (?P<rest>you control)", what)
    phrases = [f"{m['adj']} {m['a']} {m['rest']}", f"{m['adj']} {m['b']} {m['rest']}"] if m else [what]
    out = []
    for p in phrases:
        sel = selectors.parse(p)
        if sel is None or sel.player is not None:
            return None
        out.append(sel.key())
    return out


def first_sentence(first: str) -> tuple[str | None, tuple[tuple[str, ...], ...]] | None:
    """(count, options) of an "Add …" sentence this module reads, or None."""
    if m := _FOR_EACH.fullmatch(first):
        count = _value(m["what"])
        return (count, (tuple(re.findall(r"\{([WUBRGC])\}", m["syms"])),)) if count else None
    if m := _X_ONE_COLOR.fullmatch(first):
        count = _value(m["what"])
        return (count, tuple((c,) for c in COLORS)) if count else None
    if m := _X_TWO_COLORS.fullmatch(first):  # (wave 41B)
        count = _value(m["what"])
        return (count, ((m["a"],), (m["b"],))) if count else None
    if m := _X_COMBO.fullmatch(first):
        own = re.fullmatch(r"(?:this creature|[A-Z][^.]{0,60}?)'s (power|toughness)", m["what"])  # (the source's own: its current stat)
        count = "value:" + json.dumps({own[1]: "self"}) if own else _value(m["what"])
        colors = COLORS if m["colors"] else (m["a"], m["b"])
        return (count, (("@combo", *colors),)) if count else None
    if m := _AMOUNT_EQUAL.fullmatch(first):
        count = _value(m["what"])
        return (count, ((m["sym"],),)) if count else None
    if m := _AMONG.fullmatch(first):
        keys = _selectors(m["what"])
        return (None, (("@among", *keys),)) if keys else None
    if first == _EACH_COLOR:
        keys = _selectors("permanents you control")
        return (None, (("@each_color", *keys),)) if keys else None
    if m := _COMBO.fullmatch(first):
        return None, tuple(combinations_with_replacement((m["a"], m["b"], m["c"]), _n(m["n"])))
    if m := _DIFFERENT.fullmatch(first):
        return None, tuple(combinations(COLORS, _n(m["n"])))
    return None


def rider(sentence: str) -> tuple[str, int] | None:
    from app.rules.activated_copy_effects import NEXT_X

    if sentence == NEXT_X.split('. You may')[0]:
        return 'next_x_copy', 1
    if m := _GAIN.fullmatch(sentence):
        return "gain", _n(m["n"])
    if m := _OPP_GAIN.fullmatch(sentence):
        return "opp_gain", _n(m["n"])
    if m := _RAD.fullmatch(sentence):
        return "rad", _n(m["n"])
    if m := _GAIN_IF.fullmatch(sentence):  # (wave 34B)
        from app.rules import conditions

        cond = conditions.parse(m["c"])
        return (f"gain_if:{json.dumps(cond, sort_keys=True)}", _n(m["n"])) if cond is not None and not conditions.is_cast_condition(cond) else None
    from app.rules.values import UNMODELED_COUNTERS

    if (m := _PUT_COUNTER.fullmatch(sentence)) and m["k"] not in UNMODELED_COUNTERS:
        return f"counter:{m['k']}", 1
    if m := _SAC_IF_NONE.fullmatch(sentence):
        return f"sac_if_none:{m['k']}", 0
    # -- delayed triggers (wave 23B) -- "Draw a card at the beginning of the next turn's upkeep." (Barbed Sextant, Astrolabe): a delayed
    # triggered ability the mana ability creates as it resolves (603.7a; 605.3b: it resolves at once, so it is created then)
    if _UPKEEP_DRAW.fullmatch(sentence):
        return "upkeep_draw", 1
    # -- next untap step (wave 6A) -- "This land doesn't untap during your next untap step." (Cloudcrest Lake; 502.3,
    # app/rules/next_untap.py): weighed by the payer like a small cost
    if _STAYS_TAPPED.fullmatch(sentence):
        return "stay_tapped", 2
    return None


_UPKEEP_DRAW = re.compile(r"^Draw a card at the beginning of the next turn's upkeep\.?$")
_STAYS_TAPPED = re.compile(r"^(?:This (?:land|artifact|creature|permanent)|~) doesn't untap during your next untap step\.?$")


# -- as the ability is activated (605.3b) ------------------------------------------------------------------------
def _colors_among(plan: Plan, card: CardInstance, keys: tuple[str, ...]) -> set[str]:
    from app.rules import selectors

    out: set[str] = set()
    for key in keys:
        for cid in selectors.candidates(plan, selectors.from_key(key), card.controller, card.id):
            out |= set(plan.ch(plan.state.cards[cid]).colors) & set(COLORS)
    return out


def resolve(state: GameState, card: CardInstance, ab: M.ManaAbility, info: CardInfo) -> tuple[tuple[str, ...], ...] | None:
    """The options of an ability this module read, as it would be activated now; None for any other ability."""
    from app.rules import values
    from app.rules.plan import Plan

    marker = ab.options[0][0] if len(ab.options) == 1 and ab.options[0] else ""
    counted = bool(ab.count and ab.count.startswith("value:"))
    if not counted and marker not in ("@among", "@each_color"):
        return None
    if counted and marker == "@combo":  # (wave 17B) X mana in any mix of those colors
        assert ab.count is not None
        n = values.evaluate(Plan.view(state, card.controller, info), {"controller": card.controller, "source_card": card.id},
                            json.loads(ab.count[6:]))
        return tuple(combinations_with_replacement(ab.options[0][1:], n)) if n > 0 else ()
    plan = Plan.view(state, card.controller, info)
    if counted:
        assert ab.count is not None
        n = values.evaluate(plan, {"controller": card.controller, "source_card": card.id}, json.loads(ab.count[6:]))
        return tuple(opt * n for opt in ab.options) if n > 0 else ()
    found = _colors_among(plan, card, ab.options[0][1:])
    ordered = tuple(c for c in COLORS if c in found)
    if marker == "@among":
        return tuple((c,) for c in ordered)
    return (ordered,) if ordered else ()


def penalty(riders: tuple[tuple[str, int], ...]) -> int:
    """What the payer weighs against an option (an opponent's life gain: a small cost)."""
    return sum(n for kind, n in riders if kind in ("opp_gain", "stay_tapped"))  # (stay_tapped: wave 6A)


def after(plan: Plan, card: CardInstance, kind: str, n: int, who: str | None = None) -> None:
    """A rider of this module, right after the ability's mana was added (605.3b: the same resolution)."""
    from app.rules import replace

    who = who or card.controller  # (wave 24D: the activating player; 603.7e-style, the card may have left)
    if kind == 'next_x_copy':
        from app.rules import activated_copy_effects, delayed

        ctx: dict[str, Any] = {'kind': 'mana', 'controller': who, 'source_card': card.id,
               'source_object': plan.oid(card), 'name': plan.ch(card).name,
               'effects': activated_copy_effects.watch(x=True), 'next': 1}
        delayed.create(plan, ctx, ctx['effects'][0])
    elif kind.startswith("counter:"):  # (an effect of the ability: the counter choke point, 122.6 / 614)
        if card.zone.endswith(":battlefield"):
            replace.put_counters(plan, [(card.id, kind.split(":", 1)[1], n)], by=card.controller)
    elif kind.startswith("sac_if_none:"):  # 701.21a: its controller sacrifices it (it's still there, 400.7)
        from app.rules.effects import _sacrifice_cards

        if card.zone.endswith(":battlefield") and card.counters.get(kind.split(":", 1)[1], 0) == 0:
            _sacrifice_cards(plan, [card.id], card.controller)
    elif kind == "upkeep_draw":  # -- delayed triggers (wave 23B) --
        from app.rules import delayed

        # (review 23B: 603.7e — whoever activated it; a card sacrificed as the cost is back under its owner's control by now)
        delayed.create_plain(plan, who, card.id, plan.oid(card.id), plan.ch(card).name,
                             {"kind": "step", "step": "upkeep", "whose": "next_turn"}, [{"do": "draw", "who": "you", "n": 1}])
    elif kind == "stay_tapped":  # -- next untap step (wave 6A) --
        if card.zone.endswith(":battlefield"):
            plan.rules.stay_tapped.append({"oid": plan.oid(card.id), "player": who})
    elif kind == "gain":
        replace.gain_life(plan, [(who, n)], actor=who)
    elif kind.startswith("gain_if:"):  # (wave 34B) the condition as it is now, for the activating player; "another" is relative to this source
        from app.rules import conditions

        if conditions.holds(plan, {"controller": who, "source_card": card.id}, json.loads(kind[len("gain_if:"):])):
            replace.gain_life(plan, [(who, n)], actor=who)
    elif kind == "rad":  # 725.1: the activating player gets rad counters (through the counter choke point, 122.6)
        replace.put_counters(plan, [(who, "rad", n)], by=who)
    elif kind == "opp_gain":
        gains = [(p, n) for p in plan.live() if p != who]
        if gains:
            replace.gain_life(plan, gains, actor=who)


# -- "Exile this card from your hand: Add {R}." (Simian / Elvish Spirit Guide) ----------------------------------------------
def activate_from_hand(plan: Plan, card: CardInstance, ch: Any, ability: Any) -> None:
    """113.6m: an ability whose cost exiles the card from its owner's hand works only there. 605.3a / 605.3b: a mana
    ability, activated whenever its controller has priority or is paying, resolving at once: the cost (the card is
    exiled from the hand — a public move) and then the mana. The auto-payer never spends a card from the hand."""
    from app.game.errors import ActionError
    from app.game.rules_state import emit
    from app.rules import mana as M
    from app.rules.casting import commander_identity

    parsed = M.parse_mana_ability(ability.text, commander_identity(plan.state, plan.actor, plan.info), card_name=plan.ch(card).name)
    if parsed is None or not parsed.from_hand or card.owner != plan.actor or len(parsed.options) != 1:
        raise ActionError(f"Fyodor can't carry out “{ability.text}” from your hand yet. Use the table tools.")
    option = parsed.options[0]
    source_object = plan.oid(card)
    from dataclasses import asdict

    from app.rules.mana_requirement_rows import OutputProducer, ProducerFact
    from app.rules.mana_units import tags_of

    producer_before_cost = OutputProducer(source_object, ProducerFact(tuple(tags_of(plan.ch(card))), card.zone))
    plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "exile"}}, actor=plan.actor)
    added: dict[str, int] = {}
    for m in option:
        added[m] = added.get(m, 0) + 1
    from app.rules import mana_units

    plan.do({"type": "rules_mana", "player": plan.actor, "tap": [], "sacrifice": [],
             **mana_units.from_context(plan, {"source_card": card.id, "source_object": source_object,
                 "producer_before_cost": asdict(producer_before_cost)}, added), "life": 0,
             "label": f"exiled {ch.name or 'a card'} from their hand: added {M.symbols(added)}"}, actor=plan.actor)
    emit(plan.state, "mana_added", object_id=None, card=card.id, player=plan.actor, amount=sum(added.values()))
    # -- mana and sources (wave 111R2) -- 602.2, 605.3a: a mana ability activated from the hand is an activation like any other: "Whenever an
    # opponent … activates an ability of a source with the chosen name" (Kai Winn, 109.2c) sees it (its source: the card it was, 113.7a)
    from app.rules.triggers import activated as _activated111r2

    _activated111r2(plan, card, source_object, mana_ability=True, actor=plan.actor, cost_has_tap=False)
