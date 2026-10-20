"""Actual canonical collateral coverage for fixed names in costs and tutors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import answer, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / "fixtures/kyscu_patrol_cards.json").read_text())
    for i, c in enumerate(data):
        base[c["name"]] = card(
            c["name"], set_code="sec", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = ["Kyscu Drake", "Spitting Drake", "Viashivan Dragon", "Jungle Patrol"]
    s = table(cards, names, names, names)
    to_phase(s, "main1", turn=1)
    return s


@pytest.mark.parametrize("name", ["Kyscu Drake", "Jungle Patrol"])
def test_actual_canonical_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_kyscu_actual_named_sacrifice_and_tutor(cards):
    s = setup(cards)
    source = put(s, "Kyscu Drake", "battlefield")
    other = put(s, "Spitting Drake", "battlefield")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "Sacrifice"))
    settle(s)
    d = s.state.rules.decision
    if d.resume["step"] != "search":
        assert {o.id for o in d.options} == {other.id}
        answer(s, [other.id])
    d = s.state.rules.decision
    assert d.resume["step"] == "search"
    assert {s.state.cards[o.id].name for o in d.options} == {"Viashivan Dragon"}
    answer(s, [d.options[0].id])
    assert source.zone == "p1:graveyard" and other.zone == "p1:graveyard"
    assert any(c.name == "Viashivan Dragon" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    roundtrip(s)


def test_kyscu_cannot_sacrifice_wrong_name_or_opponents_drake(cards):
    s = setup(cards)
    source = put(s, "Kyscu Drake", "battlefield")
    put(s, "Jungle Patrol", "battlefield")
    put(s, "Spitting Drake", "battlefield", pid="p2")
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "Sacrifice"))
    assert s.state.model_dump(mode="json") == before


def test_jungle_patrol_native_wood_creation_and_mana(cards):
    s = setup(cards)
    source = put(s, "Jungle Patrol", "battlefield")
    to_phase(s, "main1", turn=4)
    mana(s, C=1, G=1)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{1}"))
    settle(s)
    wood = next(c for c in s.state.cards.values() if c.name == "Wood" and c.zone == "p1:battlefield")
    roundtrip(s)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "Sacrifice"))
    if s.state.rules.decision:
        answer(s, [wood.id])
    assert wood.id not in s.state.cards
    assert mana_pool(s, "p1").get("R", 0) == 1
    assert not s.state.rules.stack
    roundtrip(s)


def test_jungle_patrol_cannot_sacrifice_opponents_wood(cards):
    s = setup(cards)
    source = put(s, "Jungle Patrol", "battlefield")
    to_phase(s, "main1", turn=4)
    mana(s, C=1, G=1)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{1}"))
    settle(s)
    wood = next(c for c in s.state.cards.values() if c.name == "Wood" and c.zone == "p1:battlefield")
    act(s, "p1", type="set_controller", card_ids=[wood.id], player="p2")
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "Sacrifice"))
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)
