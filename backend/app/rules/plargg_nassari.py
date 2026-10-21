"""Each library exiles to a nonland; an opponent excludes one, then cast up to two others."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import Decision, DecisionOption, ObjectRef
from app.rules import context

if TYPE_CHECKING:
    from app.rules.plan import Plan

_TEXT = ('Each player exiles cards from the top of their library until they exile a nonland card. '
         'An opponent chooses a nonland card exiled this way. You may cast up to two spells from among the other '
         'cards exiled this way without paying their mana costs.')
_EXILED = 'plargg_exiled'
_AVAILABLE = 'plargg_available'
_PICK = 'plargg_opponent'
_CARD = 'plargg_exclude'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip().casefold() != _TEXT.casefold():
        return None
    return [{'do': 'plargg_exile'}, {'do': _PICK},
            {'do': 'free_cast', 'zone': 'that', 'who': 'ref:' + _AVAILABLE,
             'n': 2, 'exact_refs': True}], None, False


def exile(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    original: list[dict[str, Any]] = []
    for pid in plan.apnap():
        while (library := plan.state.zones.get(f'{pid}:library', [])):
            before = context.ref_of(plan, library[0])
            effects.exile_top(plan, ctx, {'do': 'exile_top', 'player': 'player:' + pid, 'n': 1, 'as': 'plargg_one'})
            moved = (context.refs(ctx).get('plargg_one') or {}).get('objects', [])
            actual = [raw for raw in moved if (card := context._same(plan, ObjectRef.model_validate(raw))) is not None
                      and card.zone.endswith(':exile')]
            original.extend(actual)
            if any(not plan.ch(plan.state.cards[raw['card']]).is_land for raw in actual):
                break
            # A prevented move cannot repeatedly attempt the same unchanged top.
            if before is not None and context._same(plan, before) is not None:
                break
    context.refs(ctx).pop('plargg_one', None)
    context.refs(ctx)[_EXILED] = {'kind': 'objects', 'objects': original}
    return True


def _pool(plan: Plan, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    binding = context.refs(ctx).get(_EXILED) or {}
    return [raw for raw in binding.get('objects', [])
            if (card := context._same(plan, ObjectRef.model_validate(raw))) is not None
            and card.zone.endswith(':exile') and plan.in_game(card)]


def _finish(plan: Plan, ctx: dict[str, Any], excluded: str | None = None) -> None:
    context.refs(ctx)[_AVAILABLE] = {'kind': 'objects', 'objects': [raw for raw in _pool(plan, ctx) if raw['card'] != excluded]}


def choose_opponent(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    if not _eligible(plan, ctx):
        _finish(plan, ctx)
        return True
    players = [pid for pid in plan.apnap() if pid != ctx['controller'] and pid in plan.live()]
    if not players:
        _finish(plan, ctx)
        return True
    if len(players) == 1:
        return _ask_card(plan, ctx, players[0])
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Choose the opponent who excludes a nonland card',
           options=[DecisionOption(id=pid, label=plan.name(pid)) for pid in players], resume={'step': _PICK, 'ctx': ctx})
    return False


def _eligible(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    return [raw['card'] for raw in _pool(plan, ctx) if not plan.ch(plan.state.cards[raw['card']]).is_land]


def _ask_card(plan: Plan, ctx: dict[str, Any], player: str) -> bool:
    from app.rules.plan import decide

    options = _eligible(plan, ctx)
    if not options:
        _finish(plan, ctx)
        return True
    if player not in plan.live():
        return choose_opponent(plan, ctx, {})
    decide(plan, player=player, kind='choose_one', prompt='Choose a nonland card that cannot be cast this way',
           options=[DecisionOption(id=cid, label=plan.state.cards[cid].name or 'Card', card_id=cid) for cid in options],
           resume={'step': _CARD, 'ctx': ctx})
    return False


def resume_opponent(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules import effects

    assert d.resume is not None
    ctx = d.resume['ctx']
    if _ask_card(plan, ctx, chosen[0]):
        effects.continue_effects(plan, ctx)


def resume_card(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules import effects

    assert d.resume is not None
    ctx = d.resume['ctx']
    if chosen[0] not in _eligible(plan, ctx):
        if _ask_card(plan, ctx, d.player):
            effects.continue_effects(plan, ctx)
        return
    _finish(plan, ctx, chosen[0])
    effects.continue_effects(plan, ctx)


PRIMITIVES = {'plargg_exile': exile, _PICK: choose_opponent}
RESUME = {_PICK: resume_opponent, _CARD: resume_card}
