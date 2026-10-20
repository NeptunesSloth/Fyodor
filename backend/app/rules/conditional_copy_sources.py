"""Resolution-selected originals for native lasting and temporary copy effects."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

ORIGINAL = 'become_original'
NO_LEGEND = 'resolved_no_legend_rule'


def key(text: str) -> str:
    from app.rules import selectors
    sel = selectors.parse(text)
    assert sel is not None, text
    return sel.key()


def become(who: str, original: str, *, duration: str = 'permanent', **excepts: Any) -> dict[str, Any]:
    return {'do': 'become_copy', 'who': who, 'with': original, 'duration': duration,
            **({'excepts': [excepts]} if excepts else {})}


def choose(sel: str | None = None, *, who: str | None = None, optional: bool = False) -> dict[str, Any]:
    return {'do': 'select_copy_originals', 'n': 1, 'as': ORIGINAL,
            **({'sel': key(sel)} if sel else {}), **({'who': who} if who else {}),
            **({'upto': True} if optional else {})}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import copying

    t = re.sub(r'\s+', ' ', body).strip().rstrip('.').lower()
    if t == 'choose a nonlegendary creature on the battlefield. target creature becomes a copy of that creature until end of turn':
        return [choose('nonlegendary creature'), become('target', 'ref:' + ORIGINAL, duration='end_of_turn')], key('creature'), False
    if t == 'choose a creature on the battlefield. any number of target creatures you control each become a copy of that creature until end of turn':
        return [choose('creature'), become('target', 'ref:' + ORIGINAL, duration='end_of_turn')], [{'what': key('creature you control'), 'min': 0, 'max': 250}], False
    if t == 'choose target artifact you control. each other artifact you control becomes a copy of that artifact until end of turn':
        return [{'do': 'conditional_copy_prepare', 'mode': 'other_artifacts', 'who': 'target'}], key('artifact you control'), False
    if t == '~ becomes a copy of target creature you control until end of turn. the "legend rule" doesn\'t apply to permanents you control this turn':
        return [become('self', 'target', duration='end_of_turn'), {'do': 'conditional_copy_prepare', 'mode': 'legend'}], key('creature you control'), False
    if t == '~ becomes a copy of the sacrificed creature, except it has this ability':
        return [{**become('self', 'cost:sacrificed', add_text=[copying.THIS_ABILITY]), 'last_known': True}], None, False
    if t == 'that creature becomes a copy of ~':
        return [{**become('event', 'self'), 'last_known': True}], None, False
    if t == 'you may have ~ become a copy of a creature card exiled with it until end of turn':
        return [choose(who='exiled_with:' + key('creature card'), optional=True),
                become('self', 'ref:' + ORIGINAL, duration='end_of_turn')], None, False
    return None


def definition(text: str, kind: str) -> dict[str, Any] | None:
    from app.rules import copying, events, selectors

    if kind != 'triggered':
        return None
    t = re.sub(r'\s+', ' ', text).strip().rstrip('.').lower()
    if t == "at the beginning of combat on your turn, you may have ~ become a copy of another target creature you control until end of turn, except its name is ~. if you do, ~ and that creature each get +2/+0 and gain haste until end of turn and attack this turn if able":
        return triggered('step:begin_combat:you', [{'do': 'conditional_copy_prepare', 'mode': 'gogo', 'who': 'self', 'with': 'target',
                                                  'excepts': [{'name': copying.NAME_MARKER}]}], key('other creature you control'))
    if t == "at the beginning of combat on your turn, put a +1/+1 counter on ~ and tap target creature an opponent controls. then you may have ~ become a copy of that creature, except its name is ~ and it has vigilance and this ability":
        return triggered('step:begin_combat:you', [{'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': 1},
            {'do': 'tap', 'who': 'target'}, {'do': 'conditional_copy_prepare', 'mode': 'optional', 'who': 'self', 'with': 'target',
              'excepts': [{'name': copying.NAME_MARKER, 'add_text': ['Vigilance', copying.THIS_ABILITY]}]}], key('creature an opponent controls'))
    if t == "at the beginning of your first main phase, until your next turn, ~ becomes a copy of up to one target creature on the battlefield or creature card in a graveyard, except ~'s name is ~ and he's a legendary human mercenary villain creature":
        sel = selectors.Selector(zones=('battlefield', 'graveyard'), either=(key('creature'), key('creature card in a graveyard'))).key()
        return {'kind': 'triggered', 'trigger': 'step:main1:you', 'optional': False, 'target': None,
                'targets': [{'what': sel, 'min': 0, 'max': 1}], 'effects': [become('self', 'target', duration='next_turn',
                    name=copying.NAME_MARKER, add_supertypes=['Legendary'], set_types=['Creature'], set_creature_types=['Human', 'Mercenary', 'Villain'])]}
    if t == "whenever ~ attacks, put a flood counter on another target creature or land. if it's a creature, it becomes a copy of ~. if it's a land, it becomes an island in addition to its other types":
        return triggered('attacks_self', [{'do': 'add_counters', 'who': 'target', 'kind': 'flood', 'n': 1},
            {'do': 'only_if', 'cond': {'object': 'target', 'is': key('creature')}, 'skip': 1},
            {**become('target', 'self'), 'last_known': True},
            {'do': 'only_if', 'cond': {'object': 'target', 'is': key('land')}, 'skip': 1},
            {'do': 'become', 'who': 'target', 'types': [], 'duration': 'permanent', 'land_types': ['Island'], 'retain': True}], key('other creature or land'))
    if t == 'at the beginning of combat on your turn, ~ explores. then you may have it become a copy of another creature you control until end of turn':
        return triggered('step:begin_combat:you', [{'do': 'explore', 'who': 'self'},
            choose('other creature you control', optional=True), become('self', 'ref:' + ORIGINAL, duration='end_of_turn')])
    if t == 'whenever you sacrifice a clue, you may have ~ become a copy of a creature card exiled with it until end of turn':
        return {'kind': 'triggered', 'trigger': 'event', 'cond': events.parse_condition('you sacrifice a Clue'),
                'optional': False, 'target': None, 'effects': [choose(who='exiled_with:' + key('creature card'), optional=True),
                    become('self', 'ref:' + ORIGINAL, duration='end_of_turn')]}
    if t == 'at the beginning of each combat, you may reveal the top card of your library. if you reveal a creature card this way, ~ becomes a copy of that card until end of turn, except it has flying':
        return triggered('step:begin_combat:each', [{'do': 'conditional_copy_prepare', 'mode': 'drifter'}])
    if t == 'at the beginning of your upkeep, each player mills three cards. you may exile a creature card from among the cards milled this way. if you do, ~ becomes a copy of that card, except it has this ability':
        return triggered('upkeep_you', [{'do': 'mill', 'who': 'each_player', 'n': 3, 'as': 'copy_milled'},
            {**choose(who='ref:copy_milled', optional=True), 'filter': key('creature card in a graveyard')},
            {'do': 'exile', 'who': 'ref:' + ORIGINAL, 'as': 'copy_exiled'},
            become('self', 'ref:copy_exiled', add_text=[copying.THIS_ABILITY])])
    if t == 'whenever ~ attacks or blocks, target opponent reveals cards from the top of their library until they reveal a creature card. ~ becomes a copy of that card until end of turn. then that player puts all cards revealed this way on the bottom of their library in a random order':
        cond = events.parse_condition('~ attacks or blocks')
        until = selectors.Selector(zones=(), card=True, types=('Creature',)).key()
        return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'optional': False,
                'target': {'what': 'opponent'}, 'effects': [
                    {'do': 'reveal_outcome_top', 'n': 0, 'player': 'target', 'until': until, 'reveal': True, 'exact_look': True},
                    {'do': 'conditional_copy_prepare', 'mode': 'revealed'}, {'do': 'rest_looked', 'to': 'bottom_random', 'viewer': 'target'}]}
    if t == 'whenever one or more cards leave your graveyard, put a +1/+1 counter on ~, then you may have ~ become a copy of an artifact or creature card from among those cards until end of turn':
        return {'kind': 'triggered', 'trigger': 'event', 'cond': events.parse_condition('one or more cards leave your graveyard'),
                'optional': False, 'target': None, 'effects': [{'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': 1},
                    {**choose(who='event.new', optional=True), 'filter': selectors.Selector(zones=(), card=True, types=('Artifact', 'Creature')).key()},
                    become('self', 'ref:' + ORIGINAL, duration='end_of_turn')]}
    return None


def triggered(trigger: str, effects: list[dict[str, Any]], target: Any = None) -> dict[str, Any]:
    return {'kind': 'triggered', 'trigger': trigger, 'optional': False, 'target': {'what': target} if target else None, 'effects': effects}


def prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, copying, effects, layers

    mode = e['mode']
    if mode == 'legend':
        layers.add_effect(plan, affected=[], layer='6', source=ctx.get('source_object'), controller=ctx['controller'],
                          duration='end_of_turn', imposes=(NO_LEGEND,), label='The legend rule does not apply this turn')
        return True
    if mode == 'drifter':
        if not plan.state.zones.get(ctx['controller'] + ':library'):
            return True
        tail = [{'do': 'optional_payment', 'who': 'you', 'cost': '', 'bind': 'copy_reveal', 'ask': 'reveal the top card'},
                {'do': 'only_if', 'cond': {'succeeded': 'copy_reveal'}, 'skip': 2},
                {'do': 'reveal_outcome_top', 'n': 1, 'player': 'you', 'reveal': True, 'exact_look': True},
                {'do': 'conditional_copy_prepare', 'mode': 'revealed', 'flying': True}]
        at = int(ctx.get('next') or 0)
        ctx['effects'][at:at] = tail
        return True
    if mode == 'revealed':
        ids = effects._looked(plan, ctx)[1]
        found = ids[0] if e.get('flying') and ids else ctx.get('found')
        if not isinstance(found, str) or found not in ids or not plan.ch(plan.state.cards[found]).is_creature:
            return True
        context.bind_objects(plan, ctx, 'copy_revealed', [found])
        return copying.become_copy(plan, ctx, become('self', 'ref:copy_revealed', duration='end_of_turn',
            **({'add_text': ['Flying']} if e.get('flying') else {})))
    if mode == 'other_artifacts':
        original = effects._cards(plan, ctx, e['who'])
        if not original:
            return True
        from app.rules import selectors
        group = selectors.candidates(plan, selectors.from_key(key('artifact you control')), ctx['controller'], ctx.get('source_card'))
        recipe = copying.recipe_of(plan, plan.state.cards[original[0]])
        copying.add_copy_effect(plan, [plan.oid(c) for c in group if c not in original], recipe, ctx['controller'], duration='end_of_turn')
        return True
    if mode in ('optional', 'gogo'):
        subjects = [c for c in effects._cards(plan, ctx, e['who']) if plan.state.cards[c].zone.endswith(':battlefield')]
        original = effects._cards(plan, ctx, e['with'])
        if not subjects or not original:
            return True
        action = {**become(e['who'], e['with'], duration='end_of_turn' if mode == 'gogo' else e.get('duration', 'permanent')),
                  'excepts': e.get('excepts') or []}
        tail = [{'do': 'optional_payment', 'who': 'you', 'cost': '', 'bind': 'choose_become', 'ask': 'become a copy'},
                {'do': 'only_if', 'cond': {'succeeded': 'choose_become'}, 'skip': 4 if mode == 'gogo' else 1}, action]
        if mode == 'gogo':
            context.bind_objects(plan, ctx, 'gogo_subjects', list(dict.fromkeys([*subjects, *original])))
            tail += [{'do': 'pump', 'who': 'ref:gogo_subjects', 'p': 2, 't': 0},
                     {'do': 'grant', 'who': 'ref:gogo_subjects', 'keywords': ['haste']},
                     {'do': 'restrict', 'who': 'ref:gogo_subjects', 'rules': ['must_attack']}]
        at = int(ctx.get('next') or 0)
        ctx['effects'][at:at] = tail
        return True
    raise AssertionError(mode)


PRIMITIVES = {'conditional_copy_prepare': prepare}
