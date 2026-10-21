"""One target's owner chooses its library destination, across battlefield/stack/graveyard."""
from __future__ import annotations

import re
from typing import Any

_CHOOSE = re.compile(r"^Choose (?P<target>.+?)\. Its owner puts it on their choice of the top or bottom of their library\.$", re.IGNORECASE)
_DETOUR = re.compile(r"^The owner of target spell, nonland permanent, or card in a graveyard puts it on their choice of the top or bottom of their library\.$", re.IGNORECASE)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language
    from app.rules.selectors import Selector

    text = body.strip()
    group: dict[str, Any] | None
    if text.casefold() == "for each attacking creature, its owner puts it on their choice of the top or bottom of their library.":
        return [{"do": "to_library", "who": Selector(types=("Creature",), attacking=True).key(), "place": "choice"}], None, False
    if text.casefold() == "for each opponent, choose up to one target creature they control with a rejection counter on it. that creature's owner puts it on their choice of the top or bottom of their library.":
        from app.rules.per_opponent import FLAG

        what = Selector(types=("Creature",), controller="opponent", extras=("counter:rejection",)).key()
        return [{"do": "to_library", "who": "all_targets", "place": "choice", "opponent_aggregate": True}], [{"what": what, "min": 0, "max": 1, FLAG: True}], False
    if _DETOUR.fullmatch(text):
        branches = (Selector(zones=('stack',)), Selector(not_types=('Land',)), Selector(card=True, zones=('graveyard',)))
        group = {'what': Selector(zones=('stack', 'battlefield', 'graveyard'), either=tuple(s.key() for s in branches)).key(),
                 'min': 1, 'max': 1}
    elif (match := _CHOOSE.fullmatch(text)) is not None:
        phrase = re.sub(r'\bcreature spell or planeswalker spell\b', 'creature or planeswalker spell', match['target'], flags=re.I)
        try:
            group = language.target_group(phrase.lower() if 'creature or planeswalker spell' in phrase else phrase)
        except (ValueError, language._Fail):
            return None
        if group is None or group.get('max') != 1:
            return None
    else:
        return None
    return [{'do': 'to_library', 'who': 'target:0', 'place': 'choice'}], [group], False
