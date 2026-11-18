"""-- I have a response -- "wait, I have a response!", as said at a real table to stop things moving on.

A seated player who doesn't hold priority calls it (``set_prefs respond=True``, the dial's button or R). It is public: the log says
"<name> has a response!" and every table shows it until they get priority (``RulesState.responding``, the rules view's
``responding``). It never takes priority out of turn (117.3): it guarantees the player *receives* priority at the next moment they
legally would (before the top object resolves, before the step ends), whatever their RESPONSE setting, PASS UNTIL … or stops would
have done there (``engine.is_stop``). A pass the engine made for them in this round of passing (an automatic pass: they never chose
it) is taken back, so the object on the stack waits for them; a pass they made themselves stands. Pressing again cancels.

Heard while another action is being worked out (a long chain resolving), the hold is taken in at the chain's next priority
(``take_calls``, from the hub's pending holds: app/rules/progress.py ``calls``); what it changes is recorded in that action's steps,
so history, undo and replay never depend on timing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.game.errors import ActionError
from app.rules import progress

if TYPE_CHECKING:
    from app.game.rules_state import RulesState
    from app.rules.plan import Plan


def call(plan: Plan, player: str, on: bool) -> None:
    """The ``set_prefs respond`` toggle."""
    r = plan.rules
    if not on:
        if player in r.responding:
            r.responding.remove(player)
            plan.note(f"{plan.name(player)} withdrew their response")
        return
    if player not in plan.live():
        raise ActionError("You have left this game")
    if r.paused or r.draw_reason is not None or r.winner is not None:
        raise ActionError("Nothing is moving on: the game is paused or over")
    if r.priority == player and r.decision is None:
        return  # (they hold priority already: the call came as they got it, e.g. after a chain it stopped)
    register(plan, player)


def register(plan: Plan, player: str) -> bool:
    """Hold for ``player`` (who must be in the game): said in the log, an automatic pass of this round taken back."""
    r = plan.rules
    if player in r.responding or player not in plan.live():
        return False
    r.responding.append(player)
    if player in r.passed and player in r.auto_passed:
        r.passed.remove(player)  # (an automatic pass they never chose: the object waits for them)
        r.auto_passed.remove(player)
    plan.note(f"{plan.name(player)} has a response!")
    return True


def take_calls(plan: Plan) -> None:
    """Holds called while this action is being worked out (engine.advance, before each priority)."""
    pending = progress.calls(plan)
    if not pending:
        return
    taken: set[str] = plan.__dict__.setdefault("response_taken", set())
    for player in pending:
        if player in taken:
            continue
        taken.add(player)
        if player in plan.state.players:
            register(plan, player)


def reached(plan: Plan, player: str) -> None:
    """``player`` gets priority now (engine.advance): their hold is answered, and a PASS UNTIL … they set before it is over."""
    r = plan.rules
    if player in r.responding:
        r.responding.remove(player)
        prefs = r.prefs.get(player)
        if prefs is not None:
            prefs.pass_until, prefs.pass_mark, prefs.pass_hand, prefs.stop_after = None, "", [], None


def passed_for(r: RulesState, player: str) -> None:
    """The engine passed for ``player`` (no stop there, or the Arena-style pass after their own cast)."""
    if player not in r.auto_passed:
        r.auto_passed.append(player)


def prune(r: RulesState, live: list[str]) -> None:
    """Keep the automatic passes of this round of passing only, and holds of players still in the game."""
    if r.auto_passed:
        r.auto_passed = [p for p in r.auto_passed if p in r.passed]
    if r.responding:
        r.responding = [p for p in r.responding if p in live]
