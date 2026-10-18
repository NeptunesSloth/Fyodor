"""Wave 46B: the flash Auras (CR 2026-09-25, real Oracle text, tests/fixtures/wave46b_cards.json). Every scenario checks the replay and a save and a load.

* 601.3b: "You may cast this spell as though it had flash" only changes when it may be cast.
* 514.3a: "at the beginning of the next cleanup step" is a delayed trigger (603.7) that waits to go on the stack after the cleanup step's discard and damage
  removal; the players get priority, and another cleanup step begins after it resolves.
* Ruling 2022-12-08 (Ward of Lights, Mystic Veil, Soar, …): the sacrifice happens only if the spell was cast using its own ability, any time a sorcery
  couldn't have been cast (not your main phase, or the stack isn't empty); cast some other way (another effect gave it flash), it isn't sacrificed.
"""

from __future__ import annotations

import pytest

from app.game.rules_state import Permission
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave38a_trailing_ifs import table
from tests.wave9c_kit import card_named, check, mana, put, to_hand
from tests.wave36a_kit import finish_turn, resolve_stack
from tests.wave45c_kit import hold
from tests.wave46b_kit import make_repo, zone

NAMES = ["Ward of Lights", "Mystic Veil", "Lightning Reflexes", "Parapet", "Spider Climb", "Relic Ward", "Armor of Thorns", "Grave Servitude", "Soar"]


@pytest.fixture()
def cards(settings):
    repo = make_repo(settings)
    yield repo
    repo.close()


@pytest.mark.parametrize("name", NAMES)
def test_the_flash_auras_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def over_a_spell(s):
    """Alice has a creature spell on the stack (so a sorcery couldn't be cast) and a creature of hers on the battlefield."""
    put(s, "Grizzly Bears")
    to_hand(s, "Young Wolf")
    hold(s)
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Young Wolf").id)


def test_soar_cast_over_a_spell_is_sacrificed_at_the_next_cleanup_step(cards):
    s = table(cards, ["Soar", "Grizzly Bears", "Young Wolf"])
    over_a_spell(s)
    to_hand(s, "Soar")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Soar").id, targets=[card_named(s, "Grizzly Bears").id])
    resolve_stack(s)
    assert zone(s, "Soar") == "p1:battlefield" and card_named(s, "Soar").attached_to == card_named(s, "Grizzly Bears").id
    finish_turn(s)
    assert zone(s, "Soar") == "p1:graveyard" and zone(s, "Grizzly Bears") == "p1:battlefield"
    check(s)


def test_soar_cast_at_sorcery_timing_stays(cards):
    s = table(cards, ["Soar", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    to_hand(s, "Soar")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Soar").id, targets=[card_named(s, "Grizzly Bears").id])
    resolve_stack(s)
    finish_turn(s)
    assert zone(s, "Soar") == "p1:battlefield"
    check(s)


def test_a_flash_from_another_effect_is_not_sacrificed(cards):
    s = table(cards, ["Mystic Veil", "Grizzly Bears", "Young Wolf"])
    over_a_spell(s)
    s.state.rules.permissions.append(Permission(id="t46b", player="p1", cast=True, flash=True, zone="any", until="end_of_turn",
                                                turn=s.state.turn.number, label="Test: cast spells as though they had flash"))
    to_hand(s, "Mystic Veil")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Mystic Veil").id, targets=[card_named(s, "Grizzly Bears").id])
    resolve_stack(s)
    finish_turn(s)
    assert zone(s, "Mystic Veil") == "p1:battlefield"
    check(s)


def test_parapet_is_sacrificed_too(cards):
    s = table(cards, ["Parapet", "Grizzly Bears", "Young Wolf"])
    over_a_spell(s)
    to_hand(s, "Parapet")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Parapet").id)
    resolve_stack(s)
    assert zone(s, "Parapet") == "p1:battlefield"
    finish_turn(s)
    assert zone(s, "Parapet") == "p1:graveyard"
    check(s)
