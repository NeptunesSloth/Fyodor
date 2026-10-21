"""Linked exile cleanup with damage for each card actually put into a graveyard.

CR 603.4, 607.2a, 608.2c/h, 614.6: check the linked cards both when the
end-step ability triggers and resolves. Replacements that send a card elsewhere
contribute no damage. The source object's linked set survives its departure.
"""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    body = body[:1].upper() + body[1:]
    if body != ("If there are cards exiled with ~, put them into their owner's graveyard, "
                "then ~ deals that much damage to each opponent."):
        return None
    return ([{'do': 'only_if', 'cond': {'value': {'exiled_with': 1}, 'op': '>=', 'n': 1}, 'skip': 2},
             {'do': 'return_card', 'who': 'exiled_with', 'to': 'graveyard', 'as': 'linked_cleanup'},
             {'do': 'damage', 'who': 'each_opponent',
              'n': {'ref_count': 'linked_cleanup', 'this_way': 'graveyard', 'of': None}}], None, False)
