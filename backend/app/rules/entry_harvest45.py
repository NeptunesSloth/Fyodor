"""Unimported existing-card/same-controller entry scheduler prototype.

No live parser, replacement or primitive registration. Copy/control/diversion,
other pre-entry actions, cross-controller scheduling and token entrants remain
integration gates. Every mutation below occurs only after an actual selection.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'entry_harvest45'
PUT_SITE = 'entry_harvest45_put'


class Incoming(BaseModel):
    original: ObjectRef
    controller: str
    program: Literal['harvest_all', 'greatest_power']
    ability_index: int
    quantity: int | None = Field(default=None, ge=0)  # None unapplied; zero completed-empty.


class RemovedCounter(BaseModel):
    source: ObjectRef
    kind: str
    amount: int = Field(ge=1)


class HarvestReceipt(BaseModel):
    entrant: ObjectRef
    removed: list[RemovedCounter] = Field(default_factory=list)
    original_total: int = Field(ge=0)


class EntryBatch(BaseModel):
    controller: str
    incoming: list[Incoming]
    ctx: dict[str, Any]
    harvests: dict[str, HarvestReceipt] = Field(default_factory=dict)
    applied_order: list[str] = Field(default_factory=list)
    counter_answers: dict[str, str] = Field(default_factory=dict)


def _program(plan: Plan, ref: ObjectRef, controller: str) -> Incoming:
    from app.rules import context, scripts

    card = context._same(plan, ref)
    if card is None or card.is_token or card.zone.endswith(':battlefield'):
        raise ActionError('The prototype needs an unchanged, unentered existing card')
    probe = card.model_copy(update={'zone': f'{controller}:battlefield', 'controller': controller})
    ch = plan.ch(probe)
    for ability in ch.abilities:
        text = scripts.self_text(ability.text, ch.name).replace('this creature', '~')
        if text == ('As ~ enters, remove all counters from all permanents. '
                    '~ enters with a +1/+1 counter on it for each counter removed this way.'):
            return Incoming(original=ref, controller=controller, program='harvest_all', ability_index=ability.index)
        if text == ('~ enters with X +1/+1 counters on it, where X is the greatest power '
                    'among other creatures you control.'):
            return Incoming(original=ref, controller=controller, program='greatest_power', ability_index=ability.index)
    raise ActionError('That entrant is outside the two printed prototype programs')


def prepare(plan: Plan, ctx: dict[str, Any], refs: list[ObjectRef]) -> EntryBatch:
    """Pure classification only: repeated previews never remove or freeze quantities."""
    if not refs or len({r.object_id for r in refs}) != len(refs):
        raise ActionError('Choose distinct original incoming objects')
    frame = EntryBatch(controller=ctx['controller'], incoming=[_program(plan, r, ctx['controller']) for r in refs], ctx=ctx)
    frame.ctx = ctx  # Preserve the caller's live context on a synchronous completion.
    return frame


def available(frame: EntryBatch) -> list[Incoming]:
    return [entry for entry in frame.incoming if entry.quantity is None]


def _validate(plan: Plan, frame: EntryBatch) -> None:
    from app.rules import context, prohibitions

    if any(entry.controller != frame.controller for entry in frame.incoming):
        raise ActionError('Cross-controller entry scheduling is outside this prototype')
    for entry in frame.incoming:
        card = context._same(plan, entry.original)
        if card is None or card.zone.endswith(':battlefield'):
            raise ActionError('An original incoming object changed before entering')
        if prohibitions.cant_enter(plan, card, frame.controller):
            raise ActionError('Entry prohibition is outside this prototype')


def apply(plan: Plan, frame: EntryBatch, object_id: str) -> None:
    """Apply exactly one selected replacement and seal its original quantity."""
    from app.rules import context, counter_removal_results, replacements, scripts

    _validate(plan, frame)
    entry = next((e for e in available(frame) if e.original.object_id == object_id), None)
    if entry is None:
        raise ActionError('Choose an unapplied incoming replacement')
    if entry.program == 'harvest_all':
        removed = []
        # Only actual old permanents exist here; incoming card plans aren't a table.
        refs = [ref for card in list(plan.state.cards.values())
                if card.zone.endswith(':battlefield') and plan.in_game(card)
                and (ref := context.ref_of(plan, card.id)) is not None]
        for ref in refs:
            card = context._same(plan, ref)
            assert card is not None
            for kind, amount in list(card.counters.items()):
                actual = counter_removal_results.remove(plan, card.id, kind, amount, by=frame.controller)
                if actual:
                    removed.append(RemovedCounter(source=ref, kind=kind, amount=actual))
        total = sum(row.amount for row in removed)
        frame.harvests[object_id] = HarvestReceipt(entrant=entry.original, removed=removed, original_total=total)
        entry.quantity = total
    else:
        card = context._same(plan, entry.original)
        assert card is not None
        probe = card.model_copy(update={'zone': f'{frame.controller}:battlefield', 'controller': frame.controller})
        definition = scripts.definitions(plan.ch(probe)).get(entry.ability_index)
        if definition is None or definition.get('replacement') != 'enters_with_counters':
            raise ActionError('The native entering quantity definition changed')
        entry.quantity = max(0, replacements._counter_amount(plan, card.id, frame.controller, definition, None,
                                                              [e.original.card for e in frame.incoming]))
    frame.applied_order.append(object_id)


def _enter(plan: Plan, frame: EntryBatch) -> bool:
    from app.rules import context, replace, replacements

    _validate(plan, frame)
    cards = [entry.original.card for entry in frame.incoming]
    entering = {cid: frame.controller for cid in cards}
    puts = [(entry.original.card, '+1/+1', int(entry.quantity or 0)) for entry in frame.incoming]
    planned = replace.plan_counters(plan, puts, by=frame.controller, effect=True, entering=entering,
                                    newcomers=cards, answers=frame.counter_answers, ask=True)
    if isinstance(planned, replace.Ask):
        replace.ask(plan, planned, frame.counter_answers,
                    {'site': PUT_SITE, 'request': {'frame': frame.model_dump(mode='json')}})
        return False
    # The existing native CounterPlan is complete before the single actual move.
    prepared = {}
    for entry in frame.incoming:
        card = context._same(plan, entry.original)
        assert card is not None
        prepared[card.id] = plan.ch(card.model_copy(update={'zone': f'{frame.controller}:battlefield',
                                                            'controller': frame.controller}))
    plan.do({'type': 'move', 'card_ids': cards, 'to': {'player': frame.controller, 'zone': 'battlefield'}},
            actor=frame.controller)
    for entry in frame.incoming:
        # Reuse native entry setup without re-reading an already sealed quantity.
        replacements.after_entry(plan, entry.original.card, frame.controller, newcomers=cards,
                                 prepared=(prepared[entry.original.card], None))
    replace.do_counters(plan, planned, by=frame.controller)
    frame.ctx['harvest45_receipts'] = {key: value.model_dump(mode='json') for key, value in frame.harvests.items()}
    frame.ctx['harvest45_quantities'] = {entry.original.object_id: entry.quantity for entry in frame.incoming}
    return True


def run(plan: Plan, frame: EntryBatch) -> bool:
    from app.rules.plan import decide

    _validate(plan, frame)
    while pending := available(frame):
        if len(pending) == 1:
            apply(plan, frame, pending[0].original.object_id)
            continue
        decide(plan, player=frame.controller, kind='choose_one', prompt='Prototype: which entry replacement applies first?',
               options=[DecisionOption(id=e.original.object_id, label=f'{plan.state.cards[e.original.card].name}: {e.program}',
                                       card_id=e.original.card) for e in pending],
               resume={'step': STEP, 'frame': frame.model_dump(mode='json')})
        return False
    return _enter(plan, frame)


def primitive(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    refs = context.refs(ctx).get(e['binding'], {}).get('objects', [])
    return run(plan, prepare(plan, ctx, [ObjectRef.model_validate(ref) for ref in refs]))


def resume(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    frame = EntryBatch.model_validate(decision.resume['frame'])
    if len(chosen) != 1:
        raise ActionError('Choose one entry replacement')
    apply(plan, frame, chosen[0])
    if run(plan, frame):
        effects.continue_effects(plan, frame.ctx)


def resume_put(plan: Plan, request: dict[str, Any], answers: dict[str, str], then: dict[str, Any] | None) -> None:
    from app.rules import effects

    frame = EntryBatch.model_validate(request['frame'])
    frame.counter_answers = dict(answers)
    if _enter(plan, frame):
        effects.continue_effects(plan, frame.ctx)
