"""-- if you do (wave 52A) -- wordings of the same "this way" instruction that the grammar reads in one form (CR 2026-09-25, 608.2c).

* "Mill five cards, then return a creature card milled this way to your hand." (Monster Manual // Zoological Study): the card is chosen among the cards the mill put into the
  graveyard, as "put a creature card from among the cards milled this way into your hand" says (the cards milled are public, 404.2).
"""

from __future__ import annotations

import re

_RETURN_MILLED = re.compile(r"\b([Rr]eturn) (an? [^.,]+? card) milled this way to your hand\b")


def rewrite(body: str) -> str:
    return _RETURN_MILLED.sub(lambda m: f"{'Put' if m[1][0] == 'R' else 'put'} {m[2]} from among the cards milled this way into your hand", body)


# * "Bottle-Cap Blast deals 5 damage to any target. If excess damage was dealt to a permanent this way, create that many tapped Treasure tokens.": one Treasure for each point of
#   excess damage (120.10), none when there was none — "Create a number of tapped Treasure tokens equal to the amount of excess damage dealt to that permanent this way".
_EXCESS_TOKENS = re.compile(r"\bIf excess damage was dealt to a permanent this way, create that many (tapped )?(Treasure) tokens\.")


def rewrite_excess(body: str) -> str:
    return _EXCESS_TOKENS.sub(lambda m: f"Create a number of {m[1] or ''}{m[2]} tokens equal to the amount of excess damage dealt to that permanent this way.", body)
