"""Durable random object receipts feed ordinary native effects; entropy is never a die event."""
from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def _native(text: str) -> list[dict[str, Any]]:
    from app.rules import scripts

    got = scripts.parse_effects(text)
    if got is None:
        raise ValueError('Unsupported native random receipt consequence: ' + text)
    return got[0]


def _step(kind: str, **kwargs: Any) -> dict[str, Any]:
    return {'do': 'random_choice_receipt', 'kind': kind, **kwargs}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    text = ' '.join(body.split())
    text = text[:1].upper() + text[1:]
    fixed = {
        'Return a card at random from your graveyard to your hand, then reorder your graveyard as you choose.': 'fossil',
        "Reorder your graveyard at random. An opponent chooses a card at random in your graveyard. If it's a creature card, put it onto the battlefield. Otherwise, exile it.": 'survivors',
        'For each nonland permanent, choose a player at random. Then each player gains control of each permanent for which they were chosen. Untap those permanents.': 'scramble',
        "Target opponent chooses a permanent they control at random and sacrifices it. If a nonland permanent is sacrificed this way, repeat this process.": 'tyrant',
        "Choose four nonenchantment permanents you don't control and put an aim counter on each of them.": 'aim',
        'Destroy one of those permanents at random.': 'bombard',
        'Target opponent reveals their hand and discards a creature card at random.': 'rag',
        "Target player reveals a card at random from their hand. If it's a land card, that player discards it unless they pay 1 life. If it isn't a land card, the player discards it unless they pay life equal to its mana value.": 'wand',
        "Target opponent reveals a card at random from their hand. Target creature gets +X/+X until end of turn, where X is the revealed card's mana value.": 'favor',
        "Target opponent reveals a card at random from their hand. Target creature gets -X/-X until end of turn, where X is the revealed card's mana value.": 'scorn',
        'Flip a coin. If you win the flip, you gain 1 life and target opponent loses 1 life, and you decide whether to flip again. If you lose the flip, you lose 1 life and that opponent gains 1 life, and that player decides whether to flip again. Double the life stakes with each flip.': 'game',
        'Roll a d6. ~ deals damage to that player equal to the result. Then attach ~ to another one of your opponents chosen at random.': 'hex',
        'Choose a creature at random ~ can enchant. Return this card to the battlefield attached to that creature.': 'rage',
        'Choose a creature at random ~ can enchant. Return ~ to the battlefield attached to that creature.': 'rage',
        '~ gets +2/+2 until end of turn unless a player has ~ deal 4 damage to them.': 'bully',
        'You and those players each draw a card, then discard a card at random.': 'zurzoth',
        'You may have it assign no combat damage this turn. If you do, defending player discards a card at random.': 'cloak',
    }
    if text == 'Target player discards a card at random. Then that player discards another card at random unless they pay {1}.':
        return _native(text.replace('another card', 'a card')), 'player', False
    if text == 'Target player reveals two cards at random from their hand, then discards each nonland card revealed this way.':
        return _native('Target player reveals two cards at random from their hand. Then that player discards each nonland card revealed this way.'), 'player', False
    if text == "Return target creature card from a graveyard and target creature on the battlefield to their owners' hands.":
        return ([{'do': 'return_card', 'who': 'target:0', 'to': 'hand', 'under': 'owner'},
                 {'do': 'bounce', 'who': 'target:1'}],
                [{'what': selectors.Selector(card=True, types=('Creature',), zones=('graveyard',)).key(), 'min': 1, 'max': 1},
                 {'what': 'creature', 'min': 1, 'max': 1}], False)
    if text == 'You choose target creature an opponent controls, and that opponent chooses target creature. Flip a coin. If you win the flip, destroy the creature you chose. If you lose the flip, destroy the creature your opponent chose.':
        return ([{'do': 'coin_flip'}, _step('mogg')],
                [{'what': selectors.Selector(types=('Creature',), controller='opponent').key(), 'min': 1, 'max': 1},
                 {'what': 'creature', 'min': 1, 'max': 1}], False)
    kind = fixed.get(text)
    if kind is None:
        return None
    targets: Any = ('opponent' if kind in ('tyrant', 'rag') else 'player' if kind == 'wand' else
                    [{'what': 'opponent', 'min': 1, 'max': 1}, {'what': 'creature', 'min': 1, 'max': 1}] if kind in ('favor', 'scorn') else
                    'opponent' if kind == 'game' else None)
    lead = ([{'do': 'roll', 'sides': 6, 'count': 1}] if kind == 'hex' else
            [{'do': 'coin_flip'}] if kind == 'game' else [])
    return [*lead, _step(kind, **({'who': 'self_aura_gy'} if kind == 'rage' else {}))], targets, False


