"""Source-preserving, immediately resolving triggered mana bodies (CR605.4a)."""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo
    from app.rules.mana import ManaAbility
    from app.rules.plan import Plan


def definition(text: str) -> dict[str, Any] | None:
    from app.rules import selectors

    text = text.replace('~ deals 1 damage to the player.', 'this enchantment deals 1 damage to the player.').replace('if ~ is tapped,', 'if this creature is tapped,')
    if text == ('Whenever an Island is tapped for mana, its controller may add an additional {U}. '
                'If that Island is snow, its controller may add an additional {U}{U} instead. '
                'Spend this mana only to pay cumulative upkeep costs.'):
        from app.rules import mana as M

        return {'kind': 'triggered', 'trigger': 'tap_for_mana', 'who': 'any',
                'sel': selectors.Selector(types=('Land',), subtypes=('Island',)).key(),
                'extra': [['U']], 'staged': True, 'snow_extra': True,
                'only': M.spend_kind('Spend this mana only to pay cumulative upkeep costs'),
                'effects': [], 'optional': False, 'target': None}
    if text == ("Whenever a player taps a snow land for mana, that player adds one mana of any type that land produced. "
                "That land doesn't untap during its controller's next untap step."):
        return {'kind': 'triggered', 'trigger': 'tap_for_mana', 'who': 'any',
                'sel': selectors.Selector(types=('Land',), supertypes=('Snow',)).key(),
                'extra': 'produced', 'staged': True, 'body': 'winter_stay85',
                'effects': [], 'optional': False, 'target': None}
    if text == 'Whenever a player taps a Mountain, Forest, or Plains for mana, that player adds one mana of any type that land produced.':
        sel = selectors.Selector(types=('Land',), subtypes=('Mountain', 'Forest', 'Plains'))
        return {'kind': 'triggered', 'trigger': 'tap_for_mana', 'who': 'any', 'sel': sel.key(),
                'extra': 'produced', 'staged': True, 'effects': [], 'optional': False, 'target': None}
    if text == 'Whenever a player taps a land for mana, that player adds one mana of any type that land produced, and this enchantment deals 1 damage to the player.':
        body = 'producer_damage'
        tapped = False
    elif text == 'Whenever a player taps a land for mana, if this creature is tapped, that player adds one mana of any type that land produced. Then that land deals 1 damage to that player.':
        body = 'land_damage'
        tapped = True
    else:
        return None
    return {'kind': 'triggered', 'trigger': 'tap_for_mana', 'who': 'any',
            'sel': selectors.Selector(types=('Land',)).key(), 'extra': 'produced',
            'staged': True, 'source_tapped': tapped, 'body': body,
            'effects': [], 'optional': False, 'target': None}


def prepare(state: GameState, card: CardInstance, info: CardInfo,
            found: list[tuple[int, ManaAbility]]) -> list[tuple[int, ManaAbility]]:
    """Unpredictable native bodies never promise aggregate mana to AUTO."""
    from app.rules import attached_mana, tap_mana

    triggers = [d for owner, d, source in tap_mana._triggers(state, info)
                if tap_mana._applies(state, info, card, owner, d, source)]
    attached = bool(attached_mana._extras(state, card, info))
    if not triggers and not attached:
        return found
    return [(i, replace(ab, native_body=True, chooses=True,
                        immediate_effects=({'do': 'staged_base_mana', 'options': [list(o) for o in ab.options]},
                                           *ab.immediate_effects)))
            if ab.tap and not ab.native_body and ab.reveal_hand is None and
               (not ab.generic_allowed or any(d.get('staged') for d in triggers)
                or bool(ab.extra_cost) or ab.sacrifice_self or ab.self_counter is not None
                or bool(ab.immediate_effects)) else (i, ab) for i, ab in found]


