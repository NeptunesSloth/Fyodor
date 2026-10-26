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
    r"|If you would planeswalk, instead look at the top two cards of your planar deck, put one on the bottom of your planar deck and the other on top, then planeswalk\."
    # (wave 110B final) 901.3, 901.9: a planar die exists only in a Planechase game; none is rolled in Commander, so this replacement never applies (Ichor Elixir)
    r"|If you would roll one or more planar dice, instead roll that many planar dice plus one and ignore one\.")


def definition(text: str) -> dict[str, Any] | None:
    """A static that does nothing (the draft isn't part of the game) for a line about the draft itself, else None."""
    return {"kind": "static", "static": "draft_only", "effects": []} if _DRAFT.fullmatch(text.strip()) else None


# 905.2 / 103.6: nothing is drafted in Commander, so these cards never have a card, note or chosen color (wave110f_cards.parse reads these).
# Each wording below is an explicit do-nothing effect (no "gain 0 life" text shown to players), not a guess at a rules result.
DRAFT_NOTHING = {
    "copy a card you exiled with cards named Arcane Savant. You may cast the copy without paying its mana cost.",
    "Create a token that's a copy of a card you exiled with cards named Caller of the Untamed. X is the mana value of that card.",
    "you may search your hand and/or library for a card with a name noted as you drafted cards named Aether Searcher. You may cast it without paying its mana cost. If you search your library this way, shuffle.",  # (wave 110I)
    "Choose a card at random you exiled with cards named Volatile Chimera. ~ becomes a copy of that card, except it has this ability.",
}
GARBAGE_FIRE = "~ deals damage to target creature equal to the highest number you noted for cards named Garbage Fire."  # target kept, nothing was noted
SMUGGLER = "you may search your library for a card with a name you noted for cards named Smuggler Captain, reveal it, put it into your hand, then shuffle."
REGICIDE = "Destroy target creature that's one or more of the colors chosen as you drafted cards named Regicide."


def nothing_drafted(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Nothing was drafted, exiled or noted, so there is nothing to do."""
    return True


def parse(body: str) -> Any:
    """(wave 110F) the effect of a spell or ability sentence that uses what a draft would have left, else None."""
    from app.rules import selectors

    if body in DRAFT_NOTHING:
        return [{"do": "nothing_drafted110f"}], None, False
    if body == GARBAGE_FIRE:
        return [{"do": "nothing_drafted110f", "who": "target"}], "creature", False
    if body == SMUGGLER:  # (wave 110C) a name was never noted, so the search finds nothing (701.23b: a quality search may fail) but the library is still shuffled
        return [{"do": "shuffle_library", "who": "you"}], None, True
    if body == REGICIDE:  # no color was chosen, so no creature is one of them: a selector that matches nothing (a creature that is not a creature), hence no legal target
        return [{"do": "destroy", "who": "target"}], selectors.Selector(types=("Creature",), not_types=("Creature",)).key(), False
    return None


# -- Paliano, the High City (wave 110J) -- ruling 2014-05-29: without a draft nothing was chosen, so the mana ability adds no mana (not even colorless). It stays a
# mana ability (605.1a): {T} is paid, the one option adds nothing.
_PALIANO = "{T}: Add one mana of any color chosen as you drafted cards named Paliano, the High City."


def mana(text: str) -> Any:
    from app.rules import mana as M

    return M.ManaAbility(tap=True, sacrifice_self=False, options=((),)) if text.strip() == _PALIANO else None
