"""-- player-relative selectors (wave 53A) -- a choice made for each player, among the objects that player controls or the cards in that player's graveyard: "For each
player, choose a creature or planeswalker card in that player's graveyard." (Breach the Multiverse), "For each player, choose a creature card in that player's graveyard."
(Ghouls' Night Out), "Each player puts a creature card from their graveyard onto the battlefield." (Exhume), "Each player returns two land cards from their graveyard to the
battlefield." (Fall of the Thran), "Each opponent chooses a creature card in their graveyard. Put those cards onto the battlefield under your control." (Dredge the Mire).

State: none beyond effects.player_chooses (wave 30K): the chosen objects are the binding the sentence after reads ("those cards", "that card"), recorded when the last choice is
made. ``zone`` ("graveyard") makes the set the cards the player owns in that zone instead of the permanents they control.

Decisions: 101.4 - every player makes their choice in APNAP order (the active player first), each knowing the earlier ones (101.4b: they are announced); "for each player, choose"
is the ability's controller's choice for each (``by: you``), "each player puts / returns / chooses" each player's own. A graveyard is public (404.2), so nobody is told
anything new by a skipped question; "up to" and "may" always ask. Nothing is moved until every choice is made, then all at once (the cards enter / return together).

Rules: 101.4, 101.4b, 404.1-404.2, 608.2c, 608.2d, 110.2a (an object put onto the battlefield by an instruction given to a player enters under that player's control unless
the instruction says otherwise).
"""

from __future__ import annotations

import re
from typing import Any

from app.rules import selectors

_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4}
_WHO = {"player": "each_player", "opponent": "each_opponent", "other player": "each_opponent"}


def _graveyard_selector(phrase: str) -> str:
    """"creature or planeswalker card" / "land cards" / "creature card with mana value 3 or less" -> the selector over a graveyard's cards."""
    from app.rules.scripts import _NoMatch  # (scripts imports this module)

    sel = selectors.parse(re.sub(r"\bcards\b", "card", phrase) + " from a graveyard")
    if sel is None or not sel.card or sel.player is not None or sel.controller is not None or sel.zone_owner is not None or sel.zones != ("graveyard",):
        raise _NoMatch
    return sel.key()


# "For each player, choose a creature card in that player's graveyard." / "For each opponent, choose a creature that player controls." - the controller chooses for each
_FOR_EACH = re.compile(r"^for each (?P<who>player|opponent), (?:you )?choose (?P<q>an?|up to one) (?P<sel>[a-z ,'-]+?) "
                       r"(?P<where>that (?:player|opponent) controls|in that (?:player|opponent)'s graveyard)$")


def _for_each(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    graveyard = m["where"].startswith("in ")
    sel = _graveyard_selector(m["sel"]) if graveyard else language._permanent_sel(m["sel"])
    upto = m["q"].startswith("up")
    return [{"do": "player_chooses", "who": _WHO[m["who"]], "by": "you", "sel": sel, "n": 1, "label": m["sel"], **({"upto": True, "optional": True} if upto else {}),
             **({"zone": "graveyard"} if graveyard else {})}], None


# "Each player puts a creature card from their graveyard onto the battlefield." / "Each player returns two land cards from their graveyard to the battlefield." / "… may return
# a creature card …" (Enslaved Horror) / "… returns up to three cards from their graveyard to their hand." (Ill-Gotten Gains): each chooses among their own graveyard, then all of
# them move at once, each under its owner's control
_EACH = re.compile(r"^(?P<who>each player|each opponent|each other player) (?P<may>may )?(?:puts|returns|put|return) (?P<q>(?:up to )?(?:an?|one|two|three|four)) "
                   r"(?P<sel>[a-z ,]*?cards?(?: with mana value \d+ or less)?) from their graveyard (?P<to>onto the battlefield|to the battlefield|to their hand)$")


def _each(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    q = m["q"]
    upto = bool(m["may"]) or q.startswith("up to")
    n = _NUM[q.removeprefix("up to ")]
    kind = "battlefield" if "battlefield" in m["to"] else "hand"
    move = {"do": "return_card", "who": "them", "to": kind, "under": "owner", **({"tapped": False} if kind == "battlefield" else {})}
    return [{"do": "player_chooses", "who": _WHO[m["who"].removeprefix("each ")], "sel": _graveyard_selector(m["sel"]), "n": n, "label": m["sel"], "zone": "graveyard",
             **({"upto": True, "optional": True} if upto else {})}, move], None


# "Each opponent chooses a creature card in their graveyard." / "Target opponent chooses an artifact card in their graveyard." (Dredge the Mire, Scrounge): the sentence after puts
# what was chosen onto the battlefield under the controller's control
_CHOOSES = re.compile(r"^(?P<who>each opponent|each player|target opponent|target player) chooses (?P<q>an?|up to one) (?P<sel>[a-z ,]*?cards?) in their graveyard$")


def _chooses(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    target = m["who"].startswith("target")
    upto = m["q"].startswith("up")
    return [{"do": "player_chooses", "who": "target" if target else _WHO[m["who"].removeprefix("each ")], "sel": _graveyard_selector(m["sel"]), "n": 1, "label": m["sel"],
             "zone": "graveyard", **({"upto": True, "optional": True} if upto else {})}], (m["who"].removeprefix("target ") if target else None)


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_FOR_EACH, _for_each), (_EACH, _each), (_CHOOSES, _chooses)]

# "Put those cards onto the battlefield under your control." / "Put that card onto the battlefield under your control." after a choice: what was chosen, moved from where it is (the
# pronoun is bound to the instruction before by scripts.resolve_it); read last, after every wording that names the cards in another way
_PUT = re.compile(r"^put (?P<p>those cards|that card|those creatures|them) onto the battlefield(?P<tapped> tapped)? under your control$")


def _put(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "return_card", "who": "them" if m["p"] != "that card" else "it", "to": "battlefield", "tapped": bool(m["tapped"]), "under": "you"}], None


LATE: list[tuple[re.Pattern[str], Any]] = [(_PUT, _put)]