def base_mana(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import immediate_mana_resolutions
    from app.rules.plan import decide

    options = e['options']
    if len(options) == 1:
        immediate_mana_resolutions.produce_chosen(plan, ctx, ctx['controller'], options[0])
    else:
        decide(plan, player=ctx['controller'], kind='choose_one', prompt='Choose the mana to add',
               options=[DecisionOption(id=str(i), label=''.join('{'+s+'}' for s in o) or 'No mana') for i, o in enumerate(options)],
               resume={'step': 'staged_base_mana', 'ctx': ctx, 'options': options})
    return False


def resume_base(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import immediate_mana_resolutions

    ctx = d.resume['ctx']
    immediate_mana_resolutions.produce_chosen(plan, ctx, ctx['controller'], d.resume['options'][int(chosen[0])])


def frozen(plan: Plan, data: dict[str, Any], source: str | None, definition: dict[str, Any],
           owner: str, options: list[list[str]]) -> dict[str, Any] | None:
    card = plan.state.cards.get(source or '')
    if definition.get('source_tapped') and (card is None or not card.tapped):
        return None
    return {'snow_extra': bool(definition.get('snow_extra')), 'only': definition.get('only') if definition.get('snow_extra') else None,
            'same_name_count': bool(definition.get('same_name_count')),
            'source': source, 'oid': definition.get('effect_source_object') or (plan.oid(card) if card else None), 'owner': owner,
            'name': plan.ch(card).name if card else 'Additional mana', 'options': options,
            'body': definition.get('body'), 'source_tapped': definition.get('source_tapped', False),
            'land': data['source'], 'land_oid': data['oid']}


def terminal(data: dict[str, Any], then: dict[str, Any]) -> dict[str, Any]:
    return {'do': 'staged_mana_extras', 'data': {'controller': data['controller'],
             'extras': copy.deepcopy(data['extras']), 'extras_then': then}}


def next_extra(plan: Plan, data: dict[str, Any]) -> None:
    from app.rules import replace as replacements
    from app.rules.plan import decide

    if not data['extras']:
        replacements.run_then(plan, data['extras_then'])
        return
    # APNAP: all triggered mana instances resolve before another player gets priority.
    # Only triggers controlled by the active player's nearest next controller may be chosen.
    apnap = plan.apnap()
    owners = [p for p in reversed(apnap) if any(x.get('owner', data['controller']) == p for x in data['extras'])]
    owner = owners[0] if owners else data['controller']
    choices = [i for i, x in enumerate(data['extras']) if x.get('owner', data['controller']) == owner]
    if len(choices) > 1:
        decide(plan, player=owner, kind='choose_one', prompt='Choose the next triggered mana ability to resolve',
               options=[DecisionOption(id=str(i), label=data['extras'][i].get('name', 'Additional mana')) for i in choices],
               resume={'step': 'staged_mana_order', 'data': data})
        return
    resolve_extra(plan, data, choices[0] if choices else 0)


def resolve_extra(plan: Plan, data: dict[str, Any], index: int) -> None:
    from app.rules.plan import decide

    extra = data['extras'].pop(index)
    card = plan.state.cards.get(extra.get('source') or '')
    if extra.get('source_tapped'):
        if card is not None and plan.oid(card) == extra.get('oid'):
            tapped = card.tapped
        else:
            snap = plan.rules.lki.get(extra.get('oid') or '')
            tapped = snap.tapped if snap is not None else False
        if not tapped:
            next_extra(plan, data)
            return
    options = extra['options']
    if extra.get('same_name_count'):
        land = plan.state.cards.get(extra['land']['id'])
        name: str | None
        if land is not None and plan.oid(land) == extra['land_oid']:
            name = plan.ch(land).name
        else:
            from app.rules.triggers import _snapshot_card

            snap = plan.rules.lki.get(extra['land_oid'])
            name = _snapshot_card(plan, snap)[1].name if snap is not None else None
        n = sum(c.controller == extra['owner'] and c.zone.endswith(':battlefield')
                and plan.oid(c) != extra['land_oid'] and plan.ch(c).is_land and plan.ch(c).name == name
                for c in plan.state.cards.values()) if name is not None else 0
        composition_extra(plan, data, extra, n, [])
        return
    if extra.get('snow_extra'):
        land = plan.state.cards.get(extra['land']['id'])
        if land is not None and plan.oid(land) == extra['land_oid']:
            snow = 'Snow' in plan.ch(land).supertypes
        else:
            from app.rules.triggers import _snapshot_card

            snap = plan.rules.lki.get(extra['land_oid'])
            snow = snap is not None and 'Snow' in _snapshot_card(plan, snap)[1].supertypes
        options = [[], ['U', 'U'] if snow else ['U']]
        extra['options'] = options
    if len(options) > 1:
        decide(plan, player=data['controller'], kind='choose_one', prompt='Choose the additional mana',
               options=[DecisionOption(id=str(i), label=''.join('{'+s+'}' for s in o) or 'No mana') for i, o in enumerate(options)],
               resume={'step': 'staged_mana_option', 'data': data, 'extra': extra})
        return
    add_extra(plan, data, extra, options[0])


def composition_extra(plan: Plan, data: dict[str, Any], extra: dict[str, Any], left: int, got: list[str]) -> None:
    from app.rules.plan import decide

    if left == 0:
        add_extra(plan, data, extra, got)
        return
    options = extra['options']
    if len(options) == 1:
        add_extra(plan, data, extra, got + options[0] * left)
        return
    decide(plan, player=data['controller'], kind='choose_one', prompt=f'Choose additional mana ({left} remaining)',
        options=[DecisionOption(id=str(i), label=''.join('{'+s+'}' for s in o)) for i, o in enumerate(options)],
        resume={'step': 'staged_mana_composition', 'data': data, 'extra': extra, 'left': left, 'got': got})


def resume_composition_extra(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    composition_extra(plan, r['data'], r['extra'], r['left'] - 1,
        r['got'] + r['extra']['options'][int(chosen[0])])


def add_extra(plan: Plan, data: dict[str, Any], extra: dict[str, Any], option: list[str]) -> None:
    from app.game.rules_state import emit
    from app.rules import effects, reveal_mana

    if option:
        source = plan.state.cards.get(extra.get('source') or '')
        ctx = {'source_card': extra.get('source'), 'source_object': extra.get('oid') or (plan.oid(source) if source else None),
               'only': extra.get('only')}
        reveal_mana._add(plan, data['controller'], option, ctx)
        emit(plan.state, 'mana_added', object_id=ctx['source_object'], card=ctx['source_card'],
             player=data['controller'], amount=len(option))
    if extra.get('body') == 'winter_stay85':
        ctx = {'kind': 'mana', 'controller': extra['owner'], 'source_card': extra.get('source'),
               'source_object': extra.get('oid'), 'name': extra['name'], 'next': 0, 'targets': [],
               'refs': {'winter_land85': {'kind': 'objects', 'objects': [
                   {'card': extra['land']['id'], 'object_id': extra['land_oid'], 'zone': 'battlefield'}]}},
               'effects': [{'do': 'stay_tapped', 'who': 'ref:winter_land85', 'during': 'controller'}],
               'body_done': {'do': 'staged_mana_extras', 'data': data}}
        effects.continue_effects(plan, ctx)
        return
    if extra.get('body'):
        source_card, source_oid = extra.get('source'), extra.get('oid')
        if extra['body'] == 'land_damage':
            source_card, source_oid = extra['land']['id'], extra['land_oid']
        ctx = {'kind': 'mana', 'controller': extra['owner'], 'source_card': source_card,
               'source_object': source_oid, 'name': extra['name'], 'next': 0, 'targets': [],
               'refs': {'trigger_damage_source': {'kind': 'objects', 'objects': [
                   {'card': source_card, 'object_id': source_oid, 'zone': 'battlefield'}]}},
               'effects': [{'do': 'damage', 'src': 'ref:trigger_damage_source',
                            'who': 'player:'+data['controller'], 'n': 1}],
               'body_done': {'do': 'staged_mana_extras', 'data': data}}
        effects.continue_effects(plan, ctx)
        return
    next_extra(plan, data)


def resume_order(plan: Plan, d: Any, chosen: list[str]) -> None:
    resolve_extra(plan, d.resume['data'], int(chosen[0]))


def resume_option(plan: Plan, d: Any, chosen: list[str]) -> None:
    extra = d.resume['extra']
    add_extra(plan, d.resume['data'], extra, extra['options'][int(chosen[0])])


def run_extras(plan: Plan, then: dict[str, Any]) -> None:
    next_extra(plan, then['data'])


PRIMITIVES = {'staged_base_mana': base_mana}
RESUME = {'staged_base_mana': resume_base, 'staged_mana_order': resume_order, 'staged_mana_option': resume_option}
RESUME['staged_mana_composition'] = resume_composition_extra

from app.rules import replace as _replace  # noqa: E402

_replace.THEN['staged_mana_extras'] = run_extras


def stack_definition(text: str) -> dict[str, Any] | None:
    from app.rules import selectors

    if text == ("Whenever you cast a creature spell, if {S} of any of that spell's colors was spent to cast it, "
                'that creature enters with an additional +1/+1 counter on it.'):
        return {'kind': 'triggered', 'trigger': 'event', 'optional': False, 'target': None,
                'cond': {'event': 'cast', 'subject': 'player', 'player': 'you', 'snow_matches_spell': True,
                         'spell': selectors.Selector(zones=('stack',), types=('Creature',)).key()},
                'effects': [{'do': 'snow_color_entry_counter'}]}
    return None


def snow_color_entry_counter(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import cast_riders, context

    for cid in context.objects(plan, ctx, context.EVENT):
        card = plan.state.cards[cid]
        record = plan.rules.payments.get(plan.oid(card))
        if card.zone == 'stack' and record is not None and any(
                (record.snow_spent or {}).get(color, 0) > 0 for color in plan.ch(card).colors):
            cast_riders.spell_rider(plan, ctx, {'who': 'event_spell', 'riders': [{'kind': 'counter'}]})
            break
    return True


PRIMITIVES['snow_color_entry_counter'] = snow_color_entry_counter


def card_definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == 'loyalty' and text == '+1: Add {R} or {G}. If that mana is spent on a creature spell, it gains riot.':
        import json

        from app.rules import mana_units

        base = scripts.define(replace(ability, text='+1: Add {R} or {G}.'), ch)
        rider = mana_units.rider('If that mana is spent on a creature spell, it gains riot.')
        if base is not None and rider is not None:
            base['effects'] = [*base['effects'], {'do': 'restrict_mana', 'only': None,
                                                'riders': [json.loads(rider)], 'note': 'Riot for a creature spell'}]
        return base
    if ability.kind == 'triggered' and text == ("At the beginning of each player's end step, put a charge counter on ~ "
                                               'for each untapped land that player controls.'):
        base = scripts.define(replace(ability, text="At the beginning of each player's end step, put a charge counter on ~."), ch)
        if base is not None:
            base['effects'] = [{'do': 'active_untapped_land_counters'}]
        return base
    if ability.kind == 'activated' and text == '{T}: Target opponent creates X Treasure tokens, where X is the number of Treasure tokens you created this turn.':
        base = scripts.define(replace(ability, text='{T}: Target opponent creates a Treasure token.'), ch)
        if base is not None:
            base['effects'] = [{'do': 'treasure_history_tokens', 'effects': base['effects']}]
        return base
    if ability.kind == 'triggered' and text == ('Whenever an opponent casts a spell or activates an ability, if mana from a Treasure was spent to cast it or activate it, '
                                               'put a +1/+1 counter on target creature, then draw a card.'):
        base = scripts.define(replace(ability, text='Whenever an opponent casts a spell, put a +1/+1 counter on target creature, then draw a card.'), ch)
        if base is not None:
            base['cond'] = {'event': 'either', 'subject': 'player', 'conds': [
                {'event': 'cast', 'subject': 'player', 'player': 'opponent', 'treasure_paid': True,
                 'spell': selectors.Selector(zones=('stack',)).key()},
                {'event': 'activate', 'subject': 'player', 'player': 'opponent', 'treasure_paid': True}]}
        return base
    return None


def treasure_history_tokens(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import history

    log = history.log_for(plan)
    n = sum(f.kind == 'token' and f.player == ctx['controller'] and 'Treasure' in f.subtypes for f in log.facts)
    effects = copy.deepcopy(e['effects'])
    for effect in effects:
        if effect.get('do') == 'create_token':
            effect['n'] = n
    ctx['effects'][ctx['next']:ctx['next']] = effects
    return True


PRIMITIVES['treasure_history_tokens'] = treasure_history_tokens


def active_untapped_land_counters(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    n = sum(c.controller == plan.active and c.zone.endswith(':battlefield') and not c.tapped and plan.ch(c).is_land
            for c in plan.state.cards.values())
    ctx['effects'][ctx['next']:ctx['next']] = [{'do': 'add_counters', 'who': 'self', 'kind': 'charge', 'n': n}]
    return True


PRIMITIVES['active_untapped_land_counters'] = active_untapped_land_counters


def rhystic_mana_payment(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, immediate_mana_resolutions, selectors

    if ctx.pop('_rhystic_waiting', False) and context.refs(ctx).get('rhystic_paid', {}).get('ok'):
        return True
    if '_rhystic_players' not in ctx:
        ctx['_rhystic_players'] = plan.apnap()
    todo = ctx['_rhystic_players']
    if todo:
        player = todo.pop(0)
        ctx['_rhystic_waiting'] = True
        ctx['effects'][ctx['next']:ctx['next']] = [
            {'do': 'optional_payment', 'who': 'player:'+player, 'cost': '{1}', 'bind': 'rhystic_paid'},
            {'do': 'rhystic_mana_payment'}]
        return True
    color = context.refs(ctx).get('cave_color', {}).get('value', '')
    symbol = selectors.COLORS.get(color.lower())
    if symbol is not None:
        immediate_mana_resolutions.produce_chosen(plan, ctx, ctx['controller'], [symbol])
        return False
    return True


PRIMITIVES['rhystic_mana_payment'] = rhystic_mana_payment
