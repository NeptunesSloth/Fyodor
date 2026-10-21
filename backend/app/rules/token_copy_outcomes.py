"""Exact original objects and actual outputs of native copy-token instructions."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules.token_copy_sources import CREATED, cleanup, copy
from app.rules.token_source_groups import key

if TYPE_CHECKING:
    from app.rules.plan import Plan

ORIGINAL = 'outcome_original'


def action(mode: str, **extra: Any) -> dict[str, Any]:
    refs = {'exiled_only': 'ref:' + ORIGINAL, 'destroyed': 'ref:' + ORIGINAL, 'haunting': 'ref:' + ORIGINAL, 'milled_black': 'ref:outcome_milled', 'ultron': 'ref:' + CREATED}
    return {'do': 'token_copy_outcome', 'mode': mode, 'as': CREATED, **({'who': refs[mode]} if mode in refs else {}), **extra}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import delayed, events, scripts, selectors

    t = re.sub(r'\s+', ' ', body).strip().rstrip('.').lower()
    if t == 'for each creature card in your graveyard, create a token that\'s a copy of it, except it\'s a 1/1 black and green insect':
        return [copy(key('creature card in your graveyard'), power='1', toughness='1', set_colors=['B', 'G'], set_creature_types=['Insect'])], None, False
    if t == 'create a 1/1 black and green insect creature token, then mill two cards. put a deathtouch counter on the token if a black card was milled this way':
        insect = scripts.parse_effects('Create a 1/1 black and green Insect creature token.')
        assert insect is not None
        return [{**insect[0][0], 'as': CREATED}, {'do': 'mill', 'who': 'you', 'n': 2, 'as': 'outcome_milled'}, action('milled_black', with_='ref:' + CREATED)], None, False
    if t == "whenever you cast a noncreature spell this turn, create a token that's a copy of a non-saga token you control":
        cond = events.parse_condition('you cast a noncreature spell')
        assert cond is not None
        es = [{'do': 'player_chooses', 'who': 'you', 'sel': key('non-Saga token you control'), 'n': 1, 'as': ORIGINAL}, copy('ref:' + ORIGINAL)]
        wrapped = delayed.wrap_when(es, {'kind': 'watch', 'cond': cond, 'text': 'you cast a noncreature spell'}, this_turn=True)
        wrapped[0]['once'] = False
        return wrapped, None, False
    if t == 'choose any number of artifact tokens and/or creature tokens you control with different names. for each of them, create a token that\'s a copy of it':
        sel = selectors.Selector(types=('Artifact', 'Creature'), token=True, controller='you').key()
        return [{'do': 'player_chooses', 'who': 'you', 'sel': sel, 'n': 250, 'upto': True, 'optional': True,
                 'distinct_names': True, 'as': ORIGINAL}, copy('ref:' + ORIGINAL)], None, False
    if t == 'choose target artifact creature you control. for each creature chosen this way, create a token that\'s a copy of it':
        return [copy('target')], key('artifact creature you control'), False
    if t == 'choose each artifact creature you control. for each creature chosen this way, create a token that\'s a copy of it':
        return [copy(key('artifact creature you control'))], None, False
    if t == 'exile x target creature cards from your graveyard. for each card exiled this way, create a token that\'s a copy of that card, except it\'s a 4/4 black zombie':
        return [{'do': 'exile', 'who': 'target', 'as': ORIGINAL}, action('exiled_only', excepts=[{'power': '4', 'toughness': '4', 'set_colors': ['B'], 'set_creature_types': ['Zombie']}])], [{'what': key('creature card in your graveyard'), 'min': 0, 'max': 250, 'x_count': 'exact'}], False
    if t == 'until your next turn, up to one target creature attacks a player each combat if able':
        return [{'do': 'until', 'duration': 'next_turn', 'n': 1}, {'do': 'restrict', 'who': 'target', 'rules': ['attack_player_any']}], [{'what': key('creature'), 'min': 0, 'max': 1}], False
    if t == "exile target creature or equipment card with mana value less than ~'s loyalty from your graveyard. create a token that's a copy of it. that token gains haste. exile it at the beginning of the next end step":
        sel = selectors.Selector(zones=('graveyard',), zone_owner='you', card=True, types=('Creature',), subtypes=('Equipment',), union=True).key()
        return [{'do': 'exile', 'who': 'target', 'as': ORIGINAL}, action('exiled_only', excepts=[]),
                {'do': 'grant', 'who': 'ref:' + CREATED, 'keywords': ['haste'], 'duration': 'permanent'}, cleanup()], 'source_loyalty_lt:' + sel, False
    if t == "destroy up to x target artifacts. if x is 5 or more, for each artifact destroyed this way, create a token that's a copy of it. those tokens gain haste. exile them at the beginning of the next end step":
        return [{'do': 'destroy', 'who': 'target', 'as': ORIGINAL}, action('destroyed'),
                {'do': 'grant', 'who': 'ref:' + CREATED, 'keywords': ['haste'], 'duration': 'permanent'}, cleanup()], [{'what': key('artifact'), 'min': 0, 'max': 250, 'x_count': 'up_to'}], False
    if t == "each player reveals the top card of their library. for each creature card revealed this way, create a token that's a copy of that card, except it's 1/1, it's a spirit in addition to its other types, and it has flying. if no creature cards were revealed this way, return ~ to its owner's hand":
        return [{'do': 'look_top', 'n': 1, 'player': 'each_player', 'reveal': True, 'exact_look': True, 'as': ORIGINAL},
                action('haunting'), action('hide_library', who='ref:' + ORIGINAL)], None, False
    if t == "target player draws a card, then exiles a card from their hand. if a creature card is exiled this way, that player creates a token that's a copy of that card":
        return [{'do': 'draw', 'who': 'target', 'n': 1}, action('artisan_hand')], 'player', False
    return None


def definition(text: str, kind: str) -> dict[str, Any] | None:
    from app.rules import events, selectors

    t = re.sub(r'\s+', ' ', text).strip().rstrip('.').lower()
    if kind == 'spell' and t == "exile each opponent's graveyard. when you do, choose up to one target creature card exiled this way. create a token that's a copy of that card, except it's an artifact and it loses all other card types":
        return {'kind': 'spell', 'target': None, 'accumulating_link': True, 'effects': [
            {'do': 'exile', 'who': selectors.Selector(zones=('graveyard',), zone_owner='opponent', card=True).key(), 'link': True, 'as': ORIGINAL},
            {'do': 'reflexive', 'cond': {'value': {'ref_count': ORIGINAL, 'this_way': 'exiled', 'of': None}, 'op': '>', 'n': 0}, 'ability': {
                'kind': 'triggered', 'trigger': 'reflexive', 'optional': False, 'target': None,
                'targets': [{'what': 'exiled_with:' + key('creature card'), 'min': 0, 'max': 1}],
                'effects': [copy('target', set_types=['Artifact'])]}}]}
    if kind != 'triggered':
        return None
    effects: list[dict[str, Any]]
    target: Any = None
    groups: list[dict[str, Any]] | None = None
    trigger = 'event'
    cond: Any = None
    if t == "whenever you attack a player, choose target nontoken creature that's attacking that player. create a token that's a copy of that creature, except it's 1/1. the token enters tapped and attacking that player. sacrifice it at the beginning of the next end step":
        cond = events.parse_condition('you attack a player')
        target = selectors.Selector(types=('Creature',), token=False, attacking_player='that_player').key()
        effects = [{**copy('target', power='1', toughness='1'), 'tapped': True, 'attacking': True, 'at': {'as': 'that'}}, cleanup('sacrifice')]
    elif t == "whenever a nontoken equipment you control enters, create a token that's a copy of it, except it has \"this equipment's equip abilities cost {2} less to activate.\" sacrifice that token at the beginning of the next upkeep":
        cond = events.parse_condition('a nontoken Equipment you control enters')
        effects = [copy('event', add_text=["This Equipment's equip abilities cost {2} less to activate."]), {**cleanup('sacrifice'), 'step': 'upkeep'}]
    elif t == "whenever another nontoken artifact you control enters, you may pay {2}. if you do, create a token that's a copy of it. if the token isn't a creature, it becomes a 2/2 robot villain creature in addition to its other types":
        cond = events.parse_condition('another nontoken artifact you control enters')
        effects = [{'do': 'optional_payment', 'who': 'you', 'cost': '{2}', 'bind': 'outcome_paid'},
                   {'do': 'only_if', 'cond': {'succeeded': 'outcome_paid'}, 'skip': 2}, copy('event'), action('ultron')]
    elif t == "whenever ~ attacks a player, for each other opponent, create a token that's a copy of ~ tapped and attacking that player, except it isn't legendary. sacrifice those tokens at end of combat":
        cond = events.parse_condition('~ attacks a player')
        effects = [action('shredder'), {**cleanup('sacrifice'), 'step': 'end_combat'}]
    elif t in ("whenever you sacrifice ~ or another artifact, you may pay {2}. if you do, at the beginning of the next end step, create a token that's a copy of that artifact", "whenever you sacrifice this artifact or another artifact, you may pay {2}. if you do, at the beginning of the next end step, create a token that's a copy of that artifact"):
        cond = events.parse_condition('you sacrifice ~ or another artifact')
        effects = [{'do': 'optional_payment', 'who': 'you', 'cost': '{2}', 'bind': 'outcome_paid'},
                   {'do': 'only_if', 'cond': {'succeeded': 'outcome_paid'}, 'skip': 1}, action('duplicator')]
    elif t == "whenever ~ attacks, exile up to one target assassin creature card from your graveyard with a memory counter on it. then for each creature card you own in exile with a memory counter on it, create a tapped and attacking token that's a copy of it. exile those tokens at end of combat":
        trigger = 'attacks_self'
        groups = [{'what': key('Assassin creature card in your graveyard'), 'min': 0, 'max': 1}]
        effects = [{'do': 'exile', 'who': 'target', 'as': ORIGINAL}, action('memory_exiled', who='ref:' + ORIGINAL),
                   {**copy(selectors.Selector(zones=('exile',), card=True, owner='you', types=('Creature',), extras=('counter:memory',)).key()), 'tapped': True, 'attacking': True},
                   {**cleanup(), 'step': 'end_combat'}]
    elif t == 'when ~ leaves the battlefield, exile all tokens created with it at the beginning of the next end step':
        cond = events.parse_condition('~ leaves the battlefield')
        effects = [action('artisan_schedule')]
    elif t == "when you cast this spell, create a token that's a copy of it, except it isn't legendary":
        trigger = 'cast_self'
        effects = [action('osgood')]
    else:
        return None
    result: dict[str, Any] = {'kind': 'triggered', 'trigger': trigger, 'target': {'what': target} if target else None,
              'optional': False, 'effects': effects}
    if cond is not None:
        result['cond'] = cond
    if groups is not None:
        result['targets'] = groups
    return result


def insert(ctx: dict[str, Any], es: list[dict[str, Any]]) -> None:
    at = int(ctx.get('next') or 0)
    ctx['effects'][at:at] = es


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, copying, delayed, effects

    mode = e['mode']
    if mode == 'memory_exiled':
        ids = [cid for cid in effects._cards(plan, ctx, e['who']) if plan.state.cards[cid].zone.endswith(':exile')]
        context.bind_objects(plan, ctx, 'outcome_memory', ids)
        insert(ctx, [{'do': 'add_counters', 'who': 'ref:outcome_memory', 'kind': 'memory', 'n': 1}])
        return True
    if mode == 'hide_library':
        return effects.hide_revealed(plan, ctx, {'refs': e['who'].removeprefix('ref:'), 'zone': 'library'})
    if mode == 'ultron':
        ids = [cid for cid in effects._cards(plan, ctx, e['who']) if 'Creature' not in plan.ch(plan.state.cards[cid]).types]
        context.bind_objects(plan, ctx, 'outcome_noncreatures', ids)
        return effects.become(plan, ctx, {'do': 'become', 'who': 'ref:outcome_noncreatures', 'types': ['Creature'], 'retain': True,
                                        'creature_types': ['Robot', 'Villain'], 'p': 2, 't': 2, 'duration': 'permanent'})
    if mode in ('exiled_only', 'destroyed'):
        from app.rules import populate
        from app.rules.values import evaluate
        if mode == 'destroyed' and evaluate(plan, ctx, {'x': 1}) < 5:
            return True
        if mode == 'destroyed':
            refs = populate.gone_refs(plan, ctx, e['who'])
            context.refs(ctx)['outcome_destroyed'] = {'kind': 'objects', 'objects': [r.model_dump(mode='json') for r in refs]}
            original = 'ref:outcome_destroyed'
        else:
            ids = [cid for cid in effects._cards(plan, ctx, e['who']) if plan.state.cards[cid].zone.endswith(':exile')]
            context.bind_objects(plan, ctx, 'outcome_exiled', ids)
            original = 'ref:outcome_exiled'
        insert(ctx, [{**copy(original), 'as': e['as'], 'excepts': e.get('excepts', [])}])
        return True
    if mode == 'haunting':
        ids = [cid for cid in effects._cards(plan, ctx, e['who']) if 'Creature' in plan.ch(plan.state.cards[cid]).types]
        context.bind_objects(plan, ctx, 'outcome_creatures', ids)
        if not ids:
            return effects.bounce(plan, ctx, {'do': 'bounce', 'who': 'self_stack'})
        insert(ctx, [{**copy('ref:outcome_creatures', power='1', toughness='1', add_subtypes=['Spirit'], add_text=['Flying']), 'public_card_zones': ['library'], 'as': e['as']}])
        return True
    if mode == 'milled_black':
        ids = effects._cards(plan, ctx, e['who'])
        if any(c.zone.rsplit(':', 1)[-1] not in ('library', 'hand') and 'B' in plan.ch(c).colors
               for cid in ids if (c := plan.state.cards.get(cid)) is not None):
            insert(ctx, [{'do': 'add_counters', 'who': e['with_'], 'kind': 'deathtouch', 'n': 1}])
        return True
    if mode == 'osgood':
        from app.game.rules_state import CopyExcept
        from app.rules import mana_source_cast
        from app.rules import replace as replacement
        recipe, problem = mana_source_cast.spell_recipe(plan, ctx)
        if problem:
            raise AssertionError(problem)
        if recipe is None:
            return True
        request = copying.token_copy_request(plan, ctx, ctx['controller'], copying.with_excepts(recipe, [CopyExcept(remove_supertypes=['Legendary'])]), 1)
        if request is None:
            return True
        made = replacement.create_token_batch(plan, [request], ctx=ctx, bind=None, then=replacement.rerun_then(ctx, e))
        if made is None:
            return False
        effects._remember(plan, ctx, e, made)
        return True
    if mode == 'duplicator':
        from app.rules import populate
        refs = populate.gone_refs(plan, ctx, 'event')
        # The trigger's original battlefield object, even if its new card moved again.
        if not refs and ctx.get('event'):
            from app.game.rules_state import TriggerEvent
            refs = TriggerEvent.model_validate(ctx['event']).objects
        if refs:
            delayed.create_plain(plan, ctx['controller'], ctx.get('source_card') or '', ctx.get('source_object') or '', ctx.get('name') or '',
                                 {'kind': 'step', 'step': 'end', 'whose': 'next'},
                                 [{'do': 'bind_refs', 'refs': {ORIGINAL: {'kind': 'objects', 'objects': [r.model_dump(mode='json') for r in refs]}}}, copy('ref:' + ORIGINAL)])
        return True
    if mode == 'shredder':
        # Build the same native request batch as token_copy, restricting its recipient list.
        from app.game.rules_state import CopyExcept
        from app.rules import populate
        from app.rules import replace as replacement
        recipients = [p for p in effects._players(plan, ctx, 'each_opponent') if p != (ctx.get('event') or {}).get('defended')]
        source = effects._cards(plan, ctx, 'self')
        recipe = copying.recipe_of(plan, plan.state.cards[source[0]]) if source else None
        if recipe is None:
            recipe = next((r for r, _ in populate.left_battlefield(plan, ctx, 'self', False) if not isinstance(r, str)), None)
        if recipe is None:
            return True
        recipe = copying.with_excepts(recipe, [CopyExcept(remove_supertypes=['Legendary'])])
        request = copying.token_copy_request(plan, ctx, ctx['controller'], recipe, 1, tapped=True)
        made = replacement.create_token_batch(plan, [request for _ in recipients] if request else [], ctx=ctx, bind=None,
                                               then=replacement.rerun_then(ctx, e), recipient_refs=recipients,
                                               creation_atoms=["opponent:" + pid for pid in recipients])
        if made is None:
            return False
        effects._remember(plan, ctx, e, made)
        return True
    if mode == 'artisan_hand':
        players = effects._players(plan, ctx, 'target')
        if not players:
            return True
        context.bind_players(ctx, 'outcome_artisan_player', players)
        insert(ctx, [{'do': 'player_chooses', 'who': 'ref:outcome_artisan_player', 'sel': key('card in your hand'), 'zone': 'hand', 'n': 1, 'as': ORIGINAL},
                     {'do': 'exile', 'who': 'ref:' + ORIGINAL, 'as': 'artisan_exiled'}, action('artisan_copy')])
        return True
    if mode == 'artisan_copy':
        ids = [cid for cid in effects._cards(plan, ctx, 'ref:artisan_exiled') if plan.state.cards[cid].zone.endswith(':exile') and 'Creature' in plan.ch(plan.state.cards[cid]).types]
        context.bind_objects(plan, ctx, 'artisan_creature', ids)
        insert(ctx, [{**copy('ref:artisan_creature'), 'creator': 'ref:outcome_artisan_player'},
                     {'do': 'name_relation', 'kind': 'record_created_tokens', 'who': 'ref:' + CREATED}])
        return True
    if mode == 'artisan_schedule':
        delayed.create_plain(plan, ctx['controller'], ctx.get('source_card') or '', ctx.get('source_object') or '', ctx.get('name') or '',
                             {'kind': 'step', 'step': 'end', 'whose': 'next'}, [action('artisan_cleanup', borrowed_link_scope=ctx.get('borrowed_link_scope'))])
        return True
    if mode == 'artisan_cleanup':
        from app.rules import exiled_with
        key_ = exiled_with.link_key({**ctx, 'borrowed_link_scope': e.get('borrowed_link_scope')})
        saved = plan.rules.created_with.get(key_, [])
        ids = [oid.rsplit('.', 1)[0] for oid in saved if (card := plan.state.cards.get(oid.rsplit('.', 1)[0])) is not None
               and card.zone.endswith(':battlefield') and plan.oid(card) == oid]
        context.bind_objects(plan, ctx, 'artisan_cleanup', ids)
        return effects.exile(plan, ctx, {'do': 'exile', 'who': 'ref:artisan_cleanup'})
    raise AssertionError(mode)


PRIMITIVES = {'token_copy_outcome': run}
