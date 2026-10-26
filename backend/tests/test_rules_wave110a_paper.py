"""Wave 110A: Psychic Paper (701.3a becomes attached, 201.4 creature card name, 613.1c name / 613.1d creature type, ward 702.21, unblockable 509.1b)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.wave110a_kit import *

PAPER = "Psychic Paper"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def _equip(s, paper, host, name="Llanowar Elves", kind="Elf"):
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=paper.id, ability=2, targets=[host.id])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[], name=name)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[kind])
    answer(s)


def _look(s, c):
    return ch(s, c)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(PAPER)).level == "FULL"


def test_equipped_creature_takes_the_chosen_name_and_creature_type_and_gains_ward_and_evasion(cards):
    s = build(cards, [PAPER, "Grizzly Bears"])
    paper, bears = put(s, PAPER), put(s, "Grizzly Bears")
    _equip(s, paper, bears)
    c = _look(s, bears)
    assert c.name == "Llanowar Elves" and "Elf" in c.subtypes and "Bear" not in c.subtypes and "Creature" in c.types
    assert any("ward" in k.lower() for k in c.keywords) and "cant_be_blocked" in c.imposed
    check(s)
    act(s, "p1", type="move", card_ids=[paper.id], to={"player": "p1", "zone": "graveyard"})  # leaves: the creature is itself again
    c = _look(s, bears)
    assert c.name == "Grizzly Bears" and "Bear" in c.subtypes and "cant_be_blocked" not in c.imposed
    check(s)


def test_the_name_must_be_a_creature_card_name(cards):
    s = build(cards, [PAPER, "Grizzly Bears", "Naturalize"])
    paper, bears = put(s, PAPER), put(s, "Grizzly Bears")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=paper.id, ability=2, targets=[bears.id])
    d = s.state.rules.decision
    with pytest.raises(ActionError, match="creature card name"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[], name="Naturalize")


def test_the_next_equip_chooses_again_and_a_noncreature_keeps_nothing_else_changed(cards):
    s = build(cards, [PAPER, "Grizzly Bears", "Llanowar Elves"])
    paper, bears, elves = put(s, PAPER), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    _equip(s, paper, bears)
    _equip(s, paper, elves, name="Grizzly Bears", kind="Bear")
    assert _look(s, bears).name == "Grizzly Bears" and "Bear" in _look(s, bears).subtypes
    c = _look(s, elves)
    assert c.name == "Grizzly Bears" and c.subtypes == frozenset({"Bear"})  # the last choice; the Elf Druid types are replaced
    check(s)
