"""Coin outcome vectors feed ordinary native effects and exact saved repeats."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def _native(text: str) -> list[dict[str, Any]]:
    from app.rules import scripts

    parsed = scripts.parse_effects(text)
    if parsed is None:
        raise ValueError('Unsupported native coin consequence: ' + text)
    return parsed[0]


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import delayed, selectors

    text = ' '.join(body.split())
    text = text[:1].upper() + text[1:]
    fixed: dict[str, tuple[list[dict[str, Any]], Any]] = {
        'Flip five coins. Take an extra turn after this one for each coin that comes up heads.':
            ([{'do': 'coin_flip', 'n': 5, 'face': True}, {'do': 'coin_result', 'kind': 'extra'}], None),
        'Flip five coins. Target opponent skips their next X turns, where X is the number of coins that came up heads.':
            ([{'do': 'coin_flip', 'n': 5, 'face': True}, {'do': 'coin_result', 'kind': 'skip', 'who': 'target'}], 'opponent'),
        "Flip a coin for each creature that isn't a Demon, Devil, or Imp. Destroy each creature whose coin comes up tails.":
            ([{'do': 'coin_group_recipe', 'kind': 'rakdos'}, {'do': 'coin_result', 'kind': 'destroy_tails'}], None),
        'That player flips a coin. If they lose the flip, counter that spell.':
            ([{'do': 'coin_group_recipe', 'kind': 'event_player'}, {'do': 'coin_result', 'kind': 'counter'}], None),
        "Flip three coins. For each flip you win, create a 1/1 red Goblin creature token that's tapped and attacking.":
            ([{'do': 'coin_flip', 'n': 3}, {'do': 'create_attacking', 'who': 'you', 'n': {'coin_flips': 'won'}, 'token': {'name': 'Goblin', 'power': '1', 'toughness': '1', 'colors': ['R'], 'type_line': 'Token Creature — Goblin', 'text': ''}, 'tapped': True}], None),
        'Flip a coin for each opponent you have. For each flip you win, draw a card. For each flip you lose, ~ deals 3 damage to that player.':
            ([{'do': 'coin_group_recipe', 'kind': 'opponents'}, {'do': 'coin_result', 'kind': 'mutalith'}], None),
        'Each player flips a coin. Each player whose coin comes up tails sacrifices a creature of their choice.':
            ([{'do': 'coin_group_recipe', 'kind': 'players', 'face': True}, {'do': 'coin_result', 'kind': 'edict_tails'}], None),
        'Flip two coins. If both coins come up heads, ~ gains double strike until end of turn. If both coins come up tails, ~ gains menace until end of turn.':
            ([{'do': 'coin_flip', 'n': 2, 'face': True}, {'do': 'coin_result', 'kind': 'giant'}], None),
        'Flip a coin. If you win the flip, each blocking creature is sacrificed by its controller. If you lose the flip, each blocked creature is sacrificed by its controller.':
            ([{'do': 'coin_flip'}, {'do': 'coin_result', 'kind': 'combat_sacrifice'}], None),
        'Flip a coin until you lose a flip. Put a +1/+1 counter on ~ for each flip you won.':
            ([{'do': 'coin_flip', 'until_lose': True}, {'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': {'coin_flips': 'won'}}], None),
        'Flip a coin at end of combat. If you lose the flip, an opponent gains control of ~.':
            (delayed.wrap_when([{'do': 'coin_flip'}, {'do': 'coin_result', 'kind': 'control', 'who': 'self'}], delayed.END_OF_COMBAT), None),
        "If ~ is on the battlefield, flip a coin. If you win the flip, exile ~ and return it to the battlefield under its owner's control at the beginning of the next end step. If you lose the flip, sacrifice it.":
            ([{'do': 'coin_sliver'}], None),
    }
    if text in fixed:
        es, targets = fixed[text]
        return es, targets, False
    if text == 'Target creature you control with toughness 2 or less gains flying until end of turn. Flip a coin at the beginning of the next end step. If you lose the flip, sacrifice that creature.':
        return ([{'do': 'grant', 'who': 'target', 'keywords': ['flying']},
                 *delayed.wrap_when([{'do': 'coin_flip'}, {'do': 'coin_result', 'kind': 'sacrifice', 'who': 'target'}], {'kind': 'step', 'step': 'end', 'whose': 'next'})],
                selectors.Selector(types=('Creature',), controller='you', compare=(('toughness', '<=', 2),)).key(), False)
    if text == 'You and target opponent each flip a coin. ~ deals 1 damage to each player whose coin comes up tails. Repeat this process until both players\' coins come up heads on the same flip.':
        return ([{'do': 'coin_clash'}], 'opponent', False)
    if text == 'Flip a coin until you lose a flip or choose to stop flipping. If you lose a flip, ~ has no effect. If you win one or more flips, ~ deals 3 damage to target creature. If you win two or more flips, ~ deals 6 damage to each opponent. If you win three or more flips, draw nine cards and untap all lands you control.':
        return ([{'do': 'coin_flip'}, {'do': 'coin_gambit_next'}], 'creature', False)
    if text == 'Flip a coin. If you win the flip, destroy target creature an opponent controls. If you lose the flip, destroy target creature you control unless you pay {3} and repeat this process.':
        groups = [{'what': selectors.Selector(types=('Creature',), controller=p).key(), 'min': 1, 'max': 1} for p in ('opponent', 'you')]
        return ([{'do': 'coin_flip'}, {'do': 'coin_scales_next'}], groups, False)
    if text == 'Flip a coin. If you win the flip, ~ deals damage to target opponent or planeswalker equal to the number of creatures you control. If you lose the flip, ~ deals damage to you equal to the number of creatures that opponent or that planeswalker\'s controller controls.':
        return ([{'do': 'coin_flip'}, {'do': 'coin_lyre_result'}], 'opponent_or_planeswalker', False)
    if text == 'You may sacrifice an artifact. If you do, flip a coin. When you win the flip, copy that spell. You may choose new targets for the copy. When you lose the flip, ~ deals damage equal to that spell\'s mana value to any target.':
        return ([{'do': 'optional_payment', 'who': 'you', 'cost': 'Sacrifice an artifact', 'bind': 'coin_artifact'},
                 {'do': 'only_if', 'cond': {'succeeded': 'coin_artifact'}, 'skip': 3}, {'do': 'coin_flip'},
                 {'do': 'reflexive', 'cond': {'coin': 'win'}, 'keep_event': True,
                  'ability': {'kind': 'triggered', 'trigger': 'reflexive', 'effects': _native('Copy that spell. You may choose new targets for the copy.')}},
                 {'do': 'reflexive', 'cond': {'coin': 'lose'}, 'keep_event': True,
                  'ability': {'kind': 'triggered', 'trigger': 'reflexive', 'target': {'what': 'any', 'min': 1, 'max': 1},
                              'effects': [{'do': 'damage', 'who': 'target', 'n': {'mana_value': 'event'}}]}}], None, False)
    return None


def insert(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    i = ctx['next']
    ctx['effects'] = [*ctx['effects'][:i], *steps, *ctx['effects'][i:]]


def group_recipe(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import coin_outcomes, effects

    kind = e['kind']
    coins: list[dict[str, Any]]
    if kind == 'rakdos':
        coins = [{'player': ctx['controller'], 'card': c.id, 'object': plan.oid(c)} for c in plan.state.cards.values()
                 if c.zone.endswith(':battlefield') and plan.ch(c).is_creature and not (plan.ch(c).subtypes & {'Demon', 'Devil', 'Imp'})]
    elif kind == 'opponents':
        coins = [{'player': ctx['controller'], 'opponent': p} for p in plan.live() if p != ctx['controller']]
    elif kind == 'clash':
        coins = [{'player': p} for p in dict.fromkeys([ctx['controller'], *effects._players(plan, ctx, 'target')])]
    else:
        coins = [{'player': p} for p in (plan.live() if kind == 'players' else effects._players(plan, ctx, 'event_player'))]
    return coin_outcomes.group(plan, ctx, coins, face=e.get('face', kind == 'rakdos'))


def result(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, selectors

    outcomes = ctx.get('coin_outcomes') or []
    heads = sum(c['heads'] for c in outcomes)
    kind, steps = e['kind'], []
    if kind in ('extra', 'skip') and heads:
        steps = [{'do': 'skip_next' if kind == 'skip' else 'extra_turn', 'who': e.get('who', 'you'), 'n': heads,
                  **({'what': 'turn'} if kind == 'skip' else {})}]
    elif kind == 'destroy_tails':
        cards = [c['card'] for c in outcomes if not c['heads'] and c['card'] in plan.state.cards
                 and plan.oid(c['card']) == c['object'] and plan.state.cards[c['card']].zone.endswith(':battlefield')]
        context.bind_objects(plan, ctx, 'coin_doomed', cards)
        steps = [{'do': 'destroy', 'who': 'ref:coin_doomed'}]
    elif kind == 'counter' and outcomes and outcomes[0]['won'] is False:
        steps = [{'do': 'counter', 'who': 'event_spell'}]
    elif kind == 'mutalith':
        won = sum(c['won'] is True for c in outcomes)
        if won:
            steps.append({'do': 'draw', 'who': 'you', 'n': won})
        context.bind_players(ctx, 'coin_damaged', [c['opponent'] for c in outcomes if c['won'] is False])
        steps.append({'do': 'damage', 'who': 'ref:coin_damaged', 'n': 3})
    elif kind == 'clash':
        context.bind_players(ctx, 'clash_tails', [c['player'] for c in outcomes if not c['heads']])
    elif kind == 'edict_tails':
        context.bind_players(ctx, 'coin_tails', [c['player'] for c in outcomes if not c['heads']])
        steps = [{'do': 'edict', 'who': 'ref:coin_tails', 'sel': selectors.Selector(types=('Creature',)).key(), 'n': 1, 'label': 'creature'}]
    elif kind == 'giant' and outcomes and heads in (0, len(outcomes)):
        steps = [{'do': 'grant', 'who': 'self', 'keywords': ['double strike' if heads else 'menace']}]
    elif kind == 'combat_sacrifice':
        key = selectors.Selector(types=('Creature',), blocking=True).key() if ctx['coin'] else selectors.Selector(types=('Creature',), extras=('blocked',)).key()
        steps = [{'do': 'sacrifice', 'who': key, 'by': 'controller'}]
    elif kind == 'control' and ctx.get('coin') is False:
        steps = [{'do': 'gain_control', 'who': e['who'], 'to': 'choose_opponent'}]
    elif kind == 'sacrifice' and ctx.get('coin') is False:
        steps = [{'do': 'sacrifice', 'who': e['who']}]
    insert(ctx, steps)
    return True


def sliver(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    if not effects._cards(plan, ctx, 'self'):
        return True
    insert(ctx, [{'do': 'coin_flip'}, {'do': 'coin_sliver_result'}])
    return True


def sliver_result(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    if ctx.get('coin'):
        insert(ctx, _native("Exile ~. Return it to the battlefield under its owner's control at the beginning of the next end step."))
    else:
        insert(ctx, [{'do': 'sacrifice', 'who': 'self'}])
    return True


PRIMITIVES = {'coin_group_recipe': group_recipe, 'coin_result': result, 'coin_sliver': sliver, 'coin_sliver_result': sliver_result}


def clash(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    insert(ctx, [{'do': 'coin_group_recipe', 'kind': 'clash', 'face': True}, {'do': 'coin_result', 'kind': 'clash'},
                 {'do': 'damage', 'who': 'ref:clash_tails', 'n': 1}, {'do': 'coin_clash_again'}])
    return True


def clash_again(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if all(c['heads'] for c in ctx['coin_outcomes']):
        return True
    ctx['next'] -= 4
    rounds = int(ctx.get('coin_clash_rounds', 0)) + 1
    ctx['coin_clash_rounds'] = rounds
    if rounds % 16 == 0 or len(plan.steps) >= plan.max_steps - 50:
        # Decision is installed before returning to engine.settle: 704.4 prohibits SBA mid-resolution.
        decide(plan, player=ctx['controller'], kind='confirm', prompt='Continue resolving Mana Clash; no priority is available.',
               options=[DecisionOption(id='continue', label='Continue resolving')],
               resume={'step': 'coin_process', 'ctx': ctx})
        return False
    return True


def gambit_next(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if not ctx.get('coin'):
        return True
    ctx['coin_gambit_wins'] = int(ctx.get('coin_gambit_wins', 0)) + 1
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Continue flipping for Fiery Gambit, or stop?',
           options=[DecisionOption(id='continue', label='Flip again'), DecisionOption(id='stop', label='Stop flipping')],
           resume={'step': 'coin_gambit', 'ctx': ctx})
    return False


def resume_gambit(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume['ctx']
    if chosen[0] == 'continue':
        ctx['next'] -= 2
    else:
        wins = ctx['coin_gambit_wins']
        steps = [{'do': 'damage', 'who': 'target', 'n': 3}]
        if wins >= 2:
            steps.append({'do': 'damage', 'who': 'each_opponent', 'n': 6})
        if wins >= 3:
            steps += [{'do': 'draw', 'who': 'you', 'n': 9}, *_native('Untap all lands you control.')]
        insert(ctx, steps)
    effects.continue_effects(plan, ctx)


def scales_next(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    if ctx.get('coin'):
        insert(ctx, [{'do': 'destroy', 'who': 'target:0'}])
    else:
        insert(ctx, [{'do': 'optional_payment', 'who': 'you', 'cost': '{3}', 'bind': 'coin_retry'}, {'do': 'coin_scales_paid'}])
    return True


def scales_paid(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import conditions

    if conditions.holds(plan, ctx, {'succeeded': 'coin_retry'}):
        insert(ctx, [{'do': 'coin_flip'}, {'do': 'coin_scales_next'}])
    else:
        insert(ctx, [{'do': 'destroy', 'who': 'target:1'}])
    return True


def lyre_result(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    players = [ctx['controller']] if ctx.get('coin') else effects._players(plan, ctx, 'target_player_or_controller')
    count = sum(c.zone.endswith(':battlefield') and c.controller in players and plan.ch(c).is_creature for c in plan.state.cards.values())
    insert(ctx, [{'do': 'damage', 'who': 'target' if ctx.get('coin') else 'you', 'n': count}])
    return True


def resume_process(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, d.resume['ctx'])


PRIMITIVES.update({'coin_clash': clash, 'coin_clash_again': clash_again, 'coin_gambit_next': gambit_next,
                   'coin_scales_next': scales_next, 'coin_scales_paid': scales_paid, 'coin_lyre_result': lyre_result})
RESUME = {'coin_process': resume_process, 'coin_gambit': resume_gambit}
