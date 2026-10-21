"""Optional hand reveals inside immediately resolving activated mana abilities."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules import mana as M
    from app.rules.plan import Plan

_LINE = re.compile(r'\{T\}: Reveal any number of (?P<what>.+?) (?:in|from) your hand\. '
                   r'Add (?P<mana>(?:\{[WUBRGC]\})+) for each card revealed this way\.'
                   r'(?P<restriction> Spend this mana only on costs that contain \{X\}\.)?')


def spec(text: str) -> tuple[str, tuple[str, ...], bool] | None:
    from app.rules import selectors

    m = _LINE.fullmatch(text.strip())
    if m is None:
        return None
    sel = selectors.parse(m['what'] + ' in your hand')
    if sel is None or not sel.card or sel.zones != ('hand',) or sel.zone_owner != 'you':
        return None
    return sel.key(), tuple(re.findall(r'\{([WUBRGC])\}', m['mana'])), bool(m['restriction'])


def parse(text: str) -> M.ManaAbility | None:
    from app.rules import mana as M

    found = spec(text)
    if found is None:
        return None
    sel, output, restricted = found
    note = 'Spend this mana only on costs that contain {X}.' if restricted else ''
    return M.ManaAbility(tap=True, sacrifice_self=False, options=(output,), reveal_hand=sel,
                         spend_only=M.spend_kind(note.rstrip('.')) if restricted else None, spend_text=note)


def available(plan: Plan, payer: str, exclude: tuple[str, ...] = ()) -> bool:
    """A manual source can be activated without promising any hidden-card output."""
    from app.rules import casting

    for cid in plan.state.zones.get(f'{payer}:battlefield', []):
        card = plan.state.cards[cid]
        if cid in exclude or card.controller != payer or not casting.can_use_tap_abilities(plan.state, card, plan.ch(card), plan.info):
            continue
        for _, ability in casting.mana_abilities(plan.state, card, plan.info):
            if ability.reveal_hand is not None and casting.spend_allowed(ability.spend_only, None):
                return True
    return False


def start(plan: Plan, card: CardInstance, ability: M.ManaAbility, index: int) -> None:
    from app.rules import mana_units, reveal_hand
    from app.rules import payment_continuations as pc
    from app.rules.plan import decide

    nested = plan.rules.decision is not None
    if nested:
        assert plan.rules.payment_outer is None
        plan.rules.payment_outer, plan.rules.decision = plan.rules.decision, None
    controller = plan.actor
    ctx = {'controller': controller, 'source_card': card.id}
    data = {'source': card.model_dump(mode='json'), 'oid': plan.oid(card), 'controller': controller,
            'ability': pc.ability_data(ability), 'index': index, 'nested': nested,
            'mana_context': {'source_card': card.id, 'source_object': plan.oid(card), 'only': ability.spend_only,
                             'riders': mana_units.rider_specs(ability, plan.ch(card).name),
                             'note': ability.spend_text, 'tap': True}}
    # Revealing is an effect, not an activation cost: the tap is already paid.
    plan.do({'type': 'rules_mana', 'player': controller, 'tap': [card.id], 'sacrifice': [],
             'delta': {}, 'life': 0, 'label': f'activated {plan.ch(card).name}'}, actor=controller)
    options = reveal_hand._options(plan, ctx, {'sel': ability.reveal_hand})
    decide(plan, player=controller, kind='choose_cards', prompt='Reveal any number of cards from your hand',
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or 'Card', card_id=c) for c in options],
           min_choices=0, max_choices=len(options), resume={'step': 'reveal_mana', 'data': data})


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import mana_replace, reveal_hand
    from app.rules import payment_continuations as pc

    data = d.resume['data']
    ability = pc.ability_of(data['ability'])
    ctx = {'controller': data['controller'], 'source_card': data['source']['id']}
    options = set(reveal_hand._options(plan, ctx, {'sel': ability.reveal_hand}))
    picked = [c for c in chosen if c in options]
    if picked:
        plan.do({'type': 'reveal', 'card_ids': picked}, actor=data['controller'])
    data['option'] = list(ability.options[0] * len(picked))
    card = _source(plan, data)
    data['replacements'] = [definition for owner, definition in mana_replace._statics(plan.state, plan.info)
                            if mana_replace._applies(plan.state, plan.info, card, owner, definition)] if picked else []
    _replace(plan, data)


def _source(plan: Plan, data: dict[str, Any]) -> CardInstance:
    from app.game.state import CardInstance

    card = plan.state.cards.get(data['source']['id'])
    return card if card is not None and plan.oid(card) == data['oid'] else CardInstance.model_validate(data['source'])


def _replacement_label(op: dict[str, Any]) -> str:
    if op['do'] == 'mul':
        return f"Produce {op['n']} times as much mana"
    if op['do'] == 'collapse':
        return 'Replace multiple mana with one colorless mana'
    if op['do'] == 'fixed':
        return 'Replace the mana with one mana of the required type'
    return 'Change the type of mana produced'


def _replace(plan: Plan, data: dict[str, Any]) -> None:
    from app.rules.plan import decide

    left = data['replacements']
    eligible = [i for i, definition in enumerate(left)
                if definition['op']['do'] != 'collapse' or len(data['option']) >= int(definition['op']['min'])]
    if not eligible:
        _produce(plan, data)
        return
    if len(eligible) > 1:
        decide(plan, player=data['controller'], kind='choose_one', prompt='Choose the next mana replacement',
               options=[DecisionOption(id=str(i), label=_replacement_label(left[i]['op'])) for i in eligible],
               resume={'step': 'reveal_mana_replace', 'data': data})
        return
    _apply(plan, data, eligible[0])


def _apply(plan: Plan, data: dict[str, Any], index: int) -> None:
    from app.rules import mana as M
    from app.rules import mana_replace
    from app.rules.plan import decide

    definition = data['replacements'].pop(index)
    options = mana_replace._apply(definition['op'], tuple(data['option']), plan.ch(_source(plan, data)).subtypes)
    if len(options) > 1:
        decide(plan, player=data['controller'], kind='choose_one', prompt='Choose the mana produced',
               options=[DecisionOption(id=str(i), label=M.symbols({m: o.count(m) for m in set(o)})) for i, o in enumerate(options)],
               resume={'step': 'reveal_mana_type', 'data': data, 'options': [list(o) for o in options]})
        return
    data['option'] = list(options[0])
    _replace(plan, data)


def resume_replace(plan: Plan, d: Any, chosen: list[str]) -> None:
    _apply(plan, d.resume['data'], int(chosen[0]))


def resume_type(plan: Plan, d: Any, chosen: list[str]) -> None:
    data = d.resume['data']
    data['option'] = d.resume['options'][int(chosen[0])]
    _replace(plan, data)


def _add(plan: Plan, controller: str, option: list[str] | tuple[str, ...], ctx: dict[str, Any]) -> None:
    from app.rules import mana_units

    mana = {m: option.count(m) for m in set(option)}
    added = mana_units.from_context(plan, ctx, mana)
    for unit in added.get('add_units', []):
        unit.update(only=ctx.get('only'), riders=ctx.get('riders', []), note=ctx.get('note', ''),
                    generic_allowed=ctx.get('generic_allowed', True))
    plan.do({'type': 'rules_mana', 'player': controller, 'tap': [], 'sacrifice': [], **added,
             'life': 0, 'label': 'added mana'}, actor=controller)


def _produce(plan: Plan, data: dict[str, Any]) -> None:
    from app.game.rules_state import emit
    from app.rules import contextual_mana_triggers, tap_mana

    option = data['option']
    if not option:
        _finish(plan, data)
        return
    _add(plan, data.get('beneficiary',data['controller']), option, data['mana_context'])
    card = _source(plan, data)
    emit(plan.state, 'mana_added', object_id=data['oid'], card=card.id, player=data['controller'],
         amount=len(option), counter='tap' if data.get('tap',True) else None)
    # These are separate triggered mana productions, once per activation, not once per card.
    data['extras'] = []
    for owner, definition, source in tap_mana._triggers(plan.state, plan.info):
        if not tap_mana._applies(plan.state, plan.info, card, owner, definition, source):
            continue
        extra = contextual_mana_triggers.frozen(plan, data, source, definition, owner,
                    [list(o) for o in tap_mana._extra(definition, tuple(option))])
        if extra is not None:
            data['extras'].append(extra)
    if plan.ch(card).is_land:
        from app.rules import scripts

        for attached in plan.state.cards.values():
            if attached.attached_to != card.id or not attached.zone.endswith(':battlefield') or attached.face_down:
                continue
            if plan.rules.card_mode(attached.id) == 'manual':
                continue
            for definition in scripts.definitions(plan.ch(attached)).values():
                if definition.get('trigger') != 'tapped_for_mana':
                    continue
                extra_options = definition['extra']
                if extra_options == [['CHOSEN']]:
                    from app.rules.casting import _chosen_color

                    color = _chosen_color(attached)
                    if color is None:
                        continue
                    extra_options = [[color]]
                extra = contextual_mana_triggers.frozen(plan, data, attached.id, definition, attached.controller, extra_options)
                if extra is not None:
                    data['extras'].append(extra)
    _finish(plan, data)


def _extras(plan: Plan, data: dict[str, Any]) -> None:
    from app.rules import mana as M
    from app.rules.plan import decide

    if not data['extras']:
        _finish(plan, data)
        return
    extra = data['extras'].pop(0)
    options = extra['options']
    if len(options) > 1:
        decide(plan, player=data['controller'], kind='choose_one', prompt='Choose the additional mana',
               options=[DecisionOption(id=str(i), label=M.symbols({m: o.count(m) for m in set(o)})) for i, o in enumerate(options)],
               resume={'step': 'reveal_mana_extra', 'data': data, 'extra': extra})
        return
    _add_extra(plan, data, extra, options[0])


def _add_extra(plan: Plan, data: dict[str, Any], extra: dict[str, Any], option: list[str]) -> None:
    from app.game.rules_state import emit

    if option:
        source = plan.state.cards.get(extra['source'] or '')
        ctx = {'source_card': source.id if source else None, 'source_object': plan.oid(source) if source else None}
        _add(plan, data['controller'], option, ctx)
        emit(plan.state, 'mana_added', object_id=ctx['source_object'], card=ctx['source_card'],
             player=data['controller'], amount=len(option))
    _extras(plan, data)


def resume_extra(plan: Plan, d: Any, chosen: list[str]) -> None:
    extra = d.resume['extra']
    _add_extra(plan, d.resume['data'], extra, extra['options'][int(chosen[0])])


def _finish(plan: Plan, data: dict[str, Any]) -> None:
    from app.rules import casting, contextual_mana_triggers
    from app.rules import payment_continuations as pc
    from app.rules import replace as replacements_

    if data.get('then') is not None:
        then = data['then']
        ctx = then.get('ctx') if then.get('do') == 'continue' else None
        # A native mana body finishes its instructions and legacy riders first.
        # Inserting the terminal into that body's existing frame preserves every
        # paused continuation and avoids executing either activation twice.
        frame = ((ctx or {}).get('body_done') or {}).get('frame')
        if data.get('extras') and frame is not None:
            frame['then'] = contextual_mana_triggers.terminal(data, frame['then'])
        replacements_.run_then(plan, then)
        return
    ability = replace(pc.ability_of(data['ability']), reveal_hand=None)
    after = casting._mana_terminal(plan, nested=data['nested'])
    if data.get('extras'):
        after = contextual_mana_triggers.terminal(data, after)
    if casting.after_mana_ability(plan, _source(plan, data), data['index'], ability, data['controller'],
                                  source_object=data['oid'], then=after):
        replacements_.run_then(plan, after)
