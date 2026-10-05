"""Wave 20A: sized damage. Real Oracle text; every scenario checks the replay and a save/load round trip.

* 115.1 / 601.2c / 701.20a: "Choose any target. Reveal cards from the top of your library until you reveal a nonland card. ~ deals damage equal
  to that card's mana value to that permanent or player. Put the revealed cards on the bottom of your library in any order." (Erratic Explosion)
  and "Choose any target. Scry 3, then reveal the top card of your library. … that card's mana value …" (Riddle of Lightning): the target is
  declared as the spell is cast, whatever the order of the text; no card found, no "that card".
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave6c_tokens_pumps import build, card_named, mana, to_hand
from tests.test_rules_wave15e_keywords import check

EXTRA = [
    card('Erratic Explosion', set_code='tst', number='20A19', mana_cost='{2}{R}', cmc=3.0, type_line='Sorcery', oracle_text="Choose any target. Reveal cards from the top of your library until you reveal a nonland card. Erratic Explosion deals damage equal to that card's mana value to that permanent or player. Put the revealed cards on the bottom of your library in any order.", colors=['R'], color_identity=['R']),  # noqa: E501
    card('Riddle of Lightning', set_code='tst', number='20A20', mana_cost='{3}{R}{R}', cmc=5.0, type_line='Instant', oracle_text="Choose any target. Scry 3, then reveal the top card of your library. Riddle of Lightning deals damage equal to that card's mana value to that permanent or player.", colors=['R'], color_identity=['R']),  # noqa: E501
    card('Stub Giant', set_code='tst', number='20A09', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Giant', oracle_text='', power='2', toughness='2', colors=['G'], color_identity=['G']),  # noqa: E501
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Erratic Explosion", "Riddle of Lightning"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def library_is(s, *names):
    """The library emptied, then exactly these cards in it (the first one on top)."""
    for c in list(s.state.zones["p1:library"]):
        act(s, "p1", type="move", card_ids=[c], to={"player": "p1", "zone": "graveyard"})
    for n in reversed(names):
        c = next(c for c in s.state.cards.values() if c.name == n and c.owner == "p1" and c.zone != "p1:library")
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"})
    assert [s.state.cards[c].name for c in s.state.zones["p1:library"]] == list(names)


@pytest.mark.parametrize("names,damage", [(("Forest", "Stub Giant", "Forest"), 3), (("Forest", "Forest"), 0)])
def test_reveal_until_a_nonland_card_deals_its_mana_value_to_the_chosen_target(cards, names, damage):
    s = build(cards, "Erratic Explosion", "Stub Giant")
    to_hand(s, "Erratic Explosion")
    library_is(s, *names)
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Erratic Explosion").id, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 40 - damage  # no nonland card: there is no "that card", so no damage
    assert sorted(s.state.cards[c].name for c in s.state.zones["p1:library"]) == sorted(names)  # all the revealed cards went to the bottom
    check(s)


def test_riddle_of_lightning_reads_the_revealed_top_card(cards):
    s = build(cards, "Riddle of Lightning", "Stub Giant")
    to_hand(s, "Riddle of Lightning")
    library_is(s, "Stub Giant")
    mana(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Riddle of Lightning").id, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 37
    check(s)
