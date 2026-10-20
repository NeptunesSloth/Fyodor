"""Return non-targeted graveyard cards according to a prior optional hand reveal."""
from __future__ import annotations

import re
from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import selectors

    m = re.fullmatch(r'Reveal any number of (?P<color>white|blue|black|red|green) cards in your hand\. '
                     r'Return an? (?P<kind>enchantment|artifact|creature|land|instant|sorcery) card from your graveyard '
                     r'to your hand for each card revealed this way\.', body, re.I)
    if m is None:
        return None
    reveal = selectors.parse(f"{m['color'].lower()} cards in your hand")
    returned = selectors.parse(f"{m['kind'].lower()} cards from your graveyard")
    assert reveal is not None and returned is not None
    bind = 'revealed_for_return'
    return ([{'do': 'reveal_hand_cards', 'sel': reveal.key(), 'n': 99, 'as': bind},
             {'do': 'return_choice', 'sel': returned.key(), 'to': 'hand',
              'n': {'this_way': 'revealed', 'of': None, 'ref_count': bind},
              'upto': False, 'random': False, 'label': f"{m['kind'].lower()} card"}], None, False)
