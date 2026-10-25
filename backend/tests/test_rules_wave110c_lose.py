"""Wave 110C: "If you would lose the game, instead ..." (614.1a, 104.3, 704.5a): Exquisite Archangel, The Golden Throne, Lich's Mirror."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, check, life, make_db, put, real

EXTRA = [
    real("Exquisite Archangel", "{4}{W}{W}", 6, "Creature — Angel", "Flying\nIf you would lose the game, instead exile this creature and your life total becomes equal to your starting life total.",
         ("4", "5"), "W"),
    real("The Golden Throne", "{2}{W}{W}", 4, "Legendary Artifact",
         "Arcane Life-support — If you would lose the game, instead exile The Golden Throne and your life total becomes 1.\nA Thousand Souls Die Every Day — {T}, Sacrifice a creature: Add three mana in any combination of colors.",
         None, ""),
    real("Lich's Mirror", "{5}", 5, "Artifact",
         "If you would lose the game, instead shuffle your hand, your graveyard, and all permanents you own into your library, then draw seven cards and your life total becomes 20.",
         None, ""),
]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _lose(s):
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p1", type="pass_priority")  # (the next state-based check: a table edit is not an intent)
    answer(s)


def test_archangel_exiles_itself_and_resets_life(cards):
    s = build(cards, ["Exquisite Archangel"])
    angel = put(s, "Exquisite Archangel")
    _lose(s)
    assert life(s) == 40 and s.state.cards[angel.id].zone == "p1:exile" and s.state.rules.winner is None
    _lose(s)  # the replacement is used up: the next loss happens
    assert s.state.rules.winner == "p2"
    check(s)


def test_golden_throne_sets_life_to_one(cards):
    s = build(cards, ["The Golden Throne"])
    throne = put(s, "The Golden Throne")
    _lose(s)
    assert life(s) == 1 and s.state.cards[throne.id].zone == "p1:exile" and s.state.rules.winner is None
    check(s)


def test_lich_mirror_shuffles_everything_in_and_draws_seven(cards):
    s = build(cards, ["Lich's Mirror", "Grizzly Bears"])
    mirror, bears = put(s, "Lich's Mirror"), put(s, "Grizzly Bears")
    _lose(s)
    assert life(s) == 20 and s.state.rules.winner is None
    assert s.state.cards[mirror.id].zone != "p1:battlefield" and s.state.cards[bears.id].zone != "p1:battlefield"
    assert len(s.state.zones["p1:hand"]) == 7 and not s.state.zones.get("p1:graveyard")
    check(s)


def test_loss_happens_without_a_replacement(cards):
    s = build(cards, ["Grizzly Bears"])
    _lose(s)
    assert s.state.rules.winner == "p2"
