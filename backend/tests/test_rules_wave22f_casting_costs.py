"""Wave 22F (casting & costs). Real Oracle text, replay and save/load for each.

* 601.2c / 601.2f: "This spell costs {N} less to cast if it targets …" is read once the targets are chosen.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

EXTRA = [
    real("Seized from Slumber", "{4}{W}", 5, "Instant", "This spell costs {3} less to cast if it targets a tapped creature.\n"
         "Destroy target creature.", None, "W"),
    real("Mystical Dispute", "{2}{U}", 3, "Instant", "This spell costs {2} less to cast if it targets a blue spell.\n"
         "Counter target spell unless its controller pays {3}.", None, "U"),
    real("Vanish into Eternity", "{2}{W}", 3, "Instant", "This spell costs {3} more to cast if it targets a creature.\n"
         "Exile target nonland permanent.", None, "W"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_target_cost_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_costs_less_if_it_targets_a_tapped_creature(cards):
    s = build(cards, ["Seized from Slumber"], ["Grizzly Bears", "Grizzly Bears"])
    spell = to_hand(s, "Seized from Slumber")
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"]
    for c in bears:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p2", type="tap", card_ids=[bears[0].id])
    mana(s, W=1, C=1)  # {4}{W} is out of reach; {1}{W} is the price against a tapped creature
    with pytest.raises(ActionError):  # an untapped target: the full price
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears[1].id])
    assert s.state.cards[spell.id].zone == "p1:hand"  # nothing was paid or moved
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears[0].id])
    answer(s)
    assert s.state.cards[bears[0].id].zone == "p2:graveyard"
    check(s)


def test_costs_less_if_it_targets_a_blue_spell(cards):
    s = build(cards, ["Mystical Dispute", "Lightning Bolt"], ["Opt"])
    dispute, bolt, opt = to_hand(s, "Mystical Dispute"), to_hand(s, "Lightning Bolt"), to_hand(s, "Opt", "p2")
    put(s, "Island", "p2")
    mana(s, U=1, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p2", type="tap", card_ids=[put(s, "Island", "p2").id])
    mana(s, "p2", U=1)
    act(s, "p2", type="cast_spell", card_id=opt.id)  # Bob responds with a blue spell
    with pytest.raises(ActionError):  # a red spell: {2}{U} is out of reach with {U}
        act(s, "p1", type="cast_spell", card_id=dispute.id, targets=[bolt.id])
    act(s, "p1", type="cast_spell", card_id=dispute.id, targets=[opt.id])  # a blue spell: {U}
    answer(s)
    check(s)


def test_costs_more_if_it_targets_a_creature(cards):
    s = build(cards, ["Vanish into Eternity", "Llanowar Elves"], ["Grizzly Bears", "Sol Ring"])
    spell = to_hand(s, "Vanish into Eternity")
    bears, ring = put(s, "Grizzly Bears", "p2"), put(s, "Sol Ring", "p2")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[ring.id])  # not a creature: {2}{W}
    answer(s)
    assert s.state.cards[ring.id].zone == "p2:exile"
    check(s)
    s = build(cards, ["Vanish into Eternity"], ["Grizzly Bears"])
    spell, bears = to_hand(s, "Vanish into Eternity"), put(s, "Grizzly Bears", "p2")
    mana(s, W=1, C=2)
    with pytest.raises(ActionError):  # a creature: {5}{W}
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id])
