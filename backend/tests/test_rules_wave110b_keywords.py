"""Wave 110B: keyword lines and mana (real Oracle text, tests/fixtures/wave110b_cards.json). Every scenario checks the replay and a save and a load.

* Firebending among other keywords of a line (702.189a: "Trample, firebending 4, haste"; Ozai, Ran and Shaw): the attack trigger adds the red mana.
* Ozai, the Phoenix King: "If you would lose unspent mana, that mana becomes red instead." (614.1a, 500.4: the pool stays, red) and flying and
  indestructible as long as you have six or more unspent mana (106.4).
* Ran and Shaw: a token copy (not legendary, 707.2) only if cast and three or more Dragon and/or Lesson cards are in your graveyard.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import reloaded
from tests.wave110b_kit import (
    attack,
    build,
    card_named,
    ch,
    check,
    mana,
    pool,
    put,
    repository,
    settle,
    to_hand,
    token_of,
)


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Ozai, the Phoenix King", "Ran and Shaw"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_ozai_unspent_mana_becomes_red_and_six_of_it_gives_flying_and_indestructible(cards):
    s = build(cards, ["Ozai, the Phoenix King"], [])
    ozai = put(s, "Ozai, the Phoenix King")
    mana(s, "p1", U=2, B=1)
    assert "flying" not in ch(s, ozai).keywords
    act(s, "p1", type="pass_priority")  # main 1 → the next step: the mana would be lost (500.4)
    assert pool(s) == {"R": 3}
    mana(s, "p1", G=3)
    assert {"flying", "indestructible"} <= set(ch(s, ozai).keywords)  # six unspent mana of any type (106.4)
    s = reloaded(s)
    assert {"flying", "indestructible"} <= set(ch(s, card_named(s, "Ozai, the Phoenix King")).keywords)
    check(s)


def test_ozai_firebending_adds_red_mana_when_it_attacks(cards):
    s = build(cards, ["Ozai, the Phoenix King"], [])
    ozai = put(s, "Ozai, the Phoenix King")
    token_of(s, "p2", "Ogre", "Token Creature — Ogre", "3/3")  # (Bob may block: combat waits for his declaration, the mana still there)
    attack(s, ozai)
    while s.state.rules.decision is None:  # (the trigger resolves, then Bob is asked)
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.decision.kind == "declare_blockers" and [u.sym for u in s.state.players["p1"].mana_units] == ["R"] * 4  # (702.189a: firebending 4, kept to the end of combat)
    check(s)


def test_ran_and_shaw_copies_itself_only_when_cast_with_three_dragons_or_lessons_in_the_graveyard(cards):
    for cast_it, gy in ((True, 3), (True, 2), (False, 3)):
        s = build(cards, ["Ran and Shaw", "Ran and Shaw", "Ran and Shaw", "Ran and Shaw"], [])
        mana(s, "p1", R=5)
        ran = to_hand(s, "Ran and Shaw")
        grave = [c for c in s.state.cards.values() if c.name == "Ran and Shaw" and c.owner == "p1" and c.id != ran.id][:gy]
        act(s, "p1", type="move", card_ids=[c.id for c in grave], to={"zone": "graveyard"})
        if cast_it:
            act(s, "p1", type="cast_spell", card_id=ran.id)
        else:
            act(s, "p1", type="move", card_ids=[ran.id], to={"zone": "battlefield"})
        settle(s)
        tokens = [c for c in s.state.cards.values() if c.name == "Ran and Shaw" and c.token]
        assert len(tokens) == (1 if cast_it and gy == 3 else 0), (cast_it, gy)
        if tokens:
            assert "Legendary" not in ch(s, tokens[0]).supertypes
        check(s)
