"""Wave 110C: Land Equilibrium. 614.1a / 614.12 (replaces an opponent's land entering when they control at least as many lands as its controller), 701.21a
(their choice of land, possibly the one that just entered), rulings 2009-10-01 (any way a land enters: played or put by a spell)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110c_kit import answer, build, card_named, check, make_db, mana, put, real

EQUIL = ("If an opponent who controls at least as many lands as you do would put a land onto the battlefield, that player instead puts that land onto the "
         "battlefield then sacrifices a land of their choice.")
EXTRA = [real("Land Equilibrium", "{2}{U}{U}", 4, "Enchantment", EQUIL, None, "U"),
         real("Yavimaya Dryad", "{1}{G}{G}", 3, "Creature — Dryad",
              "Forestwalk (This creature can't be blocked as long as defending player controls a Forest.)\nWhen this creature enters, you may search your library "
              "for a Forest card, put it onto the battlefield tapped under target player's control, then shuffle.", ("2", "1"), "G"),
         real("Test Fetch", "{1}", 1, "Sorcery", "Put a land card from your hand onto the battlefield.", None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Land Equilibrium")).level == "FULL"


def lands(s, pid):
    return [c for c in s.state.cards.values() if c.zone == f"{pid}:battlefield" and c.name in ("Forest", "Island")]


def setup(cards, mine, theirs):
    s = build(cards, ["Land Equilibrium", "Forest", "Forest", "Forest"], ["Island", "Island", "Island"], forests=0, islands=0)
    put(s, "Land Equilibrium")
    for _ in range(mine):
        c = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    for _ in range(theirs):
        c = next(c for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library")
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    return s


def play_p2(s):
    to_phase(s, "main1", 2)
    land = next(c for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library")
    act(s, "p2", type="move", card_ids=[land.id], to={"zone": "hand"})
    act(s, "p2", type="play_land", card_id=land.id)
    answer(s)
    return land


def test_opponent_with_as_many_lands_sacrifices_one(cards):
    s = setup(cards, 1, 1)
    play_p2(s)
    assert len(lands(s, "p2")) == 1  # 2 lands, one sacrificed
    check(s)


def test_opponent_with_fewer_lands_keeps_them(cards):
    s = setup(cards, 2, 1)
    play_p2(s)
    assert len(lands(s, "p2")) == 2


def test_the_equilibrium_controller_is_unaffected(cards):
    s = setup(cards, 1, 1)
    land = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[land.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=land.id)
    answer(s)
    assert len(lands(s, "p1")) == 2


def test_a_land_put_onto_the_battlefield_by_a_spell_counts_too(cards):  # ruling 2009-10-01
    s = build(cards, ["Land Equilibrium", "Forest"], ["Island", "Island", "Test Fetch"], forests=0, islands=0)
    put(s, "Land Equilibrium")
    act(s, "p2", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library")],
        to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[card_named(s, "Forest").id], to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "main1", 2)
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.zone in ("p2:library", "p2:hand"))
    act(s, "p2", type="move", card_ids=[island.id], to={"zone": "hand"})
    fetch = card_named(s, "Test Fetch", "p2")
    act(s, "p2", type="move", card_ids=[fetch.id], to={"zone": "hand"})
    mana(s, "p2", C=1)
    act(s, "p2", type="cast_spell", card_id=fetch.id)
    answer(s)
    assert len(lands(s, "p2")) == 1  # two lands after the spell put one, then one sacrificed


@pytest.mark.parametrize("target", ["p1", "p2"])
def test_land_put_under_another_players_control_is_sacrificed_by_the_putter(cards, target):  # ruling 2009-10-01 (Yavimaya Dryad)
    s = build(cards, ["Land Equilibrium", "Forest"], ["Yavimaya Dryad", "Forest", "Forest"], forests=0, islands=0)
    put(s, "Land Equilibrium")
    act(s, "p1", type="move", card_ids=[card_named(s, "Forest").id], to={"player": "p1", "zone": "battlefield"})
    f = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p2:library")
    act(s, "p2", type="move", card_ids=[f.id], to={"player": "p2", "zone": "battlefield"})
    to_phase(s, "main1", 2)
    dryad = card_named(s, "Yavimaya Dryad", "p2")
    act(s, "p2", type="move", card_ids=[dryad.id], to={"zone": "hand"})
    mana(s, "p2", G=3)
    act(s, "p2", type="cast_spell", card_id=dryad.id)
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options]
        pick = target if target in ids else ids[0]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.zone.endswith(":battlefield")]
    # p2 (the putter) has as many lands as p1: the Forest enters under `target`, and p2 (not its controller) sacrifices a land of its own
    assert [sum(1 for c in forests if c.controller == p) for p in ("p1", "p2")] == ([2, 0] if target == "p1" else [1, 1])
    check(s)
