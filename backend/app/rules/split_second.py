"""-- split second (wave 8A) -- Krosan Grip, Sudden Shock, Siege Smash, Sudden Death, Wipe Away … Researched against the
Comprehensive Rules of 2026-09-25.

* 702.61a: split second is a static ability that works only while the spell is on the stack: "As long as this spell is on
  the stack, players can't cast other spells or activate abilities that aren't mana abilities." It is a prohibition like
  any other (601.3, 602.5: app/rules/cast_limits.py asks here on every path that casts or activates, including a cast
  made as something resolves, 608.2g, and the hints that offer a spell or ability).
* 702.61b: mana abilities and special actions (116.2: playing a land, turning a face-down creature up, suspending)
  stay possible, and triggered abilities trigger and are put on the stack as normal - none of them is stopped here.
* 702.61c: several instances are redundant. A copy of the spell has the ability too (707.10), so it counts the same.
* -- spell grants (wave 28C) -- A static that gives split second to other spells ("Instant and sorcery spells you control have split second",
  Samut, Tyrant of Naktamun) is read too (app/rules/spell_grants.py): the spell has the granted ability for as long as it is on the stack
  and the static applies (702.61a is itself a static ability that functions only on the stack, 113.6), so the spell's characteristics
  are read with the grants (a copy of the spell on the stack has it as well). An effect that gives it only on a condition of how the
  spell was paid (Shadow the Hedgehog: "if mana from an artifact was spent to cast it") isn't read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.game.state import STACK

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import CardInfo


def on_stack(state: GameState, info: CardInfo | None, other_than: str | None = None) -> str | None:
    """The name of a spell with split second that is on the stack (not ``other_than``: "other spells"), or None."""
    if info is None or not state.zones.get(STACK):
        return None
    from app.rules import characteristics as chars
    from app.rules.layers import derive

    for cid in state.zones[STACK]:
        card = state.cards.get(cid)
        if card is None or card.ability is not None or cid == other_than:
            continue  # (an ability on the stack is no spell)
        ch = derive(state, card, chars.of(card, info), info)  # (wave 28C: with the split second a static gives it, spell_grants.py)
        if any(ab.kind == "keywords" and "split second" in ab.keywords for ab in ch.abilities):
            return ch.name or card.name or "A spell"
    return None


def problem(state: GameState, info: CardInfo | None, what: str, other_than: str | None = None) -> str | None:
    found = on_stack(state, info, other_than)
    return None if found is None else f"{found} has split second: players can't {what} while it is on the stack (702.61a)"
