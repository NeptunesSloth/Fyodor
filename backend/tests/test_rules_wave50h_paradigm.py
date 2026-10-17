"""Wave 50H: paradigm (CR 702.192, 2026-09-25), real Oracle text (tests/fixtures/wave50h_cards.json, from data/cards.sqlite). Every scenario checks the replay and a
save and a load.

* 702.192a: "Paradigm (Then exile this spell. After you first resolve a spell with this name, you may cast a copy of it from exile without paying its mana cost at the
  beginning of each of your first main phases.)": the card is exiled as it resolves (Decorum Dissertation: "Target player draws two cards and loses 2 life."); at the
  beginning of each of its controller's precombat main phases a copy is made in exile and may be cast for free; the copy is not the first resolution of that name.
"""

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
from tests.test_rules_conditionals import until_asked
from tests.test_rules_wave34b_activated import next_turn, settle
from tests.wave9c_kit import build, check, life, mana, reloaded, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50h_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50h", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def hand(s, pid="p1"):
    return len([c for c in s.state.cards.values() if c.zone == f"{pid}:hand"])


def answer(s, *picks):
    """Answer what is asked: the first of ``picks`` among the options, else the first option."""
    for _ in range(12):
        d = until_asked(s)
        if d is None:
            return
        want = next((p for p in picks if p in {o.id for o in d.options}), None)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[want] if want else [d.options[0].id])


@pytest.mark.parametrize("name", ["Decorum Dissertation", "Germination Practicum"])
def test_paradigm_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_card_is_exiled_as_it_resolves_and_copied_and_cast_free_each_precombat_main_phase(cards):
    s = build(cards, ["Decorum Dissertation"])
    dis = to_hand(s, "Decorum Dissertation")
    mana(s, B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=dis.id, targets=["p2"])
    settle(s)
    assert zone_of(s, "Decorum Dissertation") == "p1:exile"  # "Then exile this spell" (not the graveyard)
    assert hand(s, "p2") == 2 and life(s, "p2") == 38  # "Target player draws two cards and loses 2 life."
    assert s.state.rules.paradigm_seen == ["p1:Decorum Dissertation"]
    check(s)
    s = reloaded(s)
    next_turn(s)  # Bob's turn (no copy: "your first main phases"), then Alice's: the copy is made in exile and she may cast it
    cards_before, bob_life = hand(s, "p2"), life(s, "p2")
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.kind == "choose_cards"  # "you may cast the copy": her choice
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
    answer(s, "p2")
    settle(s)
    assert life(s, "p2") == bob_life - 2 and hand(s, "p2") == cards_before + 2  # the copy resolved: 2 cards, 2 life
    assert zone_of(s, "Decorum Dissertation") == "p1:exile"  # the card stays; the copy is gone (704.5e)
    assert len([c for c in s.state.cards.values() if c.name == "Decorum Dissertation"]) == 1
    assert s.state.rules.paradigm_seen == ["p1:Decorum Dissertation"]  # the copy resolving isn't a first resolution: nothing new is set up
    check(s)


def test_a_copy_left_uncast_ceases_to_exist_and_the_card_stays(cards):
    s = build(cards, ["Germination Practicum"])
    pra = to_hand(s, "Germination Practicum")
    mana(s, G=2, C=3)
    act(s, "p1", type="cast_spell", card_id=pra.id)
    settle(s)
    assert zone_of(s, "Germination Practicum") == "p1:exile"
    next_turn(s)
    d = until_asked(s)
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])  # she doesn't cast the copy
    settle(s)
    assert len([c for c in s.state.cards.values() if c.name == "Germination Practicum"]) == 1  # 704.5e: the copy not cast is gone
    check(s)
