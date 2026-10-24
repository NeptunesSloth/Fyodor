"""Wave 100C: loyalty-ability counters, convoke kin and a one-more-spell limit (app/rules/static_spell100c.py), real Oracle text
(tests/fixtures/wave100c_static_spells_cards.json; CR 2026-09-25). Every scenario checks the replay and a save and a load.

* 606.3: a loyalty ability is an activated ability with a loyalty cost; only such an ability of a planeswalker is a legal target.
* 702.51a: the creatures that convoked the spell; "share a creature type" (205.3m).
* 101.2: "You can cast only one more spell this turn".
* 701.67a: "unless you waterbend {2}": each artifact or creature tapped pays {1}. 608.2d: "your choice of" as it resolves.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, check, life
from tests.wave100c_kit import (
    cast,
    chars,
    move,
    named,
    one,
    open_repo,
    pt_of,
    put_on,
    settle,
    start_cast,
    to_phase,
    walker,
    zone,
)

PROMOTED = ["Verdant Command", "Everything Comes to Dust", "Irencrag Feat", "Waterbending Lesson", "Mercurial Transformation", "Burning of Xinye",
            "Split the Party", "Dreams of Steel and Oil", "Treacherous Urge"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", PROMOTED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_verdant_command_counters_a_loyalty_ability_but_not_another_activated_one(cards):
    """Verdant Command (modes 2 and 4): Liliana's +1 is countered (nobody discards), Bob gains 3. Merfolk Looter's ability can't be targeted."""
    s = build(cards, ["Verdant Command", "Liliana of the Veil", "Merfolk Looter"], [])
    lili, looter = walker(s, "Liliana of the Veil"), put_on(s, "Merfolk Looter")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=looter.id, ability=0)
    looting = s.state.zones["stack"][-1]
    with pytest.raises(ActionError):
        start_cast(s, "Verdant Command", targets=[looting, "p2"], modes=[1, 3], G=1, C=1)
    settle(s)
    move(s, one(s, "Verdant Command"), "hand")  # (the looting may have discarded it)
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    act(s, "p1", type="activate_ability", card_id=lili.id, ability=0)
    plus = s.state.zones["stack"][-1]
    cast(s, "Verdant Command", targets=[plus, "p2"], modes=[1, 3], G=1, C=1)
    assert len(s.state.zones["p2:hand"]) == hands["p2"] and len(s.state.zones["p1:hand"]) == hands["p1"] - 1  # (only Verdant Command left it)
    assert life(s, "p2") == 43
    check(s)


