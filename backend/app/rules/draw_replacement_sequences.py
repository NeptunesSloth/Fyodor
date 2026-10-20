"""Scoped draw replacement bodies with frozen activation decisions (CR 121.6, 614.5)."""
from __future__ import annotations

import copy
from dataclasses import replace as dc_replace
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules import context
from app.rules.plan import Plan, decide


def norm(text: str) -> str:
    return ' '.join(text.lower().split()).rstrip('.')


_RECORDS = {
    "the next time you would draw a card this turn, each player returns a permanent they control to its owner's hand instead": 'wind',
    "the next time you would draw a card this turn, ~ deals 2 damage to any target instead": 'war',
    "the next time you would draw a card this turn, instead put a card you own from outside the game into your hand": 'ring',
    "the next time you would draw a card this turn, instead look at the top x cards of your library, put all but one of them on the bottom of your library in a random order, then draw a card. x can't be 0": 'lamp',
    "until end of turn, if target player would draw a card, instead that player skips that draw and you draw a card": 'plagiarize',
    "the next time they would draw a card this turn, instead they exile the top card of their library. they may play it this turn": 'urabrask',
}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    mode = _RECORDS.get(norm(body))
    if mode is None:
        return None
    target = None
    if mode in ('war', 'plagiarize'):
        native = scripts.parse_effects('~ deals 2 damage to any target.' if mode == 'war' else 'Target player gains 1 life.')
        assert native is not None
        target = native[1]
    return [{'do': 'draw_sequence_record', 'mode': mode}], target, False


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = norm(scripts.self_text(ability.text, ch.name))
    if text in (
        'each player may play lands and cast spells from among cards they exiled with ~ this turn',
        'each player may look at cards they exiled with ~, and they may play lands and cast spells from among those cards',
    ):
        return {'kind': 'static', 'static': 'draw_exile_play', 'mode': 'uba' if 'this turn' in text else 'shared', 'effects': []}
    static_modes = {
        "if a player would draw a card, they reveal it instead. then any other player may pay 2 life. if a player does, put that card into its owner's graveyard. otherwise, that player draws a card": 'weirding',
        "if a player would draw a card, that player exiles that card face up instead": 'uba',
        "if a player would draw a card, that player exiles the top card of one of their opponents' libraries face down instead": 'shared',
        "if a player would draw a card, instead they draw a card and reveal it. if it's a creature card, that player discards it unless they pay 3 life": 'crypt',
        "if a player would draw a card except the first one they draw in each of their draw steps, that player discards a card instead. if the player discards a card this way, they draw a card. if the player doesn't discard a card this way, they mill a card": 'chains',
        "if you would draw a card during your draw step, instead you may skip that draw. if you do, until your next turn, you can't be attacked except by creatures with flying and/or islandwalk": 'sanctuary',
        "as long as ~ has six or more quest counters on it, if you would draw a card, you may instead search your library for a card, put that card into your hand, then shuffle": 'archmage',
    }
    if (mode := static_modes.get(text)) is not None:
        match: dict[str, Any] = {'who': 'you'} if mode in ('sanctuary', 'archmage') else {}
        if mode == 'sanctuary':
            match['draw_step_only'] = True
        if mode == 'chains':
            match['not_first_in_draw_step'] = True
        result: dict[str, Any] = {'kind': 'static', 'static': 'replace', 'event': 'draw', 'match': match,
                                 'op': {'do': 'body', 'affected_controller': True,
                                        'effects': [{'do': 'draw_sequence_body', 'mode': mode}]}, 'effects': []}
        if mode in ('sanctuary', 'archmage'):
            result['op']['optional'] = True
        if mode == 'archmage':
            result['static_if'] = [{'value': {'counters': 'quest', 'on': 'self'}, 'op': '>=', 'n': 6}]
        return result
    if text == 'at the beginning of each end step, if you drew two or more cards this turn, you may put a quest counter on ~':
        native = scripts.define(dc_replace(ability, text='At the beginning of each end step, you may put a quest counter on ~.'), ch)
        condition = {'value': {'turn_history': 'drew'}, 'op': '>=', 'n': 2}
        return {**native, 'if': condition, 'effects': [{'do': 'only_if', 'cond': condition, 'skip': 1}, *native['effects']]} if native else None
    if text == '{x}, {t}: ' + next(k for k, v in _RECORDS.items() if v == 'lamp'):
        native = scripts.define(dc_replace(ability, text='{X}, {T}: You gain 1 life.'), ch)
        return {**native, 'effects': [{'do': 'draw_sequence_record', 'mode': 'lamp'}], 'x_min': 1} if native else None
    return None


