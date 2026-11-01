"""-- mana and sources (wave 111R2) -- two engine capabilities the Star Trek cards Queen's Diamond and Kai Winn needed.

Researched against the Comprehensive Rules of 2026-09-25 (data/rules/comprehensive_rules/).

* "Spend this mana only to cast your commander." (Queen's Diamond, Jeweled Lotus): a spending restriction (106.6) whose spell is a commander
  (903.3d: "casting a commander" is casting a spell that is a commander). The designation is an attribute of the card, not a characteristic, and
  the card keeps it in every zone (903.3), so it is read from the card the spell is (``casting.Purpose.spell_object`` / ``card``), never from its
  characteristics. "Your" is the player whose mana it is: the one who activated the mana ability, into whose pool it went, and who now spends it
  (106.4, 605.3a) — a commander that player owns (903.3: the deck's own card; 108.3). With two commanders, either one (702.124e). The mana pays
  the spell's whole total cost (601.2f-h: commander tax, additional costs), and nothing else: not an ability of the commander, not a special
  action. ``casting.spend_allowed`` reads it as the restriction kind "commander" with the state and the payer its two state-aware callers give.

* "Whenever an opponent casts a spell with the chosen name or activates an ability of a source with the chosen name, that player loses 3 life."
  (Kai Winn): 109.2c, "source" names an object in any zone (113.7: the source of an activated ability is the object whose ability was activated
  — on the battlefield, in a hand: cycling, a Spirit Guide; in a graveyard: unearth; in the command zone); 602.1c/605.1a: "activates an ability"
  includes mana abilities (605.3a: they are activated too, they just don't use the stack). The trigger itself isn't a mana ability (605.1b: it
  could add no mana), so it waits for the next time a player would receive priority (603.3; after the spell being paid for is cast, 601.2i),
  then uses the stack like any other (605.4a is about triggered *mana* abilities only). Each half is its own event (603.2c).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.casting import Purpose
    from app.rules.selectors import Selector

COMMANDER = "commander"  # the spending restriction kind (casting.spend_allowed)
_SPEND_COMMANDER = "Spend this mana only to cast your commander"


def spend_kind(sentence: str) -> str | None:
    """106.6: "Spend this mana only to cast your commander" (no final period) as the restriction kind ``casting.spend_allowed`` reads."""
    return COMMANDER if sentence == _SPEND_COMMANDER else None


def commander_spell(state: GameState | None, payer: str | None, purpose: Purpose | None) -> bool:
    """May mana restricted to "cast your commander" pay for ``purpose``? Only a spell (903.3d) whose card is a commander (903.3) that the
    payer owns (702.124e: either of two). Without the state or the payer (a caller that can't tell): no."""
    if state is None or payer is None or purpose is None or purpose.spell is None:
        return False
    from app.game.rules_state import ObjectRef

    ref = purpose.spell_object
    card_id = ObjectRef.model_validate(ref).card if ref is not None else purpose.card
    card = state.cards.get(card_id or "")
    return card is not None and card.commander_key is not None and card.owner == payer


# 109.2c: "an ability of a source <qualifier>": the qualifiers read in every zone (a card's name is the same in each, 201.2, 709.4a: a split
# card's two names off the stack). Only qualifiers tested here.
_SOURCE = re.compile(r"an? source(?P<q> with the chosen name)")


def source_selector(phrase: str) -> Selector | None:
    """"a source with the chosen name" (the object of "activates an ability of …"): any object in any zone (109.2c) with the name its
    permanent chose as it entered (614.12a; selectors' ``chosen_name``). None: not this wording."""
    from app.rules import selectors

    m = _SOURCE.fullmatch(phrase)
    if m is None:
        return None
    base = selectors.parse("permanent" + m["q"])
    if base is None or base.extras != ("chosen_name",):
        return None
    return selectors.replace(base, zones=selectors.ZONES)


# "<player> casts a spell <q> or activates an ability of a source <q>": one player's two actions, each its own event (603.2c).
_CAST_OR_ACTIVATE = re.compile(r"(?P<p>you|an opponent|a player) (?P<a>casts? an? spell [^,]+?) or (?P<b>activates? an ability of an? source [^,]+)")


def cast_or_activate(c: str, parse: Any) -> dict[str, Any] | None:
    """The either condition of "an opponent casts a spell with the chosen name or activates an ability of a source with the chosen name"
    (each half read by the ordinary grammar, ``parse``); the activation half includes mana abilities (605.1a: no "that isn't a mana ability")."""
    m = _CAST_OR_ACTIVATE.fullmatch(c)
    if m is None:
        return None
    cast, act = parse(f"{m['p']} {m['a']}"), parse(f"{m['p']} {m['b']}")
    if cast is None or act is None or cast.get("event") != "cast" or act.get("event") != "activate" or cast.get("aggregate") \
            or cast.get("subject") != "player" or act.get("subject") != "player" or cast.get("player") != act.get("player") \
            or act.get("nonmana") or act.get("loyalty"):
        return None
    return {"event": "either", "subject": "player", "player": cast["player"], "conds": [cast, act]}
