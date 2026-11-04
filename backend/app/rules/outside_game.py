"""Ordinary outside-game permissions in Commander (CR 2026-09-25, 903.11).

These permissions cannot bring traditional cards into Commander. This is a format rule,
not an assertion that a player's collection is empty. Explicit exceptions such as companion
use their own rules. (Every table plays Commander decks, a Sandbox table included, so every table follows this rule.)
"""
from __future__ import annotations

import re
from typing import Any

from app.rules import selectors
from app.rules.plan import Plan

_HAND = re.compile(r"^(?:you may )?reveal an? (?P<what>.+?) you own from outside the game and put it into your hand$")
_PUT = re.compile(r"^(?:you may )?put a card you own from outside the game into your hand$")
_TOP = re.compile(r"^(?:you may )?put a card you own from outside the game on top of your library$")  # (wave 110B, The Raven's Warning)
_NAMED = re.compile(r"^(?:you may )?reveal a card you own named (?:~|[A-Z][^,.]+) from outside the game and put it into your hand$")
_PLAY = re.compile(r"^(?:you may )?play a card you own from outside the game this turn$")
_CAST = re.compile(r"^cast any number of (?P<type>[A-Z][A-Za-z'-]*) spells from among cards you own outside the game without paying their mana costs$")
_EXILE_OR_OUTSIDE = re.compile(
    r"^You may reveal an? (?P<what>artifact|Eldrazi) card you own from outside the game or choose a face-up (?P=what) card you own in exile\. Put that card into your hand\.$")


_EXTRAPOLATE = ("You may reveal exactly two cards you own with different names from outside the game. An opponent chooses one of them. "
                "You put that card into your hand.")


def combined(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    """Karn's alternatives: CR 903.11 leaves its ordinary exile choice available."""
    if body.strip() == _EXTRAPOLATE:  # -- wave 110F -- 903.11: no card can be revealed from outside the game, so there is nothing for the opponent to choose or for you to put into your hand
        return [{'do': 'outside_permission'}], None, False
    m = _EXILE_OR_OUTSIDE.fullmatch(body.strip())
    if m is None:
        return None
    sel = selectors.parse(f"face-up {m['what']} card you own in exile")
    assert sel is not None
    return ([{'do': 'outside_permission', 'exile_choice': sel.key(),
              'exile_label': f"a face-up {m['what']} card you own in exile"}], None, False)


def _permission(m: re.Match[str]) -> tuple[list[dict[str, Any]], None]:
    from app.rules import scripts
    from app.rules.creature_types import CREATURE_TYPES

    if m.re is _HAND:
        sel = selectors.parse(m['what'])
        if sel is None or not sel.card or sel.player is not None:
            raise scripts._NoMatch
    if m.re is _CAST and m['type'] not in CREATURE_TYPES:
        raise scripts._NoMatch
    return [{'do':'outside_permission'}], None


TEMPLATES = [(pattern, _permission) for pattern in (_HAND, _PUT, _TOP, _NAMED, _PLAY, _CAST)]


def plain(body: str) -> str:
    """903.11, 608.2d: do not offer an impossible optional import as a yes/no choice."""
    parts = body.split(". ")
    for i, part in enumerate(parts):
        part = part.strip()
        clause = part.removesuffix(".")
        clause = clause[:1].lower() + clause[1:]
        if clause.startswith("you may ") and any(p.fullmatch(clause) for p in (_HAND, _NAMED, _PLAY, _PUT, _TOP)):
            parts[i] = part[len("you may "):]
    return ". ".join(parts)


def permission(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    if e.get('exile_choice'):
        from app.rules import effects

        return effects.return_choice(plan, ctx, {
            'do': 'return_choice', 'sel': e['exile_choice'], 'to': 'hand',
            'under': 'owner', 'n': 1, 'upto': True, 'random': False,
            'label': e.get('exile_label', 'a face-up artifact card you own in exile')})
    # 903.11: an ordinary Wish, play permission, or cast permission supplies no Commander exception.
    return True
