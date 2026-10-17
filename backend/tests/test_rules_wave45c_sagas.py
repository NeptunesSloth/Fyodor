"""Wave 45C: "the final chapter ability of a Saga you control triggers / resolves" (CR 2026-09-25, real Oracle text, tests/fixtures/wave45c_cards.json).
Every scenario checks the replay and a save and a load.

* 714.2d: a Saga's final chapter ability is its chapter ability with the greatest chapter number (the Tom Bombadil / Narci ruling of 2023-06-16/07-28).
* Tom Bombadil / Narci: it triggers when the ability has been removed from the stack (their ruling of 2023-06-16); Historian's Boon: when it triggers.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave38a_trailing_ifs import table
from tests.wave9c_kit import card_named, cast, check, life, mana, put, to_hand
from tests.wave36a_kit import next_own_turn, resolve_stack, to_turn_of
from tests.wave45c_kit import make_repo, zone

COMMANDERS = ["Tom Bombadil", "Narci, Fable Singer"]


@pytest.fixture()
def cards(settings):
    repo = make_repo(settings)
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [*COMMANDERS, "Historian's Boon"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def own_turn(s):
    """On to Alice's next turn: the lore counter is added in her precombat main phase, and the chapter ability that triggers resolves."""
    next_own_turn(s)
    resolve_stack(s)


def tokens(s, name, pid="p1"):
    return sum(1 for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield")


def cast_omashu(s, pid="p1"):
    """Founding of Omashu (I: two Allies, II: a discard, III: +1/+0) enters with its first lore counter."""
    to_hand(s, "Founding of Omashu", pid)
    mana(s, pid, R=1, G=2)
    cast(s, "Founding of Omashu", pid)
    resolve_stack(s, limit=40)


def test_narci_drains_for_the_sagas_mana_value_only_after_its_final_chapter_resolves(cards):
    s = table(cards, ["Narci, Fable Singer", "Founding of Omashu"])
    put(s, "Narci, Fable Singer")
    cast_omashu(s)
    assert tokens(s, "Ally") == 2 and life(s) == 40 and life(s, "p2") == 40  # (chapter I)
    own_turn(s)  # chapter II: not the final chapter
    assert life(s) == 40 and life(s, "p2") == 40
    own_turn(s)  # chapter III: the final chapter ability resolves
    assert life(s) == 43 and life(s, "p2") == 37  # (mana value 3)
    assert zone(s, "Founding of Omashu") == "p1:graveyard"  # (714.4: sacrificed once it left the stack)
    check(s)


def test_narci_ignores_a_saga_an_opponent_controls(cards):
    s = table(cards, ["Narci, Fable Singer"], ["Founding of Omashu"])
    put(s, "Narci, Fable Singer")
    to_turn_of(s, "p2")
    cast_omashu(s, "p2")
    for _ in range(2):  # (Bob's chapters II and III)
        to_turn_of(s, "p1")
        to_turn_of(s, "p2")
        resolve_stack(s)
    assert zone(s, "Founding of Omashu", "p2") == "p2:graveyard"
    assert life(s) == 40 and life(s, "p2") == 40
    check(s)


def test_historians_boon_makes_an_angel_when_the_final_chapter_triggers(cards):
    s = table(cards, ["Historian's Boon", "Founding of Omashu"])
    put(s, "Historian's Boon")
    cast_omashu(s)
    assert tokens(s, "Angel") == 0
    own_turn(s)
    assert tokens(s, "Angel") == 0  # (chapter II)
    own_turn(s)
    assert tokens(s, "Angel") == 1
    check(s)


def test_tom_bombadil_puts_a_saga_onto_the_battlefield(cards):
    s = table(cards, ["Tom Bombadil", "Origin of Black Widow", "Founding of Omashu"])
    put(s, "Tom Bombadil")
    cast_omashu(s)
    act(s, "p1", type="move", card_ids=[card_named(s, "Origin of Black Widow").id], to={"zone": "library"}, position="bottom")  # (not drawn on the way)
    own_turn(s)
    assert zone(s, "Origin of Black Widow") == "p1:library"  # (chapter II is no final chapter)
    own_turn(s)  # the final chapter ability resolves: reveal until a Saga card, put it onto the battlefield
    assert zone(s, "Origin of Black Widow") == "p1:battlefield"
    check(s)
