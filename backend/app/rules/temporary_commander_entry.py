"""CR 903.8, 603.7c: put a commander onto the battlefield, then return that object later."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import delayed, selectors

    body = body.strip()
    if body[:1].upper() + body[1:] != ('You may put a commander you own from the command zone onto the battlefield. '
                                     'It gains haste. Return it to the command zone at the beginning of the next end step.'):
        return None
    key = selectors.Selector(commander=True, owner='you', zones=('command',), card=True).key()
    who = 'ref:temporary_commander'
    return ([{'do': 'return_choice', 'sel': key, 'n': 1, 'upto': True, 'optional': True,
              'label': 'a commander you own', 'to': 'battlefield', 'under': 'you', 'as': 'temporary_commander'},
             {'do': 'grant', 'who': who, 'keywords': ['haste'], 'duration': 'permanent'},
             *delayed.wrap_when([{'do': 'return_card', 'who': who, 'to': 'command'}], delayed.WHEN['the next end step'])], None, False)
