"""Conditional inspected-card instructions compile to native verdict-bound branches."""
from __future__ import annotations

from typing import Any


def branch(cond: dict[str, Any], yes: list[dict[str, Any]], no: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flag = 'look_replacement'
    return [{'do': 'only_if', 'cond': cond, 'bind': flag, 'skip': len(yes)}, *yes,
            {'do': 'only_if', 'cond': {'flag': flag, 'negate': True}, 'skip': len(no)}, *no]


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import conditions, selectors

    text = body.strip().lower().rstrip('.').replace('spell mastery — ', '')
    look = {'do': 'look_top', 'n': 3, 'player': 'you', 'exact_look': True}
    pick = {'do': 'pick_looked', 'n': 1, 'to': 'hand'}
    rest = {'do': 'rest_looked', 'to': 'bottom_any'}
    if text == 'look at the top three cards of your library. put one of them into your hand and the rest on the bottom of your library in any order. if there is an instant card and a sorcery card in your graveyard, instead put two of them into your hand and the rest on the bottom of your library in any order':
        parts = [conditions.parse(f'there is an {kind} card in your graveyard') for kind in ('instant', 'sorcery')]
        assert all(parts)
        cond = {'all': parts}
        upgrade = {**pick, 'n': 2}
    elif text == 'look at the top three cards of your library. put one of those cards into your hand and the rest on the bottom of your library in any order. put each of those cards into your hand instead if there are three or more lesson cards in your graveyard':
        found = conditions.parse('there are three or more Lesson cards in your graveyard')
        assert found is not None
        cond = found
        upgrade = {**pick, 'which': 'all', 'n': 3}
    elif text == 'look at the top three cards of your library. put one of those cards into your hand and the rest on the bottom of your library in any order. if this spell was cast from anywhere other than your hand, put each of those cards into your hand instead':
        found = conditions.parse('this spell was cast from anywhere other than your hand', objects=True)
        assert found is not None
        cond = found
        upgrade = {**pick, 'which': 'all', 'n': 3}
    elif text.startswith('reveal the top five cards of your library. you may put a creature card from among them into your hand. put the rest into your graveyard'):
        base = 'reveal the top five cards of your library. you may put a creature card from among them into your hand. put the rest into your graveyard'
        rider = '. if there are two or more instant and/or sorcery cards in your graveyard, put up to two creature cards from among the revealed cards into your hand instead of one'
        if text not in (base, base + rider):
            return None
        creature = selectors.parse('creature card')
        assert creature is not None
        pick = {**pick, 'optional': True, 'sel': creature.key()}
        rest = {**rest, 'to': 'graveyard'}
        look = {**look, 'n': 5, 'reveal': True}
        if text == base:
            return ([look, pick, rest], None, False)
        found = conditions.parse('there are two or more instant and/or sorcery cards in your graveyard')
        assert found is not None
        cond = found
        upgrade = {**pick, 'n': 2}
    elif text in ('if this spell was bargained, look at the top four cards of your library, then put up to two of them back on top of your library in any order and the rest into your graveyard',
                  'if this spell was kicked, look at the top four cards of your library, then put up to two of them back on top of your library in any order and the rest into your graveyard'):
        return ([{'do': 'kicked_gate', 'kicked': True, 'n': 3}, {**look, 'n': 4},
                 {'do': 'pick_looked', 'n': 2, 'optional': True, 'to': 'top_any'},
                 {'do': 'rest_looked', 'to': 'graveyard'}], None, False)
    else:
        return None
    return ([look, *branch(cond, [upgrade, rest], [pick, rest])], None, False)
