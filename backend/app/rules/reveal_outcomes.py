"""Native reveal-through outcomes: snapshots precede moves and ordering decisions."""
from __future__ import annotations

from typing import Any

from app.rules import context, selectors
from app.rules.plan import Plan


def _card(kind: str, non: bool = False) -> str:
    sel = selectors.Selector(zones=(), card=True, not_types=(kind,)) if non else selectors.Selector(zones=(), card=True, types=(kind,))
    return sel.key()


def _until(kind: str, *, who: str = 'you', need: Any = None, non: bool = False) -> dict[str, Any]:
    return {'do': 'reveal_outcome_top', 'n': 0, 'player': who, 'viewer': who, 'until': _card(kind, non),
            'reveal': True, 'exact_look': True, **({'need': need} if need is not None else {})}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = body.strip().rstrip('.')
    text = text[:1].upper() + text[1:]
    if text == 'Target opponent reveals cards from the top of their library until four land cards are revealed. That player puts all cards revealed this way into their graveyard':
        return [_until('Land', who='target', need=4), {'do': 'rest_looked', 'to': 'graveyard', 'viewer': 'target'}], 'opponent', False
    if text == 'Each opponent reveals cards from the top of their library until they reveal X land cards, then puts all cards revealed this way into their graveyard':
        return [{'do': 'opponents_reveal_lands', 'n': {'x': 1}}], None, False
    if text == 'Reveal cards from the top of your library until you reveal three nonland cards. Put the nonland cards revealed this way into your hand, then put the rest of the revealed cards on the bottom of your library in any order':
        return [_until('Land', non=True, need=3), {'do': 'pick_looked', 'which': 'all', 'sel': _card('Land', True), 'to': 'hand'},
                {'do': 'rest_looked', 'to': 'bottom_any'}], None, False
    if text == ('Reveal cards from the top of your library until you reveal an artifact card. Put that card onto the battlefield and the rest on the bottom of your library in a random order. ~ deals damage to you equal to the number of cards revealed this way'):
        native = scripts.parse_effects('Reveal cards from the top of your library until you reveal an artifact card. Put that card onto the battlefield and the rest on the bottom of your library in a random order.')
        assert native is not None
        es, target, may = native
        es[0]['exact_look'] = True
        es[0]['do'] = 'reveal_outcome_top'
        es[1]['require_found'] = True
        return [es[0], {'do': 'snapshot_reveal', 'as': 'reveal_count', 'bind': 'reveal_found'}, *es[1:], {'do': 'damage', 'who': 'you', 'n': {'ref_amount': 'reveal_count'}}], target, may
    if text == ('Choose target creature. Reveal cards from the top of your library until you reveal a nonland card. That creature gets +X/-X until end of turn, where X is that card\'s mana value. Put all cards revealed this way on the bottom of your library in any order'):
        return [_until('Land', non=True), {'do': 'snapshot_reveal', 'as': 'reveal_count', 'bind': 'reveal_found'},
                {'do': 'pump', 'who': 'target', 'p': {'mana_value': 'ref:reveal_found'}, 't': {'neg': {'mana_value': 'ref:reveal_found'}}},
                {'do': 'rest_looked', 'to': 'bottom_any'}], 'creature', False
    if text == ('Reveal the top seven cards of your library, then put those cards on the bottom of your library in any order. If a card named Stomping Slabs was revealed this way, ~ deals 7 damage to any target'):
        return [{'do': 'reveal_outcome_top', 'n': 7, 'player': 'you', 'reveal': True, 'exact_look': True},
                {'do': 'snapshot_reveal', 'name': 'Stomping Slabs', 'verdict': 'revealed_name'}, {'do': 'rest_looked', 'to': 'bottom_any'},
                {'do': 'only_if', 'cond': {'flag': 'revealed_name'}, 'skip': 1}, {'do': 'damage', 'who': 'target', 'n': 7}], 'any', False
    if text == ('Target opponent reveals cards from the top of their library until they reveal a creature card. That player puts all noncreature cards revealed this way into their graveyard, then you put the creature card onto the battlefield under your control'):
        return [_until('Creature', who='target'), {'do': 'separate_revealed_found', 'as': 'found_creature'},
                {'do': 'rest_looked', 'to': 'graveyard', 'viewer': 'target'},
                {'do': 'restore_revealed_found', 'ref': 'ref:found_creature'},
                {'do': 'pick_looked', 'which': 'that', 'require_found': True, 'to': 'battlefield'}], 'opponent', False
    if text == ('The controller of target artifact sacrifices it, then reveals cards from the top of their library until they reveal an artifact card. That player puts that card onto the battlefield, then shuffles all other cards revealed this way into their library'):
        return [{'do': 'remember_reveal_controller', 'as': 'revealer'}, {'do': 'sacrifice', 'who': 'target', 'by': 'controller'},
                _until('Artifact', who='ref:revealer'),
                {'do': 'pick_looked', 'which': 'that', 'require_found': True, 'to': 'battlefield', 'by_owner': True},
                {'do': 'shuffle_library', 'who': 'ref:revealer'}], _card_target('Artifact'), False
    if text == ("Put target creature on the bottom of its owner's library. That creature's controller reveals cards from the top of their library until they reveal a creature card. The player puts that card onto the battlefield and the rest on the bottom of their library in any order"):
        return [{'do': 'remember_reveal_controller', 'as': 'revealer'}, {'do': 'to_library', 'who': 'target', 'place': 'bottom'},
                _until('Creature', who='ref:revealer'),
                {'do': 'pick_looked', 'which': 'that', 'require_found': True, 'to': 'battlefield', 'by_owner': True},
                {'do': 'rest_looked', 'to': 'bottom_any', 'viewer': 'ref:revealer'}], 'creature', False
    if text == ('Reveal the top X cards of your library. You may put a nonland permanent card with mana value X or less from among them onto the battlefield. Then shuffle the rest into your library'):
        return [{'do': 'genesis_reveal'}], None, False
    if text == ('Each player reveals the top five cards of their library, puts all land cards revealed this way onto the battlefield tapped, and exiles the rest'):
        return [{'do': 'reveal_land_entries', 'as': 'clear_revealed', 'bind': 'clear_nonlands'}], None, False
    return None


