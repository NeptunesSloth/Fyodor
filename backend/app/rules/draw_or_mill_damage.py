"""A targeted opponent chooses a draw; otherwise mill and use those cards' total mana value."""
from __future__ import annotations

import re
from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    body = body.strip()
    # CR 608.2c, 608.2h: counter and scry precede the opponent's choice;
    # the mill count uses the source's current or last known counters.
    counter_draw = re.fullmatch(
        r"put an (?P<kind>[a-z]+) counter on ~ and scry (?P<scry>\d+)\. Then target opponent may have you draw a card\. "
        r"If that player doesn't, you mill X cards, where X is the number of (?P=kind) counters on ~, "
        r"and that player loses life equal to the total mana value of those cards\.", body)
    if counter_draw:
        return ([{'do': 'add_counters', 'who': 'self', 'kind': counter_draw['kind'], 'n': 1},
                 {'do': 'scry', 'who': 'you', 'n': int(counter_draw['scry'])},
                 {'do': 'optional_payment', 'who': 'target', 'ask': 'have the ability’s controller draw a card',
                  'cost': '', 'bind': 'choose_draw'},
                 {'do': 'only_if', 'cond': {'succeeded': 'choose_draw'}, 'skip': 1},
                 {'do': 'draw', 'who': 'you', 'n': 1},
                 {'do': 'only_if', 'cond': {'succeeded': 'choose_draw', 'negate': True}, 'skip': 2},
                 {'do': 'mill', 'who': 'you', 'n': {'counters': counter_draw['kind'], 'on': 'self'}, 'as': 'choice_milled'},
                 {'do': 'lose_life', 'who': 'target', 'n': {'sum': 'mana_value', 'of': 'ref:choice_milled'}}], 'opponent', False)

    if body[:1].upper() + body[1:] != ("Target opponent may have you draw three cards. If the player doesn't, you mill three cards, "
                                      "then ~ deals damage to that player equal to the total mana value of those cards."):
        return None
    return ([{'do': 'optional_payment', 'who': 'target', 'ask': 'have the ability’s controller draw three cards',
              'cost': '', 'bind': 'choose_draw'},
             {'do': 'only_if', 'cond': {'succeeded': 'choose_draw'}, 'skip': 1},
             {'do': 'draw', 'who': 'you', 'n': 3},
             {'do': 'only_if', 'cond': {'succeeded': 'choose_draw', 'negate': True}, 'skip': 2},
             {'do': 'mill', 'who': 'you', 'n': 3, 'as': 'gearhulk_milled'},
             {'do': 'damage', 'who': 'target', 'n': {'sum': 'mana_value', 'of': 'ref:gearhulk_milled'}}], 'opponent', False)
