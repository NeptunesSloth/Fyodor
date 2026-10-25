"""Wave 110D: Sheltering Prayers, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 702.18a, 613.7: "Basic lands each player controls have shroud as long as that player controls three or fewer lands." — each basic land is judged by its own
  controller's land count: Stone Rain ("Destroy target land.") can't target a basic land of a player with three lands, can target a fifth-land player's basic land
  and a nonbasic land.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named
from tests.wave110d_kit import EXTRA, check, full, mana, put_new, settle

RAIN = real("Stone Rain", "{2}{R}", 3, "Sorcery", "Destroy target land.", None, "R")


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, RAIN], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_prayers_is_full():
    assert full("Sheltering Prayers")


def _rain(s, target):
    c = card_named(s, "Stone Rain", "p1")
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[target.id])
    settle(s)


def test_shroud_only_while_that_players_lands_are_few(cards):
    s = build(cards, ["Sheltering Prayers", "Stone Rain", "Forest", "Forest", "Forest", "Forest"], ["Forest"] * 4)
    put_new(s, "Sheltering Prayers")
    mine = [put_new(s, "Forest") for _ in range(3)]
    theirs = [put_new(s, "Forest", "p2") for _ in range(4)]
    with pytest.raises(ActionError):
        _rain(s, mine[0])  # three lands: its controller's basic lands have shroud
    _rain(s, theirs[0])  # four lands: no shroud
    assert theirs[0].id in s.state.zones["p2:graveyard"]
    check(s)
