"""Wave 110C: Retether (303.4f-g: each returned Aura enchants a creature of its controller's choice, others stay), Another Round (608.2d chosen not
targeted, 400.7 new object so counters vanish, 608.2c repeat X more times)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, cast, ch, check, make_db, mana, put, real, zone

EXTRA = [real("Retether", "{3}{W}", 4, "Sorcery",
              "Return each Aura card from your graveyard to the battlefield. Only creatures can be enchanted this way. (Aura cards that can't enchant a creature on the battlefield remain in your graveyard.)", None, "W"),
         real("Another Round", "{X}{X}{2}{W}", 3, "Sorcery",
              "Exile any number of creatures you control, then return them to the battlefield under their owner's control. Then repeat this process X more times.", None, "W"),
         real("Pacifism", "{1}{W}", 2, "Enchantment — Aura", "Enchant creature\nEnchanted creature can't attack or block.", None, "W"),
         real("Wild Growth", "{G}", 1, "Enchantment — Aura", "Enchant land\nWhenever enchanted land is tapped for mana, its controller adds an additional {G}.", None, "G"),
         real("Fix What's Broken", "{2}{W}{B}", 4, "Sorcery",
              "As an additional cost to cast this spell, pay X life.\nReturn each artifact and creature card with mana value X from your graveyard to the battlefield.", None, "W"),
         real("Spry and Mighty", "{2}{G}", 3, "Sorcery",
              "Choose exactly two creatures you control. You draw X cards and the chosen creatures get +X/+X and gain trample until end of turn, where X is the difference between the chosen creatures' powers.", None, "G"),
         real("Slime Against Humanity", "{2}{G}", 3, "Sorcery",
              "Create a 0/0 green Ooze creature token with trample. Put X +1/+1 counters on it, where X is two plus the total number of cards you own in exile and in your graveyard that are Oozes or are named Slime Against Humanity.\nA deck can have any number of cards named Slime Against Humanity.", None, "G"),
         real("Test Ooze", "{1}{G}", 2, "Creature — Ooze", "", ("1", "1"), "G"),
         real("Test Rock", "{2}", 2, "Artifact", "", None),
         real("Test Gem", "{3}", 3, "Artifact", "", None),
         real("Small Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
         real("Big Bear", "{3}{G}", 4, "Creature — Bear", "", ("4", "4"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Retether", "Another Round", "Fix What's Broken", "Spry and Mighty", "Slime Against Humanity"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_retether_returns_creature_auras_onto_any_creature_and_leaves_land_auras(cards):
    """303.4f-g: Pacifism returns attached to the creature its controller picks (an opponent's here); Wild Growth can't enchant a creature and stays."""
    s = build(cards, ["Retether", "Pacifism", "Wild Growth"], ["Small Bear"])
    opp = put(s, "Small Bear", "p2")
    pac, wg = (next(c for c in s.state.cards.values() if c.name == n and c.owner == "p1") for n in ("Pacifism", "Wild Growth"))
    act(s, "p1", type="move", card_ids=[pac.id, wg.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, W=1, C=3)
    cast(s, "Retether")
    answer(s)
    assert zone(s, pac) == "p1:battlefield" and s.state.cards[pac.id].attached_to == opp.id
    assert zone(s, wg) == "p1:graveyard"
    check(s)


def test_retether_with_no_creature_returns_nothing(cards):
    s = build(cards, ["Retether", "Pacifism"])
    pac = next(c for c in s.state.cards.values() if c.name == "Pacifism" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[pac.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, W=1, C=3)
    cast(s, "Retether")
    answer(s)
    assert zone(s, pac) == "p1:graveyard"
    check(s)


def counters(s, c):
    return s.state.cards[c.id].counters.get("+1/+1", 0)


@pytest.mark.parametrize("x,picks,left", [(0, 1, (0, 2)), (1, 1, (0, 0)), (1, 0, (2, 0))])
def test_another_round_blinks_chosen_creatures_and_repeats(cards, x, picks, left):
    """Counters come off a blinked creature (400.7). The process repeats X more times; each repeat re-chooses among the creatures then there."""
    s = build(cards, ["Another Round", "Small Bear", "Big Bear"])
    a, b = put(s, "Small Bear"), put(s, "Big Bear")
    for c in (a, b):
        act(s, "p1", type="counter", card_ids=[c.id], kind="+1/+1", delta=2)
    mana(s, W=1, C=2 + 2 * x)
    c = next(c for c in s.state.cards.values() if c.name == "Another Round" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[], x_value=x, sources=[])
    # first pass: Small Bear (or nothing); the repeat, if any, blinks Big Bear
    answer(s, [a.id] if picks else [], *([[b.id]] if x else []))
    assert (counters(s, a), counters(s, b)) == left
    check(s)


def test_fix_whats_broken_pays_x_life_and_returns_only_cards_with_that_mana_value(cards):
    """107.3a, 119.4: X announced as an additional cost (life paid); 202.3e: only artifact and creature cards of mana value X return."""
    s = build(cards, ["Fix What's Broken", "Test Rock", "Test Gem", "Small Bear", "Big Bear"])
    gone = [next(c for c in s.state.cards.values() if c.name == n and c.owner == "p1") for n in ("Test Rock", "Test Gem", "Small Bear", "Big Bear")]
    act(s, "p1", type="move", card_ids=[c.id for c in gone], to={"player": "p1", "zone": "graveyard"})
    mana(s, W=1, B=1, C=2)
    before = s.state.players["p1"].life
    c = next(c for c in s.state.cards.values() if c.name == "Fix What's Broken" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[], x_value=2, sources=[])
    answer(s)
    assert s.state.players["p1"].life == before - 2
    assert [zone(s, x) for x in gone] == ["p1:battlefield", "p1:graveyard", "p1:battlefield", "p1:graveyard"]
    check(s)


def test_spry_and_mighty_draws_and_pumps_by_the_power_difference(cards):
    """608.2d/608.2h: two creatures chosen on resolution; X = |4 - 2| = 2 cards drawn, both get +2/+2 and trample; the third creature is untouched."""
    s = build(cards, ["Spry and Mighty", "Small Bear", "Big Bear", "Test Gem"])
    a, b = put(s, "Small Bear"), put(s, "Big Bear")
    mana(s, G=1, C=2)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Spry and Mighty")
    answer(s, [a.id, b.id])
    assert len(s.state.zones["p1:hand"]) == hand + 2  # (the spell comes into hand inside cast() and leaves it again)
    assert (ch(s, a).pt, ch(s, b).pt) == ((4, 4), (6, 6))
    assert "trample" in ch(s, a).keywords and "trample" in ch(s, b).keywords
    check(s)


def test_slime_against_humanity_counts_oozes_and_copies_in_graveyard_and_exile(cards):
    """122.1: X = 2 + Oozes in graveyard and exile + cards named Slime Against Humanity (here 1 Ooze in the graveyard, 1 Ooze and 1 Slime in exile) = 5."""
    s = build(cards, ["Slime Against Humanity", "Slime Against Humanity", "Test Ooze", "Test Ooze", "Small Bear"])
    slime = [c for c in s.state.cards.values() if c.name == "Slime Against Humanity" and c.owner == "p1"]
    oozes = [c for c in s.state.cards.values() if c.name == "Test Ooze" and c.owner == "p1"]
    bear = next(c for c in s.state.cards.values() if c.name == "Small Bear" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[oozes[0].id, bear.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[oozes[1].id, slime[1].id], to={"player": "p1", "zone": "exile"})
    mana(s, G=1, C=2)
    c = slime[0]
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[], sources=[])
    answer(s)
    token = next(t for t in s.state.cards.values() if t.name == "Ooze" and t.zone == "p1:battlefield")
    assert token.counters.get("+1/+1") == 5
    check(s)
