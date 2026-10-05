"""Wave 20D: the free_cast long tail (CR 2026-09-25).

* 113.6b / 601.3: "You may cast this card from exile." (Eternal Scourge), "You may cast this card from your graveyard or from exile."
  (Squee, the Immortal): the card's own ability, functioning in those zones.
* 601.3: "Once during each of your turns, you may cast a Zombie creature spell from your graveyard." (Gisa and Geralf; Danitha: an Aura
  or Equipment spell): a capitalised subtype in the permission, once each turn, only the spells it names.

Real Oracle text; each scenario replays the recorded history and survives a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_effects import mana as add_mana
from tests.test_rules_wave19c_ifyoudo import build, find, play_out, roundtrip, to_zone

# --EXTRA-BEGIN--
EXTRA = [
    card('Eternal Scourge', set_code='tst', number='W20D1', mana_cost='{3}', cmc=3.0, type_line='Creature — Eldrazi Horror',
         oracle_text='You may cast this card from exile.\nWhen this creature becomes the target of a spell or ability an opponent controls, exile this creature.', power='3', toughness='3', colors=[], color_identity=[], keywords=[]),
    card('Squee, the Immortal', set_code='tst', number='W20D2', mana_cost='{1}{R}{R}', cmc=3.0, type_line='Legendary Creature — Goblin',
         oracle_text='You may cast this card from your graveyard or from exile.', power='2', toughness='1', colors=['R'], color_identity=['R'], keywords=[]),
    card("Danitha, New Benalia's Light", set_code='tst', number="W20D3", mana_cost='{1}{G}{W}', cmc=3.0, type_line='Legendary Creature — Human Knight',
         oracle_text='Vigilance, trample, lifelink\nOnce during each of your turns, you may cast an Aura or Equipment spell from your graveyard.', power='2', toughness='2', colors=['G', 'W'], color_identity=['G', 'W'], keywords=['Lifelink', 'Vigilance', 'Trample']),
    card('Gisa and Geralf', set_code='tst', number="W20D4", mana_cost='{2}{U}{B}', cmc=4.0, type_line='Legendary Creature — Human Wizard',
         oracle_text='When Gisa and Geralf enters, mill four cards.\nOnce during each of your turns, you may cast a Zombie creature spell from your graveyard.', power='4', toughness='4', colors=['B', 'U'], color_identity=['B', 'U'], keywords=['Mill']),
    card('Zombie Token Maker', set_code='tst', number='W20D5', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Zombie', oracle_text='', power='2', toughness='1', colors=['B'], color_identity=['B']),
    card('Grizzly Test Bear', set_code='tst', number='W20D6', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Bear', oracle_text='', power='2', toughness='2', colors=['B'], color_identity=['B']),
]
FULL = ['Eternal Scourge', 'Squee, the Immortal', "Danitha, New Benalia's Light", 'Gisa and Geralf']
# --EXTRA-END--


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_eternal_scourge_is_cast_from_exile_but_not_from_the_graveyard(cards):
    s = build(cards, p1=("Eternal Scourge",))
    scourge = find(s, "Eternal Scourge")
    to_zone(s, scourge, "graveyard")
    add_mana(s, "p1", C=3)
    with pytest.raises(ActionError):  # only from exile
        act(s, "p1", type="cast_spell", card_id=scourge.id)
    to_zone(s, scourge, "exile")
    act(s, "p1", type="cast_spell", card_id=scourge.id)
    play_out(s)
    assert s.state.cards[scourge.id].zone == "p1:battlefield"
    roundtrip(s)


def test_squee_is_cast_from_the_graveyard_or_from_exile_and_only_by_its_owner(cards):
    s = build(cards, p1=("Squee, the Immortal",))
    squee = find(s, "Squee, the Immortal")
    for where in ("graveyard", "exile"):
        to_zone(s, squee, where)
        add_mana(s, "p1", R=2, C=1)
        act(s, "p1", type="cast_spell", card_id=squee.id)
        play_out(s)
        assert s.state.cards[squee.id].zone == "p1:battlefield"
    to_zone(s, squee, "hand", "p1")
    to_zone(s, squee, "library", "p1")
    assert squee.id in zone(s.state, "p1", "library")
    add_mana(s, "p1", R=2, C=1)
    with pytest.raises(ActionError):  # not from the library
        act(s, "p1", type="cast_spell", card_id=squee.id)
    roundtrip(s)


def test_gisa_and_geralf_cast_a_zombie_from_the_graveyard_once_each_turn(cards):
    s = build(cards, p1=("Gisa and Geralf", "Zombie Token Maker", "Zombie Token Maker", "Grizzly Test Bear"))
    to_zone(s, find(s, "Gisa and Geralf"), "battlefield")
    zombies = [c for c in s.state.cards.values() if c.name == "Zombie Token Maker" and c.owner == "p1"]
    bear = find(s, "Grizzly Test Bear")
    for c in (*zombies, bear):
        to_zone(s, c, "graveyard")
    add_mana(s, "p1", B=6)
    with pytest.raises(ActionError):  # not a Zombie
        act(s, "p1", type="cast_spell", card_id=bear.id)
    act(s, "p1", type="cast_spell", card_id=zombies[0].id)
    play_out(s)
    assert s.state.cards[zombies[0].id].zone == "p1:battlefield"
    with pytest.raises(ActionError):  # once during each of your turns
        act(s, "p1", type="cast_spell", card_id=zombies[1].id)
    assert s.state.cards[zombies[1].id].zone == "p1:graveyard"
    roundtrip(s)
