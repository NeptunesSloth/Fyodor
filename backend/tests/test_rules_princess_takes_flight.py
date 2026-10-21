"""Canonical three-chapter Saga linked exile and owner-return collateral proof."""

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
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_linked_aggregates import cast, choose
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["The Princess Takes Flight"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/princess_takes_flight_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"],
            set_code="lor",
            number=str(i),
            **{k: v for k, v in c.items() if k not in ("name", "set_code")},
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def prepare(cards, victim_name="Grizzly Bears"):
    from tests.test_rules_linked_aggregates import ch

    support = ["Grizzly Bears", "Llanowar Elves", "Clone", "Naturalize", "Pull from Eternity"]
    s = table(cards, ["The Princess Takes Flight", *support], support, support)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True)
    saga = put(s, "The Princess Takes Flight", "hand")
    ally = put(s, "Llanowar Elves", "battlefield")
    if victim_name == "Clone":
        victim = put(s, victim_name, "hand")
        cast(s, victim)
        until(s, lambda s: s.state.rules.decision is not None)
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[ally.id])
        settle(s)
    else:
        victim = put(s, victim_name, "battlefield", "p2")
    cast(s, saga)
    choose(s, [victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == f"{victim.owner}:exile"
    to_phase(s, "main1", turn=4)
    choose(s, [ally.id])
    settle(s)
    assert ch(s, ally).pt == (3, 3) and "flying" in ch(s, ally).keywords
    return s, saga, victim, ally


def test_canonical_princess_all_three_native_chapters(cards):
    from tests.test_rules_linked_aggregates import ch

    assert coverage.of_card_data(cards.resolve("The Princess Takes Flight")).level == "FULL"
    s, saga, victim, ally = prepare(cards)
    to_phase(s, "main1", turn=7)
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:battlefield"
    assert s.state.cards[victim.id].controller == "p2"
    assert s.state.cards[saga.id].zone == "p1:graveyard"
    assert ch(s, ally).pt == (1, 1) and "flying" not in ch(s, ally).keywords
    roundtrip(s)


def test_princess_returned_clone_native_entry_choice_cold(cards, tmp_path):
    from tests.test_rules_linked_aggregates import ch
    from tests.test_rules_linked_return_family import cold_choose

    s, saga, victim, ally = prepare(cards, "Clone")
    to_phase(s, "main1", turn=7)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    option = next(o.id for o in d.options if o.card_id == ally.id or o.id == ally.id)
    s = cold_choose(s, cards, tmp_path, [option])
    settle(s)
    assert s.state.cards[victim.id].zone == "p1:battlefield"
    assert s.state.cards[victim.id].controller == "p1"
    assert ch(s, s.state.cards[victim.id]).name == "Llanowar Elves"
    assert s.state.cards[saga.id].zone == "p1:graveyard"
    roundtrip(s)


def test_princess_pending_third_chapter_keeps_departed_source_pool(cards):
    s, saga, victim, ally = prepare(cards)
    to_phase(s, "main1", turn=7)
    removal = put(s, "Naturalize", "hand")
    cast(s, removal, targets=[saga.id])
    settle(s)
    assert s.state.cards[saga.id].zone == "p1:graveyard"
    assert s.state.cards[victim.id].zone == "p2:battlefield"
    roundtrip(s)


def test_princess_does_not_return_a_card_that_left_its_exact_exile_pool(cards):
    s, saga, victim, ally = prepare(cards)
    removal = put(s, "Pull from Eternity", "hand")
    cast(s, removal, targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:graveyard"
    to_phase(s, "main1", turn=7)
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:graveyard"
    assert s.state.cards[saga.id].zone == "p1:graveyard"
    roundtrip(s)
