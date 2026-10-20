"""CR 707.12 / 608.2g: copying exiled cards and optionally casting their copies."""
from __future__ import annotations

import re

_EXILE_EACH = re.compile(
    r"^Exile (?P<which>target|each) card that's an instant or sorcery from your graveyard\. "
    r"For each card exiled this way, copy it, and you may cast the copy without paying its mana cost\. Exile ~\.$"
)


def normalize(body: str) -> str:
    m = _EXILE_EACH.fullmatch(body.strip())
    if m is None:
        return body
    many = m['which'] == 'each'
    return (('Exile all instant and sorcery cards from your graveyard. Copy those cards. ' if many else
             'Exile target instant or sorcery card from your graveyard. Copy that card. ')
            + 'You may cast any number of the copies without paying their mana costs. Exile ~.')
