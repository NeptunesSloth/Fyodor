"""Wave 20C: ability-word wordings (CR 2026-09-25).

* Eerie — "Whenever an enchantment you control enters and whenever you fully unlock a Room, …" (603.2: it triggers on each of the
  two events; 709.5i: a player "fully unlocks" a Room when it has one of the two unlocked designations and gets the other, or when it
  has neither and gains both). Casting a Room enters an enchantment (the first trigger) and unlocks one door (no full unlock);
  unlocking the second door later is the second trigger. Real Oracle text, a replay and a save/load round trip each."""

from __future__ import annotations

import pytest

from app.cards.importer import build_database
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, on_field, settle, to_hand
from tests.test_rules_effects import mana, replay_matches
from tests.test_rules_wave18g_rooms import EXTRA as ROOMS
DAZZLING = "Dazzling Theater // Prop Room"

EXTRA = [
    *ROOMS,
    card('Gremlin Tamer', set_code='tst', number='Y0', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Human Scout',
         oracle_text='Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, create a 1/1 red Gremlin creature token.',
         power='2', toughness='1', colors=['R'], color_identity=['R'], keywords=[]),
    card('Balemurk Leech', set_code='tst', number='Y1', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Leech',
         oracle_text='Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, each opponent loses 1 life.',
         power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=[]),
    card('Erratic Apparition', set_code='tst', number='Y2', mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Spirit',
         oracle_text='Flying, vigilance\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, this creature gets +1/+1 until end of turn.',
         power='1', toughness='3', colors=['U'], color_identity=['U'], keywords=['Flying', 'Vigilance']),
]
FULL = ['Gremlin Tamer', 'Balemurk Leech', 'Erratic Apparition']


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def reloaded(s):
    return GameSession(s.history.rebuild(), cards=s.cards)


def gremlins(s):
    return [c for c in s.state.cards.values() if c.name == "Gremlin" and c.zone.endswith(":battlefield")]


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_eerie_triggers_when_the_room_enters_and_again_when_it_is_fully_unlocked(cards):
    s = build(cards, "Gremlin Tamer", DAZZLING)
    on_field(s, "Gremlin Tamer")
    room = to_hand(s, DAZZLING)
    mana(s, "p1", W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=room.id, face=0)
    settle(s)
    assert len(gremlins(s)) == 1  # the enchantment entered; one door is unlocked, nothing is fully unlocked yet
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="unlock_door", card_id=room.id, door=2)
    settle(s)
    assert len(gremlins(s)) == 2  # 709.5i: the second designation fully unlocks it
    replay_matches(s)
    replay_matches(reloaded(s))


def test_a_room_that_entered_without_doors_is_fully_unlocked_by_its_second_door_only(cards):
    s = build(cards, "Balemurk Leech", DAZZLING)
    on_field(s, "Balemurk Leech")
    room = on_field(s, DAZZLING)  # (not cast: it enters with neither door unlocked)
    settle(s)
    life = s.state.players["p2"].life
    mana(s, "p1", W=1, C=3)
    act(s, "p1", type="unlock_door", card_id=room.id, door=1)
    settle(s)
    assert s.state.players["p2"].life == life  # the first door: not fully unlocked
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="unlock_door", card_id=room.id, door=2)
    settle(s)
    assert s.state.players["p2"].life == life - 1  # the second door
    replay_matches(s)
    replay_matches(reloaded(s))
