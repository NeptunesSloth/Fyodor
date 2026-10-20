"""Private library inspection separates the owner of the cards from their viewer."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language

    text = body.strip().lower().rstrip('.')
    target = None
    if text.startswith("look at the top") and "target " in text:
        opponent = "target opponent's library" in text
        target = language._one(language.ref('target opponent' if opponent else 'target player')[2])
    look = {'do': 'look_top', 'player': 'target', 'exact_look': True}
    if text == "look at the top three cards of target player's library. put one back and the rest into that player's graveyard":
        return ([{**look, 'n': 3}, {'do': 'pick_looked', 'n': 1, 'to': 'top'},
                 {'do': 'rest_looked', 'to': 'graveyard'}], target, False)
    if text == "look at the top five cards of target player's library. put any number of them on the bottom of that library in any order and the rest on top of the library in any order":
        return ([{**look, 'n': 5}, {'do': 'pick_looked', 'n': 5, 'optional': True, 'to': 'bottom_any'},
                 {'do': 'rest_looked', 'to': 'top_any'}], target, False)
    if text == "look at the top three cards of target opponent's library, then put them back in any order. that player looks at the top three cards of your library, then puts them back in any order":
        return ([{**look, 'n': 3}, {'do': 'rest_looked', 'to': 'top_any'},
                 {**look, 'n': 3, 'player': 'you', 'viewer': 'target'},
                 {'do': 'rest_looked', 'to': 'top_any', 'viewer': 'target'}], target, False)
    if text == "look at the top card of target player's library. if it's a nonland card, you may pay 2 life. if you do, put it into that player's graveyard":
        return ([{**look, 'n': 1}, {'do': 'looked_nonland_payment'}], target, False)
    if text == 'you may look at the top two cards of that library. you may exile one of those cards. then put the rest on top of that library in any order':
        return ([{**look, 'n': 2, 'player': 'event_player'},
                 {'do': 'pick_looked', 'n': 1, 'to': 'exile', 'optional': True},
                 {'do': 'rest_looked', 'to': 'top_any'}], None, True)
    return None


def nonland_payment(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    _, cards = effects._looked(plan, ctx)
    if len(cards) != 1 or 'Land' in plan.ch(plan.state.cards[cards[0]]).types:
        return True
    # Native optional-payment continuation owns the cost, validation and cold resume.
    at = ctx['next']
    ctx['effects'][at:at] = [
        {'do': 'optional_payment', 'who': 'you', 'cost': 'Pay 2 life', 'bind': 'look_life'},
        {'do': 'only_if', 'cond': {'succeeded': 'look_life'}, 'skip': 1},
        {'do': 'pick_looked', 'which': 'that', 'n': 1, 'to': 'graveyard'}]
    return True


PRIMITIVES = {'looked_nonland_payment': nonland_payment}
