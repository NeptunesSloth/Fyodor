"""Wave 110J last cards (official Scryfall rulings, scratchpad rul/final11.json).

* Quicksilver Elemental: the activated abilities of the target are collected when the ability resolves (611.2c; rulings 2004-10-04: several
  activations collect from several creatures, each copy of a once-each-turn ability is activated once each turn), only activated abilities
  (ruling 2004-12-01), written for "this permanent"; its own abilities may be paid with blue mana as though any color (609.4b).
* Grell Philosopher: the Oracle text is a triggered ability (enters, and your upkeep): each Horror you control gains the activated abilities
  the target artifact has at resolution, payable with blue mana as though any color (rulings 2022-06-10).
"""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import answer, card_db  # noqa: F401  (the fixture)
from tests.test_rules_wave110e_cards import cast as cast_card
from tests.wave9c_kit import build, check, life, mana, pt, put

QUICK = real("Quicksilver Elemental", "{3}{U}{U}", 5, "Creature — Elemental",
             "{U}: This creature gains all activated abilities of target creature until end of turn. (If any of the abilities use that creature's name, use this creature's name instead.)\n"
             "You may spend blue mana as though it were mana of any color to pay the activation costs of this creature's abilities.", ("3", "4"), "U")
GRELL = real("Grell Philosopher", "{2}{U}", 3, "Creature — Horror Wizard",
             "Aberrant Tinkering — When this creature enters and at the beginning of your upkeep, each Horror you control gains all activated abilities of target artifact an opponent controls until end of turn. "
             "You may spend blue mana as though it were mana of any color to activate those abilities.", ("1", "4"), "U")
SORC = real("Prodigal Sorcerer", "{2}{U}", 3, "Creature — Human Wizard Sorcerer", "{T}: This creature deals 1 damage to any target.", ("1", "1"), "U")
SHIVAN = real("Shivan Dragon", "{4}{R}{R}", 6, "Creature — Dragon", "Flying\n{R}: This creature gets +1/+0 until end of turn.", ("5", "5"), "R")
WALLA = real("Basking Rootwalla", "{G}", 1, "Creature — Lizard",
             "{1}{G}: This creature gets +2/+2 until end of turn. Activate only once each turn.\n"
             "Madness {0} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.)", ("1", "1"), "G")
SPELLBOMB = real("Pyrite Spellbomb", "{1}", 1, "Artifact", "{R}, Sacrifice this artifact: It deals 2 damage to any target.\n{1}, Sacrifice this artifact: Draw a card.", None)
HORROR = real("Test Horror", "{1}{B}", 2, "Creature — Horror", "", ("2", "2"), "B")
base.EXTRA.extend([QUICK, GRELL, SORC, SHIVAN, WALLA, SPELLBOMB, HORROR])


@pytest.mark.parametrize("name", ["Quicksilver Elemental", "Grell Philosopher"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _plan(s):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None)


def _abilities(s, card, needle):
    return [a.index for a in _plan(s).ch(s.state.cards[card.id]).abilities if a.kind == "activated" and needle in a.text]


def _activated(s, card, needle):
    return _abilities(s, card, needle)[0]


def _borrow(s, q, lender):
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=q.id, ability=_activated(s, q, "gains all activated"), targets=[lender.id])
    answer(s)


def _quick(cards, *others):
    s = build(cards, ["Quicksilver Elemental"], list(others))
    q = put(s, "Quicksilver Elemental")
    s.state.rules.controlled_since[q.id].turn = 0
    return s, q


def test_quicksilver_gains_the_activated_abilities_of_the_target_and_pays_with_blue(cards):
    s, q = _quick(cards, "Prodigal Sorcerer", "Shivan Dragon")
    sorc, dragon = put(s, "Prodigal Sorcerer", "p2"), put(s, "Shivan Dragon", "p2")
    _borrow(s, q, sorc)
    act(s, "p1", type="activate_ability", card_id=q.id, ability=_activated(s, q, "deals 1 damage"), targets=["p2"])
    answer(s)
    assert life(s, "p2") == 39 and s.state.cards[q.id].tapped  # "This creature" is Quicksilver Elemental (ruling 2004-12-01)
    _borrow(s, q, dragon)
    pump = _activated(s, q, "gets +1/+0")
    mana(s, G=1)
    with pytest.raises(ActionError):  # green mana is not blue mana
        act(s, "p1", type="activate_ability", card_id=q.id, ability=pump)
    mana(s, U=1)  # blue mana pays {R}
    act(s, "p1", type="activate_ability", card_id=q.id, ability=pump)
    answer(s)
    assert pt(s, "Quicksilver Elemental")[0] == 4
    check(s)


