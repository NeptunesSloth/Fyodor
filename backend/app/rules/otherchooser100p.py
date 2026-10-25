# -- other choosers (wave 100P) --
"""Exact wordings of wave 100P (choices made by a player other than the controller, votes, piles), each read as the native instructions it
amounts to. Researched against CR 2026-09-25 and the cards' rulings.

* Path of the Pyromancer: "Add {R} for each card discarded this way, then draw that many cards plus one." — the mana and the draw both count the
  cards the discard put into the graveyard (701.9a); an empty hand adds nothing and still draws one (ruling 2023-04-14).
* Council's dilemma (701.38a; the rulings: every vote adds to the result, the effects happen in the stated order after the vote):
  - Travel Through Caradhras: one search for each Redhorn Pass vote (each a basic land onto the battlefield tapped), then one shuffle if a search
    happened (701.24: "If you search your library this way, shuffle": none when no vote asked for one or the player can't search, 701.23); a card
    from the graveyard returned to the hand for each Mines of Moria vote.
  - Fateful Tempest: one mill of as many cards as past votes, the damage to each opponent the total mana value of the cards milled (X is 0: ruling
    2026-03-20); then as many cards as present votes exiled from the top, playable until the end of your next turn (the normal timing: ruling).
  - Selvala's Stampede: cards revealed until as many creature cards as wild votes, those creatures put onto the battlefield together, the rest
    shuffled in; then up to as many permanent cards from your hand as free votes, put onto the battlefield together (ruling 2016-08-23: after the
    creatures).
  - Expropriate: an extra turn for each time vote; for each money vote, in the order of the votes, you choose a permanent the voter owns (wherever
    it is controlled) and gain control of it.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_DISCARDED = {"this_way": "discarded", "of": None, "ref_count": "e0"}
_EXACT: dict[str, list[dict[str, Any]]] = {
    "Discard all the cards in your hand. Add {R} for each card discarded this way, then draw that many cards plus one.": [
        {"do": "discard", "who": "you", "n": 0, "all": True, "as": "e0"}, {"do": "add_mana", "sym": "R", "n": dict(_DISCARDED)},
        {"do": "draw", "who": "you", "n": {**_DISCARDED, "delta": 1}}],
}
_VOTES = {
    "Starting with you, each player votes for Redhorn Pass or Mines of Moria. For each Redhorn Pass vote, search your library for a basic land card "
    "and put it onto the battlefield tapped. If you search your library this way, shuffle. For each Mines of Moria vote, return a card from your "
    "graveyard to your hand.": ("Redhorn Pass", "Mines of Moria"),
    "Starting with you, each player votes for past or present. You mill a card for each past vote, then ~ deals damage to each opponent equal to the "
    "total mana value of cards milled this way. Exile the top card of your library for each present vote. Until the end of your next turn, you may "
    "play the exiled cards.": ("past", "present"),
    "Starting with you, each player votes for wild or free. Reveal cards from the top of your library until you reveal a creature card for each wild "
    "vote. Put those creature cards onto the battlefield, then shuffle the rest into your library. You may put a permanent card from your hand onto "
    "the battlefield for each free vote.": ("wild", "free"),
    "Starting with you, each player votes for time or money. For each time vote, take an extra turn after this one. For each money vote, choose a "
    "permanent owned by the voter and gain control of it. Exile ~.": ("time", "money"),
}


class _Miss(Exception):
    pass


def _one(text: str, do: str | None = None) -> list[dict[str, Any]]:
    from app.rules import scripts

    found = scripts.parse_effects(text)
    if found is None or found[2] or not found[0] or (do is not None and found[0][0]["do"] != do):
        raise _Miss(text)  # (the native wording it is built from no longer reads so: stays manual)
    return found[0]


def _votes(word: str) -> dict[str, str]:
    return {"votes100p": word}


def _council(body: str) -> list[dict[str, Any]] | None:
    labels = _VOTES.get(body)
    if labels is None:
        return None
    a, b = (w.lower() for w in labels)
    out: list[dict[str, Any]] = [{"do": "vote", "secret": False, "opts": [a, b], "labels": list(labels)}]
    if a == "redhorn pass":
        search = _one("Search your library for a basic land card and put it onto the battlefield tapped.")
        back = _one("Return a card from your graveyard to your hand.")
        return [*out, {"do": "vote_repeat", "choice": a, "skip": len(search)}, *search, {"do": "searched_shuffle100p", "choice": a},
                {"do": "vote_repeat", "choice": b, "skip": len(back)}, *back]
    if a == "past":
        play = _one("Exile the top X cards of your library. Until the end of your next turn, you may play those cards.", "exile_top")
        return [*out, {"do": "mill", "who": "you", "n": _votes(a), "as": "tempest_milled"},
                {"do": "damage", "who": "each_opponent", "n": {"sum": "mana_value", "of": "ref:tempest_milled"}}, {**play[0], "n": _votes(b)}, *play[1:]]
    if a == "wild":
        reveal = _one("Reveal cards from the top of your library until you reveal X creature cards. Put those creature cards onto the battlefield, "
                      "then shuffle the rest into your library.", "look_top")
        put = _one("Put up to two permanent cards from your hand onto the battlefield.", "put_from_hand")
        return [*out, {**reveal[0], "need": _votes(a)}, *reveal[1:], {**put[0], "cap": _votes(b)}]
    take = _one("Gain control of target creature.")
    return [*out, {"do": "vote_repeat", "choice": a, "skip": 1}, *_one("Take an extra turn after this one."),
            {"do": "vote_ballots100p", "choice": b, "as": "vote_money", "then": [{**take[0], "who": "ref:vote_money"}]}, *_one("Exile ~.")]


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    body = body.strip()
    found = _EXACT.get(body)
    if found is not None:
        return copy.deepcopy(found), None, False
    try:
        council = _council(body)
    except _Miss:
        return None
    return None if council is None else (council, None, False)


# -- carrying it out -----------------------------------------------------------------------------------
def votes(ctx: Context, word: str) -> int:
    """How many votes this resolution's vote gave ``word`` (values: ``{"votes100p": word}``)."""
    return int(((ctx.get("vote") or {}).get("tally") or {}).get(word, 0))


def searched_shuffle(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"If you search your library this way, shuffle.": a search happened when a vote asked for one and the controller could search (701.23)."""
    from app.rules import prohibitions

    me = ctx["controller"]
    if votes(ctx, e["choice"]) and prohibitions.cant_search(plan, me, me) is None:
        plan.do({"type": "shuffle", "player": me, "zone": "library"}, actor=me)
    return True


def ballots(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """For each vote for ``choice`` (in the order cast): you choose a permanent the voter owns (bound as ``as``), then ``then``."""
    from app.rules import selectors

    owned = selectors.parse("permanent you own")
    assert owned is not None
    out: list[dict[str, Any]] = []
    for voter, choice in (ctx.get("vote") or {}).get("ballots") or []:
        if choice == e["choice"] and voter in plan.live():
            out += [{"do": "player_chooses", "who": f"player:{voter}", "sel": owned.key(), "n": 1, "label": "permanent", "any": True,
                     "any_by_chooser": True, "by": "you", "as": e["as"]}, *copy.deepcopy(e["then"])]
    at = ctx["next"]
    ctx["effects"][at:at] = out
    return True


PRIMITIVES = {"searched_shuffle100p": searched_shuffle, "vote_ballots100p": ballots}
