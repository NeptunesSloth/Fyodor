"""Original permanent cohorts and ordered native reveal/entry instructions."""
from __future__ import annotations

from typing import Any

DIVERGENT = ('Exile two target creatures. For each of those creatures, its controller reveals cards from the top of their library '
             'until they reveal a creature card, puts that card onto the battlefield, then shuffles the rest into their library.')
CHAOS = ('Exile any number of target creatures controlled by different players. For each creature exiled this way, its controller reveals cards from the top of their '
         'library until they reveal a creature card, puts that card onto the battlefield, then puts the rest on the bottom of their library in a random order.')  # (wave 110C)
REALITY = ('Put target permanent you own on the bottom of your library. Reveal cards from the top of your library until you reveal '
           'a card that shares a card type with that permanent. Put that card onto the battlefield and the rest on the bottom of '
           'your library in a random order.')
CREATIVITY = ('Destroy X target artifacts and/or creatures. For each permanent destroyed this way, its controller reveals cards '
              'from the top of their library until an artifact or creature card is revealed and exiles that card. Those players '
              'put the exiled cards onto the battlefield, then shuffle.')
CHAOTIC = ('Exile up to one target artifact, up to one target creature, up to one target enchantment, up to one target planeswalker, and/or up to one target land. '
           'For each permanent exiled this way, its controller reveals cards from the top of their library until they reveal a card that shares a card type with it, '
           'puts that card onto the battlefield, then shuffles.')  # (wave 110A: Chaotic Transformation, ruling 2022-09-09)
SYNTHETIC = ('Exile all creatures you control. At the beginning of the next end step, reveal cards from the top of your library '
             'until you reveal that many creature cards, put all creature cards revealed this way onto the battlefield, then '
             'shuffle the rest of the revealed cards into your library.')


def _selector(phrase: str) -> str:
    from app.rules import selectors

    found = selectors.parse(phrase)
    assert found is not None
    return found.key()


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    table = {DIVERGENT: ('divergent', 'Exile two target creatures.'),
             CHAOS: ('chaos', 'Exile any number of target creatures controlled by different players.'),
             REALITY: ('reality', 'Put target permanent you own on the bottom of your library.'),
             CREATIVITY: ('creativity', 'Destroy X target artifacts and/or creatures.'),
             CHAOTIC: ('chaotic', CHAOTIC.partition(' For each')[0].replace('and/or', 'and')),
             SYNTHETIC: ('synthetic', 'Exile all creatures you control.')}
    if text not in table:
        return None
    mode, prefix = table[text]
    native = scripts.parse_effects(prefix)
    assert native is not None and (len(native[0]) == 1 or mode == 'chaotic')
    mover = native[0][0] if mode != 'chaotic' else {**native[0][0], 'who': 'all_targets'}  # (wave 110A: all five optional targets at once, 701.13a)
    effects = [{'do': 'polymorph_capture102', 'who': mover['who'], 'mode': mode}, mover,
               {'do': 'polymorph_start102'}]
    return {'kind': 'spell', **scripts.target_fields(native[1]), 'effects': effects}


