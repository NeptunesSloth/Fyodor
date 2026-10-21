"""Optional private looks, public selections, and exact-library reveal cleanup."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import selectors

    text = ' '.join(body.lower().split()).rstrip('.')
    look: dict[str, Any] = {'do': 'look_top', 'n': 1, 'player': 'you', 'exact_look': True}
    selected = 'optional_look_selected'
    pick: dict[str, Any] = {'do': 'pick_looked', 'n': 1, 'to': 'top', 'optional': True, 'reveal': True, 'as': selected}
    cleanup = {'do': 'look_reveal_cleanup', 'ref': 'ref:' + selected}
    if text == 'you may look at the top four cards of your library. if you do, reveal up to one land card from among them, then put that card on top of your library and the rest on the bottom in a random order':
        kind, n, rest = 'land card', 4, 'bottom_random'
    elif text == 'you may look at the top five cards of your library. if you do, reveal up to one basic land card from among them, then put that card on top of your library and the rest on the bottom in any order':
        kind, n, rest = 'basic land card', 5, 'bottom_any'
    elif text == "you may look at the top x cards of your library, where x is that creature's power. if you do, put one of those cards on top of your library and the rest on the bottom of your library in any order":
        return [{**look, 'n': {'power': 'event'}}, {'do': 'pick_looked', 'n': 1, 'to': 'top'},
                {'do': 'rest_looked', 'to': 'bottom_any'}], None, True
    elif text in ("you may look at the top card of your library. if it's a creature card, you may reveal it and put a quest counter on this enchantment",
                  "you may look at the top card of your library. if it's a creature card, you may reveal it and put a quest counter on ~"):
        creature = selectors.parse('creature card')
        assert creature is not None
        return [look, {**pick, 'sel': creature.key(), 'did': 'quest_revealed'},
                {'do': 'only_if', 'cond': {'succeeded': 'quest_revealed'}, 'skip': 1},
                {'do': 'add_counters', 'who': 'self', 'kind': 'quest', 'n': 1}, cleanup], None, True
    elif text in ("look at the top card of your library. if it's a land card or a creature card with mana value less than or equal to the number of loyalty counters on ~, you may put that card onto the battlefield",
                  "look at the top card of your library. if it's a land card or a creature card with mana value less than or equal to the number of loyalty counters on nissa, you may put that card onto the battlefield"):
        return [look, {'do': 'looked_loyalty_entry'}], None, False
    else:
        return None
    sel = selectors.parse(kind)
    assert sel is not None
    return [{**look, 'n': n}, {**pick, 'sel': sel.key()}, {'do': 'rest_looked', 'to': rest}, cleanup], None, True


def cleanup(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    return effects.hide_revealed(plan, ctx, {'refs': e['ref'].removeprefix('ref:'), 'zone': 'library'})


def loyalty_entry(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, selectors, values

    bound = values.evaluate(plan, ctx, {'counters': 'loyalty', 'on': 'self'})
    land, creature, card = [selectors.parse(k) for k in ('land card', 'creature card', 'card')]
    assert land is not None and creature is not None and card is not None
    creature = selectors.replace(creature, compare=(*creature.compare, ('mana_value', '<=', bound)))
    return effects.pick_looked(plan, ctx, {'do': 'pick_looked', 'n': 1, 'to': 'battlefield', 'optional': True,
                                          'sel': card.key(), 'sels': [land.key(), creature.key()]})


PRIMITIVES = {'look_reveal_cleanup': cleanup, 'looked_loyalty_entry': loyalty_entry}
