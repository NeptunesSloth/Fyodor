"""Wave 110B session 11: single cards read from an exact wording (real Oracle text in tests/fixtures/wave110b_cards.json).

* Scholarship Sponsor: 701.23, 101.4 each player with fewer lands than the most searches for up to the difference in basic lands, tapped.
* Desert Warfare: 603.2c a Desert sacrificed or put into your graveyard from your hand or library returns at your next end step (400.7: that card);
  at the beginning of your combat with five or more Deserts, a hasty Sand Warrior for each.
* Cosmic Intervention: 614.1a, 611.2a a permanent you control put into a graveyard from the battlefield this turn is exiled instead and returns at the next end step.
* Toggo, Goblin Weaponsmith: 111.4, 702.6, 613.1f the Rock token's "Equipped creature has '… Sacrifice Rock: …'" is the Equipment's own granted ability (the creature deals the damage).
* Mirror of Life Trapping: 607.2a linked exile; a cast creature is exiled as it enters and every other permanent card exiled with it returns (400.7).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import build, card_named, ch, check, drive, mana, put, repository, to_hand


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Mirror of Life Trapping", "Scholarship Sponsor", "Desert Warfare", "Cosmic Intervention", "Toggo, Goblin Weaponsmith"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_mirror_of_life_trapping_exiles_cast_creatures_and_returns_the_others(cards):
    s = build(cards, ["Mirror of Life Trapping", "Grizzly Bears", "Shivan Dragon"], [])
    put(s, "Mirror of Life Trapping")
    bears = card_named(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    mana(s, "p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)
    drive(s)
    assert s.state.cards[bears.id].zone == "p1:exile"
    mana(s, "p1", R=2, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Shivan Dragon").id)
    drive(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    assert s.state.cards[card_named(s, "Shivan Dragon").id].zone == "p1:exile"
    check(s)


def test_mirror_of_life_trapping_ignores_creatures_that_were_not_cast(cards):
    s = build(cards, ["Mirror of Life Trapping", "Grizzly Bears"], [])
    put(s, "Mirror of Life Trapping")
    put(s, "Grizzly Bears")
    assert s.state.cards[card_named(s, "Grizzly Bears").id].zone == "p1:battlefield"
    check(s)


def _land(s, pid, name):
    """A different card of that name from the library each call (put() returns the same one)."""
    cid = next(c for c in s.state.zones[f"{pid}:library"] if s.state.cards[c].name == name)
    act(s, pid, type="move", card_ids=[cid], to={"player": pid, "zone": "battlefield"})


def _lands(s, pid):
    return [c for c in s.state.cards.values() if c.controller == pid and c.zone.endswith(":battlefield") and c.name in ("Forest", "Island")]


@pytest.mark.parametrize("mine, theirs, gain_p1, gain_p2", [(0, 3, 3, 0), (4, 1, 0, 3), (2, 2, 0, 0), (1, 2, 1, 0)])
def test_scholarship_sponsor_fetches_the_land_difference_for_each_trailing_player(cards, mine, theirs, gain_p1, gain_p2):
    s = build(cards, ["Scholarship Sponsor"], [], forests=40, islands=40)
    for _ in range(mine):
        _land(s, "p1", "Forest")
    for _ in range(theirs):
        _land(s, "p2", "Island")
    before = len(_lands(s, "p1")), len(_lands(s, "p2"))
    mana(s, "p1", W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Scholarship Sponsor").id)
    drive(s, lambda d: [o.id for o in d.options][: d.max_choices])
    assert len(_lands(s, "p1")) - before[0] == gain_p1
    assert len(_lands(s, "p2")) - before[1] == gain_p2
    assert all(c.tapped for c in _lands(s, "p1")[mine:]) and all(c.tapped for c in _lands(s, "p2")[theirs:])
    check(s)


DESERTS = ["Desert", "Hostile Desert", "Endless Sands", "Hashep Oasis", "Ipnu Rivulet"]


def test_desert_warfare_returns_a_discarded_desert_at_the_end_step_but_not_other_lands(cards):
    s = build(cards, ["Desert Warfare", "Desert", "Mind Rot"], [])
    put(s, "Desert Warfare")
    desert = to_hand(s, "Desert")
    forests = [to_hand(s, "Forest").id]
    mana(s, "p1", B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Mind Rot").id, targets=["p1"])
    drive(s, lambda d: [desert.id, *forests][: d.max_choices] if desert.id in [o.id for o in d.options] else None)
    assert s.state.cards[desert.id].zone == "p1:graveyard" and s.state.cards[forests[0]].zone == "p1:graveyard"
    to_phase(s, "main1", turn=2)  # (the end step of turn 1 passes without a stop)
    drive(s)
    assert s.state.cards[desert.id].zone == "p1:battlefield"
    assert s.state.cards[forests[0]].zone == "p1:graveyard"
    check(s)


def test_desert_warfare_returns_a_sacrificed_desert(cards):
    s = build(cards, ["Desert Warfare", "Zuran Orb", "Desert"], [])
    put(s, "Desert Warfare")
    put(s, "Zuran Orb")
    desert = put(s, "Desert")
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Zuran Orb").id, ability=0)
    drive(s, lambda d: [desert.id] if desert.id in [o.id for o in d.options] else None)
    assert s.state.cards[desert.id].zone == "p1:graveyard"
    to_phase(s, "main1", turn=2)  # (the end step of turn 1 passes without a stop)
    drive(s)
    assert s.state.cards[desert.id].zone == "p1:battlefield"
    check(s)


@pytest.mark.parametrize("n, warriors", [(5, 5), (4, 0)])
def test_desert_warfare_makes_a_hasty_sand_warrior_for_each_desert(cards, n, warriors):
    s = build(cards, ["Desert Warfare", *DESERTS], [])
    put(s, "Desert Warfare")
    for name in DESERTS[:n]:
        put(s, name)
    to_phase(s, "declare_attackers" if warriors else "main2", turn=1)  # (the tokens, with haste, can attack: a decision)
    made = [c for c in s.state.cards.values() if c.name == "Sand Warrior" and c.zone == "p1:battlefield"]
    assert len(made) == warriors
    assert (s.state.rules.decision is not None) == bool(warriors)
    check(s)


@pytest.mark.parametrize("mine, zone_after, returns", [(True, "p1:battlefield", True), (False, "p2:graveyard", False)])
def test_cosmic_intervention_exiles_only_your_permanents_and_returns_them(cards, mine, zone_after, returns):
    s = build(cards, ["Cosmic Intervention", "Grizzly Bears", "Lightning Bolt"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p1" if mine else "p2")
    mana(s, "p1", W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Cosmic Intervention").id)
    drive(s)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[bears.id])
    drive(s)
    assert s.state.cards[bears.id].zone == ("p1:exile" if mine else "p2:graveyard")
    to_phase(s, "main1", turn=2)
    drive(s)
    assert s.state.cards[bears.id].zone == zone_after
    check(s)


def test_toggo_makes_a_rock_that_lets_the_equipped_creature_deal_2_damage(cards):
    """The granted {1},{T}, Sacrifice Rock ability is the creature's, so its lifelink gains the life."""
    s = build(cards, ["Toggo, Goblin Weaponsmith", "Vampire Nighthawk", "Forest"], [])
    put(s, "Toggo, Goblin Weaponsmith")
    hawk = put(s, "Vampire Nighthawk")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="play_land", card_id=to_hand(s, "Forest").id)
    drive(s)
    rock = next(c for c in s.state.cards.values() if c.name == "Rock" and c.zone == "p1:battlefield")
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=rock.id, ability=1, targets=[hawk.id])  # (Equip {1})
    drive(s)
    life = s.state.players["p1"].life
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=hawk.id, ability=next(a.index for a in ch(s, hawk).abilities if a.kind == "activated"), targets=["p2"])
    drive(s)
    assert s.state.players["p2"].life == 38 and s.state.players["p1"].life == life + 2
    assert rock.id not in s.state.cards  # (sacrificed: the token ceased to exist)
    check(s)
