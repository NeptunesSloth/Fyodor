"""Wave 110C: Kusari-Gama (120.1, 508.5, 509.1g): damage to a blocking creature hits each other creature of the defending player."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110c_kit import answer, build, check, make_db, put, real

EXTRA = [real("Kusari-Gama", "{3}", 3, "Artifact — Equipment",
              'Equipped creature has "{2}: This creature gets +1/+0 until end of turn."\n'
              "Whenever equipped creature deals damage to a blocking creature, this Equipment deals that much damage to each other creature defending player controls.\n"
              "Equip {3}", None),
         real("Test Wall", "{1}{W}", 2, "Creature — Wall", "", ("0", "5"), "W"),
         real("Test Bear", "{1}{W}", 2, "Creature — Bear", "", ("2", "2"), "W")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Kusari-Gama")).level == "FULL"


def _fight(cards, block):
    s = build(cards, ["Kusari-Gama", "Grizzly Bears", "Test Bear"], ["Test Wall", "Test Bear"])
    gama, host, mine = put(s, "Kusari-Gama"), put(s, "Grizzly Bears"), put(s, "Test Bear")
    wall, theirs = put(s, "Test Wall", "p2"), put(s, "Test Bear", "p2")
    act(s, "p1", type="attach", card_ids=[gama.id], to=host.id)
    to_phase(s, "declare_attackers", 3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": host.id, "target": "p2"}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": host.id}] if block else [])
    answer(s)
    return s, wall, theirs, mine


def test_blocker_damaged_hits_every_other_defending_creature(cards):
    s, wall, theirs, mine = _fight(cards, True)
    assert s.state.cards[theirs.id].zone == "p2:graveyard"  # 2 damage from the Equipment
    assert s.state.cards[wall.id].damage == 2 and s.state.cards[wall.id].zone == "p2:battlefield"  # the blocker is not hit again
    assert s.state.cards[mine.id].zone == "p1:battlefield" and s.state.cards[mine.id].damage == 0
    check(s)


def test_unblocked_attack_does_nothing(cards):
    s, wall, theirs, mine = _fight(cards, False)
    assert s.state.cards[theirs.id].zone == "p2:battlefield" and s.state.cards[wall.id].damage == 0
    check(s)
