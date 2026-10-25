"""Crashing Wave combines X tapping with an untargeted resolving stun distribution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_waterbend102 import take
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/evidence_cost106_cards.json").read_text())
NAME = "Bite Down on Crime"


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="w03", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    ns = [c["name"] for c in DATA] * 7
    s = table(cards, ns, ns, ns)
    to_phase(s, "main1", 4)
    return s


def test_bite_down_on_crime_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


def prepare(cards, collection=1):
    s = setup(cards)
    own = take(s, "Grizzly Bears", "battlefield")
    enemy = take(s, "Rhox Brute", "battlefield", pid="p2")
    grave = (
        [take(s, "Shivan Dragon", "graveyard").id]
        if collection == 1
        else [take(s, "Benevolent River Spirit", "graveyard").id for _ in range(collection)]
    )
    source = take(s, NAME)
    wait_priority(s, "p1")
    return s, source, own, enemy, grave


def announce(s, source, own, enemy, grave, pool, paid=True, choose=True):
    if pool:
        act(s, "p1", type="add_mana", player="p1", mana=pool)
    extra = {"optional_costs": [source.id + ":evidence"]} if paid else {}
    if paid and choose:
        extra["cost_choices"] = [{"component": 0, "cards": grave}]
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=source.id,
        targets=[own.id, enemy.id],
        target_counts=[1, 1],
        sources=[],
        **extra,
    )


@pytest.mark.parametrize("collection", [1, 3])
def test_evidence_reduction_is_two_once_regardless_of_how_many_cards_paid(cards, collection):
    from app.rules.plan import Plan

    s, source, own, enemy, grave = prepare(cards, collection)
    from app.rules.casting import optional_castable

    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "G": 1})
    assert any(o["id"] == source.id + ":evidence" for o in optional_castable(s.state, "p1", source, s.cards))
    announce(s, source, own, enemy, grave, {})
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert record.total_cost == "{1}{G}" and record.mana_spent == {"C": 1, "G": 1}
    assert all(s.state.cards[c].zone == "p1:exile" for c in grave)
    settle(s)
    assert s.state.cards[enemy.id].zone == "p2:graveyard"
    assert Plan.view(s.state, "p1", s.cards).ch(own).pt[0] == 4
    roundtrip(s)


def test_unpaid_evidence_has_full_printed_cost_and_no_exile(cards):
    s, source, own, enemy, grave = prepare(cards)
    announce(s, source, own, enemy, grave, {"C": 3, "G": 1}, paid=False)
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert record.total_cost == "{3}{G}" and record.mana_spent == {"C": 3, "G": 1}
    assert all(s.state.cards[c].zone == "p1:graveyard" for c in grave)
    settle(s)
    roundtrip(s)


def test_evidence_reduction_precedes_trinisphere_floor(cards):
    s, source, own, enemy, grave = prepare(cards)
    take(s, "Trinisphere", "battlefield")
    announce(s, source, own, enemy, grave, {"C": 2, "G": 1})
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert record.total_cost == "{2}{G}" and record.mana_spent == {"C": 2, "G": 1}
    settle(s)
    roundtrip(s)


def test_insufficient_evidence_cannot_grant_discount_or_exile_partial_payment(cards):
    from app.game.errors import ActionError

    s, source, own, enemy, grave = prepare(cards, 2)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "G": 1})
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="cast_spell",
            card_id=source.id,
            targets=[own.id, enemy.id],
            target_counts=[1, 1],
            sources=[],
            optional_costs=[source.id + ":evidence"],
            cost_choices=[{"component": 0, "cards": grave}],
        )
    assert s.state.model_dump(mode="json") == before


def test_true_cold_pending_evidence_choice_preserves_fixed_discount(cards, tmp_path):
    from tests.test_rules_cost_statics101_extra import cold

    s, source, own, enemy, grave = prepare(cards, 3)
    announce(s, source, own, enemy, grave, {"C": 1, "G": 1}, choose=False)
    assert s.state.rules.decision
    cold(
        s,
        tmp_path,
        f"d=s.state.rules.decision\nact(s,d.player,type='choose',decision_id=d.id,option_ids={grave!r})\n"
        f"r=s.state.rules.payments[s.state.rules.object_id({source.id!r})]\n"
        "assert r.total_cost=='{1}{G}' and r.mana_spent=={'C':1,'G':1}\nsettle(s)\nroundtrip(s)",
    )
