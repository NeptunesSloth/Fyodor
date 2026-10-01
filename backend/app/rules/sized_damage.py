"""-- damage sized by a count (wave 4E) -- damage whose amount is read per recipient, and damage a
creature deals to itself. Researched against CR 2026-09-25.

* **Per-player amounts.** "Price of Progress deals damage to each player equal to twice the number of
  nonbasic lands that player controls", "… to each opponent equal to the number of cards in that
  player's hand", "Heartless Hidetsugu deals damage to each player equal to half that player's life
  total, rounded down": the amount is a different number for each player dealt damage. The value is
  ``{"per_player": v}``: ``v`` is read with the recipient in the place of "you" (``recipient`` in the
  context: app/rules/effects._damage_hits sets it). Every amount is determined once, as the effect is
  applied (608.2h), and all the damage is dealt at once (one damage event: 120.3, 608.2). Only players
  are recipients of such a sentence; a permanent recipient leaves the line manual.
* **Damage to itself.** "Target creature deals damage to itself equal to its power" (Justice Strike),
  "Each creature deals damage to itself equal to its power" (Wave of Reckoning): the creature is the
  source (120.3: its deathtouch, lifelink, infect and wither count), its power read as it is or as it
  last existed (608.2h, 113.7a); every creature's damage at once.
* **Pieces of the shared grammar** (app/rules/language.py, blocks marked wave 4E): "counters on it" in
  an amount for the sentence's own subject; "he/she deals …" (a named character's pronoun: the card
  itself); "and each opponent" after a bite; "each creature that player controls" (the trigger
  event's player); "X damage to … and X damage to you, where X is …"; "each other creature" for a
  named source (other than the source dealing the damage, not the spell).

Nothing here executes card text: the phrases are matched and turned into data.
"""

from __future__ import annotations

import re
from typing import Any

from app.rules import values

PER_PLAYER = "per_player"

# What the recipient's own possessions are called in the phrase ("that player controls", "they control",
# "their hand", "that player's life total") → the words the value grammar reads for "you".
_RELATIVE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:that player|they) controls?\b"), "you control"),
    (re.compile(r"\b(?:that player's|their) hand\b"), "your hand"),
    (re.compile(r"\b(?:that player's|their) life total\b"), "your life total"),
    (re.compile(r"\b(?:that player's|their) graveyard\b"), "your graveyard"),
)


def per_player(phrase: str) -> values.Value | None:
    """A quantity read for each recipient player ("the number of nonbasic lands that player controls",
    "twice the number of creatures that player controls with flying", "half that player's life total,
    rounded down") → ``{"per_player": v}``; None when the phrase says nothing about the recipient or
    the value grammar doesn't read the rest."""
    p = phrase.strip()
    out = p
    for rx, words in _RELATIVE:
        out = rx.sub(words, out)
    if out == p:
        return None
    if re.search(r"\b(?:that player|they|their|them)\b", out):
        return None  # (another mention of the player the grammar didn't rewrite: never guessed)
    v = values.parse_count(out)
    return {PER_PLAYER: v} if v is not None else None


def has_per_player(v: Any) -> bool:
    if isinstance(v, list):
        return any(has_per_player(x) for x in v)
    return isinstance(v, dict) and (PER_PLAYER in v or any(has_per_player(x) for x in v.values()))


def evaluate(plan: Any, ctx: dict[str, Any], v: dict[str, Any]) -> int:
    """The per-player value for the recipient in ``ctx`` (0 without one: nothing to read it for)."""
    who = ctx.get("recipient")
    if who is None:
        return 0
    return values.evaluate(plan, {**ctx, "controller": who}, v[PER_PLAYER])


# "Target creature deals damage to itself equal to its power." / "… deals damage equal to its power to itself."
SELF_DAMAGE = re.compile(r"(?P<s>.+?) deals damage (?:to itself equal to (?P<a>its power|its toughness)|"
                         r"equal to (?P<b>its power|its toughness) to itself)")
