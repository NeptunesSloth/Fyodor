"""Korvold counts native own sacrifice card-type receipts at cost lock."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Korvold, Gleeful Glutton"]
DATA = json.loads((Path(__file__).parent / "fixtures/sacrifice_type_costs82_cards.json").read_text())


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    ns = [c["name"] for c in DATA] * 2
    s = table(cards, ns, ns, ns)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4)
    return s, put(s, NAMES[0], "hand")


def sac(s, target, pid="p1"):
    claws = put(s, "Claws of Gix", "battlefield", pid)
    act(s, pid, type="add_mana", player=pid, mana={"C": 1})
    wait_priority(s, pid)
    act(s, pid, type="activate_ability", card_id=claws.id, ability=0, sources=[],
        cost_choices=[{"component": 1, "cards": [target.id]}])
    answer(s)
    assert target.id not in s.state.cards or not s.state.cards[target.id].zone.endswith(":battlefield")


def cast(s, c, generic):
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": generic, "B": 1, "R": 1, "G": 1})
    act(s, "p1", type="cast_spell", card_id=c.id, sources=[], targets=[])
    paid = s.state.rules.payments[s.state.rules.object_id(c.id)]
    assert paid.total_cost == ("{" + str(generic) + "}" if generic else "") + "{B}{R}{G}"
    assert sum(s.state.players["p1"].mana.values()) == 0


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(NAMES[0])).level == "FULL"


def test_no_sacrifices_full_price(cards):
    s, c = setup(cards)
    cast(s, c, 5)


@pytest.mark.parametrize("name,n", [("Gingerbrute", 2), ("Bitterblossom", 2), ("Forest", 1)])
def test_actual_sacrifice_native_frozen_card_types(cards, name, n):
    s, c = setup(cards)
    target = put(s, name, "battlefield")
    sac(s, target)
    cast(s, c, 5 - n)


def test_repeated_types_do_not_stack(cards):
    s, c = setup(cards)
    for name in ["Gingerbrute", "Ornithopter"]:
        sac(s, put(s, name, "battlefield"))
    cast(s, c, 3)


def test_opponent_sacrifices_do_not_count(cards):
    s, c = setup(cards)
    sac(s, put(s, "Gingerbrute", "battlefield", "p2"), "p2")
    cast(s, c, 5)


def test_controller_at_actual_sacrifice_not_owner_counts(cards):
    s, c = setup(cards)
    target = put(s, "Gingerbrute", "battlefield", "p2")
    act(s, "p1", type="set_controller", card_ids=[target.id], player="p1")
    sac(s, target)
    assert s.state.cards[target.id].zone == "p2:graveyard"
    cast(s, c, 3)
