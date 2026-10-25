"""Wave 110I (session 6): real Oracle text; every scenario checks the replay and a save and a load.

* Confession Dial: the legendary creature card gains escape this turn only (702.138a, 611.2a): mana cost plus three other cards exiled.
* Dermoplasm: only a creature card with a morph ability may come from the hand; returns to hand only if one was put (603.4, 702.37b).
* Grifter's Blade: chosen as it enters (303.4f), attached on entry; only a legal host; none to choose: unattached.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import activate
from tests.wave9c_kit import card_named, pt, to_hand
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put

EXTRA = [
    real("Grifter's Blade", "{1}{R}", 2, "Artifact — Equipment",
         "Flash\nAs this Equipment enters, choose a creature you control it could be attached to. If you do, it enters attached to that creature.\nEquipped creature gets +1/+1.\nEquip {1}",
         None, "R"),
    real("Confession Dial", "{2}", 2, "Artifact",
         "When this artifact enters, surveil 3.\n{T}: Target legendary creature card in your graveyard gains escape until end of turn. The escape cost is equal to its mana cost plus exile three other cards from your graveyard. (You may cast it from your graveyard for its escape cost this turn.)",
         None, ""),
    real("Probe Legend", "{1}{G}", 2, "Legendary Creature — Elf", "", ("2", "2"), "G"),
    real("Dermoplasm", "{1}{U}{U}", 3, "Creature — Shapeshifter",
         "Flying\nMorph {2}{U}{U} (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)\nWhen this creature is turned face up, you may put a creature card with a morph ability from your hand onto the battlefield face up. If you do, return this creature to its owner's hand.",
         ("1", "1"), "U"),
    real("Probe Morpher", "{3}{G}", 4, "Creature — Beast", "Morph {2}{G}", ("3", "3"), "G"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Shivan Dragon", "{4}{R}{R}", 6, "Creature — Dragon", "", ("5", "5"), "R"),
]
BLADE = "Grifter's Blade"


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_blade_enters_attached_to_the_chosen_creature(cards):
    """303.4f: the chosen creature is the host as it enters; the other one is not."""
    s = build(cards, [BLADE, "Grizzly Bears", "Shivan Dragon"])
    put(s, "Grizzly Bears")
    giant = put(s, "Shivan Dragon")
    mana(s, R=1, C=1)
    cast(s, BLADE)
    answer(s, giant.id)
    blade = card_named(s, BLADE)
    assert s.state.cards[blade.id].attached_to == giant.id
    assert pt(s, "Shivan Dragon") == (6, 6) and pt(s, "Grizzly Bears") == (2, 2)
    check(s)


def test_blade_without_a_creature_enters_unattached(cards):
    s = build(cards, [BLADE])
    mana(s, R=1, C=1)
    cast(s, BLADE)
    answer(s)
    assert s.state.cards[card_named(s, BLADE).id].attached_to is None
    check(s)


@pytest.mark.parametrize("others,ok", [(3, True), (2, False)])
def test_dial_escape_needs_three_other_cards(cards, others, ok):
    s = build(cards, ["Confession Dial", "Probe Legend"])
    from tests.wave110c_kit import to_graveyard

    act(s, "p1", type="move", card_ids=[card_named(s, "Probe Legend").id], to={"player": "p1", "zone": "graveyard"})
    to_graveyard(s, others)
    dial = put(s, "Confession Dial")
    legend = card_named(s, "Probe Legend")
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=legend.id)  # no escape before the Dial
    activate(s, "p1", s.state.cards[dial.id], "escape", targets=[legend.id])
    answer(s)
    if not ok:
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=legend.id)
        return
    act(s, "p1", type="cast_spell", card_id=legend.id)
    answer(s)
    assert s.state.cards[legend.id].zone == "p1:battlefield"
    assert len(s.state.zones["p1:exile"]) == 3
    check(s)


def test_dial_escape_ends_with_the_turn(cards):
    from tests.wave110a_kit import next_turn
    from tests.wave110c_kit import to_graveyard

    s = build(cards, ["Confession Dial", "Probe Legend"])
    act(s, "p1", type="move", card_ids=[card_named(s, "Probe Legend").id], to={"player": "p1", "zone": "graveyard"})
    to_graveyard(s, 3)
    dial = put(s, "Confession Dial")
    legend = card_named(s, "Probe Legend")
    activate(s, "p1", s.state.cards[dial.id], "escape", targets=[legend.id])
    answer(s)
    next_turn(s)
    next_turn(s)
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=legend.id)
    check(s)


@pytest.mark.parametrize("morpher", [True, False])
def test_dermoplasm_puts_only_a_morph_creature_and_then_returns_itself(cards, morpher):
    s = build(cards, ["Dermoplasm", "Probe Morpher", "Grizzly Bears"])
    to_hand(s, "Grizzly Bears")
    if morpher:
        to_hand(s, "Probe Morpher")
    derm = to_hand(s, "Dermoplasm")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=derm.id, face_down=True)
    answer(s)
    mana(s, U=2, C=2)
    act(s, "p1", type="turn_face_up", card_id=derm.id)
    answer(s)
    z = {n: s.state.cards[card_named(s, n).id].zone for n in ("Probe Morpher", "Grizzly Bears")}
    assert z["Grizzly Bears"] == "p1:hand"
    assert z["Probe Morpher"] == ("p1:battlefield" if morpher else "p1:library")
    assert s.state.cards[derm.id].zone == ("p1:hand" if morpher else "p1:battlefield")
    if morpher:
        assert not s.state.cards[card_named(s, "Probe Morpher").id].face_down
    check(s)
