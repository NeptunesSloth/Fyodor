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


def _permanents(phrase: str) -> str:
    """A permanent selector (language._permanent_sel) or no reading at all."""
    from app.rules import language
    from app.rules.scripts import _NoMatch

    try:
        return language._permanent_sel(phrase)
    except language._Fail:
        raise _NoMatch from None


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
    graveyard = m["where"].startswith("in ")
    sel = _graveyard_selector(m["sel"]) if graveyard else _permanents(m["sel"])
    upto = m["q"].startswith("up")
    return [{"do": "player_chooses", "who": _WHO[m["who"]], "by": "you", "sel": sel, "n": 1, "label": m["sel"], **({"upto": True, "optional": True} if upto else {}),
             **({"zone": "graveyard"} if graveyard else {})}], None


# "Each player puts a creature card from their graveyard onto the battlefield." / "Each player returns two land cards from their graveyard to the battlefield." / "… may return
# a creature card …" (Enslaved Horror) / "… returns up to three cards from their graveyard to their hand." (Ill-Gotten Gains): each chooses among their own graveyard, then all of
# them move at once, each under its owner's control
_EACH = re.compile(r"^(?P<who>each player|each opponent|each other player|that player) (?P<may>may )?(?:puts|returns|put|return) (?P<q>(?:up to )?(?:an?|one|two|three|four)) "
                   r"(?P<sel>[a-z ,]*?cards?(?: with mana value \d+ or less)?) from their graveyard (?P<to>onto the battlefield|to the battlefield|to their hand)$")


def _each(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    q = m["q"]
    upto = bool(m["may"]) or q.startswith("up to")
    n = _NUM[q.removeprefix("up to ")]
    kind = "battlefield" if "battlefield" in m["to"] else "hand"
    who = "that_player" if m["who"] == "that player" else _WHO[m["who"].removeprefix("each ")]  # (that player: Skullwinder, bound to the opponent chosen before)
    move = {"do": "return_card", "who": "it" if who == "that_player" and n == 1 else "them", "to": kind, "under": "owner", **({"tapped": False} if kind == "battlefield" else {})}
    return [{"do": "player_chooses", "who": who, "sel": _graveyard_selector(m["sel"]), "n": n, "label": m["sel"], "zone": "graveyard",
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

# "For each player, choose a creature that player controls. Each player sacrifices all creatures they control not chosen this way." (The Eternal Wanderer -4): one choice for each
# player (the controller's), then everything else of that kind goes at once (101.4, 701.21a): the wording player_chooses already has for "chooses ..., then sacrifices the rest"
_NOT_CHOSEN = re.compile(r"(For each (?:player|opponent), (?:you )?choose an? (?P<sel>[a-z ]+?) that (?:player|opponent) controls)\. "
                         r"Each (?:player|opponent) sacrifices all (?P=sel)s they control not chosen this way\.")


def rewrite(body: str) -> str:
    # "exile it and each player returns all creature cards from their graveyard to their hand" (Underworld Cerberus): two instructions, two subjects (608.2c)
    body = re.sub(r"(^|[.,] )([Ee])xile it and (each player returns )", lambda m: f"{m[1]}{m[2]}xile it. {m[3].capitalize()}", body)
    # "Each player discards their hand, then returns up to three cards from their graveyard to their hand." (Ill-Gotten Gains): the discard first, then the choice (608.2c)
    body = re.sub(r"\b(Each player discards their hand), then (returns up to \w+ cards from their graveyard)", r"\1. Each player \2", body)
    return _NOT_CHOSEN.sub(lambda m: m[1] + ", then each player sacrifices the rest.", body)


_FOR_EACH_REST = re.compile(r"^for each (?P<who>player|opponent), (?:you )?choose (?P<q>an?) (?P<sel>[a-z ,'-]+?) that (?:player|opponent) controls, then each (?:player|opponent) sacrifices the rest$")


def _for_each_rest(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "player_chooses", "who": _WHO[m["who"]], "by": "you", "sel": _permanents(m["sel"]), "n": 1, "label": m["sel"], "rest": "sacrifice"}], None


TEMPLATES.append((_FOR_EACH_REST, _for_each_rest))


# "Destroy one of them chosen at random." (Chaos Defiler): the table picks one of the objects the choices before bound (recorded, so a replay or a load never draws again) and it is destroyed
_ONE_OF_THEM = re.compile(r"^destroy one of them chosen at random$")


def _one_of_them(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "destroy_random", "who": "them"}], None


TEMPLATES.append((_ONE_OF_THEM, _one_of_them))


def destroy_random(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    import secrets

    from app.rules import effects

    found = sorted(effects._cards(plan, ctx, e["who"]))
    if not found:
        return True
    pick = (plan.rng or secrets.SystemRandom()).choice(found)
    plan.note(f"{ctx.get('name') or 'It'}: chosen at random ->", [pick], actor=ctx["controller"])
    return effects._destroy_cards(plan, ctx, {**e, "as": e.get("as")}, [pick])


PRIMITIVES: dict[str, Any] = {"destroy_random": destroy_random}
