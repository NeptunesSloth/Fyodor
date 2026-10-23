"""Native spell text refresh preserving announced target identities and choices."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from pydantic import TypeAdapter

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, SpliceText71, StackEntry
from app.rules import casting, layers, scripts
from app.rules.characteristics import Characteristics
from app.rules.oracle import AbilityText
from app.rules.plan import Plan, decide


class UnprovenText71(ValueError):
    pass


def extras(name: str, own: Characteristics, full: Characteristics) -> SpliceText71:
    from dataclasses import asdict

    return SpliceText71(name=name, abilities=[asdict(a) for a in full.abilities[len(own.abilities):]])


def snapshot(plan: Plan, card: str) -> SpliceText71 | None:
    record = plan.rules.payments.get(plan.oid(card))
    if record is None:
        return None
    if record.splice_text71 is not None:
        return record.splice_text71
    # The existing exact receipt can independently prove an empty splice set.
    if record.spliced_names == []:
        return SpliceText71(name=plan.ch(plan.state.cards[card]).name, abilities=[])
    return None


def definition(plan: Plan, card_id: str, entry: StackEntry) -> dict[str, Any]:
    card = plan.state.cards[card_id]
    ch = plan.ch(card)
    receipt = snapshot(plan, card_id)
    if receipt is None:
        raise UnprovenText71('This saved spell has no original splice-text receipt')
    if receipt.abilities:
        from app.rules.copying import renamed

        extra = tuple(TypeAdapter(AbilityText).validate_python(a) for a in receipt.abilities)
        base_name = layers.copiable(plan.state, card, plan.info).name
        extra = tuple(replace(a, text=renamed(a.text, receipt.name, base_name)) for a in extra)
        extra_ch = Characteristics(name=base_name, types=frozenset({'Instant'}), abilities=extra)
        extra_ch = layers.name_changes(extra_ch, layers.affecting(plan.state, card, plan.info), [], plan.info)
        offset = max((a.index for a in ch.abilities), default=-1) + 1
        ch = replace(ch, abilities=(*ch.abilities, *(replace(a, index=offset + i) for i, a in enumerate(extra_ch.abilities))))
    result = scripts.spell_definition(ch)
    if result is None:
        raise ActionError('The changed spell text is not automated')
    return result


def fixed_scopes(d: dict[str, Any], entry: StackEntry) -> dict[str, Any]:
    """Reuse only the actual players' groups announced for a per-player clause."""
    from app.rules import per_opponent, selectors

    if not per_opponent.flagged(d):
        return d
    group = d['targets'][0]
    base = selectors.from_key(group['what'])
    first = group.get('from', 0)
    groups: list[dict[str, Any]] = []
    all_effects = []
    for old in entry.group_specs:
        was = selectors.from_key(old['what'])
        if base.zone_owner == 'opponent':
            if not isinstance(was.zone_owner, str) or not was.zone_owner.startswith('player:'):
                raise ActionError('The original player target scope is not known')
            key = replace(base, zone_owner=was.zone_owner).key()
        elif base.controller == 'opponent':
            if not isinstance(was.controller, str) or not was.controller.startswith('player:'):
                raise ActionError('The original controller target scope is not known')
            key = replace(base, controller=was.controller).key()
        else:
            raise ActionError('The original per-player target clause is not known')
        all_effects += scripts._renumber([e for e in d['effects'][first:] if not e.get('opponent_aggregate')], [len(groups)])
        groups.append({k: v for k, v in group.items() if k not in (per_opponent.FLAG, 'from', 'required_present')} | {'what': key})
    aggregate = [{k: v for k, v in e.items() if k != 'opponent_aggregate'} for e in d['effects'][first:] if e.get('opponent_aggregate')]
    return {**d, 'effects': [*d['effects'][:first], *all_effects, *aggregate], 'targets': groups}


def refresh(plan: Plan, card_id: str, entry: StackEntry) -> StackEntry | None:
    if entry.kind != 'spell':
        return entry
    card = plan.state.cards[card_id]
    if not any(e.layer == '3' and e.text_change71 is not None for e in layers.affecting(plan.state, card, plan.info)):
        return entry
    try:
        d = fixed_scopes(definition(plan, card_id, entry), entry)
    except UnprovenText71:
        decide(plan, player=entry.controller, kind='manual_resolution',
               prompt=f'{entry.name}: this older saved spell lacks its original splice text. Resolve its changed text by hand, then Done.',
               options=[DecisionOption(id='done', label='Done')],
               resume={'step': 'text71_legacy_done', 'stack_id': card_id, 'controller': entry.controller}, source=card)
        return None
    if d.get('modes'):
        grouped = casting.modal_groups(d, entry.modes)
        if grouped is not None:
            if len(grouped) != len(entry.group_specs):
                raise ActionError('A text change cannot alter the announced target groups')
            return entry.model_copy(update={'effects': casting.modal_effects(d, entry.modes, True), 'group_specs': grouped})
        specs = [d['modes'][i]['target'] for i in entry.modes]
        if len(specs) != len(entry.slot_specs):
            raise ActionError('A text change cannot alter the announced target slots')
        return entry.model_copy(update={'effects': casting.modal_effects(d, entry.modes, False), 'slot_specs': specs})
    if entry.group_specs:
        groups = scripts.target_groups(d)
        if len(groups) != len(entry.group_specs):
            raise ActionError('A text change cannot alter the announced target groups')
        return entry.model_copy(update={'effects': d['effects'], 'group_specs': groups})
    return entry.model_copy(update={'effects': d['effects'], 'target_spec': d.get('target')})


def legacy_done(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if chosen != ['done'] or d.resume is None:
        raise ActionError('Finish the legacy text resolution with Done')
    effects.finish(plan, {'stack_id': d.resume['stack_id'], 'controller': d.resume['controller']})
