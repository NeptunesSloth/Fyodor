"""Wave 44C (combat): commanders one line short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave44c_cards.json). Every scenario checks the replay and a save and a load.

* 509.1c: "Gorm must be blocked if able, and Gorm must be blocked by two or more creatures if able." (Gorm the Great [15293]) - two requirements; a creature that can't block
  it (tapped) is no excuse to demand it, and with only one creature able that one blocks.
* 510.1a: "If Loot's power is negative, he assigns combat damage as though his power were positive." (Loot, the Anomaly [24455]) - only the damage assigned changes, not its power.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import ask, attack, next_turn, settle, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand
from tests.wave44c_kit import DATA, ch, life, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", ["Gorm the Great", "Loot, the Anomaly"])
def test_coverage_full(cards, name):
    data = next(c for c in DATA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or [data], "oracle_id": name}).level == "FULL"


# ---- Gorm the Great [15293] ---------------------------------------------------------------------------------------------------------------------------
def gorm_table(cards, bob):
    s = build(cards, ["Gorm the Great"], bob)
    gorm = put(s, "Gorm the Great")
    for name in bob:
        put(s, name, "p2")
    settle(s)
    next_turn(s)  # (no summoning sickness)
    return s, gorm


def blocks(s, *pairs):
    """Bob declares these (blocker, attacker) blocks once asked."""
    d = ask(s)
    assert d.kind == "declare_blockers" and d.player == "p2"
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in pairs])


def test_gorm_must_be_blocked_by_two_creatures_while_two_can(cards):
    s, gorm = gorm_table(cards, ["Hill Giant", "Grizzly Bears"])
    attack(s, gorm)
    giant, bears = card_named(s, "Hill Giant", "p2"), card_named(s, "Grizzly Bears", "p2")
    with pytest.raises(ActionError, match="must be blocked if able"):
        blocks(s)
    with pytest.raises(ActionError, match="two or more creatures"):
        blocks(s, (giant, gorm))  # the Bears could join the Giant
    blocks(s, (giant, gorm), (bears, gorm))
    assert all(s.state.cards[c.id].blocks(gorm.id) for c in (giant, bears))
    check(s)


def test_gorm_is_blocked_by_the_one_creature_that_can(cards):
    s, gorm = gorm_table(cards, ["Hill Giant"])
    attack(s, gorm)
    giant = card_named(s, "Hill Giant", "p2")
    with pytest.raises(ActionError, match="must be blocked if able"):
        blocks(s)
    blocks(s, (giant, gorm))  # only one creature can block: that one does
    to_phase(s, "main2")
    assert life(s, "p2") == 40
    check(s)


def test_gorm_needs_no_block_when_the_only_creature_is_tapped(cards):
    s, gorm = gorm_table(cards, ["Hill Giant"])
    act(s, "p2", type="tap", card_ids=[card_named(s, "Hill Giant", "p2").id])
    attack(s, gorm)  # (nothing can block: Bob is not even asked)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 2
    check(s)


# ---- Loot, the Anomaly [24455] ------------------------------------------------------------------------------------------------------------------------
def test_loot_assigns_damage_as_though_its_negative_power_were_positive(cards):
    s = build(cards, ["Loot, the Anomaly"], [])
    loot = put(s, "Loot, the Anomaly")  # -2/4
    settle(s)
    next_turn(s)
    assert ch(s, loot).pt == (-2, 4)
    attack(s, loot)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 2  # its power is still -2; it assigns 2
    check(s)


def test_loot_with_positive_power_assigns_its_power(cards):
    s = build(cards, ["Loot, the Anomaly", "Giant Growth"], [])
    loot = put(s, "Loot, the Anomaly")
    settle(s)
    next_turn(s)
    growth = to_hand(s, "Giant Growth")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[loot.id])
    settle(s)
    assert ch(s, loot).pt == (1, 7)
    attack(s, loot)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 1
    check(s)