def capture(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    ctx['polymorph102'] = {'mode': e['mode'], 'originals': [
        {'card': cid, 'object': plan.oid(card), 'controller': card.controller, 'owner': card.owner,
         'types': sorted(plan.ch(card).types), 'name': card.name}
        for cid in effects._cards(plan, ctx, e['who'])
        if (card := plan.state.cards.get(cid)) is not None and card.zone.endswith(':battlefield')],
        'gather': [], 'next': 0}
    return True


def _moved(plan: Any, row: dict[str, Any]) -> bool:
    card = plan.state.cards.get(row['card'])
    return card is None or plan.oid(card) != row['object'] or not card.zone.endswith(':battlefield')


def start(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import scripts

    frame = ctx['polymorph102']
    rows = [r for r in frame['originals'] if frame['mode'] == 'reality' or _moved(plan, r)]
    if frame['mode'] == 'synthetic':
        # Freeze now: exiled tokens may cease to exist before the delayed trigger.
        delayed = scripts.parse_effects('At the beginning of the next end step, draw a card.')
        assert delayed is not None
        kind = _selector('creature card')
        ctx['effects'][ctx['next']:ctx['next']] = [{**delayed[0][0], 'n': 3},
            {'do': 'deferred:look_top', 'n': 0, 'player': 'you', 'reveal': True, 'until': kind,
             'need': len(rows), 'exact_look': True},
            {'do': 'deferred:pick_looked', 'which': 'all', 'sel': kind, 'to': 'battlefield'},
            {'do': 'deferred:shuffle_library', 'who': 'you'}]
        return True
    order = plan.apnap()
    frame['rows'] = sorted(rows, key=lambda r: order.index(r['controller']) if r['controller'] in order else len(order))
    frame['players'] = list(dict.fromkeys(r['controller'] for r in frame['rows']))
    return walk(plan, ctx, e)


def walk(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, selectors

    frame = ctx['polymorph102']
    if frame['next'] >= len(frame['rows']):
        if frame['mode'] == 'creativity':
            live = [r['card'] for r in frame['gather'] if (card := plan.state.cards.get(r['card'])) is not None
                    and plan.oid(card) == r['object'] and card.zone.endswith(':exile')]
            context.bind_objects(plan, ctx, 'creativity_hits102', live)
            ctx['effects'][ctx['next']:ctx['next']] = [
                {'do': 'return_card', 'who': 'ref:creativity_hits102', 'to': 'battlefield'},
                *[{'do': 'shuffle_library', 'who': 'player:' + p} for p in frame['players']]]
        return True
    if frame['mode'] == 'chaotic':  # -- (wave 110A) -- ruling 2022-09-09: a player with several of the permanents chooses which one they consider next
        from app.rules import wave110a_final

        if wave110a_final.choose_order(plan, ctx, frame):
            return False
    row = frame['rows'][frame['next']]
    frame['next'] += 1
    owner = row['owner'] if frame['mode'] == 'reality' else row['controller']
    if owner not in plan.live():
        ctx['effects'][ctx['next']:ctx['next']] = [{'do': 'polymorph_walk102'}]
        return True
    if frame['mode'] in ('reality', 'chaotic'):  # (chaotic: shares a card type with the permanent as it last existed, captured before it was exiled)
        kind = selectors.Selector(card=True, types=tuple(row['types']), zones=()).key()
    else:
        kind = _selector('artifact or creature card' if frame['mode'] == 'creativity' else 'creature card')
    sequence = [{'do': 'look_top', 'n': 0, 'player': 'player:' + owner, 'until': kind, 'reveal': True, 'exact_look': True}]
    if frame['mode'] == 'creativity':
        sequence += [{'do': 'pick_looked', 'which': 'that', 'require_found': True, 'to': 'exile',
                      'as': 'creativity_one102', 'by_owner': True}, {'do': 'polymorph_collect102'}]
    else:
        sequence += [{'do': 'polymorph_pick102'}]
        sequence += ([{'do': 'rest_looked', 'to': 'bottom_random'}] if frame['mode'] in ('reality', 'chaos')
                     else [{'do': 'shuffle_library', 'who': 'player:' + owner}])
    sequence += [{'do': 'polymorph_walk102'}]
    ctx['effects'][ctx['next']:ctx['next']] = sequence
    return True


def pick(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects
    from app.rules.characteristics import PERMANENT_TYPES

    cid = ctx.get('found')
    card = plan.state.cards.get(cid or '')
    # A Kindred permanent can find a Kindred instant/sorcery: stop there, but it
    # cannot enter the battlefield (304.4/307.4), and is not part of "the rest".
    destination = 'battlefield' if card is not None and bool(plan.ch(card).types & PERMANENT_TYPES) else 'choose'
    return effects.pick_looked(plan, ctx, {'do': 'pick_looked', 'which': 'that', 'require_found': True,
                                           'to': destination, 'by_owner': True})


def collect(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    ctx['polymorph102']['gather'] += [{'card': cid, 'object': plan.oid(plan.state.cards[cid])}
                                   for cid in effects._cards(plan, ctx, 'ref:creativity_one102')]
    return True


PRIMITIVES = {'polymorph_capture102': capture, 'polymorph_start102': start, 'polymorph_walk102': walk,
              'polymorph_pick102': pick, 'polymorph_collect102': collect}