def insert(ctx: dict[str, Any], effects: list[dict[str, Any]]) -> bool:
    ctx['effects'][ctx['next']:ctx['next']] = effects
    return True


def record(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, replace, scripts

    mode = e['mode']
    if mode == 'plagiarize':
        players = effects._players(plan, ctx, 'target')
        if players:
            replace.add_record(plan, event='draw', match={'player': players[0]}, op={'do': 'steal'},
                               controller=ctx['controller'], source=ctx.get('source_object'), source_card=ctx.get('source_card'), label=ctx['name'])
        return True
    if mode == 'wind':
        parsed = scripts.parse_effects("Each player returns a permanent they control to its owner's hand.")
        assert parsed is not None
        body = parsed[0]
    elif mode == 'war':
        body = [{'do': 'damage', 'who': 'target', 'n': 2}]
    elif mode == 'ring':
        body = [{'do': 'outside_permission'}]
    elif mode == 'lamp':
        body = [{'do': 'look_top', 'n': int(ctx.get('x') or 0), 'player': 'you'},
                {'do': 'pick_looked', 'n': 1, 'to': 'choose'},
                {'do': 'rest_looked', 'to': 'bottom_random'}, {'do': 'draw', 'who': 'you', 'n': 1}]
    elif mode == 'urabrask':
        body = [{'do': 'exile_top', 'n': 1, 'player': 'you', 'as': 'draw_exiled'},
                {'do': 'grant_play', 'who': 'ref:draw_exiled', 'play': True, 'cast': True, 'until': 'end_of_turn'}]
    else:
        raise AssertionError(mode)
    who = effects._players(plan, ctx, 'event_player') if mode == 'urabrask' else [ctx['controller']]
    for player in who:
        replace.add_record(plan, event='draw', match={'player': player},
                           op={'do': 'body', 'effects': body, 'affected_controller': mode == 'urabrask', 'once': True,
                               'targets': copy.deepcopy(ctx.get('targets') or []), 'x': int(ctx.get('x') or 0)},
                           controller=ctx['controller'], source=ctx.get('source_object'), source_card=ctx.get('source_card'), label=ctx['name'])
    return True


def followup_drawn(plan: Plan, ctx: dict[str, Any], before: list[str], inherited: list[str]) -> list[str]:
    """121.6c: only actual draws unmodified within THIS instruction, never another replacement's cards."""
    log = plan.rules.turn_log
    pid = ctx['controller']
    excluded = set(before) | set(log.drawn_counted.get(pid, ()))
    expected = set(inherited)
    refs = [oid for oid in log.drawn.get(pid, ()) if oid not in excluded and oid in log.drawn_applied
            and set(log.drawn_applied[oid]) == expected]
    return [card.id for card in plan.state.cards.values()
            if card.zone == pid + ':hand' and plan.rules.object_id(card.id) in refs]


def body(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import scripts

    mode = e['mode']
    pid = ctx['controller']
    if mode == 'weirding':
        top = list(plan.state.zones.get(pid + ':library', [])[:1])
        context.bind_objects(plan, ctx, 'weirding_card', top)
        if top:
            plan.do({'type': 'reveal', 'card_ids': top}, actor=pid)
        return insert(ctx, [{'do': 'draw_sequence_stage', 'mode': 'weirding',
                             'payers': [p for p in plan.apnap() if p != pid]}])
    if mode == 'uba':
        return insert(ctx, exile_effects(ctx, pid, mode))
    if mode == 'shared':
        players = [p for p in plan.apnap() if p != pid and p in plan.live()]
        if not players:
            return True
        decide(plan, player=pid, kind='choose_one', prompt='Choose an opponent’s library',
               options=[DecisionOption(id=p, label=plan.name(p)) for p in players], min_choices=1, max_choices=1,
               resume={'step': 'draw_exile_library', 'ctx': ctx})
        return False
    if mode == 'sanctuary':
        plan.rules.replacements.append({'kind': 'draw_attack_gate', 'controller': pid, 'until': 'next_turn',
                                        'until_player': pid, 'turn': plan.state.turn.number})
        return True
    if mode == 'archmage':
        parsed = scripts.parse_effects('Search your library for a card, put that card into your hand, then shuffle.')
        assert parsed is not None
        return insert(ctx, parsed[0])
    if mode == 'chains':
        return insert(ctx, [{'do': 'discard', 'who': 'you', 'n': 1, 'as': 'draw_discard'},
                            {'do': 'draw_sequence_stage', 'mode': mode}])
    if mode == 'crypt':
        before = list(plan.rules.turn_log.drawn.get(pid, ()))
        return insert(ctx, [{'do': 'draw', 'who': 'you', 'n': 1},
                            {'do': 'draw_sequence_stage', 'mode': mode, 'before': before,
                             'inherited': list(ctx.get('repl_applied') or [])}])
    raise AssertionError(mode)


def stage(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    if e['mode'] == 'weirding':
        if e.get('asked') and context.succeeded(ctx, 'weirding_pay'):
            cards = context.objects(plan, ctx, 'weirding_card')
            if cards:
                plan.do({'type': 'move', 'card_ids': cards, 'to': {'zone': 'graveyard'}}, actor=ctx['controller'])
            return True
        payers = [p for p in e['payers'] if p in plan.live()]
        if not payers:
            return insert(ctx, [{'do': 'draw', 'who': 'you', 'n': 1}])
        return insert(ctx, [{'do': 'optional_payment', 'who': 'player:' + payers[0], 'cost': 'Pay 2 life', 'bind': 'weirding_pay'},
                            {'do': 'draw_sequence_stage', 'mode': 'weirding', 'payers': payers[1:], 'asked': True}])
    if e['mode'] == 'exile_permission':
        from app.rules import permissions

        cards = context.objects(plan, ctx, 'draw_exile')
        if e['source_mode'] == 'shared' and cards:
            plan.do({'type': 'reveal', 'card_ids': cards, 'to': [ctx['controller']]}, actor=ctx['controller'])
        return permissions.grant_play(plan, ctx, {'who': 'ref:draw_exile', 'play': True, 'cast': True, 'from_exile': True,
                                                  'until': 'end_of_turn' if e['source_mode'] == 'uba' else 'source_on_battlefield',
                                                  'when': {'draw_source_static': {'object': ctx.get('source_object'), 'mode': e['source_mode']}}})
    if e['mode'] == 'chains':
        was = (ctx.get('refs') or {}).get('draw_discard') or {}
        discarded = bool(was.get('was'))
        return insert(ctx, [{'do': 'draw' if discarded else 'mill', 'who': 'you', 'n': 1}])
    if e['mode'] == 'crypt':
        drawn = followup_drawn(plan, ctx, e['before'], e['inherited'])
        if not drawn:
            return True
        plan.do({'type': 'reveal', 'card_ids': drawn}, actor=ctx['controller'])
        if 'Creature' not in plan.ch(plan.state.cards[drawn[0]]).types:
            return True
        context.bind_objects(plan, ctx, 'crypt_drawn', drawn[:1])
        return insert(ctx, [{'do': 'optional_payment', 'who': 'you', 'cost': 'Pay 3 life', 'bind': 'crypt_pay'},
                            {'do': 'only_if', 'cond': {'succeeded': 'crypt_pay', 'negate': True}, 'skip': 1},
                            {'do': 'draw_sequence_stage', 'mode': 'crypt_discard'}])
    if e['mode'] == 'crypt_discard':
        drawn = context.objects(plan, ctx, 'crypt_drawn')
        return effects._discard_next(plan, ctx, 0, [], drawn)
    raise AssertionError(e['mode'])


def exile_effects(ctx: dict[str, Any], owner: str, mode: str) -> list[dict[str, Any]]:
    return [{'do': 'exile_top', 'player': 'player:' + owner, 'n': 1, 'face_down': mode == 'shared', 'as': 'draw_exile'},
            {'do': 'draw_sequence_stage', 'mode': 'exile_permission', 'source_mode': mode}]


def resume_library(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume['ctx']
    if chosen and chosen[0] in plan.live() and chosen[0] != ctx['controller']:
        insert(ctx, exile_effects(ctx, chosen[0], 'shared'))
    effects.continue_effects(plan, ctx)


def source_static(plan: Plan, condition: dict[str, Any]) -> bool:
    from app.rules import scripts

    return any(card.zone.endswith(':battlefield') and plan.in_game(card) and not plan.manual(card) and plan.oid(card) == condition.get('object')
               and any(d.get('static') == 'draw_exile_play' and d.get('mode') == condition['mode']
                       for d in scripts.definitions(plan.ch(card)).values()) for card in plan.state.cards.values())


PRIMITIVES = {'draw_sequence_record': record, 'draw_sequence_body': body, 'draw_sequence_stage': stage}
RESUME = {'draw_exile_library': resume_library}
