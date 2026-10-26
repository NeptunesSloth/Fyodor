"""Wave 110C: Finale of Promise (115.1d up to one target of each kind, 601.2b X known when the targets are chosen, 608.2g the spells are cast as it resolves, 614.1a exile
instead of the graveyard, 707.10c copies with new targets): X below the cards' mana values leaves them; X of 10 or more copies each spell cast this way twice."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, to_hand
from tests.wave110c_kit import check, life, make_db, mana, real

TEXT = ("You may cast up to one target instant card and/or up to one target sorcery card from your graveyard each with mana value X or less without paying their mana costs. "
        "If a spell cast this way would be put into your graveyard, exile it instead. If X is 10 or more, copy each of those spells twice. You may choose new targets for the copies.")
EXTRA = [real("Finale of Promise", "{X}{R}{R}", 2, "Sorcery", TEXT, None, "R"),
         real("Wound", "{R}", 1, "Sorcery", "Wound deals 2 damage to any target.", None, "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Finale of Promise")).level == "FULL"


def scenario(cards, x, targets):
    s = build(cards, ["Finale of Promise", "Lightning Bolt", "Wound"])
    for n in ("Lightning Bolt", "Wound"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    to_hand(s, "Finale of Promise")
    mana(s, R=2, C=x)
    ids = [card_named(s, n).id for n in targets]
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Finale of Promise").id, targets=ids, x_value=x, target_counts=[1, 1] if len(ids) == 2 else [0, 0])
    return s


def drive(s, limit=60):
    """Answer every decision: cast the spells, aim them at p2 (the copies keep their targets)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options]
        pick = "p2" if "p2" in ids else ids[0]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick] if d.max_choices <= 1 else ids[: d.max_choices])
    raise AssertionError("never settled")


def test_both_cast_free_and_exiled_instead_of_the_graveyard(cards):
    s = scenario(cards, 1, ["Lightning Bolt", "Wound"])
    drive(s)
    assert life(s, "p2") == 40 - 3 - 2
    assert card_named(s, "Lightning Bolt").zone == "p1:exile" and card_named(s, "Wound").zone == "p1:exile"
    check(s)


def test_x_below_the_mana_value_leaves_the_cards(cards):
    s = scenario(cards, 0, [])
    drive(s)
    assert life(s, "p2") == 40 and card_named(s, "Wound").zone == "p1:graveyard"
    check(s)


def test_x_ten_copies_each_spell_twice(cards):
    s = scenario(cards, 10, ["Lightning Bolt", "Wound"])
    drive(s)
    assert life(s, "p2") == 40 - 3 * (3 + 2)
    check(s)
