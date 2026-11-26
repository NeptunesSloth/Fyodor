"""-- random choices (wave MBC-D) -- THE one way the rules engine makes a random choice, and the event it leaves.

Every random pick the engine makes while carrying out a rule or an instruction goes through a wrapper here: ``choice``, ``sample``,
``shuffle``, ``randint``, ``randrange``. Each calls the very same method, with the very same arguments, on the very same randomizer the
call site used before (``plan.rng`` or the site's own ``secrets.SystemRandom()``), so the outcomes drawn are exactly the ones drawn
before (a recorded history replays its recorded steps and never draws again; a live game draws the same way it always did). Then the
pick is recorded as one event: a ``designation`` event, counter ``random:<kind>``, ``player`` the player who made the random choice
(app/rules/designations.py: the trigger event ``random_choice``, with that kind). Coin flips and die rolls are noted the same way where the
engine flips / rolls (``noted``), beside their own events.

Kinds (``KINDS``): "discard" (701.9b, discarding cards at random — the discarding player), "target" (a target selected at random — the
controller of the spell or ability), "mode" (a mode chosen at random — its controller), "coin" (705: a coin flip — the flipper), "die"
(706: a die roll of a rules instruction — the roller), and the other random choices that no card yet asks about: "card" (a card from a
hand, library, graveyard or exile, not a discard), "object" (a permanent or other object not targeted), "player", "number", "order", "other".
Chira, All In triggers on the first five (app/rules/mbc_d.py).

Deliberately not routed here (each is not a random choice an effect makes, or is not the rules engine's):
* shuffles and "in a random order" placements (701.24; ``resolve.shuffle_data``, ``effects.bottom_at_random``, Camouflage's piles): they
  randomize an order, they don't choose; the table action records the permutation;
* the table's own dice, coins, dice cannon and draw bag (app/game/handlers/turn.py, toys.py): a player's table tool, outside any rule
  (no rules event exists for them, as for "Whenever you roll one or more dice");
* the planar die (901.9): the planechase deck's own roll, with its own events (app/rules/planar_events.py) — kept as it was, like the
  "roll" event of rules dice that has never included it;
* the random first player and the opening shuffles (103.1-103.2, app/api/games.py, app/game/factory.py): before the game begins;
* ids, salts and room codes (``secrets.token_hex`` …): no game outcome.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from app.rules.plan import Plan

T = TypeVar("T")

CHIRA_KINDS = ("discard", "target", "mode", "coin", "die")
KINDS = (*CHIRA_KINDS, "card", "object", "player", "number", "order", "other")
COUNTER = "random:"


def source(plan: Plan) -> Any:
    """The randomizer of this step: the table's (recorded through ``plan.rng``), else a fresh system one (a view never records)."""
    import secrets

    return plan.rng or secrets.SystemRandom()


def noted(plan: Plan, kind: str, player: str | None) -> None:
    """Record that ``player`` made a random choice of this kind (one event; triggers read it in the batch of the step that follows)."""
    from app.game.rules_state import emit

    assert kind in KINDS, kind
    if getattr(plan, "max_steps", 1) == 0:  # (a read-only view of the live table, ``Plan.view``: it records nothing)
        return
    if player and player in plan.state.players:
        emit(plan.state, "designation", counter=COUNTER + kind, player=player)


def choice(plan: Plan, rng: Any, seq: Any, *, kind: str, player: str | None) -> Any:
    out = rng.choice(seq)
    noted(plan, kind, player)
    return out


def sample(plan: Plan, rng: Any, population: Any, k: int, *, kind: str, player: str | None) -> list[Any]:
    out = rng.sample(population, k)
    if out:  # (nothing chosen: no choice was made — "discards a card at random" from an empty hand)
        noted(plan, kind, player)
    return out


def shuffle(plan: Plan, rng: Any, x: list[Any], *, kind: str, player: str | None) -> None:
    rng.shuffle(x)
    noted(plan, kind, player)


def randint(plan: Plan, rng: Any, a: int, b: int, *, kind: str, player: str | None) -> int:
    out = rng.randint(a, b)
    noted(plan, kind, player)
    return int(out)


def randrange(plan: Plan, rng: Any, *args: int, kind: str, player: str | None) -> int:
    out = rng.randrange(*args)
    noted(plan, kind, player)
    return int(out)


def kind_of(counter: str | None) -> str | None:
    """The kind a ``designation`` event's counter records, or None when it isn't a random choice."""
    return counter[len(COUNTER):] if counter and counter.startswith(COUNTER) else None
