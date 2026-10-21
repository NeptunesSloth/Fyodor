"""Exact native life instructions with original-object cohorts."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import conditions, scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == '0: If you have at least 15 life more than your starting life total, exile ~ and each artifact and creature your opponents control.':
        base = scripts.define(replace(ability, text='0: You gain 1 life.'), ch)
        cond = conditions.parse('you have at least 15 life more than your starting life total')
        assert cond is not None
        return {**base, 'effects': [{'do': 'only_if', 'cond': cond, 'skip': 1},
                                   {'do': 'life44_sequence', 'mode': 'ajani'}]} if base else None
    if text == '−9: Create a number of 1/1 black Vampire Knight creature tokens with lifelink equal to the highest life total among all players.':
        base = scripts.define(replace(ability, text='−9: Create a 1/1 black Vampire Knight creature token with lifelink.'), ch)
        return {**base, 'effects': [{'do': 'life44_sequence', 'mode': 'sorin'}]} if base else None
    if text == 'When ~ enters, if your life total is less than your starting life total, it becomes equal to your starting life total.':
        base = scripts.define(replace(ability, text='When ~ enters, if your life total is less than your starting life total, you gain 1 life.'), ch)
        return {**base, 'effects': [{'do': 'gain_life', 'who': 'you', 'n': {'below_start': 1}}]} if base else None
    if text == "I — The Ring tempts you, then each player mills cards equal to your Ring-bearer's power.":
        base = scripts.define(replace(ability, text='I — The Ring tempts you. Each player mills one card.'), ch)
        return {**base, 'effects': [*base['effects'][:-1], {'do': 'life44_sequence', 'mode': 'ring_mill'}]} if base else None
    if text == "III — Each opponent loses 1 life for each creature card in that player's graveyard.":
        base = scripts.define(replace(ability, text='III — Each opponent loses 1 life.'), ch)
        return {**base, 'effects': [{'do': 'life44_sequence', 'mode': 'ring_drain'}]} if base else None
    if text == 'Draw two cards, then discard a card and you lose 2 life. Create X tapped 2/2 black Zombie Druid creature tokens, where X is the number of cards that were put into your graveyard from your hand or library this turn.':
        base = scripts.define(replace(ability, text='Draw two cards. Discard a card. You lose 2 life. Create a tapped 2/2 black Zombie Druid creature token.'), ch)
        return {**base, 'effects': [*base['effects'][:-1], {'do': 'life44_sequence', 'mode': 'welcome_dead'}]} if base else None
    return None


def run(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import context, effects, scripts, selectors

    steps: list[dict[str, Any]]
    if effect['mode'] == 'ajani':
        selected = selectors.candidates(plan, selectors.Selector(types=('Artifact', 'Creature'), controller='opponent'), ctx['controller'])
        selected = list(dict.fromkeys([*effects._cards(plan, ctx, 'self'), *selected]))
        context.bind_objects(plan, ctx, 'life44_ajani', selected)
        steps = [{'do': 'exile', 'who': 'ref:life44_ajani'}]
    elif effect['mode'] == 'sorin':
        quantity = max([0, *[plan.state.players[p].life for p in plan.live()]])
        native = scripts.parse_effects('Create a 1/1 black Vampire Knight creature token with lifelink.')
        assert native is not None
        steps = [{**native[0][0], 'n': quantity}]
    elif effect['mode'] == 'ring_mill':
        from app.rules import designations

        bearer = designations._bearer_card(plan, ctx['controller'])
        amount = max(0, (plan.ch(bearer).pt or (0, 0))[0]) if bearer is not None else 0
        steps = [{'do': 'mill', 'who': 'each_player', 'n': amount}]
    elif effect['mode'] == 'ring_drain':
        counts = {pid: sum(plan.ch(plan.state.cards[cid]).is_creature
                           for cid in plan.state.zones.get(pid + ':graveyard', []))
                  for pid in plan.live() if pid != ctx['controller']}
        steps = [{'do': 'lose_life', 'who': 'each_opponent', 'n': 0, 'counts': counts}]
    elif effect['mode'] == 'welcome_dead':
        from app.game.rules_state import DecisionOption
        from app.rules import history
        from app.rules.plan import decide

        turn = plan.state.turn.number
        if plan.rules.graveyard_history_from_turn is None:
            plan.rules.graveyard_history_from_turn = turn + 1
        arrivals = [a for a in history.log_for(plan).entered_graveyard if a.owner == ctx['controller']]
        known = turn >= plan.rules.graveyard_history_from_turn and all(a.from_zone is not None for a in arrivals)
        if not known:
            decide(plan, player=ctx['controller'], kind='manual_resolution',
                   prompt='Earlier graveyard entries are unavailable in this save. Resolve the Zombie Druid creation by hand, then press Done.',
                   options=[DecisionOption(id='done', label='Done')],
                   resume={'step': 'life44_unknown_history', 'ctx': ctx})
            return False
        amount = sum(a.from_zone in ('hand', 'library') and (card := plan.state.cards.get(a.card)) is not None
                     and card.card_id is not None and not card.is_token and card.ability is None for a in arrivals)
        native = scripts.parse_effects('Create a tapped 2/2 black Zombie Druid creature token.')
        assert native is not None
        steps = [{**native[0][0], 'n': amount}]
    else:
        raise ValueError('Unknown life44 sequence')
    ctx['effects'][ctx['next']:ctx['next']] = steps
    return True


PRIMITIVES = {'life44_sequence': run}


def resume_unknown_history(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if chosen != ['done']:
        raise ActionError('Press Done after resolving the token creation by hand')
    effects.continue_effects(plan, decision.resume['ctx'])


RESUME = {'life44_unknown_history': resume_unknown_history}
