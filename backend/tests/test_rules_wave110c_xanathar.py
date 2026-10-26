"""Wave 110C: Xanathar, Guild Kingpin. 601.3 / 305.1: the controller may play the top card of the chosen opponent's library this turn; 401.5: only the controller may
look at it; 609.4b: mana of any color pays for those spells; the chosen opponent can't cast spells this turn (101.2)."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import stops, to_phase
from tests.wave9c_kit import build
from tests.wave110c_kit import answer, card_named, check, life, make_db, mana, put, real

TEXT = ("At the beginning of your upkeep, choose target opponent. Until end of turn, that player can't cast spells, you may look at the top card of their library any time, "
        "you may play the top card of their library, and you may spend mana as though it were mana of any color to cast spells this way.")
EXTRA = [real("Xanathar, Guild Kingpin", "{4}{U}{B}", 6, "Legendary Creature — Beholder", TEXT, ("5", "6"), "BU")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def top_of_p2(s, name):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p2" and c.zone == "p2:library")
    act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "library"}, position="top")
    return c


def upkeep(s, top="Lightning Bolt"):
    put(s, "Xanathar, Guild Kingpin")
    to_phase(s, "upkeep", 3)
    c = top_of_p2(s, top)  # (after p2's own draw)
    answer(s, "p2")  # (the target opponent)
    return c


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Xanathar, Guild Kingpin")).level == "FULL"


def test_cast_their_top_card_with_any_color_and_they_cannot_cast(cards):
    s = build(cards, ["Xanathar, Guild Kingpin"], ["Lightning Bolt", "Lightning Bolt"], forests=30, islands=30)
    bolt = upkeep(s)
    to_phase(s, "main1", 3)
    assert s.state.zones["p2:library"][0] == bolt.id
    assert "Lightning Bolt" in json.dumps(s.view("p1"))  # (401.5: the controller looks)
    mana(s, G=1)  # (609.4b: green mana pays {R})
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 37
    assert s.state.cards[bolt.id].zone == "p2:graveyard"  # (owner's graveyard, 400.3)
    with pytest.raises(ActionError):  # (101.2: the chosen opponent can't cast spells)
        other = card_named(s, "Lightning Bolt", "p2")
        act(s, "p2", type="move", card_ids=[other.id], to={"zone": "hand"})
        act(s, "p2", type="cast_spell", card_id=other.id, targets=["p1"])
        raise AssertionError("p2 cast a spell")
    check(s)


def test_play_their_top_land(cards):
    s = build(cards, ["Xanathar, Guild Kingpin"], [])
    island = upkeep(s, "Island")
    to_phase(s, "main1", 3)
    act(s, "p1", type="play_land", card_id=island.id)
    assert s.state.cards[island.id].zone == "p1:battlefield" and s.state.cards[island.id].controller == "p1"
    check(s)


def test_nobody_else_sees_it_and_it_ends_with_the_turn(cards):
    s = build(cards, ["Xanathar, Guild Kingpin"], ["Lightning Bolt", "Lightning Bolt"], forests=30, islands=30)
    bolt = upkeep(s)
    stops(s, "upkeep")
    to_phase(s, "upkeep", 4)  # (p2 has not drawn it yet)
    assert s.state.zones["p2:library"][0] == bolt.id
    mana(s, "p1", R=1)
    assert not s.state.rules.permissions  # (514.2: gone at cleanup)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    check(s)


def test_three_players_only_controller_sees_the_top_card(cards):
    """401.5 / 701.20: with 3 players only Xanathar's controller sees the borrowed top card (views, log, rules hints)."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    d = lambda c, n, f: deck(cards, c, [*((1, x) for x in n), (f, "Forest")])  # noqa: E731
    players = [PlayerSetup("Alice", cards=d("Krenko, Mob Boss", ["Xanathar, Guild Kingpin"], 30)),
               PlayerSetup("Bob", cards=d("Atraxa, Praetors' Voice", ["Lightning Bolt"] * 2, 30)),
               PlayerSetup("Carol", cards=d("Krenko, Mob Boss", [], 30))]
    s = GameSession(enable(new_game(players, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    put(s, "Xanathar, Guild Kingpin")
    to_phase(s, "upkeep", 4)
    bolt = top_of_p2(s, "Lightning Bolt")
    answer(s, "p2")
    to_phase(s, "main1", 4)
    assert s.state.zones["p2:library"][0] == bolt.id
    assert bolt.id in s.view("p1")["cards"]
    for viewer in ("p2", "p3", "__spectator__"):
        v = json.dumps(s.view(viewer))
        assert bolt.id not in v, viewer  # (no view, log or hint names that object)
