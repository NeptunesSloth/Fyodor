"""Wave 110C: The Irencrag. A legendary creature entering lets its controller turn it (permanently, 611.2a) into the legendary Equipment artifact Everflame, Heroes' Legacy
(205.1a, 613.1d) with equip {3} and "+3/+3", and no other abilities (613.1f): the mana ability is gone, the equipment works."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110c_kit import answer, check, ch, make_db, mana, put, real, to_hand

IRENCRAG = ("{T}: Add {C}.\nWhenever a legendary creature you control enters, you may have The Irencrag become a legendary Equipment artifact named Everflame, Heroes' Legacy. "
            "If you do, it gains equip {3} and \"Equipped creature gets +3/+3\" and loses all other abilities.")
EXTRA = [real("The Irencrag", "{3}", 3, "Legendary Artifact", IRENCRAG, None, ""),
         real("Legend Test", "{1}", 1, "Legendary Creature — Test", "", ("2", "2"), ""),
         real("Plain Test", "{1}", 1, "Creature — Test", "", ("1", "1"), "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("The Irencrag")).level == "FULL"


def enter(cards, creature, accept):
    s = build(cards, ["The Irencrag", "Legend Test", "Plain Test"])
    crag = put(s, "The Irencrag")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, creature).id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[ids[0] if accept else ids[-1]])
        elif s.state.rules.stack:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s, crag


def test_accepting_makes_it_an_equipment_that_lost_its_mana_ability_and_has_equip(cards):
    s, crag = enter(cards, "Legend Test", True)
    c = ch(s, crag)
    assert c.name == "Everflame, Heroes' Legacy" and "Equipment" in c.subtypes and "Legendary" in c.supertypes and c.types == frozenset({"Artifact"})
    assert [a.text for a in c.abilities if a.text.startswith("{T}")] == []  # (613.1f: the mana ability is lost)
    legend = next(x for x in s.state.cards.values() if x.name == "Legend Test")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=crag.id, ability=next(a.index for a in c.abilities if a.text.startswith("Equip")), targets=[legend.id])
    for _ in range(5):
        if s.state.rules.stack:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[crag.id].attached_to == legend.id and ch(s, legend).pt == (5, 5)
    check(s)


@pytest.mark.parametrize("creature,accept", [("Legend Test", False), ("Plain Test", True)])
def test_declined_or_nonlegendary_changes_nothing(cards, creature, accept):
    s, crag = enter(cards, creature, accept)
    assert ch(s, crag).name == "The Irencrag" and any(a.text.startswith("{T}") for a in ch(s, crag).abilities)
    check(s)