def random_buyback(line: str) -> Any:
    """Only this real additional cost: alternative costs keep their existing closed grammar."""
    from app.rules import costs

    if line.strip().rstrip('.') != 'Buyback—Pay 3 life, Discard a card at random':
        return None
    cost = costs.parse_ability_cost('Pay 3 life, Discard a card at random')
    return cost if not cost.unsupported else None


def bind_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """The shared delegated-announcement owner implements this typed dependency."""
    if any(e.get('do') == 'random_choice_receipt' and e.get('kind') == 'mogg' for e in definition.get('effects') or []):
        return {**definition, 'delegated_target': {'kind': 'target_controller', 'of': 0, 'group': 1}}
    return definition


def recipe(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import attachments, coin_recipes, conditions, context, effects, selectors
    from app.rules.plan import decide

    kind = e['kind']
    steps: list[dict[str, Any]] = []
    rng = plan.rng or secrets.SystemRandom()
    me = ctx['controller']
    if kind in ('favor', 'scorn', 'wand'):
        who = 'target:0' if kind in ('favor', 'scorn') else 'target'
        steps = [{'do': 'reveal_random', 'who': who, 'n': 1, 'as': 'r41_revealed'}, _step(kind + '_revealed')]
    elif kind in ('favor_revealed', 'scorn_revealed', 'wand_revealed'):
        cards = effects._cards(plan, ctx, 'ref:r41_revealed')
        mv = int(plan.ch(plan.state.cards[cards[0]]).mana_value) if cards else 0
        ctx['r41_revealed_mv'] = mv
        if kind == 'wand_revealed':
            if cards:
                n = 1 if plan.ch(plan.state.cards[cards[0]]).is_land else mv
                players = effects._players(plan, ctx, 'target')
                context.bind_players(ctx, 'r41_payer', players)
                steps = [{'do': 'optional_payment', 'who': 'ref:r41_payer', 'cost': f'Pay {n} life', 'bind': 'r41_paid'},
                         {'do': 'only_if', 'cond': {'succeeded': 'r41_paid', 'negate': True}, 'skip': 1}, _step('discard_receipt')]
        else:
            n = -mv if kind == 'scorn_revealed' else mv
            steps = [{'do': 'pump', 'who': 'target:1', 'p': n, 't': n}]
    elif kind == 'discard_receipt':
        cards = [c for c in effects._cards(plan, ctx, 'ref:r41_revealed') if plan.state.cards[c].zone.endswith(':hand')]
        return effects._discard_next(plan, ctx, 0, [], cards)
    elif kind == 'rag':
        steps = [{'do': 'reveal_hand', 'who': 'target'}, _step('rag_discard')]
    elif kind == 'rag_discard':
        players = effects._players(plan, ctx, 'target')
        cards = [c for pid in players for c in plan.state.zones.get(pid + ':hand', []) if plan.ch(plan.state.cards[c]).is_creature]
        chosen = [rng.choice(cards)] if cards else []
        context.bind_objects(plan, ctx, 'r41_revealed', chosen)
        steps = [_step('discard_receipt')]
    elif kind == 'fossil':
        steps = [*_native('Return a card at random from your graveyard to your hand.'), _step('grave_order')]
    elif kind in ('grave_order', 'survivors'):
        cards = list(plan.state.zones.get(me + ':graveyard', []))
        if kind == 'survivors':
            rng.shuffle(cards)
            if cards:
                plan.do({'type': 'move', 'card_ids': cards, 'to': {'player': me, 'zone': 'graveyard'}, 'index': 0}, actor=me)
            steps = [{'do': 'choose_value', 'who': 'you', 'what': 'opponent', 'as': 'r41_survivors_opponent'}, _step('survivors_pick')]
        elif len(cards) > 1:
            decide(plan, player=me, kind='order', prompt='Order your graveyard (first chosen on top)',
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or 'Card', card_id=c) for c in reversed(cards)],
                   min_choices=len(cards), max_choices=len(cards), resume={'step': 'r41_grave_order', 'ctx': ctx, 'cards': cards})
            return False
    elif kind == 'survivors_pick':
        players = context.players(plan, ctx, 'r41_survivors_opponent')
        if not players:
            return True
        cards = list(plan.state.zones.get(me + ':graveyard', []))
        chosen = [rng.choice(cards)] if cards else []
        context.bind_objects(plan, ctx, 'r41_survivor', chosen)
        if chosen:
            plan.note('A graveyard card was chosen at random', chosen, actor=players[0])
            steps = [{'do': 'return_card', 'who': 'ref:r41_survivor', 'to': 'battlefield', 'under': 'you'}] if plan.ch(plan.state.cards[chosen[0]]).is_creature else [{'do': 'exile', 'who': 'ref:r41_survivor'}]
    elif kind == 'game':
        won = ctx.get('coin') is True
        stake = int(ctx.get('r41_stake') or 1)
        steps = [{'do': 'gain_life' if won else 'lose_life', 'who': 'you', 'n': stake},
                 {'do': 'lose_life' if won else 'gain_life', 'who': 'target', 'n': stake}, _step('game_offer', won=won)]
    elif kind == 'game_offer':
        players = [me] if e['won'] else effects._players(plan, ctx, 'target')
        if players:
            decide(plan, player=players[0], kind='confirm', prompt='Flip again at double the life stakes?',
                   options=[DecisionOption(id='yes', label='Flip again'), DecisionOption(id='no', label='Stop')], min_choices=1, max_choices=1,
                   resume={'step': 'r41_game', 'ctx': ctx})
            return False
    elif kind == 'mogg':
        steps = [{'do': 'destroy', 'who': 'target:0' if ctx.get('coin') is True else 'target:1'}]
    elif kind == 'hex':
        steps = [{'do': 'damage', 'who': 'event_player', 'n': int(ctx.get('die') or 0)}, _step('hex_attach')]
    elif kind == 'hex_attach':
        sources = effects._cards(plan, ctx, 'self')
        previous = effects._players(plan, ctx, 'event_player')
        if sources and plan.in_game(plan.state.cards[sources[0]]):
            src = plan.state.cards[sources[0]]
            players = [pid for pid in plan.live() if pid != me and pid not in previous and attachments.host_problem(plan, src, pid) is None]
            if players:
                attachments.attach(plan, src.id, rng.choice(players), me)
    elif kind == 'rage':
        cards = effects._cards(plan, ctx, e.get('who', 'self_aura_gy'))
        if cards:
            src = plan.state.cards[cards[0]]
            hosts = [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.in_game(c) and plan.ch(c).is_creature and attachments.host_problem(plan, src, c.id) is None]
            if hosts:
                context.bind_objects(plan, ctx, 'r41_rage_host', [rng.choice(hosts)])
                steps = [{'do': 'return_card', 'who': e.get('who', 'self_aura_gy'), 'to': 'battlefield', 'under': 'you', 'host': 'ref:r41_rage_host'}]
    elif kind == 'aim':
        sel = selectors.Selector(not_types=('Enchantment',), controller='opponent')
        cards = selectors.candidates(plan, sel, me, ctx.get('source_card'))
        n = min(4, len(cards))
        if n:
            decide(plan, player=me, kind='choose_cards', prompt='Choose four nonenchantment permanents you do not control (as many as possible)',
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or 'Permanent', card_id=c) for c in cards], min_choices=n, max_choices=n,
                   resume={'step': 'r41_aim', 'ctx': ctx})
            return False
    elif kind == 'bombard':
        cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.in_game(c) and c.controller != me and c.counters.get('aim', 0)]
        if len(cards) >= 2:
            cards = [c for c in cards if 'indestructible' not in plan.ch(plan.state.cards[c]).keywords]
            if cards:
                context.bind_objects(plan, ctx, 'r41_bombard', [rng.choice(cards)])
                steps = [{'do': 'destroy', 'who': 'ref:r41_bombard'}]
    elif kind == 'tyrant':
        players = effects._players(plan, ctx, 'target')
        cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.in_game(c) and c.controller in players]
        if cards:
            cid = rng.choice(cards)
            context.bind_objects(plan, ctx, 'r41_tyrant_chosen', [cid])
            ctx['r41_tyrant_nonland'] = not plan.ch(plan.state.cards[cid]).is_land
            context.refs(ctx).pop('r41_tyrant_done', None)
            steps = [{'do': 'sacrifice', 'who': 'ref:r41_tyrant_chosen', 'by': 'controller', 'as': 'r41_tyrant_sacrificed', 'did': 'r41_tyrant_done'}, _step('tyrant_repeat')]
    elif kind == 'tyrant_repeat':
        chosen = effects._cards(plan, ctx, 'ref:r41_tyrant_chosen')
        if any((pending := plan.rules.pending_616.get(cid)) is not None
               and pending.get('oid') == plan.oid(plan.state.cards[cid]) for cid in chosen):
            from app.rules import replacements

            coin_recipes.insert(ctx, [_step('tyrant_repeat')])
            if replacements.offer_616(plan):
                assert plan.rules.decision is not None
                assert plan.rules.decision.resume is not None
                plan.rules.decision.resume['then'] = {'do': 'continue', 'ctx': ctx}
                plan.rules.decision.resume['abort_then'] = {'do': 'continue', 'ctx': {**ctx, 'next': ctx['next'] + 1}}
                return False
        if ctx.get('r41_tyrant_nonland') and conditions.holds(plan, ctx, {'succeeded': 'r41_tyrant_done'}):
            steps = [_step('tyrant')]
    elif kind == 'scramble':
        cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.in_game(c) and not plan.ch(c).is_land]
        assignments: dict[str, list[str]] = {pid: [] for pid in plan.live()}
        for cid in cards:
            assignments[rng.choice(list(assignments))].append(cid)
        for pid, chosen in assignments.items():
            context.bind_objects(plan, ctx, 'r41_scramble_' + pid, chosen)
            context.bind_players(ctx, 'r41_scramble_player_' + pid, [pid])
            steps.append({'do': 'gain_control', 'who': 'ref:r41_scramble_' + pid, 'to': 'ref:r41_scramble_player_' + pid})
        context.bind_objects(plan, ctx, 'r41_scramble_all', cards)
        steps.append({'do': 'untap', 'who': 'ref:r41_scramble_all'})
    elif kind == 'zurzoth':
        players = list(dict.fromkeys([me, *(ctx.get('event') or {}).get('attacked_players', [])]))
        context.bind_players(ctx, 'r41_devils_players', [p for p in players if p in plan.live()])
        steps = [{'do': 'draw', 'who': 'ref:r41_devils_players', 'n': 1}, {'do': 'discard', 'who': 'ref:r41_devils_players', 'n': 1, 'random': True}]
    elif kind == 'cloak':
        if effects._cards(plan, ctx, 'event'):
            decide(plan, player=me, kind='confirm', prompt='Have that creature assign no combat damage this turn?',
                   options=[DecisionOption(id='yes', label='Yes'), DecisionOption(id='no', label='No')], min_choices=1, max_choices=1,
                   resume={'step': 'r41_cloak', 'ctx': ctx})
            return False
    elif kind == 'bully':
        ctx['r41_bully_players'] = list(plan.apnap())
        steps = [_step('bully_offer')]
    elif kind == 'bully_offer':
        players = ctx.get('r41_bully_players') or []
        if players:
            pid, *ctx['r41_bully_players'] = players
            context.bind_players(ctx, 'r41_bully_payer', [pid])
            steps = [{'do': 'optional_payment', 'who': 'ref:r41_bully_payer', 'cost': 'Have ~ deal 4 damage to you', 'bind': 'r41_bully_paid'}, _step('bully_verdict')]
        else:
            steps = _native('~ gets +2/+2 until end of turn.')
    elif kind == 'bully_verdict':
        if not conditions.holds(plan, ctx, {'succeeded': 'r41_bully_paid'}):
            steps = [_step('bully_offer')]
    coin_recipes.insert(ctx, steps)
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import coin_recipes, context, effects

    ctx = d.resume['ctx']
    if d.resume['step'] == 'r41_grave_order':
        cards = [c for c in chosen if c in plan.state.zones.get(d.player + ':graveyard', [])]
        if cards:
            plan.do({'type': 'move', 'card_ids': list(reversed(cards)), 'to': {'player': d.player, 'zone': 'graveyard'}, 'index': 0}, actor=d.player)
    elif d.resume['step'] == 'r41_aim':
        context.bind_objects(plan, ctx, 'r41_aimed', chosen)
        coin_recipes.insert(ctx, [{'do': 'add_counters', 'who': 'ref:r41_aimed', 'kind': 'aim', 'n': 1}])
    elif d.resume['step'] == 'r41_cloak':
        if chosen == ['yes'] and effects._cards(plan, ctx, 'event'):
            coin_recipes.insert(ctx, [{'do': 'restrict', 'who': 'event', 'rules': ['assign_none']}, {'do': 'discard', 'who': 'defending_player', 'n': 1, 'random': True}])
    elif chosen == ['yes']:
        ctx['r41_stake'] = 2 * int(ctx.get('r41_stake') or 1)
        coin_recipes.insert(ctx, [{'do': 'coin_flip'}, _step('game')])
    effects.continue_effects(plan, ctx)


