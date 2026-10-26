"""Wave 110G session 15: Kodama of the Center Tree (702.46a soulshift; X read from the state just before it died, ruling 2005-02-01)."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, put

KODAMA = ("Kodama of the Center Tree's power and toughness are each equal to the number of Spirits you control.\n"
          "Kodama of the Center Tree has soulshift X, where X is the number of Spirits you control. (When this creature dies, you may return target Spirit "
          "card with mana value X or less from your graveyard to your hand.)")
EXTRA = [real("Kodama of the Center Tree", "{4}{G}", 5, "Legendary Creature — Spirit", KODAMA, ("0", "0"), "G"),
         real("Test Wisp", "{1}", 1, "Creature — Spirit", "", ("1", "1"), ""),
         real("Test Kami", "{2}", 2, "Creature — Spirit", "", ("2", "2"), ""),
         real("Test Gem", "{3}", 3, "Creature — Spirit", "", ("3", "3"), ""),
         real("Test Giant", "{4}", 4, "Creature — Spirit", "", ("4", "4"), "")]


@pytest.fixture
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Kodama of the Center Tree")).level == "FULL"


def _die(cards, board, gy):
    s = build(cards, ["Kodama of the Center Tree", *board, *gy])
    for n in board:
        put(s, n)
    k = put(s, "Kodama of the Center Tree")
    for n in gy:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="set_damage", card_ids=[k.id], value=1 + len(board))
    for _ in range(6):
        act(s, "p1", type="pass_priority")
        d = s.state.rules.decision
        if d is not None:
            return s, d
    raise AssertionError("no decision")


@pytest.mark.parametrize("board,gy,legal", [
    ([], ["Test Wisp", "Test Kami"], {"Test Wisp"}),  # Kodama counts itself: X = 1
    (["Test Wisp", "Test Kami"], ["Test Gem", "Test Giant"], {"Test Gem"}),  # X = 3
])
def test_x_counts_kodama_and_other_spirits(cards, board, gy, legal):
    s, d = _die(cards, board, gy)
    assert {s.state.cards[o.id].name for o in d.options} == legal
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
    assert s.state.cards[card_named(s, next(iter(legal))).id].zone == "p1:hand"
    check(s)
