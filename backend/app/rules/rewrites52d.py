"""-- activated other (wave 52D) -- Oracle wordings written as the (equal) wording the grammar already reads.

Each rewrite below says which card it is for and which rule makes the two wordings the same instruction.
"""

from __future__ import annotations

import re

# 608.2c: two groups joined by "and" are two instructions in order, and an untap needs no order ("Untap all Forests and all green creatures.", Patron of the Orochi).
_UNTAP_TWO = re.compile(r"(^\s*|\. )Untap all ([^.,]+?) and all ([^.,]+?)\.")
# 608.2c: "Exile this artifact and all cards from all graveyards." (Silent Gravestone) is two exiles in order.
_EXILE_SELF_AND_YARDS = re.compile(r"(^\s*|\. )Exile (this \w+|~) and all cards from all graveyards\.")
# 115.1d, 608.2c: "Choose any number of target creatures. Each of those creatures gains persist until end of turn." (Cauldron of Souls) is the one sentence with the targets in it.
_CHOOSE_EACH = re.compile(r"(^\s*|\. )Choose (any number of target [^.,]+?)\. Each of those (creatures|permanents) (gains|gets) ([^.]+?)\.")


# 608.2c: the card revealed is in the library (701.20a), and "that card onto the battlefield under your control" is "it onto the battlefield" for its controller's own
# library (Druidic Satchel); "a noncreature, nonland card" is a card that is both (Druidic Satchel).
_REVEALED_PUT = re.compile(r"(If it's an? [^,.]+? card, )put that card onto the battlefield under your control")
# Grenzo, Dungeon Warden: "If it's a creature card with power less than or equal to ~'s power, put it onto the battlefield." after the bottom card went to the graveyard:
# the card returns to the battlefield (the owner of the library it came from controls it: it is the controller's own library).
_BOTTOM_PUT = re.compile(r"(Put the bottom card of your library into your graveyard\. If it's [^,.]+, )put it onto the battlefield\.")


def rewrite(body: str) -> str:
    body = body.replace("noncreature, nonland card", "noncreature nonland card")
    body = _REVEALED_PUT.sub(r"\1put it onto the battlefield", body)
    body = _BOTTOM_PUT.sub(r"\1return it to the battlefield.", body)
    body = _UNTAP_TWO.sub(lambda m: f"{m[1]}Untap all {m[2]}. Untap all {m[3]}.", body)
    body = _EXILE_SELF_AND_YARDS.sub(lambda m: f"{m[1]}Exile {m[2]}. Exile all cards from all graveyards.", body)
    return _CHOOSE_EACH.sub(lambda m: f"{m[1]}{m[2][:1].upper()}{m[2][1:]} {'gain' if m[4] == 'gains' else 'get'} {m[5]}.", body)
