"""Wave 47B: "target … chosen at random" (CR 2026-09-25), real Oracle text (tests/fixtures/wave47b_cards.json, from data/cards.sqlite). Every scenario
checks the replay and a save and a load.

* The target is a target all the same (115.1, 115.7: it can become illegal), but the table picks it as the ability goes on the stack (601.2c, 603.3d), each
  legal target equally likely; nobody is asked, and a choice sent along is ignored (Scab-Clan Giant, Goblin Test Pilot, Witch Hunt rulings 2013).
* Scab-Clan Giant: "In a multiplayer game, you don't choose a single opponent at random. Any creature controlled by any of your opponents may be chosen."
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_conditionals import through_combat, until
from tests.test_rules_wave34b_activated import activate, settle
from tests.wave9c_kit import card_named, check, mana, put, to_hand
from tests.wave47b_kit import build3, cast, life, open_cards, pin_random


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("index", [0, 1])
def test_scab_clan_giant_fights_one_creature_of_any_opponent_picked_at_random(cards, monkeypatch, index):
    pin_random(monkeypatch, index)
    s = build3(cards, ["Scab-Clan Giant"], bobs=["Grizzly Bears"], carols=["Hill Giant"])
    bears, hill = put(s, "Grizzly Bears", "p2"), put(s, "Hill Giant", "p3")
    to_hand(s, "Scab-Clan Giant")
    mana(s, R=1, G=1, C=4)
    cast(s, "Scab-Clan Giant")
    picked = sorted([bears.id, hill.id])[index]
    gone = [c.id for c in (bears, hill) if s.state.cards[c.id].zone.endswith(":graveyard")]
    assert gone == [picked]  # its 4 damage kills either; the other creature was never touched
    assert s.state.cards[card_named(s, "Scab-Clan Giant").id].damage == (2 if picked == bears.id else 3)
    check(s)


def test_scab_clan_giant_with_no_creature_to_fight_does_nothing(cards):
    s = build3(cards, ["Scab-Clan Giant"])
    to_hand(s, "Scab-Clan Giant")
    mana(s, R=1, G=1, C=4)
    cast(s, "Scab-Clan Giant")
    assert s.state.rules.decision is None and s.state.cards[card_named(s, "Scab-Clan Giant").id].zone == "p1:battlefield"
    check(s)


def test_knight_rampager_deals_4_to_the_opponent_picked_at_random_when_it_dies(cards, monkeypatch):
    pin_random(monkeypatch)
    s = build3(cards, ["Knight Rampager", "Blaze"])
    knight = put(s, "Knight Rampager")
    to_hand(s, "Blaze")
    mana(s, R=6)
    cast(s, "Blaze", targets=[knight.id], x_value=5)  # 5 damage kills the 6/5
    assert s.state.cards[knight.id].zone == "p1:graveyard"
    assert (life(s, "p2"), life(s, "p3")) == (40, 36)
    check(s)


@pytest.mark.parametrize("index", [0, 1])
def test_power_pack_exiles_an_instant_or_sorcery_at_random_and_casts_it_free_next_upkeep_exiling_it_after(cards, monkeypatch, index):
    """Power Pack: the card is picked among the graveyard's instants and sorceries as the trigger goes on the stack; at the next upkeep it may be cast
    without paying its mana cost, and "If that spell would be put into your graveyard, exile it instead." (614.1a)"""
    pin_random(monkeypatch, index)
    s = build3(cards, ["Power Pack", "Lightning Bolt", "Blaze"])
    bolt, blaze = to_hand(s, "Lightning Bolt"), to_hand(s, "Blaze")
    for c in (bolt, blaze):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    put(s, "Power Pack")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, "Power Pack").id, "target": "p2"}])
    through_combat(s)
    picked = sorted([bolt.id, blaze.id])[index]
    assert s.state.cards[picked].zone == "p1:exile" and s.state.cards[({bolt.id, blaze.id} - {picked}).pop()].zone == "p1:graveyard"
    check(s)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "upkeep" and s.state.rules.decision is not None)  # (Alice's next upkeep: may cast it)
    assert s.state.rules.decision.player == "p1"
    check(s)
    settle(s)  # (yes, cast it; its target, if it has one, the first offered)
    assert s.state.cards[picked].zone == "p1:exile"  # cast from exile, resolved: exiled instead of going to the graveyard
    assert s.state.cards[({bolt.id, blaze.id} - {picked}).pop()].zone == "p1:graveyard"
    check(s)


# -- "Choose a creature at random" (not a target): the pick is bound for the instructions after it ---------------------------------------------
def three_creatures(cards, mine):
    s = build3(cards, mine, bobs=["Grizzly Bears"], carols=["Hill Giant"])
    put(s, "Llanowar Elves")
    bears, hill = put(s, "Grizzly Bears", "p2"), put(s, "Hill Giant", "p3")
    return s, sorted([card_named(s, "Llanowar Elves").id, bears.id, hill.id])


@pytest.mark.parametrize("index", [0, 1, 2])
def test_last_one_standing_destroys_every_creature_but_the_one_chosen_at_random(cards, monkeypatch, index):
    pin_random(monkeypatch, index)
    s, ids = three_creatures(cards, ["Last One Standing", "Llanowar Elves"])
    to_hand(s, "Last One Standing")
    mana(s, B=1, R=2)
    cast(s, "Last One Standing")
    alive = [c for c in ids if s.state.cards[c].zone.endswith(":battlefield")]
    assert alive == [ids[index]]
    assert "chosen at random" in str(s.view("p2")["log"])
    check(s)


def test_a_face_down_creature_picked_at_random_is_not_named_in_the_log(cards, monkeypatch):
    s, ids = three_creatures(cards, ["Last One Standing", "Llanowar Elves"])
    hill = next(c for c in ids if s.state.cards[c].name == "Hill Giant")
    act(s, "p3", type="face_down", card_ids=[hill], face_down=True)
    pin_random(monkeypatch, ids.index(hill))
    to_hand(s, "Last One Standing")
    mana(s, B=1, R=2)
    cast(s, "Last One Standing")
    for viewer in ("p1", "p2"):  # (a face-down permanent has no name: 708.2a)
        picks = [e for e in s.view(viewer)["log"] if "chosen at random" in str(e["parts"])]
        assert len(picks) == 1 and "Hill Giant" not in str(picks[0]["parts"])
    check(s)


@pytest.mark.parametrize("index", [0, 2])
def test_the_nipton_lottery_steals_the_creature_chosen_at_random_and_destroys_the_rest(cards, monkeypatch, index):
    pin_random(monkeypatch, index)
    s, ids = three_creatures(cards, ["The Nipton Lottery", "Llanowar Elves"])
    to_hand(s, "The Nipton Lottery")
    mana(s, B=1, R=1, C=2)
    cast(s, "The Nipton Lottery")
    chosen = ids[index]
    assert [c for c in ids if s.state.cards[c].zone.endswith(":battlefield")] == [chosen]
    assert s.state.cards[chosen].controller == "p1"  # until end of turn, whoever's it was
    check(s)


def test_cinderheart_giant_deals_7_to_a_creature_an_opponent_controls_chosen_at_random_when_it_dies(cards, monkeypatch):
    pin_random(monkeypatch, 0)
    s = build3(cards, ["Cinderheart Giant", "Blaze", "Llanowar Elves"], bobs=["Grizzly Bears"], carols=["Hill Giant"])
    giant = put(s, "Cinderheart Giant")
    mine = put(s, "Llanowar Elves")  # (its own controller's creatures are never the pick)
    bears, hill = put(s, "Grizzly Bears", "p2"), put(s, "Hill Giant", "p3")
    to_hand(s, "Blaze")
    mana(s, R=8)
    cast(s, "Blaze", targets=[giant.id], x_value=7)
    assert s.state.cards[giant.id].zone == "p1:graveyard" and s.state.cards[mine.id].zone == "p1:battlefield"
    picked = sorted([bears.id, hill.id])[0]
    assert [c.id for c in (bears, hill) if s.state.cards[c.id].zone.endswith(":graveyard")] == [picked]
    check(s)


def test_witch_hunt_goes_to_the_opponent_picked_at_random_at_the_end_step(cards, monkeypatch):
    pin_random(monkeypatch)  # Carol
    s = build3(cards, ["Witch Hunt"])
    hunt = put(s, "Witch Hunt")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # (Alice's end step is over)
    assert s.state.cards[hunt.id].controller == "p3"
    check(s)


def test_goblin_test_pilot_ignores_a_target_sent_along_and_picks_at_random(cards, monkeypatch):
    pin_random(monkeypatch)  # the last of the legal targets in the table's order: Carol
    s = build3(cards, ["Goblin Test Pilot"])
    pilot = put(s, "Goblin Test Pilot")
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # (no summoning sickness)
    activate(s, "p1", pilot, targets=["p2"])  # (Alice names Bob: the ability's target is not hers to choose)
    settle(s)
    assert (life(s, "p2"), life(s, "p3")) == (40, 38)
    check(s)
