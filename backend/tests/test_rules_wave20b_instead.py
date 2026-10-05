"""-- instead (wave 20B) -- "You may cast target instant or sorcery card from an opponent's graveyard without paying its mana cost. If that
spell would be put into their graveyard, exile it instead." (Arcane Heist; 614.1a: the replacement of where the spell goes, as for Kess).
Oracle text from the card database."""

from __future__ import annotations

import pytest

from app.cards.importer import build_database
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana as add_mana
from tests.test_rules_wave19c_ifyoudo import build, find, play_out, roundtrip, to_zone

HEIST = card('Arcane Heist', set_code='tst', number='W20', mana_cost='{2}{U}{U}', cmc=4.0, type_line='Sorcery',
             oracle_text="You may cast target instant or sorcery card from an opponent's graveyard without paying its mana cost. If that spell would be put into their graveyard, exile it instead.", power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=[])  # noqa: E501
ZOMBIE = card('Gravebane Zombie', set_code='tst', number='W21', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Zombie',
              oracle_text='If this creature would die, put it on top of its owner\'s library instead.', power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=[])  # noqa: E501
CHOSEN = card("Nissa's Chosen", set_code='tst', number='W22', mana_cost='{G}{G}', cmc=2.0, type_line='Creature — Elf Warrior',
              oracle_text="If this creature would die, put it on the bottom of its owner's library instead.", power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=[])  # noqa: E501


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), HEIST, ZOMBIE, CHOSEN], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_arcane_heist_casts_their_bolt_free_and_it_is_exiled(cards):
    s = build(cards, p1=("Arcane Heist",), p2=("Lightning Bolt",))
    bolt = to_zone(s, find(s, "Lightning Bolt", "p2"), "graveyard")
    heist = to_zone(s, find(s, "Arcane Heist"), "hand")
    add_mana(s, "p1", U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=heist.id, targets=[bolt.id])
    play_out(s, prefer=("yes", "p2"))
    assert s.state.players["p2"].life == 37  # the Bolt was cast and resolved
    assert s.state.cards[bolt.id].zone == "p2:exile"  # 614.1a: exiled instead of going to its owner's graveyard
    roundtrip(s)


SAMURAI = "If a permanent would be put into a graveyard, exile it instead."
DRYAD = "If an instant or sorcery card would be put into a graveyard from anywhere, exile it instead."


def test_exile_instead_of_a_graveyard_for_permanents_and_for_instants_and_sorceries(cards):
    s = build(cards, p1=("Lightning Bolt",))
    for name, text in (("Samurai", SAMURAI), ("Dryad", DRYAD)):
        act(s, "p1", type="create_token", player="p1", token={"name": name, "type_line": "Token Creature — Test", "power": "2",
                                                              "toughness": "2", "text": text})
    atraxa = to_zone(s, find(s, "Atraxa, Praetors' Voice", "p2"), "battlefield")
    act(s, "p1", type="set_damage", card_ids=[atraxa.id], value=9)
    act(s, "p1", type="pass_priority")  # a state-based action destroys it (704.5g)
    assert s.state.cards[atraxa.id].zone == "p2:exile"  # 614.1a: a permanent put into a graveyard is exiled instead (the Samurai's)
    d = s.state.rules.decision  # (903.9a: a commander put into exile may go to the command zone; Bob declines)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["no"])
    bolt = to_zone(s, find(s, "Lightning Bolt"), "hand")
    add_mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    play_out(s)
    assert s.state.cards[bolt.id].zone == "p1:exile"  # the Dryad's: an instant card put into a graveyard from anywhere
    roundtrip(s)


PRESENCE = "If a source would deal 4 or more damage to a permanent or player, that source deals 3 damage to that permanent or player instead."


def test_four_or_more_damage_becomes_three(cards):
    from tests.test_rules_combat import attack, automate, creature, table
    from tests.test_rules_conditionals import until

    s = table(cards)
    act(s, "p2", type="create_token", player="p2", token={"name": "Divine Presence", "type_line": "Token Enchantment — Test", "text": PRESENCE})
    big, small = creature(s, "p1", "Big", "5/5"), creature(s, "p1", "Small", "2/2")
    automate(s)
    attack(s, (big, "p2"), (small, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 35  # 614.1a: the 5 became 3 (a source dealing 4 or more); the 2 is untouched
    roundtrip(s)


KUJA = "If a Wizard you control would deal damage to a permanent or player, it deals double that damage instead."


def test_a_wizard_you_control_deals_double_damage(cards):
    from tests.test_rules_combat import attack, automate, table
    from tests.test_rules_conditionals import until

    s = table(cards)
    act(s, "p1", type="create_token", player="p1", token={"name": "Wizard Bear", "type_line": "Token Creature — Wizard", "power": "2",
                                                          "toughness": "2", "text": KUJA})
    act(s, "p1", type="create_token", player="p1", token={"name": "Plain Bear", "type_line": "Token Creature — Bear", "power": "2",
                                                          "toughness": "2"})
    wizard, plain = (next(c for c in s.state.cards.values() if c.name == n) for n in ("Wizard Bear", "Plain Bear"))
    automate(s)
    attack(s, (wizard, "p2"), (plain, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 34  # 614.1a: the Wizard's 2 doubled to 4; the other bear's 2 is not
    roundtrip(s)


@pytest.mark.parametrize(("name", "position"), [("Gravebane Zombie", 0), ("Nissa's Chosen", -1)])
def test_dies_into_the_library_instead(cards, name, position):
    s = build(cards, p1=(name,))
    creature = to_zone(s, find(s, name), "battlefield")
    act(s, "p1", type="set_damage", card_ids=[creature.id], value=2)
    act(s, "p1", type="pass_priority")  # lethal damage: a state-based action (704.5g)
    library = s.state.zones["p1:library"]
    assert library[position] == creature.id and s.state.cards[creature.id].zone == "p1:library"  # 614.1a: top / bottom of its owner's library
    roundtrip(s)
