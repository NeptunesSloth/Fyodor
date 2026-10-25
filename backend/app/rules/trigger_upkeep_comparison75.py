"""Active-player Oaths keep target authority and compare live player quantities twice."""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

PREFIX = 'upkeep_compare75:'
GH = ("At the beginning of each player's upkeep, that player chooses target player whose graveyard has fewer creature cards "
      "in it than their graveyard does and is their opponent. The first player may return a creature card from their graveyard to their hand.")
SC = ("At the beginning of each player's upkeep, that player chooses target player who has more cards in hand than they do "
      "and is their opponent. The first player may discard their hand and draw three cards.")
MA = ("At the beginning of each player's upkeep, that player chooses target player who has more life than they do and is "
      "their opponent. The first player may have this enchantment deal 1 damage to the second player.")
# -- other choosers (wave 100P) -- Oath of Druids, Oath of Lieges: the same target shape over permanents the players control (the rulings of 2009-10-01: the
# comparison is the targeting requirement, rechecked on resolution, 608.2b); the first player reveals / searches their own library and puts the card onto the
# battlefield under their own control (ruling 2004-10-04), the revealed rest into their graveyard
DR = ("At the beginning of each player's upkeep, that player chooses target player who controls more creatures than they do and is their opponent. The first "
      "player may reveal cards from the top of their library until they reveal a creature card. If the first player does, that player puts that card onto the "
      "battlefield and all other cards revealed this way into their graveyard.")
LI = ("At the beginning of each player's upkeep, that player chooses target player who controls more lands than they do and is their opponent. The first "
      "player may search their library for a basic land card, put that card onto the battlefield, then shuffle.")
CASES = {
    DR: ('you may reveal cards from the top of your library until you reveal a creature card. If you do, put that card onto the battlefield and all other '
         'cards revealed this way into your graveyard', 'creatures', 'gt'),
    LI: ('you may search your library for a basic land card, put that card onto the battlefield, then shuffle', 'lands', 'gt'),
    GH: ('you may return a creature card from your graveyard to your hand', 'grave_creatures', 'lt'),
    SC: ('you may discard your hand and draw three cards', 'hand', 'gt'),
    MA: ('you may have this enchantment deal 1 damage to target player', 'life', 'gt'),
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind != 'triggered' or ability.text not in CASES:
        return None
    body, metric, relation = CASES[ability.text]
    native = scripts.define(replace(ability, text="At the beginning of each player's upkeep, " + body + '.'), ch)
    if native is None or native.get('optional') is not True:
        return None
    out = copy.deepcopy(native)
    effects = out['effects']
    for e in effects:
        if e.get('who') == 'you':
            e['who'] = 'event_player'
        if e['do'] == 'return_choice':
            e['chooser'] = 'event_player'
        if e.get('player') == 'you':  # (wave 100P: Oath of Druids' reveal is of their library, and they put the card onto the battlefield)
            e['player'] = 'event_player'
        if e['do'] == 'pick_looked':
            e['by_owner'] = True
    target = selectors.Selector(player='any', player_exclude=selectors.THAT_PLAYER,
                                extras=(PREFIX + metric + ':' + relation,)).key()
    return {**out, 'optional': False, 'target_choice': 'event_player', 'target': {'what': target},
            'effects': [{'do': 'may_rest', 'who': 'event_player'}, *effects]}


def matches(plan: Any, sel: Any, candidate: str) -> bool:
    marks = [x.removeprefix(PREFIX) for x in sel.extras if x.startswith(PREFIX)]
    if not marks:
        return True
    if len(marks) != 1 or not (sel.player_exclude or '').startswith('player:'):
        return False
    reference = sel.player_exclude[7:]
    if reference not in plan.live() or candidate not in plan.live():
        return False
    mode = marks[0].split(':')
    if len(mode) != 2 or tuple(mode) not in {('grave_creatures', 'lt'), ('hand', 'gt'), ('life', 'gt'), ('creatures', 'gt'), ('lands', 'gt')}:
        return False

    def quantity(pid: str) -> int:
        if mode[0] == 'life':
            return int(plan.state.players[pid].life)
        if mode[0] == 'hand':
            return len(plan.state.zones.get(pid + ':hand', []))
        if mode[0] in ('creatures', 'lands'):  # (wave 100P)
            return sum(c.controller == pid and plan.in_game(c) and (plan.ch(c).is_creature if mode[0] == 'creatures' else plan.ch(c).is_land)
                       for c in plan.state.cards.values() if c.zone.endswith(':battlefield'))
        return sum(not c.is_token and plan.ch(c).is_creature for cid in plan.state.zones.get(pid + ':graveyard', [])
                   if (c := plan.state.cards.get(cid)) is not None)

    theirs, original = quantity(candidate), quantity(reference)
    return theirs < original if mode[1] == 'lt' else theirs > original
