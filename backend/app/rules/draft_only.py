"""-- draft-matters cards (wave 52C) -- "Draft this card face up." (Canal Dredger), "Reveal this card as you draft it." (Cogwork Spy), "As you draft a card, you may …"
(Cogwork Librarian), "During the draft, you may turn this card face down." (Whispergear Sneak).

CR 905.2: "Some cards have abilities that function during the draft" (905.2b-c: revealing and drafting face up; the draft's passing and picking are 905.1). A game here is not
preceded by a draft, so these lines are never part of it: they do nothing. Only the lines that are about the draft itself are read this way; a line that uses what a draft would
have left ("the highest number you noted", "a color chosen as you drafted") is not, and keeps its card partial.
"""

from __future__ import annotations

import re
from typing import Any

_DRAFT = re.compile(
    r"Draft (?:this card|~) face up\."
    r"|Reveal this card as you draft it\b.*"
    r"|Each player passes the last card from each booster pack to a player who drafted a card named (?:~|[A-Z][^.]+?)\."
    r"|Immediately after the draft, .*"
    r"|As you draft (?:a|an) .*"
    r"|During the draft, .*"
    r"|Before you shuffle your deck to start the game, you may reveal this card from your deck and exile .+? you drafted that (?:isn't|aren't) in your deck\."
    r"|Instead of drafting a card from a booster pack, .*"
    r"|As long as this card is face up during the draft, .*"
    r"|If you removed a creature card with flying from the draft with cards named (?:~|[A-Z][^.]+?), ~ has flying\. The same is true for .*"
    # what the draft noted: nothing was noted, so the ability has nothing to refer to (a player, a name, a type): it never applies
    r"|~ attacks a player you noted for cards named (?:~|[A-Z][^.]+?) each combat if able\."
    r"|As long as you control one or more creatures with a name you noted for cards named (?:~|[A-Z][^.]+?), ~ and those creatures get \+1/\+1 and have lifelink\."
    # (wave 110I) nothing was noted / removed, so X is 0: it enters with no counters
    r"|(?:This creature|~) enters with X \+1/\+1 counters on it, where X is (?:the highest number you noted|the number of cards you removed from the draft) (?:for|with) cards named (?:~|[A-Z][^.]+?)\."
    r"|Other creatures you control of a type you noted for cards named (?:~|[A-Z][^.]+?) get \+1/\+1\."
    # (wave 110B) 701.31a / 901.3: a player planeswalks only in a Planechase game; Commander has no planar deck, so this replacement never applies (Susan Foreman)
    r"|If you would planeswalk, instead look at the top two cards of your planar deck, put one on the bottom of your planar deck and the other on top, then planeswalk\.")


def definition(text: str) -> dict[str, Any] | None:
    """A static that does nothing (the draft isn't part of the game) for a line about the draft itself, else None."""
    return {"kind": "static", "static": "draft_only", "effects": []} if _DRAFT.fullmatch(text.strip()) else None
