"""Revealed search packets with ordered destination quantities and controllers."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import conditional_look, conditions, scripts

    text = ' '.join(body.lower().split()).rstrip('.')
    nissa = 'search your library for up to two basic forest cards, reveal those cards, and put one onto the battlefield tapped and the rest into your hand. then shuffle'
    mastery = '. if there are two or more instant and/or sorcery cards in your graveyard, search your library for up to three basic forest cards instead of two'
    quantity, kind, count = 2, 'basic land cards', 1
    config: dict[str, Any] = {}
    if text in (nissa, nissa + mastery):
        kind = 'basic Forest cards'
        if text.endswith(mastery):
            regular = _search(scripts, quantity, kind, {'n': count})
            upgraded = _search(scripts, 3, kind, {'n': count})
            cond = conditions.parse('there are two or more instant and/or sorcery cards in your graveyard')
            assert cond is not None
            return conditional_look.branch(cond, [upgraded], [regular]), None, False
    elif text == 'search your library for up to three basic land cards and reveal them. put two of them onto the battlefield tapped and the other into your hand, then shuffle':
        quantity, count = 3, 2
    elif text == 'choose an opponent who controls more lands than you. search your library for a number of plains cards equal to the difference, reveal those cards, put one of them onto the battlefield tapped and the rest into your hand, then shuffle':
        search = _search(scripts, 0, 'Plains cards', {'n': 1})
        return [{'do': 'search_partition_opponent', 'search': search}], None, False
    elif text == "search your library for up to four basic land cards and reveal them. put one of them onto the battlefield tapped under an opponent's control if the {3}{g} cost was paid. put two of them onto the battlefield tapped under your control and the rest into your hand. then shuffle":
        quantity, count = 4, 2
        config['opponent_alt'] = 'alternative'
    elif text == 'search your library for up to two basic land cards and reveal them, then roll a d20. 9 or less | put those cards into your hand, then shuffle. 10—19 | put one of those cards onto the battlefield tapped and the other into your hand, then shuffle. 20+ | put those cards onto the battlefield tapped, then shuffle':
        config['die'] = True
    else:
        return None
    return [_search(scripts, quantity, kind, {'n': count, **config})], None, False


def _search(scripts: Any, n: int, kind: str, config: dict[str, Any]) -> dict[str, Any]:
    native = scripts.parse_effects(f'Search your library for up to {n} {kind}, reveal them, put them into your hand, then shuffle.')
    assert native is not None and len(native[0]) == 1 and native[0][0]['do'] == 'search'
    return {**native[0][0], 'partition': config}


def _lands(plan: Plan, pid: str) -> int:
    return sum(1 for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and c.controller == pid
               and 'Land' in plan.ch(c).types)


def opponent(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects
    from app.rules.plan import decide

    pid = ctx['controller']
    own = _lands(plan, pid)
    options = [DecisionOption(id=p, label=plan.name(p)) for p in effects._players(plan, ctx, 'each_opponent') if _lands(plan, p) > own]
    if not options:
        return effects.search(plan, ctx, e['search'])
    decide(plan, player=pid, kind='choose_one', prompt='Choose an opponent who controls more lands than you', options=options,
           resume={'step': 'search_partition_opponent', 'ctx': ctx, 'e': e})
    return False


def resume_opponent(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume['ctx'], d.resume['e']
    n = max(0, _lands(plan, chosen[0]) - _lands(plan, ctx['controller']))
    if effects.search(plan, ctx, {**e['search'], 'max': n}):
        effects.continue_effects(plan, ctx)


def offer(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], pid: str, found: list[str], dest: dict[str, str]) -> bool:
    from app.rules import dice

    config = e.get('partition')
    if config is None:
        return False
    stages: list[dict[str, Any]] = []
    # 707.10: the alternative-cost decision is copied even though a copy
    # wasn't cast. Read only this exact stack object's payment snapshot.
    record = plan.rules.payments.get(ctx.get('source_object') or '')
    if config.get('opponent_alt') and record is not None and record.alternative == config['opponent_alt']:
        stages.append({'n': 1, 'opponent': True})
    n = config['n']
    if config.get('die'):
        dice.roll(plan, ctx, {'sides': 20, 'count': 1})
        n = 0 if ctx['die'] <= 9 else 1 if ctx['die'] <= 19 else len(found)
    stages.append({'n': n, 'player': config.get('player', pid)})
    clean = {k: v for k, v in e.items() if k != 'partition'}
    frame = {'ctx': ctx, 'e': {**clean, 'reveal': False, **({'partition_rest': config['rest_to']} if config.get('rest_to') else {})}, 'pid': pid, 'found': found, 'dest': dest,
             'refs': {c: {'object': plan.oid(c), 'zone': plan.state.cards[c].zone} for c in found},
             'stages': stages, 'recipients': {}}
    advance(plan, frame)
    return True


def _live(plan: Plan, frame: dict[str, Any], cid: str) -> bool:
    card = plan.state.cards.get(cid)
    ref = frame['refs'][cid]
    return card is not None and plan.oid(card) == ref['object'] and card.zone == ref['zone']


def advance(plan: Plan, frame: dict[str, Any]) -> None:
    from app.rules import effects
    from app.rules.plan import decide

    while frame['stages']:
        stage = frame['stages'][0]
        pool = [c for c in frame['found'] if frame['dest'][c] == 'hand' and _live(plan, frame, c)]
        n = min(stage['n'], len(pool))
        if not n:
            frame['stages'].pop(0)
            continue
        if stage.get('opponent') and not stage.get('player'):
            options = [DecisionOption(id=p, label=plan.name(p)) for p in effects._players(plan, frame['ctx'], 'each_opponent')]
            if not options:
                frame['stages'].pop(0)
                continue
            decide(plan, player=frame['pid'], kind='choose_one', prompt='Choose an opponent to receive a land', options=options,
                   resume={'step': 'search_partition_recipient', 'frame': frame})
            return
        if n == len(pool):
            _assign(frame, stage, pool)
            frame['stages'].pop(0)
            continue
        decide(plan, player=frame['pid'], kind='choose_cards', prompt=f"Choose {n} land{'s' if n != 1 else ''} to enter tapped under {plan.name(stage['player'])}'s control",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or 'Card', card_id=c) for c in pool],
               min_choices=n, max_choices=n, resume={'step': 'search_partition_cards', 'frame': frame})
        return
    if frame['e'].get('partition_rest'):
        for cid in frame['found']:
            if frame['dest'][cid] == 'hand':
                frame['dest'][cid] = frame['e']['partition_rest']
                frame['recipients'][cid] = frame['pid']
    live = [c for c in frame['found'] if _live(plan, frame, c)]
    e = {**frame['e'], 'entry_players': frame['recipients']}
    effects._finish_search(plan, frame['ctx'], e, frame['pid'], live, {c: frame['dest'][c] for c in live})


def _assign(frame: dict[str, Any], stage: dict[str, Any], cards: list[str]) -> None:
    for cid in cards:
        frame['dest'][cid] = 'battlefield_tapped'
        frame['recipients'][cid] = stage['player']


def resume_recipient(plan: Plan, d: Any, chosen: list[str]) -> None:
    frame = d.resume['frame']
    frame['stages'][0]['player'] = chosen[0]
    advance(plan, frame)


def resume_cards(plan: Plan, d: Any, chosen: list[str]) -> None:
    frame = d.resume['frame']
    stage = frame['stages'].pop(0)
    _assign(frame, stage, [c for c in chosen if _live(plan, frame, c)])
    advance(plan, frame)


PRIMITIVES = {'search_partition_opponent': opponent}
RESUME = {'search_partition_opponent': resume_opponent, 'search_partition_recipient': resume_recipient,
          'search_partition_cards': resume_cards}
