"""Exact life instructions built from native movement and casting permissions."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import player_zones, scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text == 'At the beginning of each combat, choose first strike, vigilance, or lifelink. Creatures you control gain that ability until end of turn.':
        native = scripts.define(replace(ability, text='At the beginning of each combat, creatures you control gain vigilance until end of turn.'), ch)
        return {**native, 'effects': [{'do': 'life_sequence43_keyword'}]} if native else None
    if text == 'Target opponent sacrifices a creature of their choice, discards three cards, then loses 5 life. You return a creature card from your graveyard to your hand, draw three cards, then gain 5 life.':
        sequence = scripts.parse_effects('Target opponent sacrifices a creature of their choice. That player discards three cards. That player loses 5 life. Return a creature card from your graveyard to your hand. Draw three cards. You gain 5 life.')
        return {'kind': 'spell', 'effects': sequence[0], **scripts.target_fields(sequence[1])} if sequence else None
    if text == "Choose target permanent card in your graveyard. If it has mana value 3 or less, you may put it onto the battlefield. If you don't put it onto the battlefield, put it into your hand.":
        base = scripts.define(replace(ability, text='Return target permanent card from your graveyard to your hand.'), ch)
        if base is None:
            return None
        return {**base, 'effects': [
            {'do': 'life43_cosmic_preflight'},
            {'do': 'may_rest', 'skip': 1, 'label': 'Put that card onto the battlefield'},
            {'do': 'return_card', 'who': 'target', 'to': 'battlefield', 'did': 'life43_cosmic_paid'},
            {'do': 'only_if', 'cond': {'not': {'succeeded': 'life43_cosmic_paid'}}, 'skip': 1},
            {'do': 'return_card', 'who': 'target', 'to': 'hand'},
        ]}
    offering = {
        'Choose an opponent. You and that player each create three 1/1 white Spirit creature tokens with flying.': 'tokens',
        'Choose an opponent. You gain 2 life for each creature you control and that player gains 2 life for each creature they control.': 'life',
    }
    if text in offering:
        return {'kind': 'spell', 'target': None, 'effects': [{'do': 'life43_offering', 'mode': offering[text]}]}
    if text == 'You may cast this card from your graveyard.':
        return {'kind': 'static', 'static': 'permission', 'zone': 'graveyard',
                'once': False, 'flash': False, 'self': True, 'play': False,
                'cast': True, 'filter': None, 'effects': []}
    if text == "Exile all permanents. Exile all cards from all hands and graveyards. Each player's life total becomes 1.":
        return {'kind': 'spell', 'target': None, 'effects': [
            {'do': 'exile', 'who': selectors.Selector().key()},
            {'do': 'exile', 'who': player_zones.key(['hand', 'graveyard'], 'each_player')},
            {'do': 'set_life', 'who': 'each_player', 'n': 1},
        ]}
    return None


def choose_keyword(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Choose an ability',
           options=[DecisionOption(id=k, label=k) for k in ('first strike', 'vigilance', 'lifelink')],
           resume={'step': 'life43_keyword', 'ctx': ctx})
    return False


def resume_keyword(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects, scripts

    if len(chosen) != 1 or chosen[0] not in ('first strike', 'vigilance', 'lifelink'):
        raise ActionError('Choose one ability')
    native = scripts.parse_effects('Creatures you control gain ' + chosen[0] + ' until end of turn.')
    assert native is not None
    ctx = decision.resume['ctx']
    ctx['effects'][ctx['next']:ctx['next']] = native[0]
    effects.continue_effects(plan, ctx)


def cosmic_preflight(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import attachments, context, effects, prohibitions

    context.bind_payment(ctx, 'life43_cosmic_paid', False)
    ids = effects._cards(plan, ctx, 'target')
    card = plan.state.cards[ids[0]] if len(ids) == 1 else None
    possible = card is not None and plan.ch(card).mana_value <= 3
    if card is not None and possible:
        possible = prohibitions.cant_enter(plan, card, card.owner) is None
        if possible and attachments.attach_kind(plan.ch(card)) == 'aura':
            possible = bool(attachments._entry_hosts(plan, card, {'card': card.id, 'player': card.owner, 'actor': ctx['controller']}))
    if not possible:
        ctx['next'] += 2
    return True


def offering(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    opponents = [pid for pid in plan.live() if pid != ctx['controller']]
    if not opponents:
        offering_result(plan, ctx, effect['mode'], None)
        return True
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Choose an opponent',
           options=[DecisionOption(id=pid, label=plan.name(pid)) for pid in opponents],
           resume={'step': 'life43_offering', 'ctx': ctx, 'mode': effect['mode']})
    return False


def offering_result(plan: Plan, ctx: dict[str, Any], mode: str, other: str | None) -> None:
    from app.rules import context, scripts

    players = [ctx['controller']] + ([other] if other is not None else [])
    if mode == 'tokens':
        context.bind_players(ctx, 'life43_offering_players', players)
        native = scripts.parse_effects('Create three 1/1 white Spirit creature tokens with flying.')
        assert native is not None and len(native[0]) == 1
        steps = [{**native[0][0], 'who': 'ref:life43_offering_players'}]
    else:
        counts = {pid: 2 * sum(c.controller == pid and c.zone.endswith(':battlefield') and plan.ch(c).is_creature
                              for c in plan.state.cards.values()) for pid in players}
        steps = [{'do': 'gain_life', 'who': 'each_player', 'n': 0, 'counts': counts}]
    ctx['effects'][ctx['next']:ctx['next']] = steps


def resume_offering(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx = decision.resume['ctx']
    if len(chosen) != 1 or chosen[0] not in plan.live() or chosen[0] == ctx['controller']:
        raise ActionError('Choose a current opponent')
    offering_result(plan, ctx, decision.resume['mode'], chosen[0])
    effects.continue_effects(plan, ctx)


PRIMITIVES = {'life_sequence43_keyword': choose_keyword, 'life43_cosmic_preflight': cosmic_preflight, 'life43_offering': offering}
RESUME = {'life43_keyword': resume_keyword, 'life43_offering': resume_offering}
