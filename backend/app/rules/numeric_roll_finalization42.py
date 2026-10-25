"""Native optional numeric adjustments before any die count or event."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

_NIGHT = 'After you roll a die, you may pay 1 life. If you do, increase or decrease the result by 1. Do this only once each turn.'
# -- Xenosquirrels (wave 110H) -- the same adjustment paid with a counter and offered once per die rolled (no once-a-turn limit)
_XENO = 'After you roll a die, you may remove a +1/+1 counter from this creature. If you do, increase or decrease the result by 1.'
_COST = {_NIGHT: ('Pay 1 life', True), _XENO: ('Remove a +1/+1 counter from it', False)}  # text -> (cost, once each turn)


def definition(text: str) -> dict[str, Any] | None:
    return {'kind': 'static', 'static': 'roll_adjust', 'effects': [], 'life': text == _NIGHT} if text in _COST else None  # (wave 110H) 'life': planar-die gap


class Adjustment(BaseModel):
    card: str
    oid: str
    ability: int
    scope: str = ''

    def key(self) -> str:
        return f'roll_adjust42:{self.oid}:{self.ability}:{self.scope}'


class NumericFrame(BaseModel):
    version: int = 1
    ctx: dict[str, Any]
    effect: dict[str, Any]
    naturals: list[int]
    results: list[int]
    base: int = Field(ge=0)
    sources: list[Adjustment]
    skipped: list[str] = Field(default_factory=list)
    printed_done: bool = False
    selected: Adjustment | None = None
    used: dict[str, list[int]] = Field(default_factory=dict)  # (wave 110H) the dice each repeatable source adjusted
    die_index: int | None = None
    published: bool = False


def valid_source(plan: Any, source: Adjustment, controller: str) -> bool:
    from app.rules import abilities_of
    from app.rules.replace import conditional_lines

    card = plan.state.cards.get(source.card)
    if (card is None or plan.oid(card) != source.oid or card.controller != controller
            or not card.zone.endswith(':battlefield') or card.face_down
            or not plan.in_game(card) or plan.manual(card)):
        return False
    ch = plan.ch(card)
    skipped = conditional_lines(ch)
    return any(ab.index == source.ability and ab.index not in skipped and ab.text in _COST
               and not abilities_of.manual(ab) and (abilities_of.link_scope(ab) or '') == source.scope
               for ab in ch.abilities)


def _cost(plan: Any, source: Adjustment) -> tuple[str, bool]:
    return next(_COST[ab.text] for ab in plan.ch(plan.state.cards[source.card]).abilities if ab.index == source.ability)


def has_adjustment(plan: Any, controller: str) -> bool:
    from app.rules import abilities_of

    for card in plan.state.cards.values():
        if card.controller != controller or not card.zone.endswith(':battlefield'):
            continue
        for ab in plan.ch(card).abilities:
            if ab.text in _COST:
                source = Adjustment(card=card.id, oid=plan.oid(card), ability=ab.index, scope=abilities_of.link_scope(ab) or '')
                if valid_source(plan, source, controller):
                    return True
    return False


def start(plan: Any, ctx: dict[str, Any], effect: dict[str, Any], naturals: list[int]) -> bool:
    from app.game.rules_state import turn_log_now
    from app.rules import abilities_of

    if not naturals:
        ctx['dice'], ctx['die'], ctx['die_other'] = [], 0, 0
        return True
    sources = []
    for card in plan.state.cards.values():
        if not plan.in_game(card) or not card.zone.endswith(':battlefield') or card.controller != ctx['controller']:
            continue
        for ab in plan.ch(card).abilities:
            if ab.text in _COST:
                source = Adjustment(card=card.id, oid=plan.oid(card), ability=ab.index, scope=abilities_of.link_scope(ab) or '')
                if valid_source(plan, source, ctx['controller']):
                    sources.append(source)
    log = turn_log_now(plan.state)
    frame = NumericFrame(ctx=ctx, effect=effect, naturals=list(naturals), results=list(naturals),
                         base=log.rolled.get(ctx['controller'], 0) if log else 0, sources=sources)
    return offer(plan, frame)


def _printed(plan: Any, frame: NumericFrame) -> None:
    from app.rules import effects

    mod = frame.effect.get('mod')
    if mod and not frame.printed_done:
        frame.ctx['dice'] = list(frame.results)
        delta = int(effects._amount(plan, frame.ctx, mod['v']))
        frame.results = [r + delta if mod['op'] == '+' else r - delta for r in frame.results]
    frame.printed_done = True


def offer(plan: Any, frame: NumericFrame) -> bool:
    from app.game.rules_state import DecisionOption, turn_log_now
    from app.rules import dice
    from app.rules.plan import decide

    assert not frame.published
    available = [source for source in frame.sources if valid_source(plan, source, frame.ctx['controller'])
                 and source.key() not in frame.skipped
                 and plan.rules.once_per_turn.get(source.key()) != plan.state.turn.number
                 and len(frame.used.get(source.key(), [])) < len(frame.results)]
    if available:
        options = [DecisionOption(id=source.key(), label=f'{_cost(plan, source)[0]} to adjust one result ({plan.state.cards[source.card].name})') for source in available]
        if frame.effect.get('mod') and not frame.printed_done:
            options.append(DecisionOption(id='printed', label='Apply the printed die modifier'))
        options.append(DecisionOption(id='done', label='Finish without further optional adjustments'))
        decide(plan, player=frame.ctx['controller'], kind='choose_one', prompt='Apply a die modifier?', options=options,
               resume={'step': 'numeric_roll42', 'phase': 'offer', 'frame': frame.model_dump()})
        return False
    _printed(plan, frame)
    log = turn_log_now(plan.state)
    if log is not None:
        log.rolled[frame.ctx['controller']] = frame.base + len(frame.results)
    frame.ctx['dice'] = list(frame.results)
    frame.published = True
    return dice._emit_group(plan, frame.ctx, frame.effect, frame.results, frame.naturals, frame.base, 0)


def _after(plan: Any, frame: NumericFrame) -> None:
    from app.rules import effects

    if offer(plan, frame):
        effects.continue_effects(plan, frame.ctx)


def resume(plan: Any, decision: Any, chosen: list[str]) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    frame = NumericFrame.model_validate(decision.resume['frame'])
    phase = decision.resume['phase']
    if phase == 'offer':
        if chosen == ['done']:
            frame.skipped += [s.key() for s in frame.sources]
            _after(plan, frame)
        elif chosen == ['printed']:
            _printed(plan, frame)
            _after(plan, frame)
        else:
            source = next(s for s in frame.sources if s.key() == chosen[0])
            if not valid_source(plan, source, frame.ctx['controller']):
                frame.skipped.append(source.key())
                _after(plan, frame)
                return
            frame.selected = source
            payment_ctx = {**frame.ctx, 'source_card': source.card, 'source_object': source.oid,
                           'name': plan.state.cards[source.card].name, 'refs': {}, 'next': 0,
                           'body_done': {'do': 'noop'},
                           'effects': [{'do': 'optional_payment', 'who': 'you', 'cost': _cost(plan, source)[0], 'bind': 'roll42_paid'},
                                       {'do': 'numeric_roll42_paid', 'frame': frame.model_dump()}]}
            effects.continue_effects(plan, payment_ctx)
    elif phase == 'die':
        if frame.selected is None or not valid_source(plan, frame.selected, frame.ctx['controller']):
            _after(plan, frame)
            return
        frame.die_index = int(chosen[0])
        frame.used.setdefault(frame.selected.key(), []).append(frame.die_index)
        assert 0 <= frame.die_index < len(frame.results)
        decide(plan, player=frame.ctx['controller'], kind='choose_one', prompt='Increase or decrease that result?',
               options=[DecisionOption(id='plus', label='Increase by 1'), DecisionOption(id='minus', label='Decrease by 1')],
               resume={'step': 'numeric_roll42', 'phase': 'direction', 'frame': frame.model_dump()})
    else:
        if frame.selected is None or not valid_source(plan, frame.selected, frame.ctx['controller']):
            _after(plan, frame)
            return
        assert frame.die_index is not None and chosen[0] in ('plus', 'minus')
        frame.results[frame.die_index] += 1 if chosen[0] == 'plus' else -1
        _after(plan, frame)


def paid(plan: Any, payment_ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    frame = NumericFrame.model_validate(effect['frame'])
    assert frame.selected is not None
    if not valid_source(plan, frame.selected, frame.ctx['controller']) or not context.succeeded(payment_ctx, 'roll42_paid'):
        frame.skipped.append(frame.selected.key())
        _after(plan, frame)
        return True
    if _cost(plan, frame.selected)[1]:
        plan.rules.once_per_turn[frame.selected.key()] = plan.state.turn.number
    decide(plan, player=frame.ctx['controller'], kind='choose_one', prompt='Choose the die result to adjust',
           options=[DecisionOption(id=str(i), label=f'Die {i + 1}: {n}') for i, n in enumerate(frame.results)
                    if i not in frame.used.get(frame.selected.key(), [])],
           resume={'step': 'numeric_roll42', 'phase': 'die', 'frame': frame.model_dump()})
    return True


PRIMITIVES = {'numeric_roll42_paid': paid}
RESUME = {'numeric_roll42': resume}
