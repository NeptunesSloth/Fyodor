"""Wave 110A: Teferi, Who Slows the Sunset: +1 untaps the chosen permanents its controller controls and taps the others (608.2c); the -7 emblem untaps its
holder's permanents and draws them a card in each opponent's untap / draw step (502.3, 504.1: turn-based, no trigger)."""

import pytest

from app.rules import coverage
from tests.test_rules_wave30p_combat import to_phase
from tests.wave110c_kit import act, answer, build, check, life, make_db, put, real

TEFERI = "Teferi, Who Slows the Sunset"
EXTRA = [real(TEFERI, "{2}{W}{U}", 4, "Legendary Planeswalker — Teferi",
              "+1: Choose up to one target artifact, up to one target creature, and up to one target land. Untap the chosen permanents you control. Tap the chosen "
              "permanents you don't control. You gain 2 life.\n−2: Look at the top three cards of your library. Put one of them into your hand and the rest on the "
              "bottom of your library in any order.\n−7: You get an emblem with \"Untap all permanents you control during each opponent's untap step\" and \"You draw a "
              "card during each opponent's draw step.\"", None, "WU"),
         real("Sundial Rock", "{1}", 1, "Artifact", "{T}: Add {C}.", None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(TEFERI)).level == "FULL"


def _tap(s, *cards):
    act(s, "p1", type="tap", card_ids=[c.id for c in cards], tapped=True)


def test_plus_untaps_mine_taps_theirs_and_gains_life(cards):
    s = build(cards, [TEFERI, "Grizzly Bears", "Sundial Rock"], ["Sundial Rock", "Llanowar Elves"])
    t, bears, mine_rock = put(s, TEFERI), put(s, "Grizzly Bears"), put(s, "Sundial Rock")
    foe_rock, foe_elf = put(s, "Sundial Rock", "p2"), put(s, "Llanowar Elves", "p2")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    _tap(s, bears, forest)
    act(s, "p1", type="activate_ability", card_id=t.id, ability=0, targets=[mine_rock.id, bears.id, forest.id], target_counts=[1, 1, 1])
    answer(s)
    assert not s.state.cards[bears.id].tapped and not s.state.cards[forest.id].tapped and not s.state.cards[mine_rock.id].tapped
    assert life(s, "p1") == 42
    check(s)


def test_plus_taps_the_permanents_it_does_not_control(cards):
    s = build(cards, [TEFERI], ["Sundial Rock", "Llanowar Elves", "Island"])
    t, rock, elf = put(s, TEFERI), put(s, "Sundial Rock", "p2"), put(s, "Llanowar Elves", "p2")
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=t.id, ability=0, targets=[rock.id, elf.id, island.id], target_counts=[1, 1, 1])
    answer(s)
    assert all(s.state.cards[c.id].tapped for c in (rock, elf, island))
    assert life(s, "p1") == 42
    check(s)


def test_emblem_untaps_and_draws_in_each_opponents_steps(cards):
    s = build(cards, [TEFERI, "Grizzly Bears"])
    t, bears = put(s, TEFERI), put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[t.id], kind="loyalty", delta=7)
    act(s, "p1", type="activate_ability", card_id=t.id, ability=2)
    answer(s)
    assert any(c.zone == "p1:command" for c in s.state.cards.values())
    _tap(s, bears)
    hand = len(s.state.zones["p1:hand"])
    to_phase(s, "main1", 2)  # p2's turn: their untap and draw steps
    assert not s.state.cards[bears.id].tapped
    assert len(s.state.zones["p1:hand"]) == hand + 1
    to_phase(s, "main1", 3)  # p1's own turn: the emblem does nothing for them (one draw)
    assert len(s.state.zones["p1:hand"]) == hand + 2
    check(s)
