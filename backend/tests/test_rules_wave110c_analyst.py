"""Wave 110C: Paranormal Analyst (701.62a, 603.2): manifest dread triggers it; the card the action put into the graveyard goes to hand."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real

EXTRA = [real("Paranormal Analyst", "{1}{U}", 2, "Creature — Human Detective", "Whenever you manifest dread, put a card you put into your graveyard this way into your hand.", ("1", "3"), "U"),
         real("Dissection Tools", "{5}", 5, "Artifact — Equipment", "When this Equipment enters, manifest dread, then attach this Equipment to that creature.\nEquipped creature gets +2/+2 and has deathtouch and lifelink.\nEquip—Sacrifice a creature.", None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Paranormal Analyst")).level == "FULL"


def test_binned_card_of_manifest_dread_goes_to_hand(cards):
    s = build(cards, ["Paranormal Analyst", "Dissection Tools"], [])
    put(s, "Paranormal Analyst")
    mana(s, C=5)
    cast(s, "Dissection Tools")
    d = s.state.rules.decision
    for _ in range(5):  # the Equipment's trigger resolves, then the choice opens
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards"
    top = [o.id for o in d.options]
    assert top == s.state.zones["p1:library"][:2]
    hand, gy = len(s.state.zones["p1:hand"]), len(s.state.zones.get("p1:graveyard", []))
    answer(s, top[0])
    assert any(c.face_down and c.zone == "p1:battlefield" for c in s.state.cards.values())
    assert len(s.state.zones["p1:hand"]) == hand + 1 and len(s.state.zones.get("p1:graveyard", [])) == gy
    check(s)


def test_without_the_analyst_the_card_stays_in_the_graveyard(cards):
    s = build(cards, ["Dissection Tools"], [])
    mana(s, C=5)
    cast(s, "Dissection Tools")
    d = s.state.rules.decision
    for _ in range(5):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    top = [o.id for o in d.options]
    gy = len(s.state.zones.get("p1:graveyard", []))
    answer(s, top[0])
    assert len(s.state.zones["p1:graveyard"]) == gy + 1
    check(s)
