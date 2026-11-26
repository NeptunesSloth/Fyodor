"""-- planechase more 4 (wave G2) -- two Secret Lair planes, each line read in its exact Oracle wording (the playbook's cheapest hook) and, where
no native rule exists, a small dedicated one. Every face-up plane is an object (901.11c: several can be face up, Spatial Merging; the readers
below go over all of them, ``planar_more._face_defs``). "You" is the planar controller (311.5, 901.6). Scryfall lists no rulings for either.

* Deceptive Divination: 'Change the text of each sorcery spell and sorcery card not on the stack by replacing "sorcery" with "instant."' — a
  text-changing effect (612.1; layer 3, 613.1c) on every sorcery card in every zone and every sorcery spell: the card-type word in its type line
  (612.1: "the text that appears in its type line") and the word used as a card type in its rules text (612.2; a card name is never changed,
  ``text_word_changes71.protected_spans``) become "instant", so the object is an instant card / spell (what can be cast when: 307.1 / 304.5,
  what "instant" selectors see). It is a static of the face-up plane (``DIVINATION``), applied where characteristics are derived
  (``layers._derive``: every zone) and where a spell's prospective characteristics are read as it is cast (601.3: ``prospective``). It is
  derived server-side only: nothing is logged or shown, and a hidden card's view never carries characteristics (views.card_view).
  Its chaos ability is Scheming Symmetry's sentence (multi_target_search: each of the two target players searches privately, 701.23).
* Happy Yargle Day!: the end-step trigger is the native "At the beginning of each player's end step, if that player controls no creatures
  named …" (603.4: checked as it triggers and resolves) with "that player puts a bargle counter on a creature they control" (their choice,
  any counter kind is a counter, 122.1) and "It becomes a copy of Yargle, Glutton of Urborg, except it isn't legendary": a layer-1 copy effect
  (707.2, 613.2a) with no duration (611.2a: it lasts after the plane leaves) whose copiable values are the printed values of a card outside the
  game (707.2; the card database's printing, as Garth One-Eye's copies), with the exception "it isn't legendary" (707.9b).
  The chaos ability picks one of the five named cards at random with the table's entropy source (plan.rng, as dice; random_choice's
  rule: nobody chooses, recorded — the ``copy_card`` action carries the printing and name, so a replay or a load never draws again), copies
  that card from outside the game into exile (707.12, Garth One-Eye's ``copy_card``) and offers its free cast (card_copy_sources.copy_cast,
  118.9: optional; a copy not cast ceases to exist, 704.5e).
"""

from __future__ import annotations

import copy
import re
import secrets
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

Def = dict[str, Any]

DIVINATION = "divination_g2"
STATIC_KINDS = frozenset({DIVINATION})

DIVINATION_TEXT = 'Change the text of each sorcery spell and sorcery card not on the stack by replacing "sorcery" with "instant."'
DIVINATION_CHAOS = ("Whenever chaos ensues, choose two target players. Each of them searches their library for a card, then shuffles and puts that "
                    "card on top.")
YARGLE = "Yargle, Glutton of Urborg"
YARGLE_END = ("At the beginning of each player's end step, if that player doesn't control a creature named Yargle, Glutton of Urborg, that player puts "
              "a bargle counter on a creature they control. It becomes a copy of Yargle, Glutton of Urborg, except it isn't legendary.")
YARGLE_CHAOS = ("Whenever chaos ensues, choose Swords to Plowshares, Opt, Fatal Push, Anger of the Gods, or Explore at random. Copy the chosen card. "
                "You may cast the copy without paying its mana cost.")
YARGLE_PICKS = ("Swords to Plowshares", "Opt", "Fatal Push", "Anger of the Gods", "Explore")


def _planar(ch: Characteristics) -> bool:
    from app.rules import planar

    return planar.planar(ch)


def _native(ability: AbilityText, ch: Characteristics, text: str) -> Def | None:
    from app.rules import scripts

    d = scripts.define(replace(ability, text=text), ch)
    return copy.deepcopy(d) if d is not None else None


def _planar_native(ability: AbilityText, ch: Characteristics, text: str) -> Def | None:
    from app.rules import planar

    d = planar.definition(replace(ability, text=text), ch)
    return copy.deepcopy(d) if d is not None else None


