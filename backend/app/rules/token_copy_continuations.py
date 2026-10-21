"""Native exact copy-source, entry-provenance, and attachment continuations."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(text: str, kind: str, index: int = 0) -> dict[str, Any] | None:
    t = re.sub(r'\s+', ' ', text).strip().rstrip('.').lower()
    if t == "you may have ~ enter as a copy of any creature on the battlefield, except if ~ was embalmed, the token has no mana cost, it's white, and it's a zombie in addition to its other types":
        return {'kind': 'replacement', 'replacement': 'enter_as_copy', 'optional': True, 'what': 'creature to copy', 'effects': [],
                'embalmed_except': {'no_mana_cost': True, 'set_colors': ['W'], 'add_subtypes': ['Zombie']}}
    if kind == 'triggered' and t == "whenever ~ evolves, create a token that's a copy of it":
        from app.rules.token_copy_sources import copy
        return {'kind': 'triggered', 'trigger': 'event', 'cond': {'event': 'evolved', 'subject': 'self'},
                'target': None, 'optional': False, 'effects': [copy('self')]}
    return other_definition(text, kind, index)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors
    from app.rules.token_copy_sources import cleanup, copy
    from app.rules.token_source_groups import key

    t = re.sub(r'\s+', ' ', body).strip().rstrip('.').lower()
    if t == 'choose target artifact card in a graveyard or artifact on the battlefield. create three tokens that are copies of it':
        sel = selectors.Selector(zones=('graveyard', 'battlefield'), either=(key('artifact card in a graveyard'), key('artifact'))).key()
        return [{**copy('target'), 'n': 3}], sel, False
    if t == "create a token that's a copy of target nonlegendary enchantment you control. it gains haste. if it's a saga, put up to three lore counters on it. sacrifice it at the beginning of your next end step":
        return [copy('target'), {'do': 'grant', 'who': 'ref:copy_source_created', 'keywords': ['haste'], 'duration': 'permanent'},
                action('saga_lore', who='ref:copy_source_created'), cleanup('sacrifice', whose='you')], key('nonlegendary enchantment you control'), False
    if t == 'add {w}{w}, {u}{u}, {b}{b}, {r}{r}, and {g}{g}. exile ~, then return it to the battlefield':
        return [{'do': 'add_mana', 'who': 'you', 'mana': list('WWUUBBRRGG')},
                {'do': 'exile', 'who': 'self', 'as': 'terra_front'},
                {'do': 'return_card', 'who': 'ref:terra_front', 'to': 'battlefield', 'under': 'owner'}], None, False
    if t == "create a token that's a copy of ~, except it has haste and loses soulbond. exile it at end of combat":
        return [copy('self', add_text=['Haste'], remove_keywords=['soulbond']), {**cleanup(), 'step': 'end_combat'}], None, False
    if t == "draw a card, then discard a card. if the discarded card was an artifact card, exile it from your graveyard. if you do, create a token that's a copy of it, except it's a 0/2 thopter artifact creature with flying in addition to its other types":
        return [{'do': 'draw', 'who': 'you', 'n': 1}, {'do': 'discard', 'who': 'you', 'n': 1, 'as': 'leonardo_discard'},
                action('leonardo', who='ref:leonardo_discard')], None, False
    if t == "draw a card and reveal it. remove a number of loyalty counters equal to that card's mana value from ~":
        return [action('jace_draw')], None, False
    if t == 'target player mills five cards, then puts each goblin card milled this way into their hand':
        return [{'do': 'mill', 'who': 'target', 'n': 5, 'as': 'goblin_milled'}, action('goblins', who='ref:goblin_milled')], 'player', False
    return None


def action(mode: str, **extra: Any) -> dict[str, Any]:
    return {'do': 'copy_continuation', 'mode': mode, 'as': 'copy_source_created', **extra}


def triggered(cond: Any, effects: list[dict[str, Any]], *, trigger: str = 'event', target: Any = None) -> dict[str, Any]:
    return {'kind': 'triggered', 'trigger': trigger, 'cond': cond, 'target': {'what': target} if target else None,
            'optional': False, 'effects': effects}


HOF_RETURN = "When this token leaves the battlefield, return the exiled card to its owner's graveyard."


def other_definition(text: str, kind: str, index: int = 0) -> dict[str, Any] | None:
    from app.rules import events
    from app.rules.token_copy_sources import cleanup, copy
    from app.rules.token_source_groups import key

    t = re.sub(r'\s+', ' ', text).strip().rstrip('.').lower()
    if kind != 'triggered':
        return None
    if t == 'at the beginning of the end step, sacrifice this token':
        return triggered(None, [{'do': 'sacrifice', 'who': 'self'}], trigger='step:end:each')
    if t == 'at the beginning of each player\'s upkeep, that player creates a 5/1 red elemental creature token named lightning rager. it has trample, haste, and "at the beginning of the end step, sacrifice this token."':
        return triggered(None, [{'do': 'create_token', 'who': 'event_player', 'n': 1, 'token': {
            'name': 'Lightning Rager', 'power': '5', 'toughness': '1', 'colors': ['R'],
            'type_line': 'Token Creature — Elemental',
            'text': 'Trample\nHaste\nAt the beginning of the end step, sacrifice this token.'}}], trigger='step:upkeep:each')
    if t == 'when ~ enters, if ~ was kicked, create a token that\'s a copy of ~, except it\'s not legendary and its starting loyalty is 1':
        cond = {'object': 'self', 'cast': {'kicked': True}}
        return {**triggered(None, [{'do': 'only_if', 'cond': cond, 'skip': 1}, copy('self', remove_supertypes=['Legendary'], loyalty=1)], trigger='enters_self'), 'if': cond}
    if t == "at the beginning of your upkeep, look at the top card of your library. you may reveal that card. if a creature card with mana value 6 or greater is revealed this way, transform ~":
        return triggered(None, [action('runo')], trigger='upkeep_you')
    if t == "whenever ~ attacks, create a tapped and attacking token that's a copy of another target attacking creature. if that creature is a kraken, leviathan, octopus, or serpent, create two of those tokens instead":
        return triggered(None, [action('krothuss', who='target')], trigger='attacks_self', target=key('other attacking creature'))
    if t == "whenever a modified creature you control attacks, double the number of each kind of counter on it. then for each nontoken permanent attached to it, create a token that's a copy of that permanent attached to that creature":
        return triggered(events.parse_condition('a modified creature you control attacks'),
                         [{'do': 'double_counters', 'who': 'event', 'kind': '*'}, action('attached', who='event')])
    if t == "whenever you attack, you may pay {2} and sacrifice an aura attached to ~. when you sacrifice an aura this way, for each other attacking creature you control, create a token that's a copy of that aura attached to that creature":
        return triggered(events.parse_condition('you attack'), [
            {'do': 'optional_payment', 'who': 'you', 'cost': '{2}, Sacrifice an Aura attached to ~', 'bind': 'dog_paid'},
            {'do': 'reflexive', 'cond': {'succeeded': 'dog_paid'}, 'lki': 'dog_paid',
             'ability': triggered(None, [action('attached_attackers', who='event')], trigger='reflexive')}])
    if t == "whenever ~ attacks, for each card you've discarded this turn, create a token that's a copy of ~, except the token isn't legendary. the tokens enter tapped and attacking. exile the tokens at the beginning of the next end step":
        return triggered(None, [action('laser'), cleanup()], trigger='attacks_self')
    if t == "whenever ~ attacks, you may blight 1. if you do, create a tapped and attacking token that's a copy of the blighted creature, except it has \"at the beginning of the end step, sacrifice this token.\"":
        return triggered(None, [{'do': 'optional_payment', 'who': 'you', 'cost': 'Blight 1', 'bind': 'grub_blight'},
            {'do': 'only_if', 'cond': {'succeeded': 'grub_blight'}, 'skip': 1},
            {**copy('ref:grub_blight', add_text=['At the beginning of the end step, sacrifice this token.']), 'tapped': True, 'attacking': True}], trigger='attacks_self')
    if t == "whenever ~ attacks while saddled, choose a nonlegendary creature that saddled it this turn and create a tapped and attacking token that's a copy of it. sacrifice that token at the beginning of the next end step. repeat this process once":
        return triggered(events.parse_condition('~ attacks while saddled'), [action('calamity'), action('calamity')])
    if t == "whenever another nontoken creature you control dies, exile it. if you do, create a token that's a copy of that creature, except it's a spirit in addition to its other types and it has \"when this token leaves the battlefield, return the exiled card to its owner's graveyard.\"":
        return triggered(events.parse_condition('another nontoken creature you control dies'), [
            {'do': 'exile', 'who': 'ref:event.new', 'from_zone': 'graveyard', 'as': 'hofri_exiled'},
            action('hofri', who='ref:hofri_exiled')])
    if t in ("when ~ leaves the battlefield, return the exiled card to its owner's graveyard", "when this token leaves the battlefield, return the exiled card to its owner's graveyard"):
        return triggered(events.parse_condition('~ leaves the battlefield'), [action('hofri_return', index=index)])
    return None


def evolve_outcome(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import emit

    if e['stage'] == 'mark':
        ctx['evolve_since_batch'] = plan.rules.batch
        return True
    oid = ctx.get('source_object')
    occurred = any(event.kind == 'counters' and not event.manual and event.batch > ctx.get('evolve_since_batch', plan.rules.batch)
                   and event.object_id == oid and event.counter == '+1/+1' and event.amount > 0 for event in plan.rules.events)
    card = plan.state.cards.get(ctx.get('source_card') or '')
    if occurred and card is not None and plan.oid(card) == oid:
        emit(plan.state, 'evolved', card=card.id, object_id=oid, player=card.controller, actor=ctx['controller'])
    return True


def queue(ctx: dict[str, Any], es: list[dict[str, Any]]) -> bool:
    at = int(ctx.get('next') or 0)
    ctx['effects'][at:at] = es
    return True


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, copying, effects, history, selectors
    from app.rules.token_copy_sources import cleanup, copy
    from app.rules.token_source_groups import key

    mode = e['mode']
    if mode == 'saga_lore':
        es: list[dict[str, Any]] = []
        ids = [cid for cid in effects._cards(plan, ctx, e['who']) if 'Saga' in plan.ch(plan.state.cards[cid]).subtypes]
        for i, cid in enumerate(ids):
            binding = f'copy_lore_{i}'
            context.bind_objects(plan, ctx, binding, [cid])
            es += [{'do': 'choose_value', 'who': 'you', 'what': 'number', 'options': ['0', '1', '2', '3']},
                   {'do': 'add_counters', 'who': 'ref:' + binding, 'kind': 'lore', 'n': {'chosen_n': 1}}]
        return queue(ctx, es)
    if mode == 'jace_draw':
        before = list(history.log_for(plan).drawn.get(ctx['controller'], []))
        return queue(ctx, [{'do': 'draw', 'who': 'you', 'n': 1}, action('jace_draw_finish', before=before)])
    if mode == 'jace_draw_finish':
        log = history.log_for(plan)
        me = ctx['controller']
        excluded = set(e['before']) | set(log.drawn_replaced.get(me, [])) | set(log.drawn_counted.get(me, []))
        ids = [oid.rsplit('.', 1)[0] for oid in log.drawn.get(me, []) if oid not in excluded
               and (card := plan.state.cards.get(oid.rsplit('.', 1)[0])) is not None
               and plan.oid(card) == oid and card.zone == me + ':hand']
        if not ids:
            return True
        plan.do({'type': 'reveal', 'card_ids': ids}, actor=me)
        n = sum(int(plan.ch(plan.state.cards[c]).mana_value) for c in ids)
        context.bind_objects(plan, ctx, 'jace_original_draw', ids)
        return queue(ctx, [{'do': 'remove_counters', 'who': 'self', 'kind': 'loyalty', 'n': n},
                           {'do': 'hide_revealed', 'refs': 'jace_original_draw', 'zone': 'hand'}])
    if mode == 'runo':
        if not plan.state.zones.get(ctx['controller'] + ':library'):
            return True
        return queue(ctx, [{'do': 'look_top', 'n': 1, 'player': 'you', 'as': 'runo_top'},
                           {'do': 'optional_payment', 'who': 'you', 'cost': '', 'bind': 'runo_reveal', 'ask': 'reveal the card you looked at', 'needs': 'ref:runo_top'},
                           {'do': 'only_if', 'cond': {'succeeded': 'runo_reveal'}, 'skip': 1}, action('runo_reveal', who='ref:runo_top')])
    if mode == 'runo_reveal':
        ids = [cid for cid in effects._cards(plan, ctx, e['who']) if plan.state.cards[cid].zone.endswith(':library')]
        if not ids:
            return True
        plan.do({'type': 'reveal', 'card_ids': ids}, actor=ctx['controller'])
        es = [{'do': 'transform', 'who': 'self'}] if any('Creature' in plan.ch(plan.state.cards[cid]).types and plan.ch(plan.state.cards[cid]).mana_value >= 6 for cid in ids) else []
        return queue(ctx, [*es, {'do': 'hide_revealed', 'refs': e['who'].removeprefix('ref:'), 'zone': 'library'}])
    if mode == 'krothuss':
        ids = effects._cards(plan, ctx, e['who'])
        n = 2 if any(plan.ch(plan.state.cards[cid]).subtypes & {'Kraken', 'Leviathan', 'Octopus', 'Serpent'} for cid in ids) else 1
        return queue(ctx, [{**copy(e['who']), 'n': n, 'as': e['as'], 'tapped': True, 'attacking': True}])
    if mode == 'laser':
        n = sum(f.amount for f in history.log_for(plan).facts if f.kind == 'discard' and f.player == ctx['controller'])
        return queue(ctx, [{**copy('self', remove_supertypes=['Legendary']), 'n': n, 'creation_each_count': True, 'as': e['as'], 'tapped': True, 'attacking': True}])
    if mode == 'calamity':
        from app.rules import crew_saddle
        ids = [cid for cid in selectors.candidates(plan, selectors.from_key(key('nonlegendary creature')), ctx['controller'])
               if crew_saddle.tapped_for(plan, 'saddle', plan.oid(plan.state.cards[cid]), ctx.get('source_object'))]
        context.bind_objects(plan, ctx, 'calamity_eligible', ids)
        return queue(ctx, [{'do': 'select_copy_originals', 'who': 'ref:calamity_eligible', 'n': 1, 'as': 'calamity_original'},
                           {**copy('ref:calamity_original'), 'as': e['as'], 'tapped': True, 'attacking': True},
                           {**cleanup('sacrifice'), 'ref': 'ref:' + e['as']}])
    if mode == 'leonardo':
        ids = [cid for cid in effects._cards(plan, ctx, e['who']) if plan.state.cards[cid].zone.endswith(':graveyard')
               and 'Artifact' in plan.ch(plan.state.cards[cid]).types]
        context.bind_objects(plan, ctx, 'leonardo_artifact', ids)
        return queue(ctx, [{'do': 'exile', 'who': 'ref:leonardo_artifact', 'as': 'leonardo_exiled'},
                           action('leonardo_copy', who='ref:leonardo_exiled', **{'as': e['as']})])
    if mode == 'leonardo_copy':
        ids = [cid for cid in effects._cards(plan, ctx, e['who']) if plan.state.cards[cid].zone.endswith(':exile')]
        context.bind_objects(plan, ctx, 'leonardo_copy', ids)
        return queue(ctx, [{**copy('ref:leonardo_copy', power='0', toughness='2', add_types=['Artifact', 'Creature'], add_subtypes=['Thopter'], add_text=['Flying']), 'as': e['as']}])
    if mode == 'goblins':
        ids = [cid for cid in effects._cards(plan, ctx, e['who']) if plan.state.cards[cid].zone.rsplit(':', 1)[-1] not in ('library', 'hand')
               and 'Goblin' in plan.ch(plan.state.cards[cid]).subtypes]
        context.bind_objects(plan, ctx, 'milled_goblins', ids)
        return queue(ctx, [{'do': 'return_card', 'who': 'ref:milled_goblins', 'to': 'hand', 'under': 'owner'}])
    if mode == 'hofri':
        ids = [cid for cid in effects._cards(plan, ctx, e['who']) if plan.state.cards[cid].zone.endswith(':exile')]
        if not ids:
            return True
        return queue(ctx, [{**copy('event', add_subtypes=['Spirit'], add_text=[HOF_RETURN]), 'as': e['as']},
                           action('hofri_bind', who='ref:' + e['as'], with_=e['who'])])
    if mode == 'hofri_bind':
        from app.rules import exiled_with, scripts
        linked = [plan.oid(cid) for cid in effects._cards(plan, ctx, e['with_']) if plan.state.cards[cid].zone.endswith(':exile')]
        for cid in effects._cards(plan, ctx, e['who']):
            card = plan.state.cards[cid]
            recipe = copying.copy_recipe_of(plan.rules, plan.oid(card))
            if recipe is None or not any(HOF_RETURN in ex.add_text for ex in recipe.excepts):
                continue
            indices = [i for i, d in scripts.definitions(plan.ch(card)).items() if any(x.get('do') == 'copy_continuation' and x.get('mode') == 'hofri_return' for x in d.get('effects', []))]
            if indices:
                scope = exiled_with.link_key({'source_object': plan.oid(card), 'borrowed_link_scope': f'hofri:{max(indices)}'})
                plan.rules.exiled_with[scope] = linked
        return True
    if mode == 'hofri_return':
        from app.rules import exiled_with
        if ctx.get('borrowed_link_scope'):
            return True
        scope = f'hofri:{e["index"]}'
        scoped = {**ctx, 'borrowed_link_scope': scope}
        ids = exiled_with.cards(plan, scoped)
        context.bind_objects(plan, ctx, 'hofri_return', ids)
        return queue(ctx, [{'do': 'return_card', 'who': 'ref:hofri_return', 'to': 'graveyard', 'under': 'owner'}])
    if mode in ('attached', 'attached_attackers'):
        return attached(plan, ctx, e)
    raise AssertionError(mode)


def attached(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, copying, populate, selectors
    from app.rules import replace as replacement
    from app.rules.token_source_groups import key

    saved = ctx.setdefault('copy_attachment_jobs', {})
    jobs = saved.get(e['as'])
    if jobs is None:
        jobs = []
        if e['mode'] == 'attached':
            hosts = context.objects(plan, ctx, e['who'].removeprefix('ref:')) if e['who'].startswith('ref:') else context.objects(plan, ctx, 'event')
            for host in hosts:
                href = context.ref_of(plan, host)
                if href is None:
                    continue
                for original in plan.state.cards.values():
                    if original.attached_to == host and not original.is_token and original.zone.endswith(':battlefield'):
                        jobs.append({'recipe': copying.recipe_of(plan, original).model_dump(mode='json'), 'host': href.model_dump(mode='json')})
        else:
            recipes = [recipe for recipe, _ in populate.left_battlefield(plan, ctx, e['who'], False) if not isinstance(recipe, str)]
            source = plan.state.cards.get(ctx.get('source_card') or '')
            source_id = source.id if source is not None and plan.oid(source) == ctx.get('source_object') else None
            hosts = selectors.candidates(plan, selectors.from_key(key('other attacking creature you control')), ctx['controller'], source_id)
            for recipe in recipes:
                for host in hosts:
                    href = context.ref_of(plan, host)
                    if href is not None:
                        jobs.append({'recipe': recipe.model_dump(mode='json'), 'host': href.model_dump(mode='json')})
        saved[e['as']] = jobs
    requests = []
    refs = []
    for job in jobs:
        recipe = copying.CopyRecipe.model_validate(job['recipe'])
        request = copying.token_copy_request(plan, ctx, ctx['controller'], recipe, 1)
        if request is not None:
            requests.append(request)
            refs.append(job['host'])
    made = replacement.create_token_batch(plan, requests, ctx=ctx, bind=None, then=replacement.rerun_then(ctx, e), attachment_refs=refs,
                                            creation_atoms=["attachment:" + str(i) for i in range(len(requests))])
    if made is None:
        return False
    context.bind_objects(plan, ctx, e['as'], made)
    return True


PRIMITIVES: dict[str, Any] = {'evolve_outcome': evolve_outcome, 'copy_continuation': run}
