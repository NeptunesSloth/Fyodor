"""Resolution-selected native copy sources and exact created-token groups."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

CREATED = 'copy_source_created'
CHOSEN = 'copy_source_chosen'


def copy(who: str, **excepts: Any) -> dict[str, Any]:
    return {'do': 'token_copy', 'who': who, 'n': 1, 'as': CREATED,
            **({'excepts': [excepts]} if excepts else {})}


def cleanup(what: str = 'exile', *, whose: str = 'next', ring: bool = False) -> dict[str, Any]:
    return {'do': 'schedule_copy_cleanup', 'what': what, 'whose': whose, 'unless_ring': ring, 'ref': 'ref:' + CREATED}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    t = re.sub(r'\s+', ' ', body).strip().rstrip('.').lower()
    linked = re.fullmatch(r"create a token that's a copy of a card exiled with ~(?:, except (?P<exception>.+))?(?P<tail>\. it gains haste\. exile it at the beginning of the next end step)?", body.strip().rstrip('.'), re.IGNORECASE)
    if linked:
        from app.rules import copying

        ex = copying.parse_excepts(linked['exception'])
        if ex is None:
            return None
        chosen = {'do': 'return_choice', 'who': 'exiled_with', 'to': 'choose', 'n': 1, 'upto': False,
                  'random': False, 'label': 'card to copy', 'as': CHOSEN}
        effects = [chosen, copy('ref:' + CHOSEN, **ex.model_dump(mode='json', exclude_defaults=True))]
        if linked['tail']:
            effects += [{'do': 'grant', 'who': 'ref:' + CREATED, 'keywords': ['haste'], 'duration': 'permanent'}, cleanup()]
        return effects, None, False
    if t == "create a token that's a copy of target creature card exiled with ~, except it's a 6/6 green dinosaur creature with trample":
        sel = selectors.parse('creature card')
        assert sel is not None
        return [copy('target', power='6', toughness='6', set_colors=['G'], set_types=['Creature'], set_creature_types=['Dinosaur'], add_text=['Trample'])], 'exiled_with:' + sel.key(), False
    if t == "choose up to two target creatures you don't control. for each of those creatures, create a token that's a copy of that creature. those tokens gain haste. exile them at the beginning of the next end step":
        parsed = scripts.parse_effects("Create a token that's a copy of each of up to two target creatures you don't control. Those tokens gain haste. Exile them at the beginning of the next end step.")
        if parsed is None:
            return None
        effects, targets, optional = parsed
        return [{**effect, **({'creation_each': True} if effect.get('do') == 'token_copy' else {})}
                for effect in effects], targets, optional
    if t == "flip a coin until you lose a flip. for each flip you won, create a token that's a copy of that creature. those tokens gain haste. exile them at the beginning of the next end step":
        return ([{'do': 'coin_flip', 'until_lose': True}, {**copy('event'), 'n': {'coin_flips': 'won'}, 'creation_each_count': True},
                 {'do': 'grant', 'who': 'ref:' + CREATED, 'keywords': ['haste'], 'duration': 'permanent'}, cleanup()], None, False)
    if t == "create a token that's a copy of that creature except it's an artifact in addition to its other types. then exile all other tokens created with ~":
        return [copy('event', add_types=['Artifact']), {'do': 'other_copy_tokens', 'mode': 'source', 'ref': 'ref:' + CREATED}], None, False
    if t == "exile target creature card from a graveyard that was put there this turn. create a token that's a copy of it, except it's a nightmare in addition to its other types. then exile all other nightmare tokens you control":
        found = scripts.parse_effects('Exile target creature card from a graveyard that was put there from anywhere this turn.')
        if found is None:
            return None
        sel = selectors.parse('Nightmare creature token you control')
        assert sel is not None
        return ([{**found[0][0], 'as': 'copy_source_exiled'}, copy('ref:copy_source_exiled', add_subtypes=['Nightmare']),
                 {'do': 'other_copy_tokens', 'mode': 'selector', 'sel': sel.key(), 'ref': 'ref:' + CREATED}], found[1], False)
    if t == "exile target creature card from your graveyard. create a tapped and attacking token that's a copy of that card, except it's a 3/3 black wraith with menace. at the beginning of the next end step, exile that token unless ~ is your ring-bearer":
        found = scripts.parse_effects('Exile target creature card from your graveyard.')
        assert found is not None
        return ([{**found[0][0], 'as': 'copy_source_exiled'},
                 {**copy('ref:copy_source_exiled', power='3', toughness='3', set_colors=['B'], set_creature_types=['Wraith'], add_text=['Menace']),
                  'tapped': True, 'attacking': True}, cleanup(ring=True)], found[1], False)
    if t == "for each opponent, create a tapped token that's a copy of the exiled card attacking that opponent. at the beginning of your next end step, sacrifice those tokens":
        return [{**copy('exiled_with'), 'tapped': True, 'each_opponent_attack': True}, cleanup('sacrifice', whose='you')], None, False
    if t == "each opponent creates a token that's a copy of it. the tokens are goaded for the rest of the game":
        return [{**copy('event'), 'creator': 'each_opponent', 'each_creator': True},
                {'do': 'permanent_copy_goad', 'who': 'ref:' + CREATED}], None, False
    if t == "exile target creature card from your graveyard. create a token that's a copy of that card, except it's 1/1, it's a spirit in addition to its other types, and it has flying. create a black zombie creature token with power equal to that card's power and toughness equal to that card's toughness":
        found = scripts.parse_effects('Exile target creature card from your graveyard.')
        assert found is not None
        return ([{**found[0][0], 'as': 'copy_source_exiled'},
                 copy('ref:copy_source_exiled', power='1', toughness='1', add_subtypes=['Spirit'], add_text=['Flying']),
                 {'do': 'copy_card_zombie', 'who': 'ref:copy_source_exiled'}], found[1], False)
    return None


def other_tokens(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, exiled_with, selectors

    created = context.objects(plan, ctx, e['ref'].removeprefix('ref:'))
    if e['mode'] == 'source':
        key = exiled_with.link_key(ctx)
        old = plan.rules.created_with.get(key, [])
        candidates = [oid.rsplit('.', 1)[0] for oid in old if (card := plan.state.cards.get(oid.rsplit('.', 1)[0])) is not None
                      and card.zone.endswith(':battlefield') and plan.oid(card) == oid]
        plan.rules.created_with[key] = [plan.oid(c) for c in created]
    else:
        candidates = selectors.candidates(plan, selectors.from_key(e['sel']), ctx['controller'], ctx.get('source_card'))
    context.bind_objects(plan, ctx, 'other_copy_tokens', [c for c in candidates if c not in created])
    return effects.exile(plan, ctx, {'do': 'exile', 'who': 'ref:other_copy_tokens'})


def schedule(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, delayed

    name = e['ref'].removeprefix('ref:')
    refs = context.refs(ctx).get(name)
    if refs:
        delayed.create_plain(plan, ctx['controller'], ctx.get('source_card') or '', ctx.get('source_object') or '',
                             ctx.get('name') or 'Token copy', {'kind': 'step', 'step': e.get('step', 'end'), 'whose': e.get('whose', 'next')},
                             [{'do': 'bind_refs', 'refs': {CREATED: refs}},
                              {'do': 'copy_group_cleanup', 'who': 'ref:' + CREATED, 'what': e['what'],
                               'unless_ring': bool(e.get('unless_ring')), 'source_object': ctx.get('source_object')}])
    return True


def clean_group(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    if e.get('unless_ring') and plan.rules.ring_bearers.get(ctx['controller']) == e.get('source_object'):
        return True
    return effects.PRIMITIVES[e['what']](plan, ctx, e)


PRIMITIVES = {'other_copy_tokens': other_tokens, 'schedule_copy_cleanup': schedule, 'copy_group_cleanup': clean_group}


def definition(text: str, kind: str) -> dict[str, Any] | None:
    from app.rules import events

    t = re.sub(r'\s+', ' ', text).strip().rstrip('.').lower()
    if kind == 'triggered' and t == "whenever you cast a spell that targets only a single artifact or creature you control, create a token that's a copy of that artifact or creature, except it's not legendary":
        cond = events.parse_condition('you cast a spell that targets only a single artifact or creature you control')
        assert cond is not None
        return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'optional': False, 'target': None,
                'effects': [{'do': 'select_copy_spell_target', 'original': True}, copy('ref:' + CHOSEN, remove_supertypes=['Legendary'])]}
    if kind == 'triggered' and t == "whenever you cast an instant or sorcery spell, if it targets one or more other permanents you control, create a token that's a copy of one of those permanents":
        cond = events.parse_condition('you cast an instant or sorcery spell that targets one or more other permanents you control')
        assert cond is not None
        return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'optional': False, 'target': None,
                'if': {'copy_spell_targets': cond['targets']},
                'effects': [{'do': 'select_copy_spell_target', 'selector': cond['targets']}, copy('ref:' + CHOSEN)]}
    if kind == 'triggered' and t == "whenever a nontoken creature dies, you may exile that card. if you do, return each other card exiled with ~ to its owner's graveyard":
        cond = events.parse_condition('a nontoken creature dies')
        assert cond is not None
        return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'optional': True, 'target': None,
                'accumulating_link': True, 'effects': [{'do': 'exile', 'who': 'event.new', 'as': 'vat_new', 'link': True},
                    {'do': 'replace_vat_pool', 'who': 'exiled_with', 'ref': 'ref:vat_new'}]}
    return None


def replace_vat_pool(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, exiled_with

    newest = [c for c in context.objects(plan, ctx, e['ref'].removeprefix('ref:'))
              if plan.state.cards[c].zone.endswith(':exile')]
    if not newest:
        return True
    other = [c for c in exiled_with.cards(plan, ctx) if c not in newest]
    context.bind_objects(plan, ctx, 'vat_other', other)
    return effects.return_card(plan, ctx, {'who': 'ref:vat_other', 'to': 'graveyard'})


PRIMITIVES['replace_vat_pool'] = replace_vat_pool


def permanent_goad(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, keyword_actions, layers

    cards = effects._cards(plan, ctx, e['who'])
    if cards:
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer='6', source=ctx.get('source_object'),
                          controller=ctx['controller'], duration='permanent', imposes=(keyword_actions.GOADED + ctx['controller'],),
                          label='Goaded for the rest of the game')
    return True


def zombie(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, values

    p = values._signed_stat(plan, ctx, {'power': e['who']})
    t = values._signed_stat(plan, ctx, {'toughness': e['who']})
    return effects.create_token(plan, ctx, {'do': 'create_token', 'who': 'you', 'n': 1,
        'token': {'name': 'Zombie', 'power': str(p), 'toughness': str(t), 'colors': ['B'], 'type_line': 'Token Creature — Zombie'}})


PRIMITIVES.update({'permanent_copy_goad': permanent_goad, 'copy_card_zombie': zombie})


def bind_spell_targets(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """601.2c, 115.9b: the objects the cast spell targets (still where they were), as one named group (``e["as"]``) for "those
    creatures" / "those permanents". The primitive of waves 110D (spell_permanents110d) and 110E (spell_targets110e)."""
    from app.rules import context

    refs = spell_targets(plan, ctx, e["selector"])
    context.refs(ctx)[e["as"]] = {"kind": "objects", "objects": [r.model_dump(mode="json") for r in refs]}
    return True


