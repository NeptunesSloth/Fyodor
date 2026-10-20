"""Private library selections revealed in APNAP order, followed by their common movement."""
from __future__ import annotations

import re
from typing import Any, TypedDict

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.game.state import zone_key
from app.rules.plan import Plan, decide


class LookRound(TypedDict):
    queue: list[str]
    looked: dict[str, list[str]]
    chosen: dict[str, list[str]]
    sels: list[str]


def parse(body: str, *, event_player: bool = False) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Read explicit payment/copy sequencing, or each player's own optional category selection."""
    m = re.fullmatch(r"They may pay (?P<cost>(?:\{[^}X]+\})+)\. If they don't, you may copy that spell\. You may choose new targets for the copy\.", body, re.IGNORECASE)
    if m and event_player:
        return [{"do": "optional_payment", "who": "event_player", "cost": m['cost'], "bind": "lookcopy_pay"},
                {"do": "only_if", "cond": {"succeeded": "lookcopy_pay", "negate": True}, "skip": 4},
                {"do": "optional_payment", "who": "you", "cost": "", "ask": "copy that spell", "bind": "lookcopy_copy"},
                {"do": "only_if", "cond": {"succeeded": "lookcopy_copy"}, "skip": 2},
                {"do": "copy_spell", "who": "event_spell"}, {"do": "copy_new_targets", "optional": True}], None, False
    m = re.fullmatch(r"Each player looks at the top (?P<n>\w+) cards of their library and may reveal (?P<kinds>.+) from among them\. Each player puts the cards they revealed this way into their hand and the rest on the bottom of their library in a random order\. Each player gains (?P<life>\d+) life\.", body)
    if m is None:
        return None
    from app.rules import selectors
    from app.rules.scripts import num

    try:
        n = num(m['n'])
    except KeyError:
        return None
    kinds = m['kinds'].split(' and/or ')
    sels = [selectors.parse(re.sub(r'^an? ', '', k)) for k in kinds]
    if len(sels) != 2 or any(s is None for s in sels):
        return None
    return [{"do": "multiplayer_look", "n": n, "sels": [s.key() for s in sels if s is not None]},
            {"do": "gain_life", "who": "each_player", "n": int(m['life'])}], None, False


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    players = plan.apnap()
    looked = {p: list(plan.state.zones.get(zone_key(p, 'library'), [])[:e['n']]) for p in players}
    for p, cards in looked.items():
        if cards:
            plan.do({"type": "look_top", "player": p, "count": len(cards)}, actor=p)
    return advance(plan, ctx, LookRound(queue=players, looked=looked, chosen={}, sels=e['sels']))


def advance(plan: Plan, ctx: dict[str, Any], state: LookRound) -> bool:
    from app.rules import looking
    from app.rules.effects import bottom_at_random

    state['queue'] = [p for p in state['queue'] if p in plan.live()]
    if state['queue']:
        pid = state['queue'][0]
        cards = state['looked'][pid]
        options = [c for c in cards if looking.kinds_of(plan, pid, c, state['sels'])]
        # Even no matches gives the private chooser a choice; observers cannot infer the matches.
        decide(plan, player=pid, kind='choose_cards', prompt='Choose cards to reveal and put into your hand (up to one of each kind)',
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or 'Card', card_id=c) for c in options],
               min_choices=0, max_choices=min(len(state['sels']), len(options)),
               resume={'step': 'multiplayer_look', 'ctx': ctx, 'state': state})
        return False
    for pid, cards in state['looked'].items():
        if pid not in plan.live():
            continue
        chosen = state['chosen'].get(pid, [])
        if chosen:
            plan.do({'type': 'move', 'card_ids': chosen, 'to': {'player': pid, 'zone': 'hand'}}, actor=pid)
        rest = [c for c in cards if c not in chosen]
        if rest:
            bottom_at_random(plan, pid, rest, actor=pid)
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects, looking

    state: LookRound = d.resume['state']
    if not looking.distinct_kinds(plan, d.player, chosen, state['sels']):
        raise ActionError('Choose at most one card of each kind')
    state['chosen'][d.player] = list(chosen)
    state['queue'].pop(0)
    if chosen:
        plan.do({'type': 'reveal', 'card_ids': chosen}, actor=d.player)
    ctx = d.resume['ctx']
    if advance(plan, ctx, state):
        effects.continue_effects(plan, ctx)
