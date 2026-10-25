"""Wave 110D: Ghostly Dancers, Marina Vendrell (real Oracle text, tests/fixtures/wave110d_cards.json).

* 709.5f: "unlock a locked door of a Room you control" (Ghostly Dancers; or return an enchantment card from the graveyard, 608.2c choice on resolution).
* 709.5g: "Lock or unlock a door of target Room you control" (Marina Vendrell, sorcery speed, {T}).
* 709.5h-i: unlocking this way still triggers "when you unlock this door" and eerie's "fully unlock".
"""

from __future__ import annotations

import pytest

from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave18g_rooms import EXTRA as ROOMS
from tests.test_rules_wave18g_rooms import GRAND, doors, glimmers
from tests.wave110d_kit import (
    EXTRA,
    ability,
    build,
    check,
    full,
    grave_new,
    hand_new,
    mana,
    put_new,
    settle,
    to_phase,
)


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *ROOMS], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Ghostly Dancers", "Marina Vendrell", "Keys to the House"])
def test_full(name):
    assert full(name)


def spirits(s):
    return [c for c in s.state.cards.values() if c.name == "Spirit" and c.zone.endswith(":battlefield")]


def cast_room(s):
    room = hand_new(s, GRAND)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=room.id, face=0)
    settle(s)
    return room


def cast_dancers(s, answers):
    c = hand_new(s, "Ghostly Dancers")
    mana(s, "p1", C=3, W=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s, answers=answers)


def test_dancers_unlock_a_locked_door_and_fully_unlock(cards):
    s = build(cards, ["Ghostly Dancers", GRAND])
    room = cast_room(s)
    assert doors(s, room) == [1] and len(glimmers(s)) == 1
    cast_dancers(s, [f"{room.id}|2"])
    assert doors(s, room) == [1, 2]
    assert len(spirits(s)) == 1  # eerie: only the Room fully unlocked (709.5i); the Dancers is no enchantment
    check(s)


def test_dancers_return_an_enchantment_instead(cards):
    s = build(cards, ["Ghostly Dancers", GRAND, GRAND])
    room = cast_room(s)
    grave = grave_new(s, GRAND)
    cast_dancers(s, [grave.id])
    assert s.state.cards[grave.id].zone == "p1:hand" and doors(s, room) == [1]
    check(s)


def test_dancers_do_nothing_without_options(cards):
    s = build(cards, ["Ghostly Dancers"])
    cast_dancers(s, [])
    assert not s.state.rules.decision
    check(s)


def marina(s, room, pick):
    m = put_new(s, "Marina Vendrell")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="activate_ability", card_id=m.id, ability=ability(s, m, "{T}: Lock or unlock"), targets=[room.id])
    settle(s, answers=[pick])


def test_marina_locks_an_unlocked_door(cards):
    s = build(cards, ["Marina Vendrell", GRAND])
    room = cast_room(s)
    marina(s, room, f"{room.id}|1")
    assert doors(s, room) == []
    check(s)


def test_marina_unlocks_a_locked_door_with_its_trigger(cards):
    s = build(cards, ["Marina Vendrell", GRAND])
    room = cast_room(s)
    marina(s, room, f"{room.id}|2")
    assert doors(s, room) == [1, 2] and len(spirits(s)) == 0
    check(s)


def test_keys_to_the_house_sacrifices_and_unlocks(cards):
    s = build(cards, ["Keys to the House", GRAND])
    room = cast_room(s)
    keys = put_new(s, "Keys to the House")
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=keys.id, ability=ability(s, keys, "{3}, {T}, Sacrifice"), targets=[room.id])
    settle(s, answers=[f"{room.id}|2"])
    assert doors(s, room) == [1, 2] and s.state.cards[keys.id].zone == "p1:graveyard"
    check(s)
