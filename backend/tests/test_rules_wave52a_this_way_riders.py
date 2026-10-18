"""Wave 52A: "this way" outcomes of a choice the ability made (CR 2026-09-25), real Oracle text (tests/fixtures/wave52a_cards.json, from data/cards.sqlite). Every scenario
checks the replay and a save and a load.

* 608.2c / 608.2h: Arid Archway - "When this land enters, return a land you control to its owner's hand. If another Desert was returned this way, surveil 1." The land it
  returned, as it was (itself or not: "another" is than the Archway), decides.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave52a_kit import build_n, open_repo

ARCHWAY = "Arid Archway"
WITCH_KING, BREW = "Rise of the Witch-king", "Deadly Brew"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [ARCHWAY, WITCH_KING, BREW])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def steps(s, answer=None, limit=20):
    """Pass priority and answer the land choice with ``answer`` (a card id) until the trigger is done; returns the decisions asked, in order."""
    asked = []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            asked.append(d.prompt)
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer] if answer in ids else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return asked
    raise AssertionError("never settled")


def enter(s, name, n=0, pid="p1"):
    """Onto the battlefield without any trigger (a move)."""
    c = [x for x in s.state.cards.values() if x.name == name and x.owner == pid][n]
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def play(s, name, n=0, pid="p1"):
    """Play it as a land from the hand (305.1): it enters, its trigger goes on the stack."""
    c = [x for x in s.state.cards.values() if x.name == name and x.owner == pid][n]
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, pid, type="play_land", card_id=c.id)
    return c


def test_archway_returning_another_desert_surveils(cards):
    s = build_n(cards, [(2, ARCHWAY)])
    first = enter(s, ARCHWAY, 0)
    second = play(s, ARCHWAY, 1)
    asked = steps(s, answer=first.id)  # the second one returns the first: another Desert
    assert s.state.cards[first.id].zone == "p1:hand" and s.state.cards[second.id].zone == "p1:battlefield"
    assert any("Surveil" in p for p in asked), asked
    check(s)


def test_archway_returning_itself_does_not_surveil(cards):
    s = build_n(cards, [ARCHWAY])
    play(s, ARCHWAY)
    asked = steps(s)
    assert zone_of(s, ARCHWAY) == "p1:hand"  # the only land it could return
    assert not any("Surveil" in p for p in asked), asked
    check(s)


def test_archway_returning_a_forest_does_not_surveil(cards):
    s = build_n(cards, [ARCHWAY])
    forest = enter(s, "Forest")
    play(s, ARCHWAY)
    asked = steps(s, answer=forest.id)
    assert s.state.cards[forest.id].zone == "p1:hand" and zone_of(s, ARCHWAY) == "p1:battlefield"
    assert not any("Surveil" in p for p in asked), asked
    check(s)


# -- Rise of the Witch-king / Deadly Brew ------------------------------------------------------------------------------------------------
def to_graveyard(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


def brewed(cards, spell, in_graveyard=("Hill Giant",), sacrificer="Grizzly Bears"):
    """Alice with ``sacrificer`` on the battlefield (none if None), Bob with a creature; the permanent cards ``in_graveyard`` in Alice's graveyard; the spell cast."""
    s = build(cards, [spell, "Hill Giant", "Soul Warden", *([sacrificer] if sacrificer else [])], ["Hill Giant"])
    put(s, "Hill Giant", "p2")
    if sacrificer:
        put(s, sacrificer)
    for name in in_graveyard:
        to_graveyard(s, name)
    to_hand(s, spell)
    mana(s, "p1", B=1, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, spell).id)
    return s


def test_witch_king_returns_another_permanent_card_but_not_the_one_sacrificed(cards):
    s = brewed(cards, WITCH_KING, in_graveyard=("Hill Giant", "Soul Warden"))
    d = s.state.rules.decision  # which permanent card to return: the Bears, just sacrificed, is no choice ("another")
    assert d is not None and {s.state.cards[o.id].name for o in d.options} == {"Hill Giant", "Soul Warden"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if s.state.cards[o.id].name == "Hill Giant")])
    settle(s)
    assert zone_of(s, "Hill Giant") == "p1:battlefield" and zone_of(s, "Grizzly Bears") == "p1:graveyard" and zone_of(s, "Soul Warden") == "p1:graveyard"
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard"  # Bob sacrificed his only creature too
    check(s)


def test_witch_king_with_only_the_sacrificed_card_in_the_graveyard_returns_nothing(cards):
    s = brewed(cards, WITCH_KING, in_graveyard=())
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard"  # (the Bears is the only permanent card there, and it is no "another")
    check(s)


def test_witch_king_without_a_creature_to_sacrifice_returns_nothing(cards):
    s = brewed(cards, WITCH_KING, in_graveyard=("Hill Giant",), sacrificer=None)
    settle(s)
    assert zone_of(s, "Hill Giant") == "p1:graveyard"  # "If you sacrificed a creature this way": she did not
    check(s)


def test_deadly_brew_returns_another_permanent_card_to_the_hand(cards):
    s = brewed(cards, BREW, in_graveyard=("Soul Warden",))
    d = s.state.rules.decision
    if d is not None:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
    settle(s)
    assert zone_of(s, "Soul Warden") == "p1:hand" and zone_of(s, "Grizzly Bears") == "p1:graveyard"
    check(s)
