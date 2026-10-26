"""Wave 110B: Lolth, Spider Queen's -8 emblem (114.1 an emblem, 603.4 intervening "if", 119.3 life lost counts the whole turn)."""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import attack, build, check, life, put, through_combat

LOLTH = ("Whenever a creature you control dies, put a loyalty counter on Lolth.\n0: You draw a card and you lose 1 life.\n"
         "−3: Create two 2/1 black Spider creature tokens with reach and menace.\n"
         "−8: You get an emblem with \"Whenever an opponent is dealt combat damage by one or more creatures you control, if that player lost less than 8 life this turn, "
         "they lose life equal to the difference.\"")


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository
    from tests.fixtures.cards import card, fixture_cards

    settings.ensure_dirs()
    lolth = card("Lolth, Spider Queen", set_code="tst", number="L1", mana_cost="{3}{B}{B}", cmc=5.0, type_line="Legendary Planeswalker — Lolth",
                 oracle_text=LOLTH, loyalty="5", colors=["B"], color_identity=["B"])
    build_database([*fixture_cards(), lolth], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def emblem_game(cards, already_lost):
    """Alice ultimates Lolth (-8), then attacks with Grizzly Bears; Bob has already lost ``already_lost`` life this turn."""
    s = build(cards, ["Lolth, Spider Queen", "Grizzly Bears"], [], forests=30)
    lolth = put(s, "Lolth, Spider Queen")
    act(s, "p1", type="counter", card_ids=[lolth.id], kind="loyalty", delta=8 - s.state.cards[lolth.id].counters.get("loyalty", 0))
    act(s, "p1", type="activate_ability", card_id=lolth.id, ability=3)
    if already_lost:
        act(s, "p2", type="life", player="p2", delta=-already_lost)
    attack(s, put(s, "Grizzly Bears"))
    through_combat(s)
    return s


@pytest.mark.parametrize("lost", [0, 3, 6, 7, 9])
def test_lolth_emblem_tops_life_lost_up_to_eight(cards, lost):
    """The Bears' 2 combat damage plus 'the difference': Bob's total loss this turn reaches 8 unless he had already lost 8 or more before the damage."""
    assert coverage.of_card_data(cards.resolve("Lolth, Spider Queen")).level == "FULL"
    s = emblem_game(cards, lost)
    assert 40 - life(s, "p2") == max(8, lost + 2)
    check(s)
