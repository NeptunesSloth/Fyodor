"""-- token piles -- one instruction creating more tokens than one table step makes (replace.MAX_TOKENS_STEP) makes them in several steps; every
step lands on the spot the first one chose, so the tokens lie in one pile (not one pile per hundred). Real Oracle text (Scryfall); each
scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.rules import replace
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, mana, put, to_hand

EXTRA = [
    real("Secure the Wastes", "{X}{W}", 1, "Instant", "Create X 1/1 white Warrior creature tokens.", None, "W"),
    real("Soul Warden", "{W}", 1, "Creature — Human Cleric", "Whenever another creature enters, you gain 1 life.", ("1", "1"), "W"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _warriors(s):
    return [c for c in s.state.cards.values() if c.is_token and c.token and c.token.name == "Warrior" and c.zone == "p1:battlefield"]


def test_two_hundred_fifty_tokens_of_one_instruction_lie_in_one_pile(cards):
    s = build(cards, ["Secure the Wastes", "Soul Warden"])
    put(s, "Soul Warden")  # (a watcher of each token entering: the tokens are made one object each, in table steps of a hundred)
    wastes = to_hand(s, "Secure the Wastes")
    for c in (100, 100, 50):
        mana(s, C=c)
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=wastes.id, x_value=250)
    settle(s, limit=400)
    made = _warriors(s)
    assert len(made) == 250 and sum(c.quantity for c in made) == 250
    assert 250 > replace.MAX_TOKENS_STEP and len({(c.x, c.y) for c in made}) == 1  # one spot: one pile ×250
    check(s)
