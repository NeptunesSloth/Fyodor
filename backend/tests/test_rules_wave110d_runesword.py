"""Wave 110D: Runesword (wave 110K) against its Oracle text: 611.2a +2/+0 only for the targeted attacker, 508.1 it must be attacking."""
from __future__ import annotations

from tests.wave9c_kit import build
from tests.wave110k_kit import card_db, check  # noqa: F401, F811


# -- Runesword (shares wave 110K's fixtures and combat driver) --
def test_runesword_gives_plus_two_power_to_the_attacker(cards):
    from tests.test_rules_wave110k_cards import _runesword_combat
    from tests.wave110k_kit import now

    s, rune, bears, wall = _runesword_combat(cards, "Twisted Abomination", sword=True, regen_mana=False)
    assert now(s, wall).zone == "p2:exile"  # 2 + 2 = 4 damage kills the 5/3; it is exiled instead of dying (a plain Bears would not kill it)
    s, rune, bears, wall = _runesword_combat(cards, "Twisted Abomination", sword=False, regen_mana=False)
    assert now(s, wall).zone == "p2:battlefield"
    check(s)


def test_runesword_wants_an_attacking_creature(cards):
    from tests.wave110k_kit import mana, put_new, refused, to_phase

    s = build(cards, ["Runesword", "Grizzly Bears"], [])
    rune, bears = put_new(s, "Runesword"), put_new(s, "Grizzly Bears")
    s.state.rules.controlled_since[rune.id].turn = 0
    to_phase(s, "main1", turn=3)
    mana(s, C=3)
    refused(s, "legal target", rune, "{3}", targets=[bears.id])
