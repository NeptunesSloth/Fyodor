"""Finite original library packets use native reveal, exile and entry continuations."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

AUSPICIOUS = ('Whenever ~ mutates, exile cards from the top of your library until you exile X permanent cards, '
              'where X is the number of times ~ has mutated. Put those permanent cards onto the battlefield.')
ILLUNA = ('Whenever ~ mutates, exile cards from the top of your library until you exile a nonland permanent card. '
          'Put that card onto the battlefield or into your hand.')
EMPTY = ('Sacrifice X Zombies, then reveal cards from the top of your library until you reveal a number of Zombie creature cards '
         'equal to the number of Zombies sacrificed this way. Put those cards onto the battlefield and the rest on the bottom '
         'of your library in a random order.')
AURORA = ('When ~ enters, reveal cards from the top of your library until you reveal X permanent cards, '
          'where X is the number of colors among permanents you control. Put any number of those permanent cards onto the '
          'battlefield, then put the rest of the revealed cards on the bottom of your library in a random order.')

BELZENLOK = ("When ~ enters, exile cards from the top of your library until you exile a nonland card, then put that card "
             "into your hand. If the card's mana value is 4 or greater, repeat this process. ~ deals 1 damage to you for each "
             "card put into your hand this way.")

VENTURE = ('Exile cards from the top of your library until you exile a land card. Put that card onto the battlefield and '
           'the rest on the bottom of your library in a random order. Exile ~ with three time counters on it.')
CAPSTONE = ('Exile cards from the top of your library until you exile cards with total mana value 4 or greater. '
            'You may cast any number of spells from among them without paying their mana costs.')


def _selector(kind: str) -> str:
    from app.rules import selectors

    found = selectors.parse(kind)
    assert found is not None
    return found.key()


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name).replace('this creature', '~')
    if text == VENTURE:
        return {'kind': 'spell', 'target': None, 'effects': [
            {'do': 'library_packet101', 'mode': 'exile', 'as': 'packet101', 'hits': 'ref:packet_hits101', 'sel': _selector('land card'), 'need': 1},
            {'do': 'return_card', 'who': 'ref:packet_hits101', 'to': 'battlefield', 'under': 'you'},
            {'do': 'packet_rest101', 'who': 'ref:packet101'}, {'do': 'rest_looked', 'to': 'bottom_random'},
            {'do': 'spell_self_move', 'to': 'exile', 'counters': {'time': 3}}]}
    if text == CAPSTONE:
        return {'kind': 'spell', 'target': None, 'effects': [
            {'do': 'library_packet101', 'mode': 'exile', 'as': 'packet101', 'hits': 'ref:packet_hits101', 'sel': _selector('card'), 'need': 4, 'mv_sum': True},
            {'do': 'packet_cast101', 'who': 'ref:packet101'}]}
    if text in (AUSPICIOUS, ILLUNA):
        native = scripts.define(replace(ability, text='Whenever this creature mutates, draw a card.'), ch)
        if native is None:
            return None
        kind = 'permanent card' if text == AUSPICIOUS else 'nonland permanent card'
        packet = {'do': 'library_packet101', 'mode': 'exile', 'as': 'packet101', 'hits': 'ref:packet_hits101', 'sel': _selector(kind),
                  'need': {'mutated': 1} if text == AUSPICIOUS else 1}
        following = ({'do': 'return_card', 'who': 'ref:packet_hits101', 'to': 'battlefield', 'under': 'you'}
                     if text == AUSPICIOUS else {'do': 'packet_destination101', 'who': 'ref:packet_hits101'})
        return {**native, 'effects': [packet, following]}
    if text == BELZENLOK:
        native = scripts.define(replace(ability, text='When this creature enters, draw a card.'), ch)
        return {**native, 'effects': [{'do': 'belzenlok_packet101'}]} if native is not None else None
    if text == AURORA:
        native = scripts.define(replace(ability, text='When this creature enters, draw a card.'), ch)
        if native is None:
            return None
        sel = _selector('permanent card')
        return {**native, 'effects': [
            {'do': 'library_packet101', 'mode': 'reveal', 'sel': sel, 'colors': True},
            {'do': 'pick_looked', 'n': 5, 'sel': sel, 'optional': True, 'to': 'battlefield'},
            {'do': 'rest_looked', 'to': 'bottom_random'}]}
    return None


def parse(body: str) -> Any:
    if body.strip() != EMPTY:
        return None
    from app.rules import scripts

    prefix = scripts.parse_effects('Sacrifice X Zombies.')
    assert prefix is not None and len(prefix[0]) == 1
    sel = _selector('Zombie creature card')
    return ([{**prefix[0][0], 'as': 'sacrificed101'},
             {'do': 'library_packet101', 'mode': 'reveal', 'sel': sel, 'need': {'ref_count': 'sacrificed101', 'this_way': 'sacrificed'}},
             {'do': 'pick_looked', 'which': 'all', 'sel': sel, 'to': 'battlefield'},
             {'do': 'rest_looked', 'to': 'bottom_random'}], None, False)


def packet(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, selectors, values

    player = ctx['controller']
    need = (len({color for c in plan.state.cards.values() if c.controller == player and c.zone.endswith(':battlefield')
                 for color in plan.ch(c).colors}) if e.get('colors') else values.evaluate(plan, ctx, e['need']))
    if e['mode'] == 'reveal':
        return effects.look_top(plan, ctx, {'do': 'look_top', 'player': 'you', 'until': e['sel'], 'need': need,
                                             'n': 0, 'reveal': True, 'exact_look': True})
    kind = selectors.from_key(e['sel'])
    prefix: list[str] = []
    hits = 0
    if need > 0:
        for cid in effects._library(plan, player):
            prefix.append(cid)
            card = plan.state.cards[cid]
            hits += int(plan.ch(card).mana_value) if e.get('mv_sum') else int(selectors.matches(plan, kind, card, plan.ch(card), player, ctx.get('source_card')))
            if hits >= need:
                break
    binding = e.get('as', 'packet101')
    effects.exile_top(plan, ctx, {'do': 'exile_top', 'n': len(prefix), 'player': 'you', 'as': binding})
    matching = [cid for cid in effects._cards(plan, ctx, 'ref:' + binding)
                if plan.state.cards[cid].zone == player + ':exile'
                and selectors.matches(plan, kind, plan.state.cards[cid], plan.ch(plan.state.cards[cid]), player, ctx.get('source_card'))]
    context.bind_objects(plan, ctx, e.get('hits', 'ref:packet_hits101').removeprefix('ref:'), matching)
    return True


def destination(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    if not effects._cards(plan, ctx, e['who']):
        return True
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Put the exiled card onto the battlefield or into your hand',
           options=[DecisionOption(id='battlefield', label='Onto the battlefield'), DecisionOption(id='hand', label='Into your hand')],
           resume={'step': 'packet_destination101', 'ctx': ctx, 'who': e['who']})
    return False


def resume_destination(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume['ctx']
    ctx['effects'][ctx['next']:ctx['next']] = [{'do': 'return_card', 'who': d.resume['who'], 'to': chosen[0], 'under': 'you'}]
    effects.continue_effects(plan, ctx)


def _belzenlok_next(ctx: dict[str, Any]) -> None:
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do': 'library_packet101', 'mode': 'exile', 'sel': _selector('nonland card'), 'need': 1,
         'as': 'belz_packet101', 'hits': 'ref:belz_hits101'},
        {'do': 'belzenlok_hit101'}]


def _belzenlok_finish(ctx: dict[str, Any]) -> None:
    total = ctx.pop('belzenlok101')['total']
    if total:
        ctx['effects'][ctx['next']:ctx['next']] = [{'do': 'damage', 'who': 'you', 'n': total}]


def belzenlok(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    ctx['belzenlok101'] = {'total': 0}
    _belzenlok_next(ctx)
    return True


def belzenlok_hit(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    hits = effects._cards(plan, ctx, 'ref:belz_hits101')
    if not hits:
        _belzenlok_finish(ctx)
        return True
    card = plan.state.cards[hits[0]]
    ctx['belzenlok101']['hit'] = {'card': card.id, 'object': plan.oid(card), 'value': plan.ch(card).mana_value}
    # This must be a native separate instruction: run_body's 903.9b pre-probe
    # can pause before it and serialize the original hit/count before any repeat.
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do': 'return_card', 'who': 'ref:belz_hits101', 'to': 'hand'}, {'do': 'belzenlok_after101'}]
    return True


def belzenlok_after(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    saved = ctx['belzenlok101']
    hit = saved.pop('hit')
    card = plan.state.cards.get(hit['card'])
    saved['total'] += int(card is not None and plan.oid(card) != hit['object'] and card.zone == ctx['controller'] + ':hand')
    if hit['value'] >= 4 and effects._library(plan, ctx['controller']):
        _belzenlok_next(ctx)
    else:
        _belzenlok_finish(ctx)
    return True


def rest_packet(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    ctx['looked_owner'] = ctx['controller']
    ctx['looked_zone'] = 'exile'
    ctx['looked'] = effects._cards(plan, ctx, e['who'])
    ctx['looked_objects'] = {cid: plan.oid(plan.state.cards[cid]) for cid in ctx['looked']}
    return True


def cast_packet(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, permissions

    return permissions.free_cast(plan, ctx, {'do': 'free_cast', 'zone': 'that', 'who': e['who'],
                                           'filter': None, 'optional': True, 'mv': None,
                                           'n': max(1, len(effects._cards(plan, ctx, e['who'])))})


PRIMITIVES = {'library_packet101': packet, 'packet_destination101': destination, 'belzenlok_packet101': belzenlok, 'belzenlok_hit101': belzenlok_hit, 'belzenlok_after101': belzenlok_after, 'packet_rest101': rest_packet, 'packet_cast101': cast_packet}
RESUME = {'packet_destination101': resume_destination}
