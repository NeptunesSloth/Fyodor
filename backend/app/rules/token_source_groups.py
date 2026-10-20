"""Native grouped copy instructions and their resolution-time selections."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

from app.rules.token_copy_sources import CREATED, copy


def key(text: str) -> str:
    from app.rules import selectors
    sel = selectors.parse(text)
    assert sel is not None, text
    return sel.key()


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    t = re.sub(r'\s+', ' ', body).strip().rstrip('.').lower()
    if t == 'for each of x target permanents, create x tokens that are copies of that permanent':
        return [{**copy('target'), 'n': {'x': 1}, 'creation_each': True}], [{'what': key('permanent'), 'min': 0, 'max': 250, 'x_count': 'exact'}], False
    if t == "surveil 1. create a token that's a copy of ~, then sacrifice an artifact or creature":
        return scripts.parse_effects("Surveil 1. Create a token that's a copy of ~. Sacrifice an artifact or creature.")
    if t == "exile target nonland permanent. each player other than its controller creates a token that's a copy of it":
        return [{'do': 'copy_group_prepare', 'mode': 'creators', 'who': 'target', 'as': 'identity_creators'},
                {'do': 'exile', 'who': 'target', 'as': 'identity_original'},
                {**copy('ref:identity_original'), 'creator': 'ref:identity_creators', 'each_creator': True}], key('nonland permanent'), False
    if t == "create a tapped token that's a copy of ~ if seven or more land cards are in your graveyard. otherwise, create a tapped 1/1 black insect creature token with flying":
        from app.rules import conditions
        cond = conditions.parse('seven or more land cards are in your graveyard')
        assert cond is not None
        insect = scripts.parse_effects('Create a tapped 1/1 black Insect creature token with flying.')
        assert insect is not None
        return [{'do': 'only_if', 'cond': cond, 'skip': 1}, {**copy('self'), 'tapped': True},
                {'do': 'only_if', 'cond': {'not': cond}, 'skip': 1}, *insect[0]], None, False
    if t == "for each opponent, choose a creature that player controls. create a token that's a copy of one of those creatures, except its power is equal to the total power of those creatures, its toughness is equal to the total toughness of those creatures, and it's a colorless eldrazi creature":
        return [{'do': 'player_chooses', 'who': 'each_opponent', 'by': 'you', 'sel': key('creature'), 'n': 1, 'as': 'anomaly_group'},
                {'do': 'copy_group_prepare', 'mode': 'stats', 'who': 'ref:anomaly_group', 'as': 'anomaly_total'},
                {'do': 'select_copy_originals', 'who': 'ref:anomaly_group', 'n': 1, 'as': 'anomaly_original'},
                {'do': 'copy_group_prepare', 'mode': 'anomaly', 'who': 'ref:anomaly_original', 'with': 'ref:anomaly_total'}], None, False
    groups = {
        "for each creature token you control that entered this turn, create a tapped and attacking token that's a copy of that token. at the beginning of the next end step, sacrifice those tokens":
            ('creature token you control that entered this turn', 'end', 'sacrifice'),
        "for each attacking modified creature you control, create a tapped and attacking token that's a copy of that creature. exile those tokens at end of combat":
            ('attacking modified creature you control', 'end_combat', 'exile'),
    }
    if t in groups:
        sel, step, action = groups[t]
        return [{**copy(key(sel)), 'tapped': True, 'attacking': True, 'creation_each': True},
                {'do': 'schedule_copy_cleanup', 'what': action, 'whose': 'next', 'step': step,
                 'ref': 'ref:' + CREATED}], None, False
    return None


def definition(text: str, kind: str) -> dict[str, Any] | None:
    from app.rules import copying, events

    t = re.sub(r'\s+', ' ', text).strip().rstrip('.').lower()
    if kind == 'triggered' and t == "whenever ~ or an enchanted creature you control deals combat damage to a player, you may create a token that's a copy of a nonlegendary enchantment you control. do this only once each turn":
        cond = events.parse_condition('an enchanted creature you control deals combat damage to a player')
        assert cond is not None
        cond = {**cond, 'subject': 'self_or'}
        return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'target': None, 'optional': False,
                'limit': 'do_once', 'effects': [
                    {'do': 'player_chooses', 'who': 'you', 'sel': key('nonlegendary enchantment you control'),
                     'n': 1, 'upto': True, 'optional': True, 'as': 'copy_enchantment', 'did': 'copy_chosen'},
                    copy('ref:copy_enchantment')]}
    if kind == 'triggered' and t == "at the beginning of your upkeep, choose up to one other target enchantment or artifact. if you're the monarch, you may create a token that's a copy of it. if you're not the monarch, you may have ~ become a copy of it, except it has this ability":
        return {'kind': 'triggered', 'trigger': 'upkeep_you', 'optional': False,
                'target': None, 'targets': [{'what': key('other enchantment or artifact'), 'min': 0, 'max': 1}],
                'effects': [{'do': 'copy_group_prepare', 'mode': 'court', 'who': 'target',
                             'excepts': [{'add_text': [copying.THIS_ABILITY]}]}]}
    if kind == 'triggered' and t == "when ~ dies, if it had two or more +1/+1 counters on it, create a token that's a copy of it at the beginning of the next end step. the token enters with half that many +1/+1 counters on it, rounded down":
        cond = {'value': {'counters': '+1/+1', 'on': 'event'}, 'op': '>=', 'n': 2}
        return {'kind': 'triggered', 'trigger': 'event', 'cond': events.parse_condition('~ dies'),
                'if': cond, 'optional': False, 'target': None,
                'effects': [{'do': 'copy_group_prepare', 'mode': 'jelly', 'who': 'event'}]}
    return None


def prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, delayed, effects, values

    mode = e['mode']
    if mode == 'creators':
        original = values._object(plan, ctx, e['who'])
        excluded = original[0].controller if original else None
        context.bind_players(ctx, e['as'], [p for p in effects._players(plan, ctx, 'each_player') if p != excluded])
        return True
    if mode == 'stats':
        from app.rules import sba
        infos = context.infos(plan, ctx, e['who'].removeprefix('ref:'))
        ctx.setdefault('copy_group_totals', {})[e['as']] = [sum(sba.power(c, ch) or 0 for c, ch in infos),
                                                          sum(sba.toughness(c, ch) or 0 for c, ch in infos)]
        return True
    if mode == 'anomaly':
        p, t = ctx.get('copy_group_totals', {}).get(e['with'].removeprefix('ref:'), [0, 0])
        at = int(ctx.get('next') or 0)
        ctx['effects'][at:at] = [copy(e['who'], power=str(p), toughness=str(t),
                                     set_types=['Creature'], set_creature_types=['Eldrazi'], set_colors=[])]
        return True
    if mode == 'jelly':
        n = values.evaluate(plan, ctx, {'counters': '+1/+1', 'on': e['who']})
        if n < 2:
            return True
        from app.rules.triggers import _source_ref
        original_ref = _source_ref(plan, ctx.get('source_object') or '')
        if original_ref is None:
            return True
        delayed.create_plain(plan, ctx['controller'], ctx.get('source_card') or '', ctx.get('source_object') or '',
                             ctx.get('name') or 'Split', {'kind': 'step', 'step': 'end', 'whose': 'next'},
                             [{'do': 'bind_refs', 'refs': {'jelly_original': {'kind': 'objects', 'objects': [original_ref.model_dump(mode='json')]}}},
                              copy('ref:jelly_original', enter_counters=[{'counter': '+1/+1', 'n': n // 2}])])
        return True
    if mode == 'court':
        if not effects._cards(plan, ctx, e['who']):
            return True
        monarch = plan.state.table.monarch == ctx['controller']
        action = copy(e['who']) if monarch else {'do': 'become_copy', 'who': 'self', 'with': e['who'], 'excepts': e['excepts']}
        tail = [{'do': 'optional_payment', 'who': 'you', 'cost': '', 'bind': 'court_copy', 'ask': 'copy the chosen permanent'},
                {'do': 'only_if', 'cond': {'succeeded': 'court_copy'}, 'skip': 1}, action]
        at = int(ctx.get('next') or 0)
        ctx['effects'][at:at] = tail
        return True
    raise AssertionError(mode)


PRIMITIVES = {'copy_group_prepare': prepare}