def test_quicksilver_collects_from_several_creatures_activated_only_and_keeps_them_after_the_lender_leaves(cards):
    s, q = _quick(cards, "Prodigal Sorcerer", "Shivan Dragon")
    sorc, dragon = put(s, "Prodigal Sorcerer", "p2"), put(s, "Shivan Dragon", "p2")
    _borrow(s, q, sorc)
    _borrow(s, q, dragon)
    assert _abilities(s, q, "deals 1 damage") and _abilities(s, q, "gets +1/+0")  # both collected (ruling 2004-10-04)
    assert "flying" not in _plan(s).ch(s.state.cards[q.id]).keywords  # activated abilities only (ruling 2004-12-01)
    _gy(s, sorc)  # the lender leaves the battlefield
    assert _abilities(s, q, "deals 1 damage")  # fixed at resolution (611.2c)
    check(s)


def test_quicksilver_two_copies_of_a_once_each_turn_ability_are_each_activated_once(cards):
    s, q = _quick(cards, "Basking Rootwalla")
    walla = put(s, "Basking Rootwalla", "p2")
    _borrow(s, q, walla)
    _borrow(s, q, walla)
    pumps = _abilities(s, q, "+2/+2")
    assert len(pumps) == 2
    for ab in pumps:
        mana(s, U=2)
        act(s, "p1", type="activate_ability", card_id=q.id, ability=ab)
        answer(s)
    assert pt(s, "Quicksilver Elemental") == (7, 8)
    mana(s, U=2)
    with pytest.raises(ActionError):  # each copy only once each turn (ruling 2004-10-04)
        act(s, "p1", type="activate_ability", card_id=q.id, ability=pumps[0])
    check(s)


def _gy(s, card):
    act(s, card.owner, type="move", card_ids=[card.id], to={"player": card.owner, "zone": "graveyard"})


def _grell(cards, horror):
    s = build(cards, ["Grell Philosopher", "Test Horror", "Shivan Dragon"], ["Pyrite Spellbomb"])
    bomb = put(s, "Pyrite Spellbomb", "p2")
    other = put(s, "Test Horror") if horror else None
    mana(s, U=1, C=2)
    grell = cast_card(s, "Grell Philosopher")
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((o.id for o in d.options if o.card_id == bomb.id), d.options[0].id)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s, grell, bomb, other


def test_grell_gives_horrors_the_abilities_of_an_opponents_artifact_payable_with_blue(cards):
    s, grell, bomb, other = _grell(cards, True)
    assert _abilities(s, other, "deals 2 damage")  # every Horror you control
    ab = _activated(s, grell, "deals 2 damage")
    mana(s, G=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=grell.id, ability=ab, targets=["p2"])
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=grell.id, ability=ab, targets=["p2"])  # {R} paid with blue mana
    answer(s)
    assert life(s, "p2") == 38 and s.state.cards[grell.id].zone.endswith(":graveyard")  # it sacrificed itself ("this permanent")
    assert s.state.cards[bomb.id].zone.endswith(":battlefield")
    check(s)


def test_grell_abilities_stay_after_the_artifact_leaves_and_only_horrors_gain_them(cards):
    s, grell, bomb, _ = _grell(cards, False)
    shivan = put(s, "Shivan Dragon")
    _gy(s, bomb)
    assert _abilities(s, grell, "Draw a card") and not _abilities(s, shivan, "Draw a card")  # fixed at resolution (611.2c); a Dragon is no Horror
    check(s)


def test_grell_upkeep_trigger_lends_again_and_the_grant_ends_with_the_turn(cards):
    from tests.test_rules_wave100g_zones import to_step

    s = build(cards, ["Grell Philosopher"], ["Pyrite Spellbomb"])
    grell, bomb = put(s, "Grell Philosopher"), put(s, "Pyrite Spellbomb", "p2")
    assert not _abilities(s, grell, "Draw a card")
    to_step(s, "upkeep", 1 + len(s.state.players), pick=lambda d: [o.id for o in d.options if o.card_id == bomb.id] or None)
    assert s.state.turn.active_player == "p1" and _abilities(s, grell, "Draw a card")  # your upkeep
    to_step(s, "upkeep", 2 + len(s.state.players))
    assert not _abilities(s, grell, "Draw a card")  # until end of turn (514.2)
    check(s)
