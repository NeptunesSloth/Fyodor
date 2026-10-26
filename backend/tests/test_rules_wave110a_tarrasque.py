"""Wave 110A: You Look Upon the Tarrasque, "Gather Your Courage": all creatures the CASTER's opponents control able to block the target do so (509.1c),
whoever controls the target; the pump and indestructible last until end of turn."""

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_combat import attack, block
from tests.test_rules_wave30p_combat import to_phase
from tests.wave9c_kit import build, to_hand
from tests.wave110c_kit import answer, check, make_db, mana, put, real

EXTRA = [real("You Look Upon the Tarrasque", "{4}{G}", 5, "Instant",
              "Choose one —\n• Run and Hide — Prevent all combat damage that would be dealt to you and creatures you control this turn.\n"
              "• Gather Your Courage — Target creature gets +5/+5 and gains indestructible until end of turn. All creatures your opponents control able to block "
              "that creature this turn do so.", None, "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("You Look Upon the Tarrasque")).level == "FULL"


def _cast(s, target):
    mana(s, "p1", G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "You Look Upon the Tarrasque").id, modes=[1], targets=[target.id])
    answer(s)


def test_my_attacker_is_blocked_by_all_my_opponents_creatures(cards):
    s = build(cards, ["You Look Upon the Tarrasque", "Grizzly Bears"], ["Benalish Hero"])
    bears, guard = put(s, "Grizzly Bears"), put(s, "Benalish Hero", pid="p2")
    to_phase(s, "main1", 3)
    _cast(s, bears)
    to_phase(s, "declare_attackers", 3)
    attack(s, (bears, "p2"))
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2")
    block(s, "p2", (guard, bears))
    check(s)


def test_an_opponents_attacker_does_not_force_my_creatures(cards):
    """The caster p1 targets p2's attacker: p2's creatures are the caster's opponents', so p1's creature is not made to block."""
    s = build(cards, ["You Look Upon the Tarrasque", "Grizzly Bears"], ["Benalish Hero"])
    foe = put(s, "Benalish Hero", pid="p2")
    put(s, "Grizzly Bears")
    act(s, "p1", type="set_stops", own=[], others=["declare_attackers"], smart_pass=False)
    to_phase(s, "declare_attackers", 4)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": foe.id, "target": "p1"}])
    _cast(s, foe)
    while s.state.rules.decision is None or s.state.rules.decision.kind != "declare_blockers":
        act(s, s.state.rules.priority, type="pass_priority")
    block(s, "p1")  # no block: the lure binds p2's creatures only
    check(s)
