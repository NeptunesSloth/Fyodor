"""Wave 110C: Shriekwood Devourer (608.2h: X is the attack batch's greatest power), Ugin's Nexus (614.6, 500.7: the exile replacement's extra turn),
Starnheim Unleashed (702.143: a foretell cost with {X}, X tokens when foretold), Chandra, Chill of Compliance (701.25a: surveil, then the card to hand)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real, to_hand

EXTRA = [real("Shriekwood Devourer", "{4}{G}{G}", 6, "Creature — Treefolk",
              "Trample\nWhenever you attack with one or more creatures, untap up to X lands, where X is the greatest power among those creatures.", ("6", "6"), "G"),
         real("Ugin's Nexus", "{5}", 5, "Legendary Artifact",
              "If a player would begin an extra turn, that player skips that turn instead.\n"
              "If Ugin's Nexus would be put into a graveyard from the battlefield, instead exile it and take an extra turn after this one.", None),
         real("Starnheim Unleashed", "{2}{W}{W}", 4, "Sorcery",
              "Create a 4/4 white Angel Warrior creature token with flying and vigilance. If this spell was foretold, create X of those tokens instead.\n"
              "Foretell {X}{X}{W} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)", None, "W"),
         card("Chandra, Chill of Compliance", set_code="tst", number="110C-CH", mana_cost="{2}{U}{R}", cmc=4.0, type_line="Legendary Planeswalker — Chandra",
              oracle_text="+1: Surveil 1. If you put a noncreature, nonland card into your graveyard this way, put that card into your hand.\n"
                          "+1: Add {U}. Spend this mana only to cast a noncreature spell.", loyalty="4", colors=["U", "R"], color_identity=["U", "R"]),
         real("Small Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
         real("Big Bear", "{3}{G}", 4, "Creature — Bear", "", ("4", "4"), "G"),
         real("Test Smash", "{R}", 1, "Instant", "Destroy target artifact.", None, "R"),
         real("Test Bolt", "{R}", 1, "Instant", "Test Bolt deals 3 damage to any target.", None, "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Shriekwood Devourer", "Ugin's Nexus", "Starnheim Unleashed", "Chandra, Chill of Compliance"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def tapped_lands(s):
    return [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest" and c.zone == "p1:battlefield" and c.tapped]


@pytest.mark.parametrize("attackers,untapped", [(["Small Bear"], 2), (["Small Bear", "Big Bear"], 4), (["Shriekwood Devourer"], 5)])
def test_shriekwood_untaps_up_to_the_greatest_power_among_the_attackers(cards, attackers, untapped):
    """608.2h: X is the greatest power among the creatures that attacked (not among all the creatures): up to X tapped lands untap."""
    s = build(cards, ["Shriekwood Devourer", "Small Bear", "Big Bear"])
    for n in {"Shriekwood Devourer", "Small Bear", "Big Bear"}:
        put(s, n)
    lands = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest" and c.zone == "p1:library"][:5]
    act(s, "p1", type="move", card_ids=[c.id for c in lands], to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "main1", 3)  # (summoning sickness is over on the controller's next turn)
    act(s, "p1", type="tap", card_ids=[c.id for c in lands], tapped=True)
    to_phase(s, "declare_attackers", 3)
    ids = {c.name: c.id for c in s.state.cards.values() if c.zone == "p1:battlefield"}
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ids[n], "target": "p2"} for n in attackers])
    d = s.state.rules.decision
    assert d is not None and "untap" in d.prompt.lower(), d
    answer(s, [o.id for o in d.options][: d.max_choices])
    assert len(tapped_lands(s)) == len(lands) - untapped
    check(s)


def test_ugin_nexus_is_exiled_and_its_controller_takes_the_extra_turn(cards):
    """614.6: the exile replaces the move; the extra turn (500.7) follows this one, Nexus having left so its own skip is gone."""
    s = build(cards, ["Ugin's Nexus", "Test Smash"])
    n = put(s, "Ugin's Nexus")
    mana(s, R=1)
    cast(s, "Test Smash", [n.id])
    answer(s)
    assert s.state.cards[n.id].zone == "p1:exile"
    to_phase(s, "main1", 2)
    assert s.state.turn.active_player == "p1"
    to_phase(s, "main1", 3)
    assert s.state.turn.active_player == "p2"
    check(s)


def test_starnheim_foretold_makes_x_angels_and_hard_cast_one(cards):
    """702.143b, 608.2c: the foretold cast (X announced for {X}{X}{W}) makes X tokens; cast from hand it makes one."""
    s = build(cards, ["Starnheim Unleashed"])
    c = to_hand(s, "Starnheim Unleashed")
    from app.rules.plan import Plan

    ab = next(a for a in Plan(s.state, "p1", s.cards, None).ch(c).abilities if "foretell" in a.keywords)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ab.index, sources=[])
    assert s.state.cards[c.id].zone == "p1:foretell"
    to_phase(s, "main1", 3)
    mana(s, C=4, W=1)
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=2, sources=[])
    answer(s)
    angels = [t for t in s.state.cards.values() if t.name == "Angel Warrior" and t.zone == "p1:battlefield"]
    assert len(angels) == 2
    check(s)


def test_starnheim_cast_from_hand_makes_one(cards):
    s = build(cards, ["Starnheim Unleashed"])
    mana(s, W=2, C=2)
    cast(s, "Starnheim Unleashed")
    answer(s)
    assert len([t for t in s.state.cards.values() if t.name == "Angel Warrior" and t.zone == "p1:battlefield"]) == 1
    check(s)


@pytest.mark.parametrize("top,to_hand_", [("Test Bolt", True), ("Small Bear", False), ("Forest", False)])
def test_chandra_surveil_returns_only_noncreature_nonland(cards, top, to_hand_):
    """608.2c: only a noncreature, nonland card put into the graveyard this way goes to hand; kept on top, nothing."""
    s = build(cards, ["Chandra, Chill of Compliance", "Test Bolt", "Small Bear"])
    w = put(s, "Chandra, Chill of Compliance")
    t = next(c for c in s.state.cards.values() if c.name == top and c.owner == "p1" and c.zone in ("p1:library", "p1:hand"))
    act(s, "p1", type="move", card_ids=[t.id], to={"zone": "library"}, position="top")
    act(s, "p1", type="activate_ability", card_id=w.id, ability=0)
    answer(s, [t.id])
    assert (s.state.cards[t.id].zone == "p1:hand") == to_hand_
    if not to_hand_:
        assert s.state.cards[t.id].zone == "p1:graveyard"
    check(s)


def test_chandra_kept_on_top_stays(cards):
    s = build(cards, ["Chandra, Chill of Compliance", "Test Bolt"])
    w = put(s, "Chandra, Chill of Compliance")
    t = next(c for c in s.state.cards.values() if c.name == "Test Bolt")
    act(s, "p1", type="move", card_ids=[t.id], to={"zone": "library"}, position="top")
    act(s, "p1", type="activate_ability", card_id=w.id, ability=0)
    answer(s, [])
    assert s.state.cards[t.id].zone == "p1:library"
    check(s)
