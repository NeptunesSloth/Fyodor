"""Wave 110C: Kozilek, the Broken Reality (701.40a, 603.3b): the cast trigger makes each chosen player manifest up to two cards from their hand; you draw per card."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, real, to_hand

TEXT = ("When you cast this spell, up to two target players each manifest two cards from their hands. For each card manifested this way, you draw a card. (To manifest a card, put it onto the battlefield face down as a 2/2 creature. Turn it face up any time for its mana cost if it's a creature card.)\n"
        "Other colorless creatures you control get +3/+2.")
EXTRA = [real("Kozilek, the Broken Reality", "{9}", 9, "Legendary Creature — Eldrazi", TEXT, ("9", "9"), "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Kozilek, the Broken Reality")).level == "FULL"


def test_each_target_player_manifests_two_and_you_draw_for_each(cards):
    s = build(cards, ["Kozilek, the Broken Reality", "Grizzly Bears"], ["Courser of Kruphix", "Foundry Inspector", "Lightning Bolt"])
    for n in ("Courser of Kruphix", "Foundry Inspector", "Lightning Bolt"):
        to_hand(s, n, "p2")
    to_hand(s, "Grizzly Bears")
    mana(s, C=9)
    cast(s, "Kozilek, the Broken Reality")
    mine = len(s.state.zones["p1:hand"])
    d = s.state.rules.decision
    assert d is not None
    answer(s, ["p1", "p2"])
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            break
        answer(s, d.options[0].id)
    face_down = [c for c in s.state.cards.values() if c.face_down and c.zone.endswith(":battlefield")]
    assert sorted(c.controller for c in face_down) == ["p1", "p2", "p2"]
    assert len(s.state.zones["p2:hand"]) == 1
    assert len(s.state.zones["p1:hand"]) == mine - 1 + 3
    check(s)
