"""A token's "created by" link never picks its source out of a hidden zone (found by tools/soak.py with the pod's Group play deck).

Mischievous Mystic's Faerie tokens said ``token_source.source_id``: the Mystic's card id. Once the Mystic went back to its owner's hand,
the other players could tell which hidden card in that hand was the Mystic. The name ("Created by Mischievous Mystic") stays: everyone saw
the token made. Real Oracle text; replay and save/load.
"""

from __future__ import annotations

import json

import pytest

from app.game.views import build_view
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, mana, put, to_hand

EXTRA = [
    real("Mischievous Mystic", "{1}{U}", 2, "Creature — Faerie Wizard",
         "Flying\nWhenever you draw your second card each turn, create a 1/1 blue Faerie creature token with flying.", ("1", "1"), "U"),
    real("Divination", "{2}{U}", 3, "Sorcery", "Draw two cards.", None, "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_a_token_doesnt_point_at_its_source_once_the_source_is_hidden(cards):
    s = build(cards, ["Mischievous Mystic", "Divination"])
    mystic = put(s, "Mischievous Mystic")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Divination").id)
    from tests.test_rules_conditionals import settle

    settle(s)
    faerie = next(c for c in s.state.cards.values() if c.is_token and c.name.startswith("Faerie"))
    seen = build_view(s.state, "p2")["cards"][faerie.id]["token_source"]
    assert seen["name"] == "Mischievous Mystic" and seen["source_id"] == mystic.id  # (the Mystic is on the battlefield: public)
    act(s, "p1", type="move", card_ids=[mystic.id], to={"player": "p1", "zone": "hand"})
    view = build_view(s.state, "p2")
    assert view["cards"][faerie.id]["token_source"] == {"source_id": None, "name": "Mischievous Mystic", "object_id": None}
    assert s.state.cards[mystic.id].zone == "p1:hand" and mystic.id not in json.dumps({k: v for k, v in view.items() if k != "log"})
    assert build_view(s.state, "p1")["cards"][faerie.id]["token_source"]["source_id"] == mystic.id  # (its owner sees their own hand)
    check(s)