PRIMITIVES = {'random_choice_receipt': recipe}
RESUME = {step: resume for step in ('r41_game', 'r41_grave_order', 'r41_aim', 'r41_cloak')}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import selectors

    if ability.kind != 'triggered':
        return None
    if ability.text == "Whenever one or more Devils you control attack one or more players, you and those players each draw a card, then discard a card at random.":
        return {'kind': 'triggered', 'trigger': 'event',
                'cond': {'event': 'you_attack', 'subject': 'player', 'player': 'you', 'min_attackers': 1,
                         'sel': selectors.Selector(types=('Creature',), subtypes=('Devil',), controller='you').key()},
                'event_players_from_counted_attackers': True, 'effects': [_step('zurzoth')]}
    if ability.text == "At the beginning of your end step, if two or more permanents you don't control have an aim counter on them, destroy one of those permanents at random.":
        return {'kind': 'triggered', 'trigger': 'step:end:you',
                'if': {'value': {'count': selectors.Selector(controller='opponent', extras=('counter:aim',)).key()}, 'op': '>=', 'n': 2},
                'effects': [_step('bombard')]}
    return None


def freeze_attacked_players(event: Any, counted: list[Any]) -> bool:
    """A typed trigger receipt: actual players attacked by counted original attackers, once each."""
    event.attacked_players = list(dict.fromkeys(c.attacking.id for c in counted if c.attacking is not None and c.attacking.kind == 'player'))
    return bool(event.attacked_players)
