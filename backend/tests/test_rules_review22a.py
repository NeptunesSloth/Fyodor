"""Review of wave 22A (group layers), CR 2026-09-25: findings fixed with real Oracle text, replay and save/load.

* 613.8a-b in layer 6: an effect that would take away the ability another "lose all abilities" static comes from goes first
  (Dress Down on Sludge Monster), whatever the timestamps.
* 208.5: a creature whose "*" characteristic-defining ability was taken away (Dress Down; Blood Moon on Ashaya, 305.7) has 0 for
  that "*" (Tarmogoyf 0/1; Ashaya 0/0 dies).
* 614.12 (Magus of the Moon / Blood Moon rulings): a nonbasic land entering under Blood Moon has lost its "enters tapped", "As …
  enters, you may pay 2 life" and "enter as a copy" abilities before they apply; a creature entering under Humility has no "enters
  with X +1/+1 counters".
"""

from __future__ import annotations

import pytest

from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty, rules
from tests.test_rules_permissions import build, put
from tests.test_rules_wave22a_layers import EXTRA, ch, mana_texts, roundtrip

MORE = [
    card('Sludge Monster', set_code="tst", number="R22A1", mana_cost='{3}{U}{U}', cmc=5.0, type_line='Creature — Horror',
         oracle_text='Whenever this creature enters or attacks, put a slime counter on up to one other target creature.\nNon-Horror '
                     'creatures with slime counters on them lose all abilities and have base power and toughness 2/2.', power='5',
         toughness='5', colors=['U'], color_identity=['U']),
    card('Tarmogoyf', set_code="tst", number="R22A2", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Lhurgoyf',
         oracle_text="Tarmogoyf's power is equal to the number of card types among cards in all graveyards and its toughness is equal "
                     "to that number plus 1.", power='*', toughness='1+*', colors=['G'], color_identity=['G']),
    card('Temple of Malady', set_code="tst", number="R22A3", type_line='Land',
         oracle_text='This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that '
                     'card on the bottom.)\n{T}: Add {B} or {G}.'),
    card('Vesuva', set_code="tst", number="R22A4", type_line='Land',
         oracle_text='You may have this land enter tapped as a copy of any land on the battlefield.'),
    card('Walking Ballista', set_code="tst", number="R22A5", mana_cost='{X}{X}', cmc=0.0, type_line='Artifact Creature — Construct',
         oracle_text='This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 counter on this creature.\nRemove a +1/+1 '
                     'counter from this creature: It deals 1 damage to any target.', power='0', toughness='0'),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *MORE], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("sludge_first", [True, False])
def test_dress_down_takes_sludge_monsters_ability_before_it_applies(cards, sludge_first):
    """613.8a: Dress Down would take away the ability Sludge Monster's effect comes from, so that effect depends on it and waits
    (613.8b); by then it doesn't exist: the slimed Elves keep their printed 1/1, whatever the timestamps."""
    s = build(cards, [(1, "Dress Down"), (1, "Sludge Monster"), (1, "Llanowar Elves")])
    elves = put(s, "Llanowar Elves", "battlefield")
    act(s, "p1", type="counter", card_ids=[elves.id], kind="slime", delta=1)
    for name in (["Sludge Monster", "Dress Down"] if sludge_first else ["Dress Down", "Sludge Monster"]):
        put(s, name, "battlefield")
    assert ch(s, elves).pt == (1, 1) and ch(s, elves).abilities == ()
    roundtrip(s)
    put(s, "Dress Down", "graveyard")
    assert ch(s, elves).pt == (2, 2) and ch(s, elves).abilities == ()  # (Sludge Monster's effect again)
    roundtrip(s)


def test_a_lost_star_ability_leaves_zero(cards):
    s = build(cards, [(1, "Dress Down"), (1, "Tarmogoyf"), (1, "Lightning Bolt")])
    goyf = put(s, "Tarmogoyf", "battlefield")
    put(s, "Lightning Bolt", "graveyard")
    assert ch(s, goyf).pt == (1, 2)
    put(s, "Dress Down", "battlefield")
    assert ch(s, goyf).pt == (0, 1)  # 208.5: "*" with no ability defining it is 0
    roundtrip(s)


def test_blood_moon_takes_ashayas_power_and_toughness(cards):
    """Ashaya makes itself a Forest land; Blood Moon (which waits for it, 613.8) makes it a Mountain: it loses its rules text,
    the P/T ability too (305.7), and is 0/0 (208.5): it dies (704.5f)."""
    s = build(cards, [(1, "Blood Moon"), (1, "Ashaya, Soul of the Wild"), (1, "Forest")])
    put(s, "Forest", "battlefield")
    put(s, "Blood Moon", "battlefield")
    ash = put(s, "Ashaya, Soul of the Wild", "battlefield")
    assert ch(s, ash).subtypes == {"Elemental", "Mountain"} and ch(s, ash).pt == (0, 0)
    act(s, "p1", type="pass_priority")
    assert s.state.cards[ash.id].zone == "p1:graveyard"
    roundtrip(s)


def test_lands_entering_under_blood_moon_lose_their_entering_abilities(cards):
    s = build(cards, [(1, "Blood Moon"), (1, "Breeding Pool"), (1, "Temple of Malady"), (1, "Vesuva"), (1, "Command Tower")])
    put(s, "Command Tower", "battlefield")
    pool = put(s, "Breeding Pool", "hand")
    act(s, "p1", type="play_land", card_id=pool.id)
    assert rules(s).decision is not None  # (without Blood Moon: pay 2 life or enter tapped)
    s = build(cards, [(1, "Blood Moon"), (1, "Breeding Pool"), (1, "Temple of Malady"), (1, "Vesuva"), (1, "Command Tower")])
    put(s, "Command Tower", "battlefield")
    put(s, "Blood Moon", "battlefield")
    for name in ("Breeding Pool", "Temple of Malady", "Vesuva"):
        land = put(s, name, "hand")
        rules(s).lands_played.clear()
        act(s, "p1", type="play_land", card_id=land.id)
        land = s.state.cards[land.id]
        assert rules(s).decision is None and land.zone == "p1:battlefield" and not land.tapped, name
        assert not s.state.zones.get("stack") and mana_texts(s, land) == ["{T}: Add {R}."], name  # (no scry trigger, no copy)
    assert s.state.players["p1"].life == 40
    roundtrip(s)


def test_a_creature_entering_under_humility_has_no_enters_with_counters(cards):
    s = build(cards, [(1, "Humility"), (1, "Walking Ballista")])
    put(s, "Humility", "battlefield")
    ballista = put(s, "Walking Ballista", "hand")
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=ballista.id, x_value=2)
    pass_until_stack_empty(s)
    ballista = s.state.cards[ballista.id]
    assert ballista.zone == "p1:battlefield" and not ballista.counters.get("+1/+1") and ch(s, ballista).pt == (1, 1)
    roundtrip(s)
