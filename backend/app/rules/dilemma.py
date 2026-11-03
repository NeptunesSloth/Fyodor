"""-- Star Trek mechanics (wave 112T) -- facing a dilemma, from the Star Trek release notes
(https://magic.wizards.com/en/news/feature/star-trek-release-notes). The Comprehensive Rules (2026-09-25) don't define it yet.
# Star Trek release notes (2026-11): re-check against the CR when it defines face a dilemma

* "Some cards in this release have abilities that trigger whenever a player 'faces a dilemma,' which happens whenever that player chooses
  one or more modes for a spell or ability." A modal spell or ability is 700.2's ("Spells with spree or tiered are modal spells").
* "As long as you choose one or more modes for a spell or ability, you've faced a dilemma. It doesn't matter if that spell or ability goes
  on to resolve or not." / "If a player chooses more than one mode for a spell or ability, that player still faced only one dilemma." /
  "If a player chooses no modes …, the player did not face a dilemma." (the modes as the spell or ability is put on the stack: a cast
  spell, 601.2b; an activated ability, 602.2b; a triggered ability, 603.3c — one fact per object, none for zero modes)
* "If the copied spell is modal …, the copy will have the same mode or modes. … you didn't choose a mode for the copy and this doesn't count
  as facing a dilemma." (a copy, 707.10, never passes through here)
* "An ability that triggers whenever a player faces a dilemma will resolve before the spell or ability that caused it to trigger. It
  resolves even if that spell or ability is countered" (the trigger waits for the next priority, 603.3, above the object on the stack).
* The turn's log keeps one ``TurnFact`` "dilemma" per dilemma: "for each dilemma you've faced this turn" (Captain Benjamin Sisko) and "if
  you faced a dilemma this turn" (The Caretaker) count them; the event "designation"/"dilemma" fires "Whenever you face a dilemma".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rules.plan import Plan

KIND = "dilemma"


def note(plan: Plan, player: str, modes: list[int] | list[str] | None) -> None:
    """``player`` chose ``modes`` for a spell or ability being put on the stack: one dilemma if they chose any."""
    from app.game.rules_state import TurnFact, emit, turn_log_now

    if not modes:
        return
    log = turn_log_now(plan.state)
    if log is not None:
        log.facts.append(TurnFact(kind=KIND, player=player))
    emit(plan.state, "designation", counter=KIND, player=player)


def faced(plan: Plan, player: str) -> int:
    """How many dilemmas ``player`` faced this turn."""
    from app.rules import history

    log = history.log_for(plan)
    return sum(1 for f in log.facts if f.kind == KIND and f.player == player)
