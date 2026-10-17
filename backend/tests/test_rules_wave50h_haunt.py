"""Wave 50H: haunt (CR 702.55, 2026-09-25), real Oracle text (tests/fixtures/wave50h_cards.json, from data/cards.sqlite). Every scenario checks the replay and a
save and a load.

* 702.55a: "Haunt (When this creature dies, exile it haunting target creature.)": the dead card is exiled haunting the target (Blind Hunter, Belfry Spirit).
* 702.55b-c: "When this creature enters or the creature it haunts dies, …": the enters half works as usual; the other half functions in exile and triggers when the
  haunted object dies, and only that one.
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
from tests.test_rules_conditionals import token_of, until_asked
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, check, life, mana, put, reloaded, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50h_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50h", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
BEAR = card("Runeclaw Bear", set_code="w50h", number="P01", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Bear", oracle_text="", power="2", toughness="2",
            colors=["G"], color_identity=["G"])


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, BEAR], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def answer(s, *picks):
    """Answer whatever is asked: the first of ``picks`` among the options (a target), else the first option."""
    for _ in range(12):
        d = until_asked(s)
        if d is None:
            return
        want = next((p for p in picks if p in {o.id for o in d.options}), None)
        act(s, d.player, type="choose", decision_id=d.id,
            option_ids=[want] if want and d.min_choices <= 1 else [o.id for o in d.options][: max(1, d.min_choices)])


@pytest.mark.parametrize("name", ["Blind Hunter", "Belfry Spirit"])
def test_haunt_creatures_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_a_haunt_card_haunts_the_creature_and_only_its_death_triggers_the_ability_from_exile(cards):
    s = build(cards, ["Blind Hunter", "Lightning Bolt", "Day of Judgment"], ["Runeclaw Bear"])
    bear = put(s, "Runeclaw Bear", "p2")
    other = token_of(s, "p2", "Wolf", "Token Creature — Wolf", "2/2")
    hunter = to_hand(s, "Blind Hunter")
    mana(s, W=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=hunter.id)
    answer(s, "p2")
    settle(s)
    assert (life(s, "p1"), life(s, "p2")) == (42, 38)  # the enters half: "target player loses 2 life and you gain 2 life"
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[hunter.id])  # 3 damage to the 2/2: it dies
    answer(s, bear.id)  # "exile it haunting target creature": the Bear, not the Wolf
    settle(s)
    assert zone_of(s, "Blind Hunter") == "p1:exile"  # 702.55a
    assert s.state.rules.haunting == {s.state.rules.object_id(hunter.id): s.state.rules.object_id(bear.id)}
    check(s)
    s = reloaded(s)  # a save and a load while it haunts
    assert zone_of(s, "Blind Hunter") == "p1:exile"
    day = to_hand(s, "Day of Judgment")
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=day.id)
    answer(s, "p2")  # the haunted Bear and the Wolf die together; only the Bear's death triggers (702.55c): one target player to choose
    settle(s)
    assert zone_of(s, "Runeclaw Bear", "p2") == "p2:graveyard" and other.id not in s.state.cards
    assert (life(s, "p1"), life(s, "p2")) == (44, 36)  # once: the Wolf's death is not the haunted creature's
    assert zone_of(s, "Blind Hunter") == "p1:exile"  # (it stays in exile: haunting nothing now)
    check(s)


def test_a_haunt_card_with_no_creature_left_to_target_stays_in_the_graveyard(cards):
    # 603.3d: a haunt ability with no legal target is removed from the stack; the card stays in the graveyard
    s = build(cards, ["Blind Hunter", "Day of Judgment"], ["Runeclaw Bear"])
    put(s, "Runeclaw Bear", "p2")
    hunter = to_hand(s, "Blind Hunter")
    mana(s, W=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=hunter.id)
    answer(s, "p2")
    settle(s)
    day = to_hand(s, "Day of Judgment")
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=day.id)
    settle(s)  # (Blind Hunter and the Bear die together: no creature is left to haunt)
    assert zone_of(s, "Blind Hunter") == "p1:graveyard" and not s.state.rules.haunting
    check(s)


def test_haunt_on_a_sorcery_is_not_read(cards):
    assert coverage.of_card_data(cards.resolve("Cry of Contrition")).level != "FULL"