def definition(ability: AbilityText, ch: Characteristics) -> Def | None:
    """A plane's line in one of the wordings of the module docstring; else None."""
    if not _planar(ch):
        return None
    text = ability.text.strip()
    if ability.kind == "static":
        return {"kind": "static", "static": DIVINATION, "effects": []} if text == DIVINATION_TEXT else None
    if ability.kind != "triggered":
        return None
    if text == DIVINATION_CHAOS:  # (the sentence capitalized as multi_target_search reads it: Scheming Symmetry's)
        d = _planar_native(ability, ch, DIVINATION_CHAOS.replace("ensues, choose", "ensues, Choose", 1))
        if d is None or d.get("trigger") != "planar_chaos" or [e.get("do") for e in d["effects"]] != ["choose_targets", "search"] \
                or not d["effects"][1].get("each_target") or [(g.get("min"), g.get("max")) for g in d.get("targets") or []] != [(2, 2)]:
            return None
        return d
    if text == YARGLE_END:  # (a stand-in name parsed natively, then Yargle's own: its comma is not read by the name grammar)
        d = _native(ability, ch, "At the beginning of each player's end step, if that player controls no creatures named Shivan Dragon, that player "
                                 "puts a +1/+1 counter on a creature they control.")
        if d is None or d.get("trigger") != "step:end:each" or [e.get("do") for e in d["effects"]] != ["only_if", "player_chooses", "add_counters"]:
            return None
        gate, chooses, counter = d["effects"]
        if chooses.get("who") != "event_player" or chooses.get("any") or counter.get("who") != f"ref:{chooses.get('as')}":
            return None
        named = d["if"]["cond"]["value"]["count"]
        if "name:Shivan Dragon" not in named:
            return None
        yargle = named.replace("name:Shivan Dragon", f"name:{YARGLE}")
        cond = {**d["if"], "cond": {**d["if"]["cond"], "value": {"count": yargle}}}
        return {**d, "if": cond, "effects": [{**gate, "cond": cond, "skip": 3}, chooses, {**counter, "kind": "bargle"},
                                             {"do": "yargle_copy_g2", "who": counter["who"]}]}
    if text == YARGLE_CHAOS:
        from app.rules import card_copy_sources

        d = _planar_native(ability, ch, "Whenever chaos ensues, you gain 1 life.")
        if d is None or d.get("trigger") != "planar_chaos":
            return None
        return {**d, "effects": [{"do": "yargle_pick_g2"}, card_copy_sources.copy_cast()[1]]}
    return None


# -- Deceptive Divination: "sorcery" → "instant" (612.1-2, 613.1c) -------------------------------------------------------------------------
_WORDS = re.compile(r"(?<![A-Za-z])(?:(?P<a>an? )?(?P<w>nonsorcery|sorceries|sorcery))(?![A-Za-z])", re.IGNORECASE)
_NEW = {"sorcery": "instant", "sorceries": "instants", "nonsorcery": "noninstant"}


def _swap_word(m: re.Match[str]) -> str:
    word = m["w"]
    new = _NEW[word.lower()]
    new = new.upper() if word.isupper() else new[0].upper() + new[1:] if word[0].isupper() else new
    article = m["a"]
    if article is not None:  # ("a sorcery" → "an instant")
        article = ("An " if article[0] == "A" else "an ") if new[0].lower() in "aeiou" else article
    return f"{article or ''}{new}"


def retext(text: str, names: tuple[str, ...], name_at: Callable[[str, int], str | None] | None = None) -> str:
    """The text with each "sorcery" used as the card-type word replaced (612.2: never inside a card name — its own, or one it names)."""
    if "orcer" not in text.lower():
        return text
    from app.rules import text_word_changes71

    spans = text_word_changes71.protected_spans(text, names, (), name_at)

    def changed(m: re.Match[str]) -> str:
        if any(a < m.end() and m.start() < b for a, b in spans):
            return m.group()
        return _swap_word(m)

    return _WORDS.sub(changed, text)


