"""Dynamic grants bind actual selected spell costs and announced X."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import alt_costs, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_table_activation_modifiers52 import game


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/dynamic_keyword_costs55_cards.json").read_text())
    ):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ['Henzie "Toolbox" Torre', "Herigast, Erupting Nullkite"])
def test_complete_canonical_initial_two(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def offer(s, c):
    plan = Plan(s.state, "p1", s.cards, None)
    offers = alt_costs.offers(s.state, "p1", c, plan.ch(c), s.cards)
    assert len(offers) == 1
    return offers[0]


def test_henzie_grants_real_blitz_body(cards):
    s = game(cards, ['Henzie "Toolbox" Torre', "Shivan Dragon"])
    put(s, 'Henzie "Toolbox" Torre', "battlefield")
    c = put(s, "Shivan Dragon", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 4, "R": 2})
    o = offer(s, c)
    assert o.tag == "blitz" and o.alt.mana_cost.text() == "{4}{R}{R}"
    act(s, "p1", type="cast_spell", card_id=c.id, alt_cost=o.key, sources=[])
    answer(s)
    assert c.zone == "p1:battlefield" and "haste" in Plan(s.state, "p1", cards, None).ch(c).keywords
    roundtrip(s)


@pytest.mark.parametrize("x", [0, 3, 4, 6])
def test_henzie_announced_x_minimum_and_actual_cost(cards, x):
    s = game(cards, ['Henzie "Toolbox" Torre', "Stonecoil Serpent"])
    put(s, 'Henzie "Toolbox" Torre', "battlefield")
    c = put(s, "Stonecoil Serpent", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": x})
    o = offer(s, c)
    action = dict(type="cast_spell", card_id=c.id, alt_cost=o.key, x_value=x, sources=[])
    if x < 4:
        before = s.state.model_dump_json()
        with pytest.raises(ActionError):
            act(s, "p1", **action)
        assert s.state.model_dump_json() == before
    else:
        act(s, "p1", **action)
        answer(s)
        assert c.zone == "p1:battlefield" and c.counters.get("+1/+1") == x
        assert "haste" in Plan(s.state, "p1", cards, None).ch(c).keywords
        roundtrip(s)


def test_herigast_own_sacrifice_preserves_selected_dynamic_emerge(cards):
    s = game(cards, ["Herigast, Erupting Nullkite", "Shivan Dragon"])
    source = put(s, "Herigast, Erupting Nullkite", "battlefield")
    c = put(s, "Shivan Dragon", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 2})
    o = offer(s, c)
    assert o.tag == "emerge"
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=c.id,
        alt_cost=o.key,
        sources=[],
        cost_choices=[{"component": 0, "cards": [source.id]}],
    )
    answer(s)
    assert source.zone == "p1:graveyard" and c.zone == "p1:battlefield"
    roundtrip(s)
