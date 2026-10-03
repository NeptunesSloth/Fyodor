"""Wave 13E: mass "don't untap during … next untap step" (Sleep, Bontu's Last Reckoning, Exhaustion, Mana Vapors, Kiora
Bests the Sea God), researched against CR 2026-09-25.

* 502.3: effects can keep permanents from untapping. 611.2c: a resolution effect that modifies no characteristics applies
  to whatever matches when the untap step comes ("Lands you control …": a land that entered later is held too); "those
  creatures" (Sleep) are the objects the tap named. The effect ends with that player's untap step.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, on_field, settle, to_hand, to_turn
from tests.test_rules_effects import mana
from tests.test_rules_wave4h_activation_costs import build, roundtrip
from tests.test_rules_wave6a_permanent_effects import EXTRA as OLD

EXTRA = [c for c in OLD if c["name"] in ("Sleep", "Bontu's Last Reckoning")] + [
    card('Exhaustion', set_code="tst", number="N01", mana_cost='{2}{U}{U}', cmc=4.0, type_line='Sorcery', oracle_text="Creatures and lands target opponent controls don't untap during their next untap step.", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Mana Vapors', set_code="tst", number="N02", mana_cost='{1}{U}', cmc=2.0, type_line='Sorcery', oracle_text="Lands target player controls don't untap during their next untap step.", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Kiora Bests the Sea God', set_code="tst", number="N03", mana_cost='{5}{U}{U}', cmc=7.0, type_line='Enchantment — Saga', oracle_text="I — Create a 8/8 blue Kraken creature token.\nII — Tap all nonland permanents target opponent controls. They don't untap during their controller's next untap step.\nIII — Gain control of target permanent an opponent controls.", colors=['U'], color_identity=['U']),  # noqa: E501
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Sleep", "Bontu's Last Reckoning", "Exhaustion", "Mana Vapors"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def tapped(s, c):
    return s.state.cards[c.id].tapped


def test_sleep_holds_those_creatures_for_that_players_next_untap_step(cards):
    s = build(cards, p1=("Sleep",))
    sleep = to_hand(s, "Sleep")
    a, b = creature(s, "p2", "Ox"), creature(s, "p2", "Yak")
    mana(s, U=4)
    act(s, "p1", type="cast_spell", card_id=sleep.id, targets=["p2"])
    settle(s)
    assert tapped(s, a) and tapped(s, b) and len(s.state.rules.stay_tapped) == 2
    roundtrip(s)
    to_turn(s, 2)  # Bob's untap step: they stay tapped (502.3)
    assert tapped(s, a) and tapped(s, b) and not s.state.rules.stay_tapped
    to_turn(s, 4)
    assert not tapped(s, a) and not tapped(s, b)
    roundtrip(s)


def test_lands_you_control_means_the_lands_you_control_when_the_untap_step_comes(cards):
    s = build(cards, p1=("Bontu's Last Reckoning", "Forest"))
    bontu = to_hand(s, "Bontu's Last Reckoning")
    old = on_field(s, "Forest")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=bontu.id)
    settle(s)
    act(s, "p1", type="tap", card_ids=[old.id], tapped=True)
    late = to_hand(s, "Forest")  # a land that arrives after the spell resolved is held too (611.2c)
    act(s, "p1", type="move", card_ids=[late.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="tap", card_ids=[late.id], tapped=True)
    roundtrip(s)
    to_turn(s, 2)  # Bob's untap step: not Alice's
    assert tapped(s, old) and s.state.rules.stay_tapped
    to_turn(s, 3)  # Alice's: both stay tapped, and the effect ends
    assert tapped(s, old) and tapped(s, late) and not s.state.rules.stay_tapped
    to_turn(s, 5)
    assert not tapped(s, old) and not tapped(s, late)
    roundtrip(s)


def test_exhaustion_holds_creatures_and_lands_but_not_other_permanents(cards):
    s = build(cards, p1=("Exhaustion",), p2=("Island",))
    spell = to_hand(s, "Exhaustion")
    ox = creature(s, "p2", "Ox")
    isle = on_field(s, "Island", pid="p2")
    ring = creature(s, "p2", "Ring", type_line="Token Artifact — Test")
    mana(s, U=4)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    settle(s)
    for c in (ox, isle, ring):
        act(s, "p2", type="tap", card_ids=[c.id], tapped=True)
    to_turn(s, 2)
    assert tapped(s, ox) and tapped(s, isle) and not tapped(s, ring)
    to_turn(s, 4)
    assert not tapped(s, ox) and not tapped(s, isle)
    roundtrip(s)