def spell_targets(plan: Plan, ctx: dict[str, Any], selector: str | None = None) -> list[Any]:
    from app.game.rules_state import ObjectRef
    from app.rules import context, selectors, triggers

    event = ctx.get('event') or {}
    refs = [ObjectRef.model_validate(r) for r in event.get('cast_targets') or []]
    if selector and event.get('objects'):
        spell_ref = ObjectRef.model_validate(event['objects'][0])
        spell = context._same(plan, spell_ref)
        memory = plan.rules.stack_lki.get(spell_ref.object_id)
        entry = plan.rules.stack.get(spell.id) if spell is not None and spell.zone == 'stack' else memory.entry if memory else None
        if entry is not None:
            refs = [r for target in entry.targets if target.object_id and (r := triggers._source_ref(plan, target.object_id)) is not None]
    distinct = list({ref.object_id: ref for ref in refs}.values())
    if not selector:
        return distinct
    sel = selectors.from_key(selector)
    out = []
    for ref in distinct:
        card = context._same(plan, ref)
        if card is None or not card.zone.endswith(':battlefield'):
            continue  # CR115.9b: departed targets are ignored, not read through LKI.
        if sel.other and ref.object_id == ctx.get('source_object'):
            continue
        if selectors.matches(plan, selectors.replace(sel, other=False), card, plan.ch(card), ctx['controller'], None):
            out.append(ref)
    return out


def select_spell_target(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    refs = spell_targets(plan, ctx, e.get('selector'))
    if len(refs) <= 1:
        context.refs(ctx)[CHOSEN] = {'kind': 'objects', 'objects': [ref.model_dump(mode='json') for ref in refs]}
        return True
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Choose a targeted permanent to copy',
           options=[DecisionOption(id=ref.card, label=plan.state.cards[ref.card].name or 'Permanent', card_id=ref.card) for ref in refs],
           resume={'step': 'copy_spell_target', 'ctx': ctx, 'refs': [ref.model_dump(mode='json') for ref in refs]})
    return False


def resume_spell_target(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx = d.resume['ctx']
    context.refs(ctx)[CHOSEN] = {'kind': 'objects', 'objects': [ref for ref in d.resume['refs'] if ref['card'] in chosen]}
    effects.continue_effects(plan, ctx)


PRIMITIVES['select_copy_spell_target'] = select_spell_target
RESUME = {'copy_spell_target': resume_spell_target}
