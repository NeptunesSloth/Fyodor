"""Wave 110D: Chef's Kiss, real Oracle text.

* 110.2a/707.10: you gain control of the spell and its copy is yours; 115.7: both get a new target at random, never you or a permanent you control.
* "targets only a single permanent or player" (115.9c): a spell aimed at a card in a graveyard does not qualify.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import stops
from tests.wave9c_kit import build, check, life, mana, put, to_hand
from tests.wave110d_kit import card_db as _kit_db  # noqa: F401
from tests.wave110d_kit import next_turn, now, settle

EXTRA = [real("Chef's Kiss", "{1}{R}{R}", 3, "Instant",
              "Gain control of target spell that targets only a single permanent or player. Copy it, then reselect the targets at random for the spell and the copy. "
              "The new targets can't be you or a permanent you control.", None, "R")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Chef's Kiss")).level == "FULL"


def bolt_at(cards, target_is_creature=False):
    s = build(cards, ["Chef's Kiss", "Grizzly Bears"], ["Lightning Bolt"])
    bears = put(s, "Grizzly Bears")
    next_turn(s)  # p2's turn
    stops(s)
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[bears.id if target_is_creature else "p1"])
    return s, bolt, bears


def kiss(s, bolt):
    k = to_hand(s, "Chef's Kiss")
    mana(s, "p1", R=2, C=1)
    act(s, "p1", type="cast_spell", card_id=k.id, targets=[bolt.id])
    return k


@pytest.mark.parametrize("creature", [False, True])
def test_both_bolts_are_redirected_to_the_only_legal_target(cards, creature):
    s, bolt, bears = bolt_at(cards, creature)
    kiss(s, bolt)
    settle(s)
    assert life(s, "p1") == 40 and now(s, bears).zone == "p1:battlefield"  # neither Bolt can hit me or my creature
    assert life(s, "p2") == 34  # the Bolt (now mine) and its copy, 3 each, at their only legal target
    check(s)


def test_a_spell_without_a_single_target_is_not_a_legal_target(cards):
    s = build(cards, ["Chef's Kiss"], ["Grizzly Bears"])
    next_turn(s)
    stops(s)
    bears = to_hand(s, "Grizzly Bears", "p2")
    mana(s, "p2", G=1, C=1)
    act(s, "p2", type="cast_spell", card_id=bears.id)
    k = to_hand(s, "Chef's Kiss")
    mana(s, "p1", R=2, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=k.id, targets=[bears.id])