def changed(ch: Characteristics, name_at: Callable[[str, int], str | None] | None = None) -> Characteristics:
    """A sorcery object's characteristics under the text change: an instant (its type line) with its rules text changed (abilities re-read,
    as text_word_changes71.ability_text: same slots, the new words)."""
    from app.rules.oracle import parse_abilities

    names = tuple(n for n in ch.name.split(" // ") if n)
    abilities = []
    for ab in ch.abilities:
        text = retext(ab.text, names, name_at)
        if text == ab.text or ab.intrinsic:
            abilities.append(ab)
            continue
        parsed = next((a for a in parse_abilities(text, spell=True) if a.kind == ab.kind), None)
        abilities.append(replace(ab, text=text, cost=retext(ab.cost, names, name_at) if ab.cost else ab.cost,
                                 keywords=parsed.keywords if parsed is not None else ab.keywords))
    return replace(ch, types=(ch.types - {"Sorcery"}) | {"Instant"}, oracle_text=retext(ch.oracle_text, names, name_at), abilities=tuple(abilities))


def _divination_up(state: GameState, info: CardInfo | None) -> bool:
    from app.rules import planar_more

    return bool(planar_more._face_defs(state, info, DIVINATION))


def divination(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> Characteristics:
    """Layer 3 (613.1c) for any object in any zone: a sorcery while a face-up Deceptive Divination's statics work is an instant."""
    if "Sorcery" not in ch.types or state.planechase is None or not _divination_up(state, info):
        return ch
    return changed(ch, getattr(info, "name_at", None))


def prospective(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> Characteristics:
    """601.3: the spell a card would become as it is cast (the half or face being cast: chars.as_cast) is a sorcery spell, so it is changed."""
    return divination(state, card, ch, info)


# -- Happy Yargle Day! -------------------------------------------------------------------------------------------------------------------------
def yargle_copy(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"It becomes a copy of Yargle, Glutton of Urborg, except it isn't legendary." — a layer-1 copy effect with no duration (611.2a) from the
    printed values of the card (707.2: a card from outside the game, read from the card database) with its exception (707.9b)."""
    from app.game.rules_state import CopyExcept, CopyRecipe
    from app.rules import copying, effects

    who = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    if not who:
        return True
    found = getattr(plan.info, "resolve", lambda n: None)(YARGLE)
    if found is None:
        plan.note(f"{YARGLE} isn't in the card database: make the copy by hand", who)
        return True
    recipe = CopyRecipe(printing=found["id"], source=YARGLE, excepts=[CopyExcept(remove_supertypes=["Legendary"])])
    copying.add_copy_effect(plan, [plan.oid(c) for c in who], recipe, ctx["controller"], duration="permanent")
    plan.note(f"{', '.join(plan.state.cards[c].name or 'It' for c in who)} becomes a copy of {YARGLE}, except it isn't legendary", who,
              actor=ctx["controller"])
    return True


def yargle_pick(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"choose … at random. Copy the chosen card." — the table's entropy source picks one of the five names (each equally likely); the copy of
    that card is made in exile (707.12) and bound for the free cast that follows (``card_copy_sources.COPIES``)."""
    from app.rules import card_copy_sources, effects

    rng = plan.rng or secrets.SystemRandom()
    from app.rules import randomness  # -- random choices (wave MBC-D) --
    name = YARGLE_PICKS[randomness.randint(plan, rng, 0, len(YARGLE_PICKS) - 1, kind='other', player=ctx['controller'])]
    plan.note(f"{ctx.get('name') or 'Happy Yargle Day!'}: {name} is chosen at random", actor=ctx["controller"])
    found = getattr(plan.info, "resolve", lambda n: None)(name)
    source = plan.state.cards.get(ctx.get("source_card") or "")
    made: list[str] = []
    if found is not None and source is not None:
        created = plan.do({"type": "copy_card", "card_id": source.id, "player": ctx["controller"], "count": 1, "zone": "exile",
                           "printing": found["id"], "name": name}, actor=ctx["controller"])
        made = list(getattr(getattr(created, "r", None), "ids", []))
    if not made:
        ctx["effects"][ctx["next"]:] = [x for x in ctx["effects"][ctx["next"]:] if x.get("do") != "free_cast"]
        plan.note(f"{name} isn't in the card database: make the copy by hand")
        return True
    effects._remember(plan, ctx, {"as": card_copy_sources.COPIES}, made)
    return True


PRIMITIVES: dict[str, Any] = {"yargle_copy_g2": yargle_copy, "yargle_pick_g2": yargle_pick}
