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


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), HEIST], settings.cards_db_path, meta={"bulk_type": "test"})
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
