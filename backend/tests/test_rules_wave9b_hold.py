"""Wave 9B: "That creature doesn't untap during its controller's untap step for as long as you control this creature"
(Icefall Regent, Dungeon Geists, Tidebinder Mage, Ty Lee, Merchant Raiders, Time of Ice), researched against CR 2026-09-25.

* 611.2b: the duration ends the moment the source leaves the battlefield or another player controls it; until then the
  tapped creature skips its untap (502.3).
* 502.3: the restriction is on the untap step only; the creature can be untapped by other means.

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_wave7f_untap_choice import play_to
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card('Icefall Regent', set_code='tst', number='H01', mana_cost='{3}{U}{U}', cmc=5.0, type_line='Creature — Dragon', oracle_text="Flying\nWhen this creature enters, tap target creature an opponent controls. That creature doesn't untap during its controller's untap step for as long as you control this creature.\nSpells your opponents cast that target this creature cost {2} more to cast.", power='4', toughness='3', colors=['U'], color_identity=['U'], keywords=['Flying']),  # noqa: E501
    card('Ty Lee, Chi Blocker', set_code='tst', number='H02', mana_cost='{2}{U}', cmc=3.0, type_line='Legendary Creature — Human Performer Ally', oracle_text="Flash\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhen Ty Lee enters, tap up to one target creature. It doesn't untap during its controller's untap step for as long as you control Ty Lee.", power='2', toughness='1', colors=['U'], color_identity=['U'], keywords=['Prowess', 'Flash']),  # noqa: E501
    card('Time of Ice', set_code='tst', number='H03', mana_cost='{3}{U}', cmc=4.0, type_line='Enchantment — Saga', oracle_text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — Tap target creature an opponent controls. It doesn't untap during its controller's untap step for as long as you control this Saga.\nIII — Return all tapped creatures to their owners' hands.", colors=['U'], color_identity=['U']),  # noqa: E501
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_wording_is_exact():
    ok = scripts.parse_effects("Tap target creature an opponent controls. That creature doesn't untap during its controller's "
                               "untap step for as long as you control ~.")
    assert ok is not None and ok[0][1] == {"do": "until", "duration": "source_controlled", "n": 1}
    for text in ("Tap target creature. It doesn't untap during its controller's untap step for as long as an opponent controls ~.",
                 "Tap target creature. It doesn't untap during its controller's untap step for as long as you control a Dragon.",
                 "Tap target creature. It doesn't untap during its controller's untap step for as long as ~ remains untapped.",
                 "Creatures your opponents control don't untap during their controllers' untap steps for as long as you control ~."):
        assert scripts.parse_effects(text) is None, text


def tapped(s, c):
    return s.state.cards[c.id].tapped


def test_the_creature_stays_tapped_while_the_regent_stays_and_untaps_after_it_leaves(cards):
    s = build(cards, p1=("Icefall Regent",), p2=("Ambush Viper",))
    regent = put(s, "Icefall Regent", "hand")
    viper = put(s, "Ambush Viper", "battlefield", pid="p2")
    mana(s, U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=regent.id)
    pass_until_stack_empty(s)
    answer(s, pick=viper.id)
    assert tapped(s, viper)
    play_to(s, 4)  # Bob's untap step: held (502.3, 611.2b)
    assert tapped(s, viper)
    roundtrip(s)
    play_to(s, 6)  # and the next one
    assert tapped(s, viper)
    act(s, "p1", type="set_damage", card_ids=[regent.id], value=3)  # the Regent dies (state-based actions)
    act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[regent.id].zone != "p1:battlefield"
    roundtrip(s)
    play_to(s, 8)  # Bob's next untap step: nothing holds it any more
    assert not tapped(s, viper)
    roundtrip(s)


def test_a_change_of_control_of_the_source_ends_it_too(cards):
    s = build(cards, p1=("Icefall Regent",), p2=("Ambush Viper",))
    regent = put(s, "Icefall Regent", "hand")
    viper = put(s, "Ambush Viper", "battlefield", pid="p2")
    mana(s, U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=regent.id)
    pass_until_stack_empty(s)
    answer(s, pick=viper.id)
    assert tapped(s, viper)
    act(s, "p1", type="set_controller", card_ids=[regent.id], player="p2")  # 611.2b: Alice no longer controls it
    act(s, s.state.rules.priority, type="pass_priority")
    play_to(s, 4)
    assert not tapped(s, viper)
    roundtrip(s)


def test_ty_lee_taps_up_to_one_target_and_holds_it(cards):
    s = build(cards, p1=("Ty Lee, Chi Blocker",), p2=("Ambush Viper",))
    lee = put(s, "Ty Lee, Chi Blocker", "hand")
    viper = put(s, "Ambush Viper", "battlefield", pid="p2")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=lee.id)
    pass_until_stack_empty(s)
    answer(s, pick=viper.id)
    assert tapped(s, viper)
    play_to(s, 4)
    assert tapped(s, viper)
    roundtrip(s)
