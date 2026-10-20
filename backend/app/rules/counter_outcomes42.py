"""Follow-ups that consume exact committed counter-placement receipts."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text == ('Put a number of +1/+1 counters on target creature you control equal to the mana value of the exiled card.'):
        first = scripts.parse_effects('Put a +1/+1 counter on target creature you control.')
        assert first is not None
        return ([{'do': 'linked_cards', 'as': '_aesir_linked42'},
                 {'do': 'add_counters', 'who': 'target', 'kind': '+1/+1',
                  'n': {'sum': 'mana_value', 'of': 'ref:_aesir_linked42'}}], first[1], False)
    if text == "Return ~ and the exiled card to their owner's hand.":
        return ([{'do': 'return_linked_source42'}], None, False)
    rise = re.fullmatch(r'(Target|Each) noncreature artifact you control becomes a 0/0 artifact creature\. '
                        r'Put four \+1/\+1 counters on each artifact that became a creature this way\.', text)
    if rise is not None:
        first = scripts.parse_effects(f'{rise[1]} noncreature artifact you control becomes a 0/0 artifact creature.')
        if first is not None and len(first[0]) == 1 and first[0][0]['do'] == 'become':
            return ([{**first[0][0], 'as': '_rise_became42'},
                     {'do': 'add_counters', 'who': 'ref:_rise_became42', 'kind': '+1/+1', 'n': 4}], first[1], False)
        return None
    if text.rstrip('.') == ('Remove a loyalty counter from each of any number of permanents you control. '
                            'Exile that many cards from the top of your library. You may play them this turn'):
        from app.rules import counter_group_choices, selectors

        return ([{'do': counter_group_choices.STEP, 'sel': selectors.Selector(controller='you').key(),
                  'kind': 'loyalty', 'each': 1, 'bind': '_chandra_removed42'},
                 {'do': 'chandra_packet42', 'binding': '_chandra42', 'n': {'ref_amount': '_chandra_removed42'}}], None, False)
    if text.rstrip('.') == ('Exile up to that many target cards from their graveyard. '
                            'Put a +1/+1 counter on ~ for each creature card exiled this way. '
                            'You gain 1 life for each noncreature card exiled this way'):
        from app.rules import selectors

        group = {'what': selectors.Selector(card=True, zones=('graveyard',), zone_owner='that_player').key(),
                 'min': 0, 'x_count': 'upto', 'x_value': {'event_amount': 1}}
        return ([{'do': 'froghemoth_packet42', 'stage': 'freeze'},
                 {'do': 'exile', 'who': 'target:0', 'as': '_frog_exiled'},
                 {'do': 'froghemoth_packet42', 'stage': 'finish'}], [group], False)
    if text.rstrip('.') == ('Tap target creature defending player controls. If that creature has greater power than ~, '
                            'put a number of +1/+1 counters on ~ equal to the difference'):
        first = scripts.parse_effects('Tap target creature defending player controls.')
        if first is None:
            return None
        return ([*first[0], {'do': 'conformer_difference42'}], first[1], False)
    if text.rstrip('.') == "Tap X target creatures. Put a stun counter on each of those creatures you don't control":
        first = scripts.parse_effects('Tap X target creatures.')
        if first is None:
            return None
        return ([*first[0], {'do': 'stun_opposing_targets42'}], first[1], False)
    if text.rstrip('.') in ('Move a loyalty counter from ~ onto that planeswalker',
                            'You may move a loyalty counter from ~ onto that planeswalker'):
        return ([{'do': 'move_counters', 'who': 'event', 'kind': 'loyalty', 'n': 1}], None, text.startswith('You may '))
    match = re.fullmatch(r'Put a double strike counter on (target|each) creature, then goad each creature '
                         r'that had a double strike counter put on it this way\.?', text)
    if match is None:
        return None
    first = scripts.parse_effects(f'Put a double strike counter on {match[1]} creature.')
    if first is None:
        return None
    return ([{**e, 'receipt': 'showdown'} for e in first[0]] +
            [{'do': 'goad_counter_recipients', 'receipt': 'showdown', 'kind': 'double strike'}], first[1], False)


def goad_recipients(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, counter_receipts, keyword_actions

    cards = []
    for entry in counter_receipts.placements(ctx, e['receipt']):
        card = context._same(plan, entry.destination)
        if (entry.kind == e['kind'] and entry.amount > 0 and card is not None
                and card.zone.endswith(':battlefield') and plan.ch(card).is_creature and card.id not in cards):
            cards.append(card.id)
    context.bind_objects(plan, ctx, '_counter_goad', cards)
    return keyword_actions.goad(plan, ctx, {'who': 'ref:_counter_goad'})


def stun_opponents(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    cards = [cid for cid in effects._cards(plan, ctx, 'target')
             if plan.state.cards[cid].zone.endswith(':battlefield')
             and plan.state.cards[cid].controller != ctx['controller']]
    context.bind_objects(plan, ctx, '_maze_stun', cards)
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do': 'add_counters', 'who': 'ref:_maze_stun', 'kind': 'stun', 'n': 1}]
    return True


def conformer_difference(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import values

    n = values.evaluate(plan, ctx, {'power': 'target'}) - values.evaluate(plan, ctx, {'power': 'self'})
    if n > 0:
        ctx['effects'][ctx['next']:ctx['next']] = [
            {'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': n}]
    return True


def froghemoth_packet(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, this_way

    if e['stage'] == 'freeze':
        ctx['_frog_kinds'] = {plan.oid(cid): plan.ch(plan.state.cards[cid]).is_creature
                              for cid in effects._cards(plan, ctx, 'target:0')}
        return True
    matched = this_way._matched(plan, ctx, {'this_way': 'exiled', 'ref_count': '_frog_exiled', 'of': None})
    kinds = ctx.pop('_frog_kinds', {})
    creatures = sum(bool(kinds.get(was['object_id'])) for _, was in matched)
    other = len(matched) - creatures
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': creatures},
        {'do': 'gain_life', 'who': 'you', 'n': other}]
    return True


def chandra_packet(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import exile_packet_continuations as packets
    from app.rules import values

    n = values.evaluate(plan, ctx, e['n'])
    packets.top_packet(plan, ctx, e, [ctx['controller']], n=n)
    packets.insert(ctx, [packets.grant(e, play=True)])
    return True


def return_linked_source(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, exiled_with

    cards = [*effects._cards(plan, ctx, 'self'), *exiled_with.cards(plan, ctx)]
    context.bind_objects(plan, ctx, '_linked_source_return42', list(dict.fromkeys(cards)))
    ctx['effects'][ctx['next']:ctx['next']] = [{'do': 'bounce', 'who': 'ref:_linked_source_return42'}]
    return True


PRIMITIVES = {'return_linked_source42': return_linked_source, 'chandra_packet42': chandra_packet, 'froghemoth_packet42': froghemoth_packet, 'goad_counter_recipients': goad_recipients, 'stun_opposing_targets42': stun_opponents,
              'conformer_difference42': conformer_difference}
