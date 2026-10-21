"""Exact packet authority and native resolution continuations.

Native movement, casting, payments, event history and delayed abilities own the
rules machinery. This module binds only actual objects and printed recipients.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules import context
from app.rules import exile_packet_continuations as packets
from app.rules.plan import Plan

BINDING = 'ref:exile_authority41'
_SPELLS = {
    "choose any number of target creatures, planeswalkers, and/or players. for each of them, exile the top card of your library, then ~ deals damage equal to that card's mana value to that permanent or player. you may play the exiled cards until the end of your next turn": 'soulfire',
    'exile target nonland permanent. you may cast that card for as long as it remains exiled, and you may spend colorless mana as though it were mana of any color to cast that spell': 'abstruse',
    "exile all opponents' graveyards. you may cast spells from among those cards this turn, and mana of any type can be spent to cast them. at the beginning of the next end step, if any of those cards remain exiled, return them to their owners' graveyards": 'mnemonic',
    'exile all the cards from your hand, then draw that many cards. until the end of your next turn, you may play cards exiled this way': 'hex',
    'exile the top card of your library. during your next turn, you may play that card': 'relay',
    "each opponent exiles the top card of their library. you may cast spells from among those cards this turn. if you cast a spell this way, pay life equal to that spell's mana value rather than pay its mana cost": 'xander',
    'reveal the top six cards of your library. an opponent exiles a nonland card from among them, then you put the rest into your hand. that opponent may cast the exiled card without paying its mana cost': 'allure',
    'look at the top five cards of your library. you may exile a creature card from among them. put the rest on the bottom of your library in a random order. you may cast the exiled card this turn. at the beginning of the next combat phase this turn, target creature you control deals damage equal to its power to up to one target creature you don\'t control': 'feral',
    "target opponent reveals their hand. you choose a nonland card from it. exile that card. if the gift was promised, you may cast that card for as long as it remains exiled, and mana of any type can be spent to cast it": 'heist',
    "target giant you control gets +2/+2 and gains trample until end of turn. whenever it deals combat damage to a player this turn, exile that many cards from the top of your library. until the end of your next turn, you may play those cards": 'fury',
}
_ABILITIES = {
    'whenever ~ attacks, exile the top five cards of your library. you may cast an artifact spell from among them this turn. if you do, it has affinity for artifacts': ('chiss', 'Whenever ~ attacks, you gain 1 life.'),
    'whenever ~ attacks, look at the top four cards of your library. you may exile a creature card from among them. put the rest on the bottom of your library in any order. for as long as that card remains exiled, you may cast it. that spell has undaunted': ('durnan', 'Whenever ~ attacks, you gain 1 life.'),
    'at the beginning of your end step, each player exiles the top card of their library. until your next end step, each player may play the card they exiled this way': ('rocco', 'At the beginning of your end step, you gain 1 life.'),
    "at the beginning of your end step, if you didn't play a card from exile this turn, create a tapped powerstone token": ('visions', 'At the beginning of your end step, you gain 1 life.'),
    'at the beginning of each of your postcombat main phases, if you attacked this turn, exile the top card of your library. until end of combat on your next turn, you may play that card': ('cannonade', 'At the beginning of each of your postcombat main phases, if you attacked this turn, you gain 1 life.'),
    "whenever one or more pirates you control deal damage to your opponents, exile the top card of each of those opponents' libraries. you may play those cards this turn, and you may spend mana as though it were mana of any color to cast those spells": ('breeches', 'Whenever one or more Pirates you control deal damage to your opponents, you gain 1 life.'),
    'exile a face-down permanent you control face up: you may play that card this turn': ('mist', 'Exile a face-down permanent you control face up: You gain 1 life.'),
    'when ~ dies, exile it. if you do, exile the top card of your library. until the end of your next turn, you may play one of those cards': ('flameskull', 'When ~ dies, you gain 1 life.'),
    "whenever ~ deals combat damage to a player, that player exiles cards from the top of their library until they exile a nonland card. you may cast that card by paying life equal to the spell's mana value rather than paying its mana cost": ('bismuth', 'Whenever ~ deals combat damage to a player, you gain 1 life.'),
    'whenever ~ deals combat damage to a player, exile cards from the top of your library until you exile a nonland card. you may cast that card by discarding a card rather than paying its mana cost': ('cruelclaw', 'Whenever ~ deals combat damage to a player, you gain 1 life.'),
}


def descriptor(mode: str) -> dict[str, Any]:
    return {'do': 'exile_authority41', 'mode': mode, 'binding': BINDING}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = packets.normalize(body)
    text = text.replace('if this spell was kicked,', 'if the gift was promised,')
    mnemonic_self = text.endswith('. exile ~') and _SPELLS.get(text[:-len('. exile ~')]) == 'mnemonic'
    mode = 'mnemonic' if mnemonic_self else _SPELLS.get(text)
    if mode is None:
        return None
    if mode == 'soulfire':
        from app.rules import language

        group = {'what': 'creature_planeswalker_or_player', 'min': 0, 'max': language.MAX_TARGETS}
        return [descriptor(mode)], [group], False
    if mode == 'abstruse':
        native = scripts.parse_effects('Exile target nonland permanent.')
        assert native is not None
        return [{**effect, 'as': packets.bind(descriptor(mode), '_packet')} for effect in native[0]] + [descriptor(mode)], native[1], False
    if mode == 'feral':
        prefix = body[:body.lower().index(' at the beginning')]
        native = scripts.parse_effects(prefix)
        assert native is not None
        return [*native[0], descriptor(mode)], None, False
    if mode == 'heist':
        native = scripts.parse_effects('Target opponent reveals their hand. You choose a nonland card from it. Exile that card.')
        assert native is not None
        return [*native[0][:-1], {**native[0][-1], 'as': packets.bind(descriptor(mode), '_packet')}, descriptor(mode)], native[1], False
    if mode == 'fury':
        native = scripts.parse_effects('Target Giant you control gets +2/+2 and gains trample until end of turn. Whenever it deals combat damage to a player this turn, you gain 1 life.')
        assert native is not None
        effects = [*native[0][:-1], {'do': 'deferred:exile_authority41', 'mode': 'fury_damage', 'binding': BINDING}]
        return effects, native[1], False
    return [descriptor(mode), *([{'do': 'exile', 'who': 'self'}] if mnemonic_self else [])], None, False


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind == 'spell':
        parsed = parse(scripts.self_text(ability.text, ch.name))
        if parsed is not None:
            return {'kind': 'spell', 'effects': parsed[0], **scripts.target_fields(parsed[1])}
    found = _ABILITIES.get(packets.normalize(scripts.self_text(ability.text, ch.name)))
    if found is None:
        return None
    mode, template = found
    native = scripts.define(replace(ability, text=template), ch)
    assert native is not None, mode
    if mode == 'visions':
        native = {**native, 'if': {'not': {'history': 'played_from_exile'}}}
    if mode == 'durnan':
        prefix = scripts.parse_effects('Look at the top four cards of your library. You may exile a creature card from among them. Put the rest on the bottom of your library in any order.')
        assert prefix is not None
        body = [dict(effect) for effect in prefix[0]]
        for effect in body:
            if effect.get('do') == 'pick_looked':
                effect['as'] = packets.bind(descriptor(mode), '_packet')
        return {**native, 'effects': [*body, descriptor(mode)]}
    return {**native, 'effects': [descriptor(mode)]}


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import conditions, effects, scripts

    you, mode = ctx['controller'], e['mode']
    if mode == 'soulfire':
        targets = [dict(target) for target in ctx.get('targets', [])]
        for target in targets:
            target['kind'] = 'player' if target['id'] in plan.state.players else 'card'
            target['player'] = target['id'] if target['kind'] == 'player' else plan.state.cards[target['id']].controller
        return soul_next(plan, ctx, {**e, 'remaining': targets, 'order': plan.apnap()})
    if mode == 'abstruse':
        return packets.insert(ctx, [packets.grant(e, until='permanent', spend='colorless_color')])
    if mode == 'chiss':
        packets.top_packet(plan, ctx, e, [you], 5)
        return packets.insert(ctx, [packets.grant(e, limit=1, spell_keywords=['affinity for artifacts'],
                                                filter=packets.selector('artifact spell', zones=('stack',)))])
    if mode == 'durnan':
        return packets.insert(ctx, [packets.grant(e, until='permanent', spell_keywords=['undaunted'])])
    if mode == 'mnemonic':
        ids = [cid for player in plan.apnap() if player != you
               for cid in plan.state.zones.get(player + ':graveyard', [])]
        effects.exile_cards(plan, ctx, {'as': packets.bind(e, '_packet')}, ids)
        return packets.insert(ctx, [packets.grant(e, spend='type'),
            {'do': 'delayed', 'when': {'kind': 'step', 'step': 'end', 'whose': 'next',
                                     'if': {'value': {'live_ref_count': packets.bind(e, '_packet'), 'zone': 'exile'}, 'op': '>', 'n': 0}}, 'n': 1},
            {'do': 'deferred:return_card', 'who': packets.ref(e, '_packet'), 'to': 'graveyard', 'under': 'owner'}])
    if mode == 'hex':
        ids = list(plan.state.zones.get(you + ':hand', []))
        effects.exile_cards(plan, ctx, {'as': packets.bind(e, '_packet')}, ids)
        n = len(packets.remaining(plan, ctx, e))
        return packets.insert(ctx, [{'do': 'draw', 'who': 'you', 'n': n},
                                    packets.grant(e, play=True, until='end_of_next_turn')])
    if mode == 'relay':
        packets.top_packet(plan, ctx, e, [you])
        return packets.insert(ctx, [packets.grant(e, play=True, until='end_of_next_turn',
                                                after_turn=plan.state.turn.number, when={'turn': 'yours'})])
    if mode == 'xander':
        packets.top_packet(plan, ctx, e, [player for player in plan.apnap() if player != you])
        return packets.insert(ctx, [packets.grant(e, free=True, life_mv=True)])
    if mode == 'rocco':
        packets.top_packet(plan, ctx, e, plan.apnap())
        return packets.insert(ctx, [packets.grant(e, play=True, owner=True, until='next_end_step', until_player=you)])
    if mode == 'visions':
        native = scripts.parse_effects('You create a tapped Powerstone token.')
        assert native is not None
        return packets.insert(ctx, native[0])
    if mode == 'cannonade':
        packets.top_packet(plan, ctx, e, [you])
        return packets.insert(ctx, [packets.grant(e, play=True, until='next_combat_end', until_player=you)])
    if mode == 'breeches':
        players = [player for player in (ctx.get('event') or {}).get('players') or [] if player in plan.live() and player != you]
        packets.top_packet(plan, ctx, e, list(dict.fromkeys(players)))
        return packets.insert(ctx, [packets.grant(e, play=True, spend='color')])
    if mode in ('bismuth', 'cruelclaw'):
        damaged = [player for player in (ctx.get('event') or {}).get('players') or [] if player in plan.live()]
        if mode == 'bismuth' and not damaged:
            return True
        owner = damaged[0] if mode == 'bismuth' else you
        packets.until_packet(plan, ctx, e, owner, packets.selector('nonland card', zones=('library',)))
        return packets.insert(ctx, [packets.offer(e, '_found', effect_alternative='life_mv' if mode == 'bismuth' else 'discard')])
    if mode == 'mist':
        ids = effects._cards(plan, ctx, 'cost:exiled')
        context.bind_objects(plan, ctx, packets.bind(e, '_packet'), ids)
        return packets.insert(ctx, [packets.grant(e, play=True)])
    if mode == 'flameskull':
        ids = [cid for cid in context.objects(plan, ctx, context.EVENT_NEW)
               if cid == ctx.get('source_card') and plan.state.cards[cid].zone.endswith(':graveyard')]
        if not ids:
            return True
        effects.exile_cards(plan, ctx, {'as': packets.bind(e, '_self')}, ids)
        if not packets.remaining(plan, ctx, e, '_self'):
            return True
        packets.top_packet(plan, ctx, e, [you])
        ids = [*packets.remaining(plan, ctx, e, '_self'), *packets.remaining(plan, ctx, e)]
        context.bind_objects(plan, ctx, packets.bind(e, '_packet'), ids)
        return packets.insert(ctx, [packets.grant(e, play=True, until='end_of_next_turn', limit=1)])
    if mode == 'heist':
        if not conditions.holds(plan, ctx, {'object': 'self', 'cast': {'kicked': True}}):
            return True
        ids = packets.remaining(plan, ctx, e)
        context.bind_objects(plan, ctx, packets.bind(e, '_packet'),
                             [cid for cid in ids if plan.state.cards[cid].zone.endswith(':exile')])
        return packets.insert(ctx, [packets.grant(e, until='permanent', spend='type')])
    if mode == 'feral':
        native = scripts.parse_effects("Target creature you control deals damage equal to its power to up to one target creature you don't control.")
        assert native is not None
        return packets.insert(ctx, [
            {'do': 'delayed', 'when': {'kind': 'step', 'step': 'begin_combat', 'whose': 'next'},
             'n': 1, 'this_turn': True, 'targets': native[1]},
            {'do': 'deferred:damage', 'who': 'watch_target:1', 'src': 'watch_target:0', 'n': {'power': 'watch_target:0'}}])
    if mode == 'fury_damage':
        n = max(0, int((ctx.get('event') or {}).get('amount') or 0))
        packets.top_packet(plan, ctx, e, [you], n)
        return packets.insert(ctx, [packets.grant(e, play=True, until='end_of_next_turn')])
    if mode == 'allure':
        effects.look_top(plan, ctx, {'n': 6, 'player': 'you', 'reveal': True})
        context.bind_objects(plan, ctx, packets.bind(e, '_packet'), list(ctx.get('looked') or []))
        opponents = [player for player in plan.apnap() if player != you]
        if not opponents:
            return packets.insert(ctx, [{'do': 'return_card', 'who': packets.ref(e, '_packet'), 'to': 'hand', 'under': 'owner'}])
        if len(opponents) == 1:
            return allure_offer(plan, ctx, e, opponents[0])
        effects.decide(plan, player=you, kind='choose_one', prompt='Choose an opponent to exile a revealed card',
                       options=[DecisionOption(id=player, label=plan.name(player)) for player in opponents],
                       resume={'step': 'exile_authority41_opponent', 'ctx': ctx, 'e': e})
        return False
    raise AssertionError(mode)


def soul_next(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    remaining = e.get('remaining', [])
    group = next(([target for target in remaining if target['player'] == player]
                  for player in e['order'] if any(target['player'] == player for target in remaining)), [])
    if not group:
        return True
    if len(group) == 1:
        return soul_chosen(plan, ctx, e, group[0]['id'])
    effects.decide(plan, player=ctx['controller'], kind='choose_one', prompt='Choose the next target in this player’s group',
                   options=[DecisionOption(id=target['id'], label=plan.name(target['id']) if target['kind'] == 'player' else plan.state.cards[target['id']].name,
                                           card_id=target['id'] if target['kind'] != 'player' else None) for target in group],
                   resume={'step': 'exile_authority41_soul', 'ctx': ctx, 'e': e})
    return False


def soul_chosen(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], chosen: str) -> bool:
    target = next(target for target in e['remaining'] if target['id'] == chosen)
    packet = packets.top_packet(plan, ctx, e, [ctx['controller']])
    n = int(plan.ch(plan.state.cards[packet[0]]).mana_value) if packet else 0
    if target['kind'] == 'player':
        who = 'player:' + chosen
    else:
        context.bind_objects(plan, ctx, packets.bind(e, '_recipient'), [chosen])
        who = packets.ref(e, '_recipient')
    after = {**e, 'do': 'exile_authority41_soul', 'remaining': [t for t in e['remaining'] if t['id'] != chosen]}
    return packets.insert(ctx, [packets.grant(e, play=True, until='end_of_next_turn'),
                                {'do': 'damage', 'who': who, 'n': n}, after])


def resume_soul(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = decision.resume['ctx'], decision.resume['e']
    soul_chosen(plan, ctx, e, chosen[0])
    effects.continue_effects(plan, ctx)


def allure_offer(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], opponent: str) -> bool:
    ids = context.objects(plan, ctx, packets.bind(e, '_packet'))
    nonlands = [cid for cid in ids if not plan.ch(plan.state.cards[cid]).is_land]
    context.bind_objects(plan, ctx, packets.bind(e, '_nonlands'), nonlands)
    return packets.insert(ctx, [{'do': 'as_player', 'player': opponent},
        {'do': 'return_choice', 'who': packets.ref(e, '_nonlands'), 'to': 'exile', 'under': 'owner',
         'n': 1, 'upto': False, 'label': 'nonland card', 'as': packets.bind(e, '_found')},
        {'do': 'return_card', 'who': packets.ref(e, '_packet'), 'to': 'hand', 'under': 'owner'},
        packets.offer(e, '_found'), {'do': 'as_player_end'}])


def resume_opponent(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = decision.resume['ctx'], decision.resume['e']
    allure_offer(plan, ctx, e, chosen[0])
    effects.continue_effects(plan, ctx)


PRIMITIVES = {'exile_authority41': run, 'exile_authority41_soul': soul_next}
RESUME = {'exile_authority41_opponent': resume_opponent, 'exile_authority41_soul': resume_soul}
