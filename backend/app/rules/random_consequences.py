"""Printed random result vectors feed native effects with closed result ranges."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    text = ' '.join(body.split())
    text = text[:1].upper() + text[1:]
    if text == 'Flip a coin. If you win the flip, the next time that creature would deal combat damage this turn, it deals double that damage instead. If you lose the flip, the next time that creature would deal combat damage this turn, prevent that damage.':
        return ([{'do': 'coin_flip'}, {'do': 'random_source_damage', 'mode': 'double_or_prevent', 'who': 'event', 'combat': True}], None, False)
    if text == 'Flip a coin. If you lose the flip, the next time it would deal combat damage this turn, it deals that damage to you instead.':
        return ([{'do': 'coin_flip'}, {'do': 'random_source_damage', 'mode': 'redirect_loss', 'who': 'self', 'combat': True}], None, False)
    if text == 'For each blocking creature, flip a coin. If you win the flip, prevent all combat damage that would be dealt by that creature this turn.':
        return ([{'do': 'random_blocker_coins'}, {'do': 'random_source_damage', 'mode': 'blocking_wins'}], None, False)
    if text == 'Choose a source you control and flip a coin. If you win the flip, the next time that source would deal damage this turn, it deals double that damage instead. If you lose the flip, the next time it would deal damage this turn, prevent that damage.':
        return ([{'do': 'random_choose_source'}, {'do': 'coin_flip'}, {'do': 'random_source_damage', 'mode': 'double_or_prevent', 'who': 'chosen_source'}], None, False)
    if text == 'Choose target creature that\'s blocking equipped creature. Flip a coin. If you win the flip, exile the chosen creature. Otherwise, ~ deals 1 damage to it.':
        return ([{'do': 'coin_flip'}, {'do': 'random_consequence', 'kind': 'plasma'}],
                selectors.Selector(types=('Creature',), extras=('rel:blocking_live@host',)).key(), False)
    if text == 'Roll a d20. 1—9 | ~ deals 3 damage to each creature. 10—19 | You may choose a creature. ~ deals 3 damage to each creature not chosen this way. 20 | ~ deals 6 damage to each creature your opponents control.':
        return ([{'do': 'roll', 'sides': 20, 'count': 1}, {'do': 'random_consequence', 'kind': 'thunder'}], None, False)
    if text == "Roll a d20. 1—9 | Tap all creatures your opponents control. 10—19 | Tap all creatures your opponents control. Those creatures don't untap during their controllers' next untap steps. 20 | Tap all creatures your opponents control. Those creatures don't untap during their controllers' next untap steps. Until your next turn, creatures your opponents control enter tapped.":
        return ([{'do': 'roll', 'sides': 20, 'count': 1}, {'do': 'random_consequence', 'kind': 'cone'}], None, False)
    if text == 'Choose up to two target permanent cards in your graveyard. Roll a d20 and add the total mana value of those cards. 1—14 | Return those cards to your hand. 15+ | Return those cards to your hand. You gain life equal to their total mana value.':
        return ([{'do': 'random_consequence', 'kind': 'song_prepare'}],
                [{'what': selectors.Selector(card=True, types=('Artifact', 'Battle', 'Creature', 'Enchantment', 'Land', 'Planeswalker'), zones=('graveyard',), zone_owner='you').key(), 'min': 0, 'max': 2}], False)
    if text == 'Roll a d20 and add the number of creature cards in your graveyard that were put there from the battlefield this turn. 1—14 | Return all creature cards in your graveyard that were put there from the battlefield this turn to your hand. 15+ | Return those cards from your graveyard to the battlefield.':
        return ([{'do': 'random_consequence', 'kind': 'revivify_prepare'}], None, False)
    if text == 'Roll a d20 for each player being attacked and ignore all but the highest roll. 1—9 | ~ deals damage equal to its power to you. 10—19 | ~ deals damage equal to its power to defending player. 20 | ~ deals damage equal to its power to each opponent.':
        return ([{'do': 'random_consequence', 'kind': 'mastiff_roll'}, {'do': 'random_consequence', 'kind': 'mastiff'}], None, False)
    if text == 'Each player sacrifices a nontoken creature of their choice. Roll a d20 and add the toughness of the creature you sacrificed this way. 1—14 | Return a creature card put into a graveyard this way to the battlefield under your control. 15+ | Return up to two creature cards put into graveyards this way to the battlefield under your control.':
        return ([{'do': 'edict', 'who': 'each_player', 'sel': selectors.Selector(types=('Creature',), token=False).key(), 'n': 1, 'label': 'nontoken creature', 'as': 'random_sacrificed'},
                 {'do': 'random_consequence', 'kind': 'danse_prepare', 'who': 'ref:random_sacrificed'}], None, False)
    if text == 'Choose target spell or ability with one or more targets. Roll a d20 and add the greatest power among creatures you control. 1—14 | You may choose new targets for that spell or ability. 15+ | You may choose new targets for that spell or ability. Then copy it. You may choose new targets for the copy.':
        return ([{'do': 'random_consequence', 'kind': 'wyll_prepare'}],
                selectors.Selector(zones=('stack',), ability='spell_or_ability', extras=('random_has_targets',)).key(), False)
    if text == "Flip a coin. If you win the flip, draw a card. If you lose the flip, counter target artifact spell you control that isn't the target of an ability from another creature named Goblin Artisans.":
        return ([{'do': 'coin_flip'}, {'do': 'random_consequence', 'kind': 'artisans'}],
                selectors.Selector(zones=('stack',), types=('Artifact',), controller='you', extras=('random_artisans_uncontested',)).key(), False)
    if text == 'Choose a creature you control and an opponent. Flip a coin. If you lose the flip, that opponent gains control of that creature.':
        return ([{'do': 'player_chooses', 'who': 'you', 'sel': selectors.Selector(types=('Creature',), controller='you').key(),
                  'n': 1, 'any': True, 'label': 'creature', 'as': 'random_risky_creature'},
                 {'do': 'choose_opponent', 'as': 'random_risky_opponent'}, {'do': 'coin_flip'},
                 {'do': 'random_consequence', 'kind': 'risky', 'who': 'ref:random_risky_creature', 'to': 'ref:random_risky_opponent'}], None, False)
    if text == "Exile target spell, then roll a d20 and add that spell's mana value. 1—14 | You may cast the exiled card for as long as it remains exiled, and you may spend mana as though it were mana of any color to cast that spell. 15+ | You may cast the exiled card without paying its mana cost for as long as it remains exiled.":
        return ([{'do': 'random_consequence', 'kind': 'gale_prepare'}], 'spell', False)
    if text == "Exile all nontoken creatures you control, then roll a d20. 1—9 | Return those cards to the battlefield under their owner's control at the beginning of the next end step. 10—20 | Return those cards to the battlefield under their owner's control, then exile them again. Return those cards to the battlefield under their owner's control at the beginning of the next end step.":
        return ([{'do': 'exile', 'who': selectors.Selector(types=('Creature',), token=False, controller='you').key(), 'as': 'random_acrobatics'},
                 {'do': 'roll', 'sides': 20, 'count': 1}, {'do': 'random_consequence', 'kind': 'acrobatics', 'who': 'ref:random_acrobatics'}], None, False)
    if text == 'Roll two d6 and choose one result. Destroy each creature with power greater than or equal to that result. Then create a number of 2/2 white Knight creature tokens with vigilance equal to the other result.':
        return ([{'do': 'roll', 'sides': 6, 'count': 2, 'choose': True}, {'do': 'random_consequence', 'kind': 'valiant'}], None, False)
    if text == 'Choose target instant or sorcery card in your graveyard, then roll a d20. 1—9 | You may put that card on top of your library. 10—20 | Return that card to your hand.':
        return ([{'do': 'roll', 'sides': 20, 'count': 1}, {'do': 'random_consequence', 'kind': 'aberrant'}],
                selectors.Selector(card=True, types=('Instant', 'Sorcery'), zones=('graveyard',), zone_owner='you').key(), False)
    if text == 'Roll X six-sided dice, where X is the number of Bobbleheads you control. Create a tapped Treasure token for each even result. If you rolled 6 exactly seven times, you win the game.':
        return ([{'do': 'random_consequence', 'kind': 'luck_roll'}, {'do': 'random_consequence', 'kind': 'luck'}], None, False)
    return None


def consequence(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import coin_recipes, effects, selectors

    kind = e['kind']
    steps: list[dict[str, Any]] = []
    if kind == 'acrobatics':
        from app.rules import delayed

        r = ctx.get('die', 0)
        if 1 <= r <= 9:
            steps = delayed.wrap_when([{'do': 'return_card', 'who': e['who'], 'to': 'battlefield', 'under': 'owner'}], {'kind': 'step', 'step': 'end', 'whose': 'next'})
        elif 10 <= r <= 20:
            steps = [{'do': 'return_card', 'who': e['who'], 'to': 'battlefield', 'under': 'owner', 'as': 'random_acro_first'},
                     {'do': 'random_consequence', 'kind': 'acrobatics_again', 'who': e['who']}]
    elif kind == 'acrobatics_again':
        cards = effects._cards(plan, ctx, 'ref:random_acro_first')
        unchanged = [cid for cid in effects._cards(plan, ctx, e['who']) if plan.state.cards[cid].zone.endswith(':exile')]
        effects._remember(plan, ctx, {'as': 'random_acro_unchanged'}, unchanged)
        returned = [cid for cid in cards if plan.state.cards[cid].zone.endswith(':battlefield')]
        effects._remember(plan, ctx, {'as': 'random_acro_returned'}, returned)
        steps = [{'do': 'exile', 'who': 'ref:random_acro_returned', 'as': 'random_acro_second'},
                 {'do': 'random_consequence', 'kind': 'acrobatics_schedule'}]
    elif kind == 'acrobatics_schedule':
        from app.rules import delayed

        cards = [cid for key in ('random_acro_unchanged', 'random_acro_second') for cid in effects._cards(plan, ctx, 'ref:' + key) if plan.state.cards[cid].zone.endswith(':exile')]
        effects._remember(plan, ctx, {'as': 'random_acro_delayed'}, list(dict.fromkeys(cards)))
        steps = delayed.wrap_when([{'do': 'return_card', 'who': 'ref:random_acro_delayed', 'to': 'battlefield', 'under': 'owner'}], {'kind': 'step', 'step': 'end', 'whose': 'next'})
    elif kind == 'gale_prepare':
        from app.rules import stack_interaction

        targets = effects._cards(plan, ctx, 'target')
        if targets:
            card = plan.state.cards[targets[0]]
            value = stack_interaction.mana_value(card, plan.ch(card))
            steps = [{'do': 'exile', 'who': 'target', 'as': 'random_gale_card'},
                     {'do': 'roll', 'sides': 20, 'count': 1, 'mod': {'op': '+', 'v': value}},
                     {'do': 'random_consequence', 'kind': 'gale_grant'}]
    elif kind == 'gale_grant':
        cards = [cid for cid in effects._cards(plan, ctx, 'ref:random_gale_card') if plan.state.cards[cid].zone.endswith(':exile') and not plan.state.cards[cid].token]
        effects._remember(plan, ctx, {'as': 'random_gale_exiled'}, cards)
        r = ctx.get('die', 0)
        if r >= 1 and cards:
            steps = [{'do': 'grant_play', 'who': 'ref:random_gale_exiled', 'play': False, 'cast': True,
                      'until': 'permanent', 'optional': True, **({'free': True} if r >= 15 else {'spend': 'color'})}]
    elif kind == 'risky':
        if not ctx.get('coin'):
            steps = [{'do': 'gain_control', 'who': e['who'], 'to': e['to']}]
    elif kind == 'artisans':
        steps = [{'do': 'draw', 'who': 'you', 'n': 1}] if ctx.get('coin') else [{'do': 'counter', 'who': 'target'}]
    elif kind == 'wyll_prepare':
        power = max([(plan.ch(c).pt or (0, 0))[0] for c in plan.state.cards.values()
                     if c.zone.endswith(':battlefield') and c.controller == ctx['controller'] and plan.ch(c).is_creature], default=0)
        steps = [{'do': 'roll', 'sides': 20, 'count': 1, 'mod': {'op': '+' if power >= 0 else '-', 'v': abs(power)}}, {'do': 'random_consequence', 'kind': 'wyll'}]
    elif kind == 'wyll':
        r = ctx.get('die', 0)
        if r >= 1:
            steps = [{'do': 'choose_new_targets', 'who': 'target'}]
            if r >= 15:
                steps += [{'do': 'copy_spell', 'who': 'target', 'hybrid': True}, {'do': 'copy_new_targets', 'optional': True}]
    elif kind == 'danse_prepare':
        from app.rules import context

        original = [(c, ch) for c, ch in context.infos(plan, ctx, e['who'][4:]) if c.controller == ctx['controller']]
        delta = (original[0][1].pt or (0, 0))[1] if original else 0
        cards = [cid for cid in effects._cards(plan, ctx, e['who'])
                 if plan.state.cards[cid].zone.endswith(':graveyard') and not plan.state.cards[cid].token and plan.ch(plan.state.cards[cid]).is_creature]
        effects._remember(plan, ctx, {'as': 'random_danse_pool'}, cards)
        steps = [{'do': 'roll', 'sides': 20, 'count': 1, 'mod': {'op': '+' if delta >= 0 else '-', 'v': abs(delta)}},
                 {'do': 'random_consequence', 'kind': 'danse_return'}]
    elif kind == 'danse_return':
        r = ctx.get('die', 0)
        if r >= 1:
            steps = [{'do': 'return_choice', 'who': 'ref:random_danse_pool', 'to': 'battlefield', 'under': 'you',
                      'n': 2 if r >= 15 else 1, 'upto': r >= 15, 'label': 'creature card'}]
    elif kind == 'mastiff_roll':
        players = {c.attacking.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield')
                   and c.attacking is not None and c.attacking.kind == 'player'}
        steps = [{'do': 'roll', 'sides': 20, 'count': len(players), 'keep_highest': True}]
    elif kind == 'mastiff':
        r = ctx.get('die', 0)
        who = 'you' if 1 <= r <= 9 else 'defending_player' if 10 <= r <= 19 else 'each_opponent' if r == 20 else None
        if who:
            steps = [{'do': 'damage', 'who': who, 'n': {'power': 'self'}}]
    elif kind in ('song_prepare', 'revivify_prepare'):
        from app.rules import stack_interaction

        if kind == 'song_prepare':
            cards = effects._cards(plan, ctx, 'target:0')
            delta = sum(stack_interaction.mana_value(None, plan.ch(plan.state.cards[c])) for c in cards)
        else:
            cards = [c.id for c in plan.state.cards.values() if c.zone == ctx['controller'] + ':graveyard'
                     and not c.token and plan.ch(c).is_creature and selectors.put_there_state(plan.state, c, 'battlefield')]
            delta = len(cards)
        effects._remember(plan, ctx, {'as': 'random_return'}, cards)
        ctx['random_return_value'] = delta
        steps = [{'do': 'roll', 'sides': 20, 'count': 1, 'mod': {'op': '+' if delta >= 0 else '-', 'v': abs(delta)}},
                 {'do': 'random_consequence', 'kind': 'song_return' if kind == 'song_prepare' else 'revivify_return'}]
    elif kind in ('song_return', 'revivify_return'):
        r = ctx.get('die', 0)
        if r >= 1:
            steps = [{'do': 'return_card', 'who': 'ref:random_return', 'to': 'battlefield' if kind == 'revivify_return' and r >= 15 else 'hand', 'under': 'you'}]
            if kind == 'song_return' and r >= 15:
                steps.append({'do': 'gain_life', 'who': 'you', 'n': ctx.get('random_return_value', 0)})
    elif kind == 'cone':
        from app.rules import replace

        r = ctx.get('die', 0)
        if 1 <= r <= 20:
            who = selectors.Selector(types=('Creature',), controller='opponent').key()
            steps = [{'do': 'tap', 'who': who, 'as': 'random_frozen'}]
            if r >= 10:
                steps.append({'do': 'stay_tapped', 'who': 'ref:random_frozen', 'during': 'controller'})
            if r == 20:
                replace.add_record(plan, event='enters_tapped', match={'selector': who}, op={'do': 'tap'},
                                   controller=ctx['controller'], source=ctx.get('source_object'), source_card=ctx.get('source_card'),
                                   label=ctx.get('name') or 'Entry tapped', until='next_turn', until_player=ctx['controller'])
    elif kind == 'thunder':
        r = ctx.get('die', 0)
        if 1 <= r <= 9:
            steps = [{'do': 'damage', 'who': 'each_creature', 'n': 3}]
        elif 10 <= r <= 19:
            steps = [{'do': 'player_chooses', 'who': 'you', 'sel': selectors.Selector(types=('Creature',)).key(),
                      'n': 1, 'upto': True, 'optional': True, 'any': True, 'label': 'creature', 'as': 'random_spared'},
                     {'do': 'random_consequence', 'kind': 'thunder_damage'}]
        elif r == 20:
            steps = [{'do': 'damage', 'who': selectors.Selector(types=('Creature',), controller='opponent').key(), 'n': 6}]
    elif kind == 'thunder_damage':
        exempt = effects._cards(plan, ctx, 'ref:random_spared')
        cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.ch(c).is_creature and c.id not in exempt]
        effects._remember(plan, ctx, {'as': 'random_damaged'}, cards)
        steps = [{'do': 'damage', 'who': 'ref:random_damaged', 'n': 3}]
    elif kind == 'six':
        r = ctx.get('die', 0)
        branches: dict[int, list[dict[str, Any]]] = {1: [{'do': 'become', 'who': 'target', 'types': [], 'duration': 'end_of_turn', 't': 1}],
                    2: [{'do': 'add_counters', 'who': 'target', 'kind': '-1/-1', 'n': 2}],
                    3: [{'do': 'damage', 'who': 'target', 'n': 3}, {'do': 'gain_life', 'who': 'you', 'n': 3}],
                    4: [{'do': 'pump', 'who': 'target', 'p': -4, 't': -4}],
                    5: [{'do': 'destroy', 'who': 'target'}], 6: [{'do': 'exile', 'who': 'target'}]}
        steps = branches.get(r, [])
    elif kind == 'plasma':
        steps = [{'do': 'exile', 'who': 'target'}] if ctx.get('coin') else [{'do': 'damage', 'who': 'target', 'n': 1}]
    elif kind == 'valiant':
        cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.ch(c).is_creature
                 and (plan.ch(c).pt or (0, 0))[0] >= ctx.get('die', 0)]
        effects._remember(plan, ctx, {'as': 'random_destroy'}, cards)
        steps = [{'do': 'destroy', 'who': 'ref:random_destroy'},
                 {'do': 'create_token', 'who': 'you', 'n': {'die': 'other'}, 'token': {
                     'name': 'Knight', 'type_line': 'Token Creature — Knight', 'power': '2', 'toughness': '2',
                     'colors': ['W'], 'text': 'Vigilance'}}]
    elif kind == 'aberrant':
        r = ctx.get('die', 0)
        if 1 <= r <= 9:
            from app.game.rules_state import DecisionOption
            from app.rules.plan import decide

            decide(plan, player=ctx['controller'], kind='choose_one', prompt='Put that card on top of your library?',
                   options=[DecisionOption(id='yes', label='Put it on top'), DecisionOption(id='no', label='Leave it')],
                   resume={'step': 'random_optional_top', 'ctx': ctx})
            return False
        elif 10 <= r <= 20:
            steps = [{'do': 'return_card', 'who': 'target', 'to': 'hand', 'under': 'you'}]
    elif kind == 'luck_roll':
        n = sum(c.zone.endswith(':battlefield') and c.controller == ctx['controller'] and 'Bobblehead' in plan.ch(c).subtypes
                for c in plan.state.cards.values())
        steps = [{'do': 'roll', 'sides': 6, 'count': n}]
    elif kind == 'luck':
        results = ctx.get('dice') or []
        n = sum(r % 2 == 0 for r in results)
        if n:
            from app.rules import scripts

            parsed = scripts.parse_effects('Create a tapped Treasure token.')
            assert parsed is not None
            steps = [{**parsed[0][0], 'n': n}]
        if results.count(6) == 7:
            steps.append({'do': 'win_game', 'who': 'you'})
    coin_recipes.insert(ctx, steps)
    return True


PRIMITIVES = {'random_consequence': consequence}


def resume_optional_top(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import coin_recipes, effects

    if len(chosen) != 1 or chosen[0] not in ('yes', 'no'):
        raise ActionError('Choose whether to put the card on top')
    ctx = d.resume['ctx']
    if chosen == ['yes']:
        coin_recipes.insert(ctx, [{'do': 'to_library', 'who': 'target', 'place': 'top'}])
    effects.continue_effects(plan, ctx)


RESUME = {'random_optional_top': resume_optional_top}


def blocker_coins(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import coin_outcomes

    coins = [{'player': ctx['controller'], 'object': plan.oid(c)} for c in plan.state.cards.values()
             if c.zone.endswith(':battlefield') and c.is_blocking and plan.ch(c).is_creature]
    return coin_outcomes.group(plan, ctx, coins)


def source_damage(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, replace

    mode = e['mode']
    groups: list[tuple[Any, dict[str, Any]]]
    if mode == 'blocking_wins':
        groups = [(outcome.get('object'), {'do': 'prevent_all', 'prevention': True})
                  for outcome in ctx.get('coin_outcomes') or [] if outcome.get('won')]
    else:
        if mode == 'redirect_loss' and ctx.get('coin'):
            return True
        oids = ctx.get('random_source_oids', []) if e['who'] == 'chosen_source' else [plan.oid(cid) for cid in effects._cards(plan, ctx, e['who'])]
        if e['who'] == 'self':
            oids = [ctx.get('source_object')]
        elif e['who'] == 'event':
            oids = [ref.object_id for ref in context._object_refs(ctx, context.EVENT, was=True)]
        op = ({'do': 'mul', 'n': 2} if ctx.get('coin') else {'do': 'prevent_all', 'prevention': True})
        if mode == 'redirect_loss':
            op = {'do': 'redirect', 'to': 'pid', 'pid': ctx['controller']}
        groups = [(oids, {**op, 'once': True, 'batch': True, **({'consume_unpreventable': True} if op.get('prevention') else {})})] if oids else []
    for oid, op in groups:
        if oid:
            replace.add_record(plan, event='damage', match={'source': {'oids': oid if isinstance(oid, list) else [oid]}, 'to': {}, **({'combat': True} if e.get('combat') or mode == 'blocking_wins' else {})},
                               op=op, controller=ctx['controller'], source=ctx.get('source_object'),
                               source_card=ctx.get('source_card'), label=ctx.get('name') or 'Coin result')
    return True


PRIMITIVES.update({'random_source_damage': source_damage, 'random_blocker_coins': blocker_coins})


def choose_source(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import source_shields
    from app.rules.plan import decide

    choices = source_shields.choosable(plan, {'choice_controller': ctx['controller']})
    if not choices:
        ctx['random_source_oids'] = []
        return True
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Choose a source you control',
           options=[DecisionOption(id=str(i), label=label, card_id=card) for i, (label, _, card) in enumerate(choices)],
           resume={'step': 'random_choose_source', 'ctx': ctx, 'choices': [oids for _, oids, _ in choices]})
    return False


def resume_choose_source(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    choices = d.resume['choices']
    if len(chosen) != 1 or chosen[0] not in [str(i) for i in range(len(choices))]:
        raise ActionError('Choose one source')
    ctx = d.resume['ctx']
    ctx['random_source_oids'] = choices[int(chosen[0])]
    effects.continue_effects(plan, ctx)


PRIMITIVES['random_choose_source'] = choose_source
RESUME['random_choose_source'] = resume_choose_source


def bind_activation(plan: Plan, card: Any, definition: dict[str, Any] | None) -> dict[str, Any] | None:
    import json

    if definition is None:
        return None
    text = json.dumps(definition)
    import re

    text = re.sub(r'random_artisans_uncontested(?!:)', 'random_artisans_uncontested:' + plan.oid(card), text)
    if 'rel:blocking_live@host' not in text:
        return json.loads(text)
    host = plan.state.cards.get(card.attached_to or '')
    bound = 'obj:' + plan.oid(host) if host is not None and host.zone.endswith(':battlefield') else 'none'
    return json.loads(text.replace('rel:blocking_live@host', 'rel:blocking_live@' + bound))


def merge_lines(ch: Any, out: dict[int, Any]) -> None:
    from app.rules import scripts

    lines = [ab for ab in ch.abilities if ab.kind == 'spell']
    expected = ['Choose target creature. Roll a six-sided die.', '1 — It has base toughness 1 until end of turn.',
                '2 — Put two -1/-1 counters on it.', '3 — ~ deals 3 damage to it and you gain 3 life.',
                '4 — It gets -4/-4 until end of turn.', '5 — Destroy it.', '6 — Exile it.']
    if len(lines) != len(expected):
        return
    # The ordinary self-text normalizer also preserves word-changing effects.
    if any(not ab.text.startswith(f'{i} — ') for i, ab in enumerate(lines[1:], 1)):
        return
    texts = [scripts.self_text(ab.text, ch.name) for ab in lines]
    normalized = [expected[0], *(text.split(' — ', 1)[1] for text in expected[1:])]
    if texts != normalized:
        return
    out[lines[0].index] = {'kind': 'spell', 'target': {'what': 'creature'},
                           'effects': [{'do': 'roll', 'sides': 6, 'count': 1}, {'do': 'random_consequence', 'kind': 'six'}]}
    for ab in lines[1:]:
        out[ab.index] = {'kind': 'spell', 'effects': [], 'target': None, 'merged_into': lines[0].index}
