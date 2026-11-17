"""Kept die receipts and finite random partitions feed the native effect pipeline."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def _program(kind: str, *, sides: int | None = None, count: int = 1) -> list[dict[str, Any]]:
    return ([{'do': 'roll', 'sides': sides, 'count': count}] if sides else []) + [{'do': 'random_receipt', 'kind': kind}]


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    text = ' '.join(body.split())
    text = text[:1].upper() + text[1:]
    fixed = {
        'Roll a d8. Reveal cards from the top of your library until you reveal a creature card with mana value equal to the result. Put that card onto the battlefield and the rest on the bottom of your library in a random order.': ('bag', 8, 1),
        'You may reveal the top card of your library. Do this only once each turn. Whenever you reveal a card with mana value less than the result this way, you may exile it. If you do, you may play it this turn.': ('boarding', None, 1),
        'Exile the top four cards of your library, then roll a d20. 1—9 | You may put a land card from among those cards onto the battlefield. 10—19 | Create a 2/2 green Wolf creature token, then put a +1/+1 counter on it for each creature card among those cards. 20 | Put all permanent cards exiled with ~ onto the battlefield, then sacrifice it.': ('journey_prepare', None, 1),
        'Roll a d4 and create a number of Treasure tokens equal to the result. The player to your right gains control of ~.': ('purse', 4, 1),
        'Roll two d4 and choose one result. Create a number of 3/3 green Beast creature tokens equal to that result. Then search your library for a number of basic land cards equal to the other result, put them onto the battlefield tapped, then shuffle.': ('wild', 4, 2),
        'Roll a d12. If the result is greater than the damage dealt or the result is 12, double the number of +1/+1 counters on that creature.': ('sword', 12, 1),
        'Roll a d6. Until end of turn, you may have ~ become an X/X Insect artifact creature with flying, where X is the result.': ('fly', 6, 1),
        'Create two 1/1 white Clown Robot artifact creature tokens, then roll a six-sided die. If the result is equal to or less than the number of Robots you control, create a 1/1 white Clown Robot artifact creature token.': ('clowns_prepare', None, 1),
        'Roll two six-sided dice. Return any number of cards with total mana value X or less from your graveyard to your hand, where X is the total of those results. Exile ~.': ('pair', 6, 2),
        '~ gains flying and menace until end of turn. If any of those results was 10 or higher, draw a card.': ('farideh', None, 1),
        'Return this card from your graveyard to your hand.': ('critical', None, 1),
        'Create a 3/3 colorless Robot artifact creature token. If you rolled 6 or higher, instead create that token and a Treasure token.': ('house_trigger', None, 1),
        'Roll a six-sided die plus an additional six-sided die for each mana from Treasures spent to activate this ability.': ('house_roll', None, 1),
        "Choose a kind of counter at random that ~ doesn't have on it from among flying, first strike, deathtouch, hexproof, lifelink, menace, reach, trample, vigilance, and +1/+1. Put a counter of that kind on ~.": ('giant', None, 1),
        "Return a Zombie creature card at random from your graveyard to the battlefield.": ('tyrant', None, 1),
    }
    if text in fixed:
        kind, sides, count = fixed[text]
        steps = _program(kind, sides=sides, count=count)
        if kind == 'wild':
            steps[0]['choose'] = True
        # This generic return is already supported natively; do not replace arbitrary effects.
        if kind == 'critical':
            return None
        return steps, None, False
    if text == "Roll a d10. Put target artifact, creature, or planeswalker into its owner's library just beneath the top X cards of that library, where X is the result.":
        return _program('rift', sides=10), selectors.Selector(types=('Artifact', 'Creature', 'Planeswalker')).key(), False
    if text == 'Choose three target creature cards in your graveyard. Return two of them at random to the battlefield and put the other on the bottom of your library.':
        return _program('waltz'), [{'what': selectors.Selector(card=True, types=('Creature',), zones=('graveyard',), zone_owner='you').key(), 'min': 3, 'max': 3}], False
    if text == "Choose target nonland permanent you control and up to two target nonland permanents you don't control. Destroy one of them at random.":
        return _program('random_destroy'), [{'what': selectors.Selector(not_types=('Land',), controller=p).key(), 'min': lo, 'max': hi}
                                            for p, lo, hi in [('you', 1, 1), ('opponent', 0, 2)]], False
    if text == 'Choose three target nonenchantment permanents. Destroy one of them at random.':
        return _program('random_destroy'), [{'what': selectors.Selector(not_types=('Enchantment',)).key(), 'min': 3, 'max': 3}], False
    return None


def _native(text: str) -> list[dict[str, Any]]:
    from app.rules import scripts

    out = scripts.parse_effects(text)
    if out is None:
        raise ValueError('Unsupported native random receipt consequence: ' + text)
    return out[0]


def receipt(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    import secrets

    from app.rules import coin_recipes, context, effects, selectors

    kind = e['kind']
    steps: list[dict[str, Any]] = []
    result = int(ctx.get('die') or 0)
    if kind == 'bag':
        steps = _native(f'Reveal cards from the top of your library until you reveal a creature card with mana value {result}. Put that card onto the battlefield and the rest on the bottom of your library in a random order.')
    elif kind == 'journey_prepare':
        steps = [{'do': 'exile_top', 'n': 4, 'player': 'you', 'link': True, 'as': 'receipt_journey'},
                 {'do': 'roll', 'sides': 20, 'count': 1}, {'do': 'random_receipt', 'kind': 'journey'}]
    elif kind == 'journey':
        cards = effects._cards(plan, ctx, 'ref:receipt_journey')
        if 1 <= result <= 9:
            lands = [c for c in cards if plan.ch(plan.state.cards[c]).is_land]
            context.bind_objects(plan, ctx, 'receipt_journey_lands', lands)
            steps = [{'do': 'return_choice', 'who': 'ref:receipt_journey_lands', 'n': 1, 'upto': True, 'to': 'battlefield'}]
        elif 10 <= result <= 19:
            n = sum(plan.ch(plan.state.cards[c]).is_creature for c in cards)
            steps = [{**_native('Create a 2/2 green Wolf creature token.')[0], 'as': 'receipt_wolf'},
                     {'do': 'add_counters', 'who': 'ref:receipt_wolf', 'kind': '+1/+1', 'n': n}]
        elif result == 20:
            steps = [{'do': 'return_card', 'who': 'exiled_with:' + selectors.Selector(card=True, zones=(), types=('Artifact', 'Battle', 'Creature', 'Enchantment', 'Land', 'Planeswalker')).key(), 'to': 'battlefield'}, {'do': 'sacrifice', 'who': 'self'}]
    elif kind in ('boarding', 'boarding_exile'):
        from app.game.rules_state import DecisionOption
        from app.rules.plan import decide

        key = 'receipt_boarding:' + str(ctx.get('source_object') or '')
        if kind == 'boarding' and plan.rules.once_per_turn.get(key) == plan.state.turn.number:
            return True
        decide(plan, player=ctx['controller'], kind='confirm', prompt='Reveal the top card?' if kind == 'boarding' else 'Exile the revealed card?',
               options=[DecisionOption(id='yes', label='Yes'), DecisionOption(id='no', label='No')], min_choices=1, max_choices=1,
               resume={'step': 'receipt_boarding', 'ctx': ctx, 'kind': kind, 'key': key})
        return False
    elif kind == 'boarding_revealed':
        from app.game.rules_state import TriggerEvent
        from app.rules.triggers import _add

        cards = ctx.get('looked') or []
        if cards and plan.ch(plan.state.cards[cards[0]]).mana_value < int((ctx.get('event') or {}).get('amount') or 0):
            ref = context.ref_of(plan, cards[0])
            if ref:
                _add(plan, controller=ctx['controller'], source_card=ctx.get('source_card') or '', source_object=ctx.get('source_object') or '',
                     name=str(ctx.get('name') or ''), index=7301,
                     definition={'kind': 'triggered', 'trigger': 'reflexive', 'effects': [{'do': 'random_receipt', 'kind': 'boarding_exile'}]},
                     event=TriggerEvent(kind='reflexive', objects=[ref]))
    elif kind == 'purse':
        steps = [{**_native('Create a Treasure token.')[0], 'n': result}]
        seats = [pid for pid in plan.state.players if pid in plan.live()]
        actor = ctx['controller']
        if actor in seats and len(seats) > 1:
            context.bind_players(ctx, 'receipt_right', [seats[(seats.index(actor) - 1) % len(seats)]])
            steps.append({'do': 'gain_control', 'who': 'self', 'to': 'ref:receipt_right'})
    elif kind == 'wild':
        steps = [{**_native('Create a 3/3 green Beast creature token.')[0], 'n': result},
                 *_native(f'Search your library for up to {int(ctx.get("die_other") or 0)} basic land cards, put them onto the battlefield tapped, then shuffle.')]
    elif kind == 'sword':
        event = ctx.get('event') or {}
        if result == 12 or result > int(event.get('amount') or 0):
            cards = effects._cards(plan, ctx, 'event')
            for cid in cards:
                steps.append({'do': 'add_counters', 'who': 'object:' + plan.oid(cid), 'kind': '+1/+1', 'n': plan.state.cards[cid].counters.get('+1/+1', 0)})
    elif kind == 'farideh':
        steps = [{'do': 'grant', 'who': 'self', 'keywords': ['flying', 'menace']}]
        if int((ctx.get('event') or {}).get('amount') or 0) >= 10:
            steps.append({'do': 'draw', 'who': 'you', 'n': 1})
    elif kind == 'house_trigger':
        steps = _native('Create a 3/3 colorless Robot artifact creature token.')
        if int((ctx.get('event') or {}).get('amount') or 0) >= 6:
            steps += _native('Create a Treasure token.')
    elif kind == 'house_roll':
        stack_id = ctx.get('stack_id')
        paid = plan.rules.payments.get(plan.oid(stack_id)) if stack_id in plan.state.cards else None
        n = 1 + sum('Treasure' in tags for tags in paid.mana_tags) if paid is not None else 1
        steps = [{'do': 'roll', 'sides': 6, 'count': n}]
    elif kind == 'giant':
        cards = effects._cards(plan, ctx, 'self')
        if cards:
            card = plan.state.cards[cards[0]]
            kinds = [k for k in ('flying', 'first strike', 'deathtouch', 'hexproof', 'lifelink', 'menace', 'reach', 'trample', 'vigilance', '+1/+1') if not card.counters.get(k, 0)]
            if kinds:
                from app.rules import randomness  # -- random choices (wave MBC-D) --
                chosen = randomness.choice(plan, plan.rng or secrets.SystemRandom(), kinds, kind='other', player=ctx['controller'])
                steps = [{'do': 'add_counters', 'who': 'self', 'kind': chosen, 'n': 1}]
    elif kind == 'tyrant':
        steps = [{'do': 'return_choice', 'sel': selectors.Selector(card=True, types=('Creature',), subtypes=('Zombie',), zones=('graveyard',), zone_owner='you').key(), 'n': 1, 'random': True, 'to': 'battlefield'}]
    elif kind == 'random_destroy':
        cards = effects._cards(plan, ctx, 'target')
        if cards:
            from app.rules import randomness  # -- random choices (wave MBC-D) --
            cid = cards[0] if len(cards) == 1 else randomness.choice(plan, plan.rng or secrets.SystemRandom(), cards, kind='object', player=ctx['controller'])
            context.bind_objects(plan, ctx, 'receipt_doomed', [cid])
            steps = [{'do': 'destroy', 'who': 'ref:receipt_doomed'}]
    elif kind == 'waltz':
        cards = effects._cards(plan, ctx, 'target')
        from app.rules import randomness  # -- random choices (wave MBC-D) --
        picked = randomness.sample(plan, plan.rng or secrets.SystemRandom(), cards, min(2, len(cards)), kind='object', player=ctx['controller']) if len(cards) > 2 else cards
        context.bind_objects(plan, ctx, 'receipt_returns', picked)
        context.bind_objects(plan, ctx, 'receipt_bottom', [c for c in cards if c not in picked])
        steps = [{'do': 'return_card', 'who': 'ref:receipt_returns', 'to': 'battlefield'}, {'do': 'to_library', 'who': 'ref:receipt_bottom', 'place': 'bottom'}]
    elif kind == 'pair':
        pool = [c.id for c in plan.state.cards.values() if c.zone == ctx['controller'] + ':graveyard']
        context.bind_objects(plan, ctx, 'receipt_pair', pool)
        steps = [{'do': 'return_choice', 'who': 'ref:receipt_pair', 'n': len(pool), 'upto': True, 'total_mv': sum(ctx.get('dice') or []), 'to': 'hand'}, {'do': 'exile', 'who': 'self_stack'}]
    elif kind == 'clowns_prepare':
        steps = [{**_native('Create a 1/1 white Clown Robot artifact creature token.')[0], 'n': 2}, {'do': 'roll', 'sides': 6, 'count': 1}, {'do': 'random_receipt', 'kind': 'clowns'}]
    elif kind == 'clowns':
        n = sum(c.zone.endswith(':battlefield') and c.controller == ctx['controller'] and plan.ch(c).is_creature and 'Robot' in plan.ch(c).subtypes for c in plan.state.cards.values())
        if result <= n:
            steps = _native('Create a 1/1 white Clown Robot artifact creature token.')
    elif kind == 'fly':
        from app.game.rules_state import DecisionOption
        from app.rules.plan import decide

        decide(plan, player=ctx['controller'], kind='choose_one', prompt='Have this artifact become a creature until end of turn?',
               options=[DecisionOption(id='yes', label='Yes'), DecisionOption(id='no', label='No')], min_choices=1, max_choices=1,
               resume={'step': 'receipt_fly', 'ctx': ctx, 'result': result})
        return False
    elif kind == 'rift':
        cards = effects._cards(plan, ctx, 'target')
        for cid in cards:
            card = plan.state.cards[cid]
            size = len(plan.state.zones.get(card.owner + ':library', []))
            plan.do({'type': 'move', 'card_ids': [cid], 'to': {'player': card.owner, 'zone': 'library'}, 'index': min(result, size)}, actor=ctx['controller'])
    coin_recipes.insert(ctx, steps)
    return True


def resume_fly(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import coin_recipes, effects

    ctx = d.resume['ctx']
    if chosen == ['yes']:
        n = d.resume['result']
        coin_recipes.insert(ctx, _native(f'Until end of turn, ~ becomes a {n}/{n} Insect artifact creature with flying.'))
    effects.continue_effects(plan, ctx)


def resume_boarding(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import coin_recipes, effects

    ctx = d.resume['ctx']
    steps: list[dict[str, Any]]
    if chosen == ['yes']:
        if d.resume['kind'] == 'boarding':
            plan.rules.once_per_turn[d.resume['key']] = plan.state.turn.number
            steps = [{'do': 'look_top', 'n': 1, 'player': 'you', 'reveal': True}, {'do': 'random_receipt', 'kind': 'boarding_revealed'}]
        else:
            steps = [{'do': 'exile', 'who': 'event', 'as': 'receipt_boarding_exile'},
                     {'do': 'grant_play', 'who': 'ref:receipt_boarding_exile', 'play': True, 'cast': True, 'until': 'end_of_turn', 'optional': True}]
        coin_recipes.insert(ctx, steps)
    effects.continue_effects(plan, ctx)


PRIMITIVES = {'random_receipt': receipt}
RESUME = {'receipt_fly': resume_fly, 'receipt_boarding': resume_boarding}
