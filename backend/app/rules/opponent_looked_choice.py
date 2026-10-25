"""An opponent selects cards; the instruction's controller still moves them."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language, selectors

    text = body.strip().lower().rstrip('.')
    look: dict[str, Any] = {'do': 'look_top', 'player': 'you', 'reveal': True, 'exact_look': True}
    opponent = {'do': 'choose_opponent', 'as': 'card_chooser'}
    pick: dict[str, Any] = {'do': 'pick_looked', 'n': 1, 'chooser': 'ref:card_chooser'}
    if text == 'reveal the top three cards of your library. an opponent chooses one of them. put that card into your graveyard and the rest into your hand':
        return ([{**look, 'n': 3}, opponent, {**pick, 'to': 'graveyard'},
                 {'do': 'rest_looked', 'to': 'hand'}], None, False)
    if text == 'reveal the top five cards of your library. an opponent chooses a creature card from among them. put that card onto the battlefield and the rest into your graveyard':
        creature = selectors.parse('creature card')
        assert creature is not None
        return ([{**look, 'n': 5}, opponent, {**pick, 'to': 'battlefield', 'sel': creature.key()},
                 {'do': 'rest_looked', 'to': 'graveyard'}], None, False)
    if text == 'reveal the top three cards of your library. target opponent chooses one of those cards. put that card into your graveyard, then draw two cards':
        target = language._one(language.ref('target opponent')[2])
        return ([{**look, 'n': 3, 'as': 'tome_reveal'}, {**pick, 'chooser': 'target', 'to': 'graveyard'},
                 {'do': 'draw', 'who': 'you', 'n': 2},
                 {'do': 'hide_revealed', 'refs': 'tome_reveal', 'zone': 'library'}], target, False)
    if text == 'reveal the top two cards of your library. an opponent chooses one of them. put that card into your hand and exile the other with a silver counter on it':
        return ([{**look, 'n': 2}, opponent, {**pick, 'to': 'hand'},
                 {'do': 'rest_looked', 'to': 'exile', 'as': 'silver_exiled'},
                 {'do': 'add_counters', 'who': 'ref:silver_exiled', 'kind': 'silver', 'n': 1}], None, False)
    if text == "reveal the top three cards of your library. target opponent may choose to put those cards into your hand. if they don't, put those cards into your graveyard and draw five cards":
        # -- wave 110E -- 608.2d: the target opponent decides (a yes/no they alone answer); their refusal sends the revealed cards to the graveyard
        target = language._one(language.ref('target opponent')[2])
        return ([{**look, 'n': 3}, {'do': 'optional_payment', 'who': 'target', 'ask': 'put those cards into their hand', 'bind': 'cov110e'},
                 {'do': 'only_if', 'cond': {'succeeded': 'cov110e'}, 'skip': 1}, {'do': 'rest_looked', 'to': 'hand'},
                 {'do': 'only_if', 'cond': {'succeeded': 'cov110e', 'negate': True}, 'skip': 2},
                 {'do': 'rest_looked', 'to': 'graveyard'}, {'do': 'draw', 'who': 'you', 'n': 5}], target, False)
    if text == 'put a card you own with a silver counter on it from exile into your hand':
        sel = selectors.parse('card you own with a silver counter on it from exile')
        assert sel is not None
        return ([{'do': 'return_choice', 'sel': sel.key(), 'to': 'hand', 'n': 1, 'upto': False,
                  'random': False, 'label': 'card with a silver counter'}], None, False)
    if text == 'target opponent chooses one of the top two cards of your graveyard. exile that card and put the other one into your hand':
        target = language._one(language.ref('target opponent')[2])
        return ([{'do': 'inspect_graveyard_top', 'n': 2}, {**pick, 'chooser': 'target', 'to': 'exile'},
                 {'do': 'rest_looked', 'to': 'hand'}], target, False)
    if text == 'reveal the cards in your library. an opponent chooses from among them a creature card, a land card, and a noncreature, nonland card. you put the chosen cards into your hand. then shuffle':
        kinds = [selectors.parse(w) for w in ('creature card', 'land card', 'noncreature nonland card')]
        assert all(kinds)
        return ([{**look, 'n': {'library': 'you'}}, opponent,
                 *[{**pick, 'to': 'hand', 'sel': sel.key()} for sel in kinds if sel is not None],
                 {'do': 'shuffle_library', 'who': 'you'}], None, False)
    return None


def inspect_graveyard_top(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    owner = ctx['controller']
    cards = list(reversed(plan.state.zones.get(owner + ':graveyard', [])[-int(e['n']):]))
    ctx.update(looked_owner=owner, looked_zone='graveyard', looked=cards, found=None,
               looked_objects={c: plan.oid(plan.state.cards[c]) for c in cards})
    return True


PRIMITIVES = {'inspect_graveyard_top': inspect_graveyard_top}