def test_everything_comes_to_dust_spares_creatures_sharing_a_type_with_a_convoker(cards):
    """Alice's Grizzly Bears convokes: Bob's Grizzly Bears (a Bear) stays with it; Bob's Llanowar Elves, Alice's Sol Ring and Holy Strength go."""
    s = build(cards, ["Everything Comes to Dust", "Grizzly Bears", "Sol Ring", "Holy Strength"], ["Grizzly Bears", "Llanowar Elves"])
    bear, theirs, elves = put_on(s, "Grizzly Bears"), put_on(s, "Grizzly Bears", "p2"), put_on(s, "Llanowar Elves", "p2")
    ring, strength = put_on(s, "Sol Ring"), put_on(s, "Holy Strength")
    act(s, "p1", type="attach", card_ids=[strength.id], to=bear.id)
    spell = move(s, one(s, "Everything Comes to Dust"), "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 3, "C": 6})
    act(s, "p1", type="cast_spell", card_id=spell.id, contributions=[{"kind": "convoke", "card": bear.id}])
    settle(s)
    assert zone(s, bear) == "p1:battlefield" and zone(s, theirs) == "p2:battlefield" and zone(s, elves) == "p2:exile"
    assert zone(s, ring) == "p1:exile" and zone(s, strength) == "p1:exile"
    check(s)


def test_irencrag_feat_adds_seven_red_then_allows_one_more_spell(cards):
    s = build(cards, ["Irencrag Feat", "Lightning Bolt", "Opt"], [])
    cast(s, "Irencrag Feat", R=3, C=1)
    me = s.state.players["p1"]
    assert me.mana.get("R", 0) + sum(1 for u in me.mana_units if u.sym == "R") == 7
    cast(s, "Lightning Bolt", targets=["p2"])
    with pytest.raises(ActionError):
        start_cast(s, "Opt", U=1)
    check(s)


@pytest.mark.parametrize("bend", [True, False])
def test_waterbending_lesson_discards_unless_you_waterbend(cards, bend):
    """Waterbending Lesson: Alice draws three; she waterbends {2} by tapping Grizzly Bears and Sol Ring (no discard), or declines (discards one)."""
    s = build(cards, ["Waterbending Lesson", "Grizzly Bears", "Sol Ring"], [])
    bear, ring = put_on(s, "Grizzly Bears"), put_on(s, "Sol Ring")
    move(s, one(s, "Waterbending Lesson"), "hand")
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Waterbending Lesson", prefer=["pay", bear.id, ring.id] if bend else ["decline"], U=1, C=3)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 3 - (0 if bend else 1)
    assert s.state.cards[bear.id].tapped is bend and s.state.cards[ring.id].tapped is bend
    check(s)


@pytest.mark.parametrize(("form", "pt"), [("Frog 1/1", (1, 1)), ("Octopus 4/4", (4, 4))])
def test_mercurial_transformation_becomes_the_chosen_creature_without_abilities(cards, form, pt):
    s = build(cards, ["Mercurial Transformation"], ["Sol Ring"])
    ring = put_on(s, "Sol Ring", "p2")
    cast(s, "Mercurial Transformation", targets=[ring.id], prefer=[form], U=1, C=1)
    ch = chars(s, ring)
    assert pt_of(s, ring) == pt and ch.is_creature and form.split()[0] in ch.subtypes and ch.colors == {"U"} and not ch.abilities
    check(s)


def test_burning_of_xinye_you_then_the_opponent_destroy_four_lands_then_four_damage(cards):
    """Alice destroys four of her five lands (her choice), Bob his only two; then 4 damage to each creature."""
    s = build(cards, ["Burning of Xinye", "Hulking Cyclops"], [])
    mine = [move(s, c, "battlefield") for c in named(s, "Forest")[:5]]
    theirs = [move(s, c, "battlefield") for c in named(s, "Island", "p2")[:2]]
    cyclops = put_on(s, "Hulking Cyclops")
    cast(s, "Burning of Xinye", targets=["p2"], prefer=[c.id for c in mine[1:]], R=2, C=4)
    assert [zone(s, c) for c in mine] == ["p1:battlefield"] + ["p1:graveyard"] * 4
    assert all(zone(s, c) == "p2:graveyard" for c in theirs) and s.state.cards[cyclops.id].damage == 4
    check(s)


def test_split_the_party_alice_returns_half_of_bobs_creatures_rounded_up(cards):
    """Bob controls three creatures: Alice chooses two (Grizzly Bears, Llanowar Elves) to return; Benalish Hero stays."""
    s = build(cards, ["Split the Party"], ["Grizzly Bears", "Llanowar Elves", "Benalish Hero"])
    bear, elves, hero = (put_on(s, n, "p2") for n in ("Grizzly Bears", "Llanowar Elves", "Benalish Hero"))
    cast(s, "Split the Party", targets=["p2"], prefer=[bear.id, elves.id], U=2, C=3)
    assert zone(s, bear) == "p2:hand" and zone(s, elves) == "p2:hand" and zone(s, hero) == "p2:battlefield"
    check(s)


def test_dreams_of_steel_and_oil_exiles_one_card_from_the_hand_and_one_from_the_graveyard(cards):
    s = build(cards, ["Dreams of Steel and Oil"], ["Sol Ring", "Grizzly Bears", "Opt"])
    ring, bear = move(s, one(s, "Sol Ring", "p2"), "hand"), move(s, one(s, "Grizzly Bears", "p2"), "graveyard")
    opt = move(s, one(s, "Opt", "p2"), "hand")
    cast(s, "Dreams of Steel and Oil", targets=["p2"], prefer=[ring.id, bear.id], B=1)
    assert zone(s, ring) == "p2:exile" and zone(s, bear) == "p2:exile" and zone(s, opt) == "p2:hand"
    check(s)


def test_treacherous_urge_steals_a_creature_from_the_hand_with_haste_until_the_end_step(cards):
    s = build(cards, ["Treacherous Urge"], ["Grizzly Bears"])
    bear = move(s, one(s, "Grizzly Bears", "p2"), "hand")
    cast(s, "Treacherous Urge", targets=["p2"], prefer=[bear.id], B=1, C=4)
    assert zone(s, bear) == "p1:battlefield" and "haste" in chars(s, bear).keywords
    act(s, "p1", type="set_stops", own=["end"], others=[], smart_pass=False)
    to_phase(s, "end", turn=1)
    settle(s)
    assert zone(s, bear) == "p2:graveyard"
    check(s)

