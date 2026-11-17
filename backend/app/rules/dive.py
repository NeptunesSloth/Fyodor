"""-- dive (wave DV) -- the keyword action dive: "it dives. (It can't be blocked until it deals combat damage while attacking.)"

A creature that dives can't be blocked until it deals combat damage while it's an attacking creature (the reminder text of the first
card printed with it: "Devour 3 / When this creature enters, if it devoured a creature, it dives."). Three pieces, each a rewrite into
wording the engine already reads, so nothing about blocks or durations is modelled twice:

* **The duration** "until it deals combat damage while attacking" (``delayed.DURATIONS``: ``until_combat_damage_attacking``; and "until it
  deals combat damage": ``until_combat_damage``): a continuous effect with it lasts past the turn (611.2a) and ends the moment the object it
  affects deals combat damage as an attacking creature (510.2; the first-strike and the regular combat damage steps alike). Prevented damage
  isn't dealt (120.1); damage dealt while blocking doesn't end the "while attacking" form. ``combat_damage_dealt`` is called from
  ``combat.after_damage`` (also on the resumed path after a replacement choice). The effect names its object (611.2c): a creature that
  leaves and returns is a new object the effect never applied to (400.7; ``departed``, from ``delayed.expire``, ends the effect as it
  leaves), so a diving creature that is bounced no longer dives.
* **The keyword action** "X dives": "X can't be blocked until it deals combat damage while attacking" — the text is rewritten
  (``scripts.self_text``) and read by the ordinary grammar, so "it", "~", "that creature", "target creature" and "target creature you
  control" come out as that grammar reads them. "Each creature you control dives" is left alone: a group restriction can't end for one
  creature at a time, so that line stays manual.
* **The condition** "if it devoured a creature" / "if it devoured two or more creatures" (an intervening if on the devourer's own enters
  trigger, 603.4; 702.82b: what it sacrificed to its own devour, ``RulesState.devoured`` — a new object devoured nothing).

Tests: tests/test_rules_dive.py. Teach Fyodor (docs/TEACH_FYODOR.md) offers the duration and the condition as pieces, and "an action"
as a thing to teach, with this card as its worked example.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

ACTION = "dive"
MEANING = "can't be blocked until it deals combat damage while attacking"
ATTACKING = "until_combat_damage_attacking"
ANY = "until_combat_damage"

_DIVES = re.compile(r"(?<![A-Za-z])(?P<who>~|[Ii]t|[Tt]hat creature|[Tt]arget creature(?: you control)?) dives\b")
_DEVOURED = re.compile(r"^(?:it|this creature|this permanent|~) devoured (?:an? creature|(?P<n>\w+) or more creatures)$")
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def rewrite(text: str) -> str:
    """"It dives." / "Target creature dives." → "… can't be blocked until it deals combat damage while attacking" (``scripts.self_text``: the
    text the grammar reads, the card's own name already "~"; a reminder text was stripped before)."""
    if "dives" not in text:
        return text
    return _DIVES.sub(lambda m: f"{m['who']} {MEANING}", text)


def devoured_condition(t: str) -> dict[str, Any] | None:
    """"it devoured a creature" → the number of permanents the source devoured as it entered (values: ``devoured``, 702.82b) is 1 or more."""
    m = _DEVOURED.fullmatch(t.strip().lower())
    if m is None:
        return None
    n = 1 if m["n"] is None else (_WORDS.get(m["n"]) if not m["n"].isdigit() else int(m["n"]))
    if n is None:
        return None
    return {"value": {"devoured": 1}, "op": ">=", "n": n}


def departed(plan: Plan) -> None:
    """After a table change (``delayed.expire``): a "until it deals combat damage [while attacking]" effect whose object left the battlefield
    ends with it (400.7: the card that comes back is a new object; 611.2c: the effect was about the one that left)."""
    r = plan.rules
    if r is None or not r.effects:
        return
    live = {plan.oid(c) for c in plan.state.cards.values() if c.zone.endswith(":battlefield")}
    ended = []
    for e in list(r.effects):
        if e.duration not in (ATTACKING, ANY) or e.who:  # (a group effect names no object of its own)
            continue
        kept = [oid for oid in e.affected if oid in live]
        if not kept:
            ended.append(e)
        elif len(kept) < len(e.affected):
            from app.rules import delayed

            delayed._drop(plan, e, kept)
    if ended:
        from app.rules import delayed

        delayed._end(plan, ended)


def combat_damage_dealt(plan: Plan, dealt: list[tuple[str, str, int]]) -> None:
    """Combat damage was just dealt (510.2): the "until it deals combat damage [while attacking]" effects on a source that dealt some end —
    for that object only (an effect over several objects keeps the others, 611.2c)."""
    r = plan.rules
    if r is None or not r.effects:
        return
    attacking: set[str] = set()
    any_role: set[str] = set()
    for src, _tgt, n in dealt:
        card = plan.state.cards.get(src)
        if card is None or n <= 0 or not card.zone.endswith(":battlefield"):
            continue
        oid = plan.oid(card)
        any_role.add(oid)
        if card.is_attacking:
            attacking.add(oid)
    if not any_role:
        return
    from app.rules import delayed

    ended = []
    for e in list(r.effects):
        hit = attacking if e.duration == ATTACKING else any_role if e.duration == ANY else None
        if not hit or not (set(e.affected) & hit):
            continue
        kept = [oid for oid in e.affected if oid not in hit]
        if kept:
            delayed._drop(plan, e, kept)
        else:
            ended.append(e)
    if ended:
        delayed._end(plan, ended)
        for e in ended:
            for card in plan.state.cards.values():
                if plan.oid(card) in e.affected:
                    plan.note(f"{card.name} has dealt combat damage: it can be blocked again", [card.id])