def reveal_outcome_top(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    # Every use here is mandatory and has no decision before the reveal completes.
    if not effects.look_top(plan, ctx, e):
        return False
    # Exact cleanup belongs to THIS reveal, including cards put back in an ordered
    # library. Later reveals in a multi-player resolution keep separate bindings.
    key = f"reveal_outcome_{ctx['next']}"
    context.bind_objects(plan, ctx, key, ctx.get('looked') or [])
    start = ctx['next']
    stop = next((i for i in range(start, len(ctx['effects']))
                 if ctx['effects'][i].get('do') == 'reveal_outcome_top'), len(ctx['effects']))
    placements = [i for i in range(start, stop)
                  if ctx['effects'][i].get('do') in ('pick_looked', 'rest_looked', 'shuffle_library', 'to_library')]
    at = max(placements) + 1 if placements else start
    ctx['effects'].insert(at, {'do': 'hide_revealed', 'refs': key, 'zone': 'library'})
    return True


def snapshot_reveal(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    _, cards = effects._looked(plan, ctx)
    if e.get('as'):
        context.bind_amount(ctx, e['as'], len(cards))
    found = ctx.get('found')
    if e.get('bind'):
        context.bind_objects(plan, ctx, e['bind'], [found] if found in cards else [])
    if e.get('name'):
        sel = selectors.Selector(zones=(), card=True, extras=('name:' + e['name'],))
        context.bind_flag(ctx, e['verdict'], any(selectors.matches(plan, sel, plan.state.cards[c], plan.ch(plan.state.cards[c]),
                                                                   ctx['controller'], ctx.get('source_card')) for c in cards))
    return True


def opponents_reveal_lands(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    steps = []
    for pid in plan.live():
        if pid != ctx['controller']:
            steps.extend([_until('Land', who='player:' + pid, need=e['n']),
                          {'do': 'rest_looked', 'to': 'graveyard', 'viewer': 'player:' + pid}])
    ctx['effects'][ctx['next']:ctx['next']] = steps
    return True


def _card_target(kind: str) -> str:
    return selectors.Selector(types=(kind,)).key()


def remember_reveal_controller(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    cards = effects._cards(plan, ctx, 'target')
    context.bind_players(ctx, e['as'], [plan.state.cards[cards[0]].controller] if cards else [])
    return True


def separate_revealed_found(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    _, cards = effects._looked(plan, ctx)
    found = ctx.get('found')
    context.bind_objects(plan, ctx, e['as'], [found] if found in cards else [])
    ctx['looked'] = [c for c in cards if c != found]
    return True


def restore_revealed_found(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    ids = context.objects(plan, ctx, e['ref'].removeprefix(context.PREFIX))
    ctx['looked'] = [c for c in ids if plan.state.cards[c].zone.endswith(':library')]
    ctx['found'] = ctx['looked'][0] if ctx['looked'] else None
    return True


def genesis_reveal(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from dataclasses import replace

    from app.rules import effects

    n = effects._amount(plan, ctx, {'x': 1})
    sel = selectors.parse('nonland permanent card with mana value X or less')
    assert sel is not None
    sel = replace(sel, compare=(('mv', '<=', n),))
    steps = [{'do': 'reveal_outcome_top', 'n': n, 'player': 'you', 'reveal': True, 'exact_look': True},
             {'do': 'pick_looked', 'n': 1, 'sel': sel.key(), 'to': 'battlefield', 'optional': True},
             {'do': 'shuffle_library', 'who': 'you'}]
    ctx['effects'][ctx['next']:ctx['next']] = steps
    return True


def reveal_land_entries(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import attachments

    shown, rest, entries = [], [], []
    land = selectors.from_key(_card('Land'))
    for pid in plan.live():
        ids = list(plan.state.zones.get(f'{pid}:library', []))[:5]
        if ids:
            plan.do({'type': 'reveal', 'card_ids': ids}, actor=pid)
        shown.extend(ids)
        for cid in ids:
            if selectors.matches(plan, land, plan.state.cards[cid], plan.ch(plan.state.cards[cid]), pid, ctx.get('source_card')):
                entries.append({'card': cid, 'player': pid, 'actor': pid, 'tapped': True})
            else:
                rest.append(cid)
    context.bind_objects(plan, ctx, e['as'], shown)
    context.bind_objects(plan, ctx, e['bind'], rest)
    steps = [{'do': 'exile', 'who': 'ref:' + e['bind']},
             {'do': 'hide_revealed', 'refs': e['as'], 'zone': 'library'}]
    ctx['effects'][ctx['next']:ctx['next']] = steps
    return attachments.enter(plan, entries, ctx)


PRIMITIVES = {f.__name__: f for f in (reveal_outcome_top, snapshot_reveal, opponents_reveal_lands, remember_reveal_controller,
                                              separate_revealed_found, restore_revealed_found, genesis_reveal, reveal_land_entries)}


def definition(text: str, kind: str) -> dict[str, Any] | None:
    if kind != 'spell' or text != ("Each opponent reveals cards from the top of their library until they reveal X land cards, then puts all cards revealed this way into their graveyard. X can't be 0."):
        return None
    parsed = parse(text.removesuffix(" X can't be 0."))
    assert parsed is not None
    return {'kind': 'spell', 'effects': parsed[0], 'target': None, 'x_min': 1}
