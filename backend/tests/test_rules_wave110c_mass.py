"""Wave 110C mass effects built from the native grammar (608.2c: the instructions in the printed order).

* Over the Top: reveal as many cards as nonland permanents you control, permanent cards enter together, the rest go to the graveyard (701.20a, 603.6a, 303.4f-g).
* Scrap Mastery: exile every graveyard's artifact cards, sacrifice every artifact, then put the cards exiled by the first step onto the battlefield (701.21a, 404.1).
"""

from __future__ import annotations

import pytest
from tests.game_helpers import act

from app.rules import coverage
from tests.wave110c_kit import answer, build, card_named, cast, check, make_db, mana, put, real, zone

EXTRA = [
    real('Scrap Mastery', '{3}{R}{R}', 5, 'Sorcery',
         'Each player exiles all artifact cards from their graveyard, then sacrifices all artifacts they control, then puts all cards they exiled this way onto the battlefield.', None, 'R'),
    real('Over the Top', '{5}{R}{R}', 7, 'Sorcery',
         'Each player reveals a number of cards from the top of their library equal to the number of nonland permanents they control, puts all permanent cards they revealed this way onto the battlefield, and puts the rest into their graveyard.', None, 'R'),
    real('Pacifism', '{1}{W}', 2, 'Enchantment — Aura', "Enchant creature\nEnchanted creature can't attack or block.", None, 'W'),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_scrap_mastery_swaps_each_players_graveyard_artifacts_for_those_on_the_battlefield(cards):
    """Scrap Mastery: Alice's ring is sacrificed and her graveyard Signet returns; Bob's Signet is sacrificed and his graveyard ring returns."""
    s = build(cards, ["Scrap Mastery", "Sol Ring", "Arcane Signet"], ["Sol Ring", "Arcane Signet"])
    a_ring, a_signet = card_named(s, "Sol Ring"), card_named(s, "Arcane Signet")
    b_ring, b_signet = card_named(s, "Sol Ring", "p2"), card_named(s, "Arcane Signet", "p2")
    put(s, "Sol Ring")
    act(s, "p1", type="move", card_ids=[a_signet.id], to={"player": "p1", "zone": "graveyard"})
    put(s, "Arcane Signet", "p2")
    act(s, "p2", type="move", card_ids=[b_ring.id], to={"player": "p2", "zone": "graveyard"})
    mana(s, R=2, C=3)
    cast(s, "Scrap Mastery")
    answer(s)
    assert [zone(s, c) for c in (a_ring, a_signet, b_ring, b_signet)] == ["p1:graveyard", "p1:battlefield", "p2:battlefield", "p2:graveyard"]
    assert s.state.cards[a_signet.id].controller == "p1" and s.state.cards[b_ring.id].controller == "p2"
    check(s)


def _top(s, name, pid="p1"):
    act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"zone": "library"}, position="top")


def test_over_the_top_permanents_enter_together_and_the_rest_go_to_the_graveyard(cards):
    """Over the Top: Alice controls two nonland permanents, so she reveals two (a creature and an instant); Bob controls none and reveals nothing."""
    s = build(cards, ["Over the Top", "Grizzly Bears", "Lightning Bolt", "Sol Ring", "Kami of Ancient Law"], ["Grizzly Bears"])
    put(s, "Sol Ring")
    put(s, "Kami of Ancient Law")
    _top(s, "Lightning Bolt")
    _top(s, "Grizzly Bears")
    theirs = len(s.state.zones["p2:library"])
    mana(s, R=2, C=5)
    cast(s, "Over the Top")
    answer(s)
    bears, bolt = card_named(s, "Grizzly Bears"), card_named(s, "Lightning Bolt")
    assert zone(s, bears) == "p1:battlefield" and zone(s, bolt) == "p1:graveyard"
    assert len(s.state.zones["p2:library"]) == theirs and not s.state.zones["p2:graveyard"]
    check(s)


@pytest.mark.parametrize("has_creature", [True, False])
def test_over_the_top_an_aura_enchants_a_creature_already_there_never_one_entering_with_it(cards, has_creature):
    """Over the Top: Bob's Bears is the only creature an Aura can enchant (303.4f: not Alice's Bears entering at the same time); with none the Aura
    stays in the library and goes to the graveyard with the rest (303.4g)."""
    s = build(cards, ["Over the Top", "Grizzly Bears", "Pacifism", "Sol Ring", "Arcane Signet"], ["Grizzly Bears"])
    theirs = put(s, "Grizzly Bears", "p2") if has_creature else None
    put(s, "Sol Ring")
    put(s, "Arcane Signet")  # (two nonland permanents: she reveals two cards)
    _top(s, "Pacifism")
    _top(s, "Grizzly Bears")
    mana(s, R=2, C=5)
    cast(s, "Over the Top")
    answer(s)
    aura, bears = card_named(s, "Pacifism"), card_named(s, "Grizzly Bears")
    assert zone(s, bears) == "p1:battlefield"
    if has_creature:
        assert zone(s, aura) == "p1:battlefield" and s.state.cards[aura.id].attached_to == theirs.id
    else:
        assert zone(s, aura) == "p1:graveyard"
    check(s)
