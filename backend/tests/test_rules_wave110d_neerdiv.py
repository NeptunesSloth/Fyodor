"""Wave 110D: Neerdiv, Devious Diver, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 603.2c, 602.2, 603.10a: "Whenever you cast a spell from your graveyard or activate an ability of a card in your graveyard, draw a card and put a +1/+1
  counter on Neerdiv." — a flashback cast, an unearth activation and an embalm activation (the card exiled as a cost) each draw and grow it once;
  a spell cast from the hand does not.
"""

from __future__ import annotations

import pytest

from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named
from tests.wave110d_kit import EXTRA, ability, cast_on, check, full, mana, put, settle

CAT = real("Sacred Cat", "{W}", 1, "Creature — Cat", "Lifelink\nEmbalm {W} ({W}, Exile this card from your graveyard: Create a token that's a copy of it, except "
           "it's a white Zombie Cat with no mana cost. Embalm only as a sorcery.)", ("1", "1"), "W")


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, CAT], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_neerdiv_is_full():
    assert full("Neerdiv, Devious Diver")


def _gy(s, name):
    c = card_named(s, name, "p1")
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def _hand(s):
    return len(s.state.zones["p1:hand"])


def _neerdiv(cards):
    s = build(cards, ["Neerdiv, Devious Diver", "Firebolt", "Dregscape Zombie", "Sacred Cat", "Lightning Bolt"])
    return s, put(s, "Neerdiv, Devious Diver")


def test_cast_from_hand_does_nothing(cards):
    s, nd = _neerdiv(cards)
    hand, counters = _hand(s), dict(s.state.cards[nd.id].counters)
    cast_on(s, "Lightning Bolt", "p2")
    assert s.state.cards[nd.id].counters == counters and _hand(s) == hand
    check(s)


def test_flashback_and_activations_from_graveyard_each_draw_and_grow(cards):
    s, nd = _neerdiv(cards)
    fb = _gy(s, "Firebolt")
    mana(s, C=4, R=1)
    hand = _hand(s)
    act(s, "p1", type="cast_spell", card_id=fb.id, targets=["p2"])
    settle(s)
    assert _hand(s) == hand + 1 and s.state.cards[nd.id].counters.get("+1/+1") == 1
    zom = _gy(s, "Dregscape Zombie")  # (it may have been drawn)
    hand = _hand(s)
    mana(s, B=1)
    act(s, "p1", type="activate_ability", card_id=zom.id, ability=ability(s, zom, "Unearth"))
    settle(s)
    assert _hand(s) == hand + 1 and s.state.cards[nd.id].counters.get("+1/+1") == 2
    wg = _gy(s, "Sacred Cat")
    hand = _hand(s)
    mana(s, W=1)
    act(s, "p1", type="activate_ability", card_id=wg.id, ability=ability(s, wg, "Embalm"))
    settle(s)
    assert _hand(s) == hand + 1 and s.state.cards[nd.id].counters.get("+1/+1") == 3
    check(s)
