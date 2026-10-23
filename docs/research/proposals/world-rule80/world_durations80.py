"""Staged CR 704.5k interval receipts; not installed or admitted."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from typing import TYPE_CHECKING, Concatenate, ParamSpec, TypeVar

from app.game.errors import ActionError
from app.game.rules_state import WorldInterval80

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

P = ParamSpec('P')
T = TypeVar('T')


def profile(plan: Plan) -> dict[str, str]:
    """Read effective supertype, including phased history, without applying SBAs."""
    from app.rules import layers

    # Cache only the potential carriers, never derived World membership. Every
    # actual member is still derived after each mutation. Native static grants
    # currently add Basic/Legendary/Snow; a resolved World grant takes the full
    # candidate set regardless of its selector or current conditions.
    cards = [c for c in plan.state.cards.values() if c.zone.endswith((':battlefield', ':phased')) and plan.in_game(c)]
    added = any('World' in e.add_supertypes for e in plan.rules.effects)
    signature = (
        tuple((plan.oid(c), c.card_id, c.face, c.face_down, c.flipped,
               c.token.model_dump_json() if c.token is not None else None,
               c.copy_of.model_dump_json() if c.copy_of is not None else None,
               tuple(p.model_dump_json() for p in c.merged), str(c.melded)) for c in cards),
        tuple((e.id, e.timestamp, tuple(e.affected), e.copy_recipe.model_dump_json())
              for e in plan.rules.effects if e.layer == '1' and e.copy_recipe is not None), added)
    cached = plan.world_candidates80
    if cached is None or cached[0] != signature:
        candidates = tuple(c.id for c in cards if added or 'World' in layers.copiable(plan.state, c, plan.info).supertypes)
        plan.world_candidates80 = signature, candidates
    else:
        candidates = cached[1]
    return {plan.oid(c): c.id for cid in candidates if (c := plan.state.cards.get(cid)) is not None
            and 'World' in plan.ch(c).supertypes}



def observe(plan: Plan, current: dict[str, str]) -> None:
    """Unknown existing history stays unknown, with an honest relative-age bound."""
    r = plan.rules
    r.world_intervals80 = {oid: v for oid, v in r.world_intervals80.items()
                           if oid in current and v.card == current[oid]}
    for oid, card in current.items():
        if oid not in r.world_intervals80:
            r.world_intervals80[oid] = WorldInterval80(card=card, observed_before=r.world_epoch80)


def before(plan: Plan) -> dict[str, str] | None:
    if plan.world_depth80:
        return None
    current = profile(plan)
    observe(plan, current)
    return current


def after(plan: Plan, prior: dict[str, str]) -> None:
    current = profile(plan)
    gained = {oid: card for oid, card in current.items() if oid not in prior}
    r = plan.rules
    # Finish losses before issuing the shared interval start. Ordinary APNAP
    # timestamps and object-ID ordering never decide a World comparison.
    observe(plan, current)
    if gained:
        r.world_epoch80 += 1
        for oid, card in gained.items():
            r.world_intervals80[oid] = WorldInterval80(card=card, since=r.world_epoch80,
                observed_before=r.world_epoch80, event_batch=r.batch)


@contextmanager
def atomic(plan: Plan) -> Iterator[None]:
    prior = before(plan)
    plan.world_depth80 += 1
    try:
        yield
    finally:
        plan.world_depth80 -= 1
    if prior is not None:
        after(plan, prior)


def native(fn: Callable[Concatenate[Plan, P], T]) -> Callable[Concatenate[Plan, P], T]:
    @wraps(fn)
    def wrapped(plan: Plan, *args: P.args, **kwargs: P.kwargs) -> T:
        with atomic(plan):
            return fn(plan, *args, **kwargs)
    return wrapped


def dying(plan: Plan) -> list[CardInstance]:
    current = profile(plan)
    observe(plan, current)
    worlds = [plan.state.cards[cid] for cid in current.values()
              if plan.state.cards[cid].zone.endswith(':battlefield')]
    if len(worlds) < 2:
        return []
    entries = [(c, plan.rules.world_intervals80[plan.oid(c)]) for c in worlds]
    known = [v.since for _, v in entries if v.since is not None]
    latest = max(known, default=0)
    if any(v.since is None and v.observed_before >= latest for _, v in entries):
        raise ActionError('The World rule needs historical World durations that this save does not record. '
                          'Resolve the World rule with the table tools before continuing; no survivor was guessed.')
    winners = [c for c, v in entries if v.since == latest]
    return worlds if len(winners) != 1 else [c for c in worlds if c.id != winners[0].id]
